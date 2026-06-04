import json
import os
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from tqdm import tqdm
import multiprocessing as mp
from queue import Empty
import time

JSONL_FILE    = "/mnt/HC_Volume_105779177/cancer_articles.jsonl"
PROGRESS_FILE = "/mnt/HC_Volume_105779177/embed_progress.txt"
COLLECTION    = "cancer_articles"
BATCH_SIZE    = 512
VECTOR_DIM    = 768
NUM_WORKERS   = 4  # 4 parallel embedding processes

def embed_worker(worker_id, input_queue, output_queue):
    """Each worker loads its own model instance and embeds batches"""
    print(f"Worker {worker_id} loading model...")
    tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")
    model = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder")
    model.eval()
    
    # Set threads per worker
    torch.set_num_threads(4)
    
    print(f"Worker {worker_id} ready")
    
    while True:
        try:
            batch = input_queue.get(timeout=30)
            if batch is None:  # Poison pill
                break
                
            texts, points = batch
            
            encoded = tokenizer(
                texts,
                truncation=True,
                padding=True,
                max_length=512,
                return_tensors="pt"
            )
            
            with torch.no_grad():
                output = model(**encoded)
            
            embeddings = output.last_hidden_state.mean(dim=1).numpy().tolist()
            output_queue.put((points, embeddings))
            
        except Empty:
            continue
        except Exception as e:
            print(f"Worker {worker_id} error: {e}")
            continue

def qdrant_writer(output_queue, total_records, start_line):
    """Dedicated process for writing to Qdrant"""
    client = QdrantClient(host="localhost", port=6333, timeout=60)
    processed = 0
    last_save = start_line
    
    pbar = tqdm(total=total_records, initial=start_line, desc="Embedding")
    
    while True:
        try:
            result = output_queue.get(timeout=60)
            if result is None:
                break
                
            points_meta, vectors = result
            
            points = [
                PointStruct(
                    id=p["id"],
                    vector=v,
                    payload=p
                )
                for p, v in zip(points_meta, vectors)
            ]
            
            client.upsert(collection_name=COLLECTION, points=points)
            processed += len(points)
            pbar.update(len(points))
            
            # Save progress every 10k records
            current_id = points_meta[-1]["id"]
            if current_id - last_save > 10000:
                with open(PROGRESS_FILE, "w") as f:
                    f.write(str(current_id))
                last_save = current_id
                
        except Empty:
            continue
        except Exception as e:
            print(f"Writer error: {e}")
            continue
    
    pbar.close()
    print(f"\nWriter done. Total processed: {processed:,}")

def main():
    # Connect to Qdrant
    client = QdrantClient(host="localhost", port=6333)
    
    # Create collection if needed
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)
        )
        print(f"Created collection: {COLLECTION}")
    else:
        print(f"Collection exists — resuming")

    # Resume support
    start_line = 0
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            start_line = int(f.read().strip())
        print(f"Resuming from line {start_line:,}")

    # Count total
    print("Counting records...")
    total_lines = sum(1 for _ in open(JSONL_FILE))
    print(f"Total records: {total_lines:,}")

    # Set up queues
    input_queue  = mp.Queue(maxsize=8)
    output_queue = mp.Queue(maxsize=8)

    # Start embedding workers
    workers = []
    for i in range(NUM_WORKERS):
        p = mp.Process(target=embed_worker, args=(i, input_queue, output_queue))
        p.start()
        workers.append(p)

    # Start Qdrant writer
    writer = mp.Process(
        target=qdrant_writer,
        args=(output_queue, total_lines, start_line)
    )
    writer.start()

    # Feed batches from file
    batch_texts  = []
    batch_points = []

    print("Starting feed...")
    with open(JSONL_FILE) as f:
        for i, line in enumerate(f):
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
                input_queue.put((batch_texts, batch_points))
                batch_texts  = []
                batch_points = []

    # Send remaining batch
    if batch_texts:
        input_queue.put((batch_texts, batch_points))

    # Send poison pills to workers
    for _ in workers:
        input_queue.put(None)

    # Wait for workers
    for w in workers:
        w.join()

    # Signal writer to finish
    output_queue.put(None)
    writer.join()

    print("\nAll done!")

if __name__ == "__main__":
    mp.set_start_method("spawn")
