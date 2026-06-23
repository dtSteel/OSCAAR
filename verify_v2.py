from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333, timeout=120)
COLLECTION = "cancer_articles_v2"

info = client.get_collection(COLLECTION)
count = client.count(collection_name=COLLECTION, exact=True).count
print(f"Collection : {COLLECTION}")
print(f"Points     : {count:,}")
print(f"Vector dim : {info.config.params.vectors.size}")
print(f"Distance   : {info.config.params.vectors.distance}")
print(f"Status     : {info.status}")
print("-" * 60)

records, _ = client.scroll(
    collection_name=COLLECTION, limit=5,
    with_payload=True, with_vectors=True,
)
for i, rec in enumerate(records, 1):
    p = rec.payload or {}
    vec_ok = isinstance(rec.vector, list) and len(rec.vector) == 768
    print(f"[{i}] point id : {rec.id}")
    print(f"    doc_id   : {p.get('doc_id')}")
    print(f"    source   : {p.get('source')}")
    print(f"    pmid     : {p.get('pmid')}")
    print(f"    year     : {p.get('year')!r}   year_int: {p.get('year_int')!r}")
    print(f"    title    : {str(p.get('title',''))[:70]}")
    print(f"    abstract : {len(str(p.get('abstract','')))} chars")
    print(f"    vector   : {'OK 768-dim' if vec_ok else 'MISSING/WRONG'}")
    print(f"    id==doc_id tail: {p.get('doc_id') == 'GV-' + str(rec.id)}")
    print()

sample_n = 5000
seen = 0
nulls = 0
offset = None
while seen < sample_n:
    recs, offset = client.scroll(
        collection_name=COLLECTION,
        limit=min(1000, sample_n - seen),
        offset=offset, with_payload=True, with_vectors=False,
    )
    if not recs:
        break
    for r in recs:
        seen += 1
        if (r.payload or {}).get("year_int") is None:
            nulls += 1
    if offset is None:
        break

print("-" * 60)
print(f"year_int null rate (sample of {seen:,}): {nulls:,} null "
      f"({100*nulls/seen:.2f}%) — points with unparseable/blank year")
