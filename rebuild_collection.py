"""
OSCAAR — Collection Rebuild
============================

Rebuilds the Qdrant collection from scratch with uniform UUID point IDs and a
complete canonical payload baked in at load time.

WHAT IT DOES
  - Reads every point from the OLD collection via scroll (with_vectors=True).
  - REUSES the existing vector (no re-embedding — vectors were embedded from
    title+abstract and are good).
  - Generates a DETERMINISTIC point ID = uuid5(NAMESPACE, pmid), so a re-run
    after a crash overwrites the same points instead of duplicating them.
  - Builds the full canonical payload, parsing year -> year_int.
  - Upserts into a NEW collection (cancer_articles_v2), non-destructively.
  - Saves a scroll-offset progress file so the job is resumable.

This script does NOT touch the JSONL and does NOT load MedCPT/torch — it is a
pure scroll-transform-upsert loop, which keeps memory use low on the box.

AFTER THIS RUNS
  - Verify counts + spot-check points in v2.
  - Add the integer payload index on year_int, apply the native year_int filter
    in query_api.py, point the API at v2 (or alias-swap), retire the old one.
  - This script becomes the corrected canonical ingestion path the nightly
    PubMed job reuses.
"""

import os
import re
import json
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from tqdm import tqdm

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
SRC_COLLECTION = "cancer_articles"
DST_COLLECTION = "cancer_articles_v2"
PROGRESS_FILE  = "/mnt/oscaar/rebuild_progress.txt"
VECTOR_DIM     = 768
BATCH_SIZE     = 256          # scroll page size == upsert batch size
DOC_PREFIX     = "GV"         # PubMed baseline
SOURCE         = "pubmed"

# Fixed namespace for deterministic uuid5. Do NOT change this once any data has
# been written — changing it changes every derived UUID.
OSCAAR_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# ALWAYS set timeout — the default crashes on this box under load.
client = QdrantClient(host="localhost", port=6333, timeout=120)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def parse_year_int(year_value):
    """First 4-digit run in the year string, bounded 1500-2100. None if no match."""
    if not year_value:
        return None
    m = re.search(r"\d{4}", str(year_value))
    if not m:
        return None
    y = int(m.group())
    if 1500 <= y <= 2100:
        return y
    return None


def point_uuid(pmid):
    """Deterministic UUID derived from pmid. Re-runs reproduce the same id."""
    return str(uuid.uuid5(OSCAAR_NAMESPACE, str(pmid)))


def build_payload(old_payload, new_uuid):
    """Assemble the full canonical payload from an old point's payload."""
    pmid = old_payload.get("pmid", "")
    year = old_payload.get("year", "")
    return {
        "doc_id":   f"{DOC_PREFIX}-{new_uuid}",
        "source":   SOURCE,
        "pmid":     pmid,
        "title":    old_payload.get("title", ""),
        "authors":  old_payload.get("authors", []),
        "journal":  old_payload.get("journal", ""),
        "year":     year,
        "year_int": parse_year_int(year),
        "abstract": old_payload.get("abstract", ""),
    }


# ----------------------------------------------------------------------------
# Destination collection
# ----------------------------------------------------------------------------
existing = [c.name for c in client.get_collections().collections]
if DST_COLLECTION not in existing:
    client.create_collection(
        collection_name=DST_COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"Created collection: {DST_COLLECTION}")
else:
    print(f"Collection {DST_COLLECTION} already exists — resuming")

src_count = client.count(collection_name=SRC_COLLECTION, exact=True).count
print(f"Source {SRC_COLLECTION}: {src_count:,} points")


# ----------------------------------------------------------------------------
# Resume support — store the scroll offset (next_page_offset) between batches
# ----------------------------------------------------------------------------
offset = None
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE) as f:
        saved = f.read().strip()
    if saved:
        # offset may be an int id or a UUID string depending on Qdrant version
        try:
            offset = int(saved)
        except ValueError:
            offset = saved
        print(f"Resuming from scroll offset: {offset}")


# ----------------------------------------------------------------------------
# Scroll -> transform -> upsert
# ----------------------------------------------------------------------------
migrated   = 0
skipped_no_pmid = 0

with tqdm(total=src_count, initial=0, desc="rebuild") as bar:
    while True:
        records, next_offset = client.scroll(
            collection_name=SRC_COLLECTION,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        if not records:
            break

        points = []
        for rec in records:
            payload = rec.payload or {}
            pmid = payload.get("pmid", "")

            # Every point here is PubMed and should have a pmid. Guard anyway:
            # a blank pmid would make uuid5 collide on the empty string.
            if not pmid:
                skipped_no_pmid += 1
                continue

            new_uuid = point_uuid(pmid)
            points.append(
                PointStruct(
                    id=new_uuid,
                    vector=rec.vector,
                    payload=build_payload(payload, new_uuid),
                )
            )

        if points:
            client.upsert(collection_name=DST_COLLECTION, points=points)
            migrated += len(points)

        bar.update(len(records))

        # Persist offset AFTER a successful upsert so a crash resumes safely.
        with open(PROGRESS_FILE, "w") as pf:
            pf.write("" if next_offset is None else str(next_offset))

        if next_offset is None:
            break
        offset = next_offset


# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
dst_count = client.count(collection_name=DST_COLLECTION, exact=True).count
print()
print(f"Done. Migrated {migrated:,} points into {DST_COLLECTION}")
if skipped_no_pmid:
    print(f"Skipped {skipped_no_pmid:,} points with blank pmid")
print(f"Source count: {src_count:,}   Destination count: {dst_count:,}")
print("Note: dst may be < migrated upserts if any pmids collided (duplicates "
      "in source collapse to one point — verify this is expected).")
