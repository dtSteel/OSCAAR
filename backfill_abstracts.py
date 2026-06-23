import json
import os
from qdrant_client import QdrantClient
from tqdm import tqdm

JSONL_FILE    = "/mnt/oscaar/cancer_articles.jsonl"
PROGRESS_FILE = "/mnt/oscaar/backfill_progress.txt"
BATCH_SIZE    = 1000

client = QdrantClient(host="localhost", port=6333, timeout=120)

# Resume support
start_line = 0
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE) as f:
        start_line = int(f.read().strip())
    print(f"Resuming from line {start_line:,}")

# Count total
print("Counting records...")
total = sum(1 for _ in open(JSONL_FILE))
print(f"Total: {total:,}")

batch_ids     = []
batch_payload = []
updated       = 0

with open(JSONL_FILE) as f:
    for i, line in enumerate(tqdm(f, total=total)):
        if i < start_line:
            continue

        article = json.loads(line)
        abstract = article.get("abstract", "").strip()
        pmid     = article.get("pmid", "").strip()

        # Skip if no abstract
        if not abstract:
            continue

        # Build doc_id — use PMID if available, otherwise use index
        doc_id = f"GV-{pmid}" if pmid else f"GV-{i:07d}"

        batch_ids.append(i)
        batch_payload.append({
            "abstract": abstract,
            "doc_id":   doc_id
        })

        if len(batch_ids) >= BATCH_SIZE:
            for pid, payload in zip(batch_ids, batch_payload):
                client.set_payload(
                    collection_name="cancer_articles",
                    payload=payload,
                    points=[pid]
                )
            updated += len(batch_ids)
            with open(PROGRESS_FILE, "w") as pf:
                pf.write(str(i))
            batch_ids     = []
            batch_payload = []

# Final batch
if batch_ids:
    for pid, payload in zip(batch_ids, batch_payload):
        client.set_payload(
            collection_name="cancer_articles",
            payload=payload,
            points=[pid]
        )
    updated += len(batch_ids)

print(f"\nDone. Updated {updated:,} articles with abstract text and doc_id")
