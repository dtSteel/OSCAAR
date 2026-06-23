import json
import os
import torch
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from tqdm import tqdm

JSONL_FILE    = "/mnt/HC_Volume_105779177/cancer_articles.jsonl"
PROGRESS_FILE = "/mnt/HC_Volume_105779177/embed_progress.txt"
COLLECTION    = "cancer_articles"
BATCH_SIZE    = 128
VECTOR_DIM    = 768

# Connect to Qdrant
client = QdrantClient(host="localhost", port=6333)

# Create collection if it doesn't exist
existing = [c.name for c in client.get_collections().collections]
if COLLECTION not in existing:
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
    )
    print(f"Created collection: {COLLECTION}")
else:
    print(f"Collection {COLLECTION} already exists — resuming")

# Load MedCPT model
print("Loading MedCPT model...")
tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")
model     = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder")
model.eval()
torch.set_num_threads(16)
torch.set_num_interop_threads(4)
print("Model loaded")

def embed_batch(texts):
    encoded = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt"
    )
    with torch.no_grad():
        output = model(**encoded)
    # Mean pooling
    embeddings = output.last_hidden_state.mean(dim=1)
    return embeddings.numpy().tolist()

# Resume support
start_line = 0
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE) as f:
        start_line = int(f.read().strip())
    print(f"Resuming from line {start_line:,}")

# Count total lines
print("Counting records...")
total_lines = sum(1 for _ in open(JSONL_FILE))
print(f"Total records: {total_lines:,}")

# Embed and load
batch_texts  = []
batch_points = []
processed    = 0

with open(JSONL_FILE) as f:
    for i, line in enumerate(tqdm(f, total=total_lines)):
        if i < start_line:
            continue

        article = json.loads(line)
        text = f"{article.get('title','')} {article.get('abstract','')}".strip()
        if not text:
            continue

        batch_texts.append(text)
        batch_points.append({
            "id":      i,
            "pmid":    article.get("pmid",""),
            "title":   article.get("title",""),
            "year":    article.get("year",""),
            "journal": article.get("journal",""),
            "authors": article.get("authors",[]),
        })

        if len(batch_texts) >= BATCH_SIZE:
            vectors = embed_batch(batch_texts)
            points = [
                PointStruct(
                    id=p["id"],
                    vector=v,
                    payload=p
                )
                for p, v in zip(batch_points, vectors)
            ]
            client.upsert(collection_name=COLLECTION, points=points)
            processed += len(points)

            # Save progress
            with open(PROGRESS_FILE, "w") as pf:
                pf.write(str(i))

            batch_texts  = []
            batch_points = []

# Final batch
if batch_texts:
    vectors = embed_batch(batch_texts)
    points = [
        PointStruct(id=p["id"], vector=v, payload=p)
        for p, v in zip(batch_points, vectors)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    processed += len(points)

print(f"\nDone. Loaded {processed:,} vectors into Qdrant")
