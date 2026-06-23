#!/usr/bin/env python3
"""
apply_date_filter.py
Applies the date-range filter (Option 2, Python-side) to query_api.py.

- Backs up the original to query_api.py.bak-<timestamp>
- Makes 2 edits:
    1. Adds year_from / year_to to the QueryRequest model
    2. Over-fetches and filters results by year in Python (handles string years)
- Verifies the result compiles; if not, restores the backup automatically.

Run:  /mnt/oscaar/pubmed_env/bin/python3 apply_date_filter.py
(or just: python3 apply_date_filter.py  — it only edits text, no special libs)
"""

import os, sys, time, shutil, py_compile

TARGET = "/mnt/oscaar/query_api.py"

if not os.path.exists(TARGET):
    print(f"ERROR: {TARGET} not found.")
    sys.exit(1)

src = open(TARGET).read()

# ---- guard: already applied? ----
if "year_from" in src:
    print("It looks like the date filter is already applied (found 'year_from'). Nothing to do.")
    sys.exit(0)

# ---- backup ----
stamp = time.strftime("%Y%m%d-%H%M%S")
backup = f"{TARGET}.bak-{stamp}"
shutil.copy(TARGET, backup)
print(f"Backed up to {backup}")

orig = src

# ---- Edit 1: request model ----
model_old = """class QueryRequest(BaseModel):
    question: str
    top_k: int = TOP_K"""

model_new = """class QueryRequest(BaseModel):
    question: str
    top_k: int = TOP_K
    year_from: int | None = None
    year_to: int | None = None"""

if model_old not in src:
    print("ERROR: could not find the QueryRequest model block to edit.")
    print("       Your file differs from expected. No changes made.")
    sys.exit(1)
src = src.replace(model_old, model_new, 1)

# ---- Edit 2: search + python-side year filter ----
search_old = """    # Search Qdrant
    raw = qdrant.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=request.top_k,
        with_payload=True
    )
    results = raw.points"""

search_new = """    # Decide how many candidates to pull. If a year filter is active, over-fetch
    # so that after filtering we still have enough results to work with.
    has_year_filter = (request.year_from is not None) or (request.year_to is not None)
    fetch_limit = (request.top_k * 8) if has_year_filter else request.top_k

    # Search Qdrant
    raw = qdrant.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=fetch_limit,
        with_payload=True
    )
    results = raw.points

    # Python-side year filtering (years are stored as strings; parse defensively).
    if has_year_filter:
        def _year_ok(hit):
            raw_year = (hit.payload or {}).get("year", "")
            try:
                y = int(str(raw_year)[:4])   # first 4 chars handles "1975 Jul" etc.
            except (ValueError, TypeError):
                return False                  # unparseable/missing year -> exclude when filtering
            if request.year_from is not None and y < request.year_from:
                return False
            if request.year_to is not None and y > request.year_to:
                return False
            return True

        results = [h for h in results if _year_ok(h)]
        results = results[:request.top_k]     # trim back to requested count"""

if search_old not in src:
    print("ERROR: could not find the Qdrant search block to edit.")
    print("       Your file differs from expected. No changes made.")
    # roll back edit 1 by restoring original
    open(TARGET, "w").write(orig)
    print("       Restored original (no net changes).")
    sys.exit(1)
src = src.replace(search_old, search_new, 1)

# ---- write ----
open(TARGET, "w").write(src)
print("Edits written.")

# ---- validate ----
try:
    py_compile.compile(TARGET, doraise=True)
    print("Syntax OK - file compiles cleanly.")
    print()
    print("Next steps:")
    print("  sudo systemctl restart oscaar-api")
    print("  sleep 15 && curl -s https://oscaar.org/api/health")
    print()
    print(f"If anything looks wrong, restore with:")
    print(f"  cp {backup} {TARGET} && sudo systemctl restart oscaar-api")
except py_compile.PyCompileError as e:
    print("SYNTAX ERROR after edit — restoring backup, no harm done:")
    print(e)
    shutil.copy(backup, TARGET)
    print(f"Restored {TARGET} from backup. The API file is unchanged from before.")
    sys.exit(1)
