import os
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from openai import OpenAI

app = FastAPI(title="OSCAAR Query API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

COLLECTION    = "cancer_articles"
TOP_K         = 15
OPENAI_KEY    = os.environ.get("OPENAI_API_KEY", "")

print("Loading MedCPT model...")
tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Article-Encoder")
model     = AutoModel.from_pretrained("ncbi/MedCPT-Article-Encoder")
model.eval()
torch.set_num_threads(16)
print("Model ready")

qdrant    = QdrantClient(host="localhost", port=6333, timeout=120)
ai_client = OpenAI(api_key=OPENAI_KEY)

SYSTEM_PROMPT = """You are OSCAAR, an expert oncology research assistant.
You answer clinical and research questions about cancer based solely on
the peer-reviewed articles provided to you.

CITATION REQUIREMENTS — MANDATORY:
- Every factual claim MUST be cited inline
- Format: [Author et al., Journal, Year, PMID: xxxxxxx]
- If a claim cannot be supported by the provided articles, state:
  "This is not supported by the retrieved literature"
- Never use knowledge from your training data alone

RESPONSE FORMAT:
- Begin with a direct answer
- Support every claim with inline citations
- Note contradictions between studies
- Flag study limitations
- End with a numbered References section

TONE:
- Clinical and precise
- Appropriate for physicians and researchers
- Include statistics, p-values, confidence intervals where available"""

# ─── Layer 1 — Keyword pre-filter ────────────────────────────
ONCOLOGY_KEYWORDS = [
    "cancer", "tumor", "tumour", "oncol", "carcinoma", "sarcoma",
    "lymphoma", "leukemia", "leukaemia", "melanoma", "neoplasm",
    "metasta", "chemotherapy", "radiation", "immunotherapy",
    "biopsy", "malignant", "benign", "remission", "staging",
    "survival", "prognosis", "treatment", "therapy", "drug",
    "mutation", "gene", "brca", "her2", "pd-l1", "checkpoint",
    "pembrolizumab", "nivolumab", "cisplatin", "carboplatin",
    "breast", "lung", "colon", "prostate", "ovarian", "cervical",
    "pancreatic", "liver", "kidney", "brain", "glioblastoma",
    "glioma", "myeloma", "hodgkin", "non-hodgkin", "nsclc",
    "tnbc", "crc", "hcc", "rcc", "clinical trial", "pathology",
    "oncologist", "radiologist", "tumor marker", "biomarker",
    "targeted therapy", "hormone therapy", "palliative", "hospice",
    "resection", "mastectomy", "lumpectomy", "colostomy",
    "cytology", "histology", "adenocarcinoma", "squamous",
    "basal cell", "small cell", "large cell", "diffuse",
    "primary", "secondary", "recurrence", "relapse", "refractory",
    "first line", "second line", "maintenance", "adjuvant",
    "neoadjuvant", "consolidation", "induction", "salvage",
    "psa", "ca-125", "cea", "afp", "her-2", "egfr", "alk",
    "kras", "braf", "msi", "mmr", "tmb", "pdl1", "ctla4",
    "vegf", "mtor", "cdk", "parp", "bcl", "p53", "rb1"
]

def passes_keyword_filter(question: str) -> bool:
    q_lower = question.lower()
    return any(kw in q_lower for kw in ONCOLOGY_KEYWORDS)

# ─── Layer 2 — GPT classifier ────────────────────────────────
def is_oncology_related(question: str) -> bool:
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4.1-mini",
            max_tokens=5,
            messages=[{
                "role": "user",
                "content": f"Is this question related to cancer, oncology, tumor biology, or cancer treatment? Answer only YES or NO.\n\nQuestion: {question}"
            }]
        )
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
    except Exception:
        return True  # if classifier fails, let it through

OFF_TOPIC_RESPONSE = "OSCAAR is designed specifically for oncology research. Please ask a question related to cancer, cancer treatment, diagnosis, or oncology research."

class QueryRequest(BaseModel):
    question: str
    top_k: int = TOP_K
    year_from: int | None = None
    year_to: int | None = None

class QueryResponse(BaseModel):
    answer:             str
    retrieved_articles: list
    tokens_used:        dict

def embed_query(text: str):
    encoded = tokenizer(
        [text],
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt"
    )
    with torch.no_grad():
        output = model(**encoded)
    return output.last_hidden_state.mean(dim=1).numpy().tolist()[0]

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Layer 1 — keyword check (free, instant)
    if not passes_keyword_filter(request.question):
        # Layer 2 — GPT classifier (fraction of a cent)
        if not is_oncology_related(request.question):
            return QueryResponse(
                answer=OFF_TOPIC_RESPONSE,
                retrieved_articles=[],
                tokens_used={"input": 0, "output": 0, "total": 0}
            )

    # Embed the question
    query_vector = embed_query(request.question)

    # Decide how many candidates to pull. If a year filter is active, over-fetch
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
        results = results[:request.top_k]     # trim back to requested count

    if not results:
        raise HTTPException(status_code=404, detail="No relevant articles found")

    context_parts = []
    articles      = []

    for i, hit in enumerate(results, 1):
        p = hit.payload
        authors_list = p.get("authors", [])
        authors_str  = ", ".join(authors_list[:3])
        if len(authors_list) > 3:
            authors_str += " et al."

        context_parts.append(
            f"[{i}] {p.get('title','')}\n"
            f"Authors: {authors_str}\n"
            f"Journal: {p.get('journal','')}, {p.get('year','')}\n"
            f"PMID: {p.get('pmid','')}\n"
            f"Relevance score: {hit.score:.3f}\n"
        )

        articles.append({
            "pmid":     p.get("pmid",""),
            "title":    p.get("title",""),
            "journal":  p.get("journal",""),
            "year":     p.get("year",""),
            "authors":  authors_list,
            "abstract": p.get("abstract",""),
            "score":    round(hit.score, 3)
        })


    context = "\n\n".join(context_parts)

    user_message = f"""Based on the following peer-reviewed cancer research articles,
please answer this question:

QUESTION: {request.question}

RETRIEVED ARTICLES:
{context}

Please provide a comprehensive, cited answer based solely on these articles."""

    response = ai_client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ]
    )

    answer = response.choices[0].message.content
    tokens_used = {
        "input":  response.usage.prompt_tokens,
        "output": response.usage.completion_tokens,
        "total":  response.usage.total_tokens
    }

    return QueryResponse(
        answer=answer,
        retrieved_articles=articles,
        tokens_used=tokens_used
    )

@app.get("/health")
async def health():
    info = qdrant.get_collection(COLLECTION)
    return {
        "status":  "healthy",
        "vectors": info.points_count,
        "model":   "ncbi/MedCPT-Article-Encoder",
        "llm":     "gpt-4.1-mini"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
