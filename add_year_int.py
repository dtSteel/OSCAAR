#!/usr/bin/env python3
"""
add_year_int.py
Adds a numeric `year_int` field to each Qdrant point, parsed from the existing
string `year`. Non-destructive: the original `year` string is left untouched
(so display like "1975 Jul" still works); filtering can use year_int natively.

Mirrors the proven backfill pattern:
  - reads the JSONL in order (point id == line index, same as embed_and_load.py)
  - resume support via a progress file
  - longer Qdrant client timeout (the default was too short and crashed the backfill)
  - batched set_payload

Records whose year can't be parsed are skipped (left without year_int) — they
simply won't match numeric date filters, which is the desired behavior.

Run:
  /mnt/oscaar/pubmed_env/bin/python3 add_year_int.py
"""

import json, os
from qdrant_client import QdrantClient
from tqdm import tqdm

# ---- adjust path here if needed (matches /mnt/oscaar layout) ----
BASE          = "/mnt/oscaar"
JSONL_FILE    = f"{BASE}/cancer_articles.jsonl"
PROGRESS_FILE = f"{BASE}/year_int_progress.txt"
COLLECTION    = "cancer_articles"
BATCH_SIZE    = 1000

client = QdrantClient(host="localhost", port=6333, timeout=120)

def parse_year(raw):
    """Return an int year from messy strings, or None if unparseable."""
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) < 4:
        return None
    head = s[:4]
    if not head.isdigit():
        return None
    y = int(head)
    # sanity bounds — reject obviously bad years
    if y < 1500 or y > 2100:
        return None
    return y

# ---- resume support ----
start_line = 0
if os.path.exists(PROGRESS_FILE):
    try:
        with open(PROGRESS_FILE) as f:
            start_line = int(f.read().strip())
        print(f"Resuming from line {start_line:,}")
    except (ValueError, TypeError):
        print("Progress file unreadable; starting from 0")
        start_line = 0

# ---- count total ----
print("Counting records...")
total = sum(1 for _ in open(JSONL_FILE))
print(f"Total: {total:,}")

batch_ids     = []
batch_payload = []
updated       = 0
skipped       = 0

with open(JSONL_FILE) as f:
    for i, line in enumerate(tqdm(f, total=total)):
        if i < start_line:
            continue
        try:
            article = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue

        y = parse_year(article.get("year", ""))
        if y is None:
            skipped += 1
            continue

        batch_ids.append(i)
        batch_payload.append({"year_int": y})

        if len(batch_ids) >= BATCH_SIZE:
            for pid, payload in zip(batch_ids, batch_payload):
                client.set_payload(
                    collection_name=COLLECTION,
                    payload=payload,
                    points=[pid]
                )
            updated += len(batch_ids)
            with open(PROGRESS_FILE, "w") as pf:
                pf.write(str(i))
            batch_ids     = []
            batch_payload = []

# ---- final partial batch ----
if batch_ids:
    for pid, payload in zip(batch_ids, batch_payload):
        client.set_payload(
            collection_name=COLLECTION,
            payload=payload,
            points=[pid]
        )
    updated += len(batch_ids)

print(f"\nDone. Added year_int to {updated:,} points. Skipped {skipped:,} (unparseable/missing year).")
print("Next: update query_api.py to filter on year_int natively (see notes).")
