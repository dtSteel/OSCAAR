import gzip
import xml.etree.ElementTree as ET
import json
import glob
import os
from tqdm import tqdm

INPUT_DIR   = "/mnt/HC_Volume_105779177/baseline"
OUTPUT_FILE = "/mnt/HC_Volume_105779177/cancer_articles.jsonl"
PROGRESS    = OUTPUT_FILE + ".progress"

def parse_file_streaming(gz_path, out_file):
    count = 0
    try:
        with gzip.open(gz_path, 'rb') as f:
            for event, elem in ET.iterparse(f, events=('end',)):
                if elem.tag != 'PubmedArticle':
                    continue

                mesh_headings = elem.findall(".//MeshHeading/DescriptorName")
                mesh_terms = [m.text for m in mesh_headings if m.text]
                if not any("neoplasm" in t.lower() for t in mesh_terms):
                    elem.clear()
                    continue

                pmid    = elem.findtext(".//PMID") or ""
                title   = elem.findtext(".//ArticleTitle") or ""
                year    = elem.findtext(".//PubDate/Year") or ""
                journal = elem.findtext(".//Journal/Title") or ""

                abstract_parts = elem.findall(".//AbstractText")
                abstract = " ".join(
                    (p.get("Label","") + ": " + (p.text or "") if p.get("Label") else (p.text or ""))
                    for p in abstract_parts
                ).strip()

                authors = []
                for author in elem.findall(".//Author"):
                    last  = author.findtext("LastName") or ""
                    first = author.findtext("ForeName") or ""
                    if last:
                        authors.append(f"{last} {first}".strip())

                out_file.write(json.dumps({
                    "pmid": pmid, "title": title, "abstract": abstract,
                    "year": year, "journal": journal,
                    "authors": authors, "mesh_terms": mesh_terms
                }) + "\n")
                count += 1
                elem.clear()

    except Exception as e:
        print(f"Error in {gz_path}: {e}")

    return count

gz_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.xml.gz")))
print(f"Found {len(gz_files)} baseline files to process")

# Resume support
last_done = None
if os.path.exists(PROGRESS):
    with open(PROGRESS) as f:
        last_done = f.read().strip()
    gz_files = [f for f in gz_files if f > last_done]
    print(f"Resuming from after {os.path.basename(last_done)}")
    mode = "a"
else:
    mode = "w"

total = 0
with open(OUTPUT_FILE, mode) as out:
    for gz_file in tqdm(gz_files):
        count = parse_file_streaming(gz_file, out)
        total += count
        with open(PROGRESS, "w") as pf:
            pf.write(gz_file)
        tqdm.write(f"  {os.path.basename(gz_file)}: {count} cancer articles (total: {total:,})")

print(f"\nDone. Total: {total:,}")
