import os
import datetime
import torch
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModel
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, Range
from openai import OpenAI

# Auth module (folded in). Provides the hard gate + user model + query logging.
import auth
from auth import require_user, current_user, log_query

app = FastAPI(title="OSCAAR Query API", version="1.0.0")

# Register auth routes (/auth/*) and the SQLite startup hook.
auth.init_auth(app)

# Directory holding index.html, login.html, favicon.svg, and any static assets.
FRONTEND_DIR = os.environ.get("OSCAAR_FRONTEND_DIR", "/mnt/oscaar")

app.add_middleware(
    CORSMiddleware,
    # The frontend is now served from the same origin as the API, so credentialed
    # (cookie) requests are same-origin and don't need a CORS wildcard. A wildcard
    # origin is, in fact, rejected by browsers when credentials are included.
    allow_origins=[os.environ.get("OSCAAR_BASE_URL", "https://oscaar.org")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COLLECTION    = "cancer_articles_v2"
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

# ─── System prompt — now varies by audience type and answer language ─────────
# The citation discipline is identical for everyone; only the tone/technicality
# and the answer language change. This is the seam where audience_type and
# response_language (stored per user) take effect.

_CITATION_BLOCK = """CITATION REQUIREMENTS — MANDATORY:
- Every factual claim MUST be cited inline
- Format: [Author et al., Journal, Year, PMID: xxxxxxx]
- If a claim cannot be supported by the provided articles, state:
  "This is not supported by the retrieved literature"
- Never use knowledge from your training data alone"""

_PROMPT_MEDICAL = """You are OSCAAR, an expert oncology research assistant.
You answer clinical and research questions about cancer based solely on
the peer-reviewed articles provided to you.

{citations}

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

_PROMPT_PATIENT = """You are OSCAAR, a careful and compassionate assistant that explains
cancer research to patients and caregivers, based solely on the peer-reviewed
articles provided to you.

{citations}

RESPONSE FORMAT:
- Begin with a clear, direct answer in plain language
- Briefly define any unavoidable medical terms
- Keep citations inline as specified, but do not let them interrupt readability
- Be honest about uncertainty and disagreements between studies
- End with a short "What this means" summary and a numbered References section

TONE:
- Warm, clear, and reassuring without overpromising
- Avoid jargon; explain ideas the way a good clinician would to a patient
- Do NOT give individual medical advice; describe what the literature shows
- Remind the reader to discuss decisions with their own care team"""

_LANG_INSTRUCTION = {
    "en": "",
    "es": "\n\nIMPORTANT: Write your entire response in Spanish (español). "
          "Keep citation brackets, author names, journal names, and PMIDs exactly as given.",
}


def build_system_prompt(audience_type: str, language: str) -> str:
    base = _PROMPT_PATIENT if audience_type == "patient" else _PROMPT_MEDICAL
    prompt = base.format(citations=_CITATION_BLOCK)
    return prompt + _LANG_INSTRUCTION.get(language, "")

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
async def query(request: QueryRequest, user=Depends(require_user)):
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

    # Clamp the year range to sane bounds before filtering:
    #   - no year below 1900
    #   - no year in the future (cap at the current year, computed live)
    #   - if start ended up after end, swap so the range is always valid
    # Bad input is corrected silently and the query still runs.
    current_year = datetime.datetime.now().year
    yf, yt = request.year_from, request.year_to
    if yf is not None:
        yf = max(1900, min(yf, current_year))
    if yt is not None:
        yt = max(1900, min(yt, current_year))
    if yf is not None and yt is not None and yf > yt:
        yf, yt = yt, yf

    # Native year_int range filter — uses the payload index, so Qdrant returns
    # the top-k most similar articles that ALREADY match the year range, instead
    # of over-fetching and discarding in Python (which failed for sparse years).
    qdrant_filter = None
    if yf is not None or yt is not None:
        rng = {}
        if yf is not None:
            rng["gte"] = yf
        if yt is not None:
            rng["lte"] = yt
        qdrant_filter = Filter(must=[FieldCondition(key="year_int", range=Range(**rng))])

    # Search Qdrant
    raw = qdrant.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=request.top_k,
        with_payload=True,
        query_filter=qdrant_filter,
    )
    results = raw.points

    # No matches is a valid outcome, not an error — return a graceful answer
    # rather than a 404 (which the frontend surfaced as "Server error: 404").
    if not results:
        return QueryResponse(
            answer="No articles in the selected year range matched your question. "
                   "Try widening the year range or removing the year filter.",
            retrieved_articles=[],
            tokens_used={"input": 0, "output": 0, "total": 0},
        )

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

    system_prompt = build_system_prompt(user.audience_type, user.response_language)

    response = ai_client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message}
        ]
    )

    answer = response.choices[0].message.content
    tokens_used = {
        "input":  response.usage.prompt_tokens,
        "output": response.usage.completion_tokens,
        "total":  response.usage.total_tokens
    }

    # Record the query for history + counts (best-effort; never breaks the response).
    log_query(user, request.question, tokens_used["total"])

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


# ─── Frontend serving + hard gate (Option A: FastAPI serves the UI) ──────────
# The login page is always reachable. The query UI at "/" is only served to a
# logged-in session; otherwise we redirect to /login. This is the hard gate:
# there is no separate static server exposing the UI on another port.

@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.get("/favicon.svg")
async def favicon():
    path = os.path.join(FRONTEND_DIR, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404, "not found")

@app.get("/")
async def index(request: Request):
    if current_user(request) is None:
        return RedirectResponse("/login", status_code=302)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/about")
async def about(request: Request):
    if current_user(request) is None:
        return RedirectResponse("/login", status_code=302)
    return FileResponse(os.path.join(FRONTEND_DIR, "about.html"))


@app.get("/trials")
async def trials(request: Request):
    if current_user(request) is None:
        return RedirectResponse("/login", status_code=302)
    return FileResponse(os.path.join(FRONTEND_DIR, "trials.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
