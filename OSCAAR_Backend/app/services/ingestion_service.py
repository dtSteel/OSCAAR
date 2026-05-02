import os
import structlog
from pathlib import Path
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.vector_store import get_vector_store

log = structlog.get_logger()
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

CHUNK_SIZE    = settings.EMBED_CHUNK_SIZE
CHUNK_OVERLAP = settings.EMBED_CHUNK_OVERLAP


def detect_source_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".pdf":  "pdf",
        ".docx": "docx",
        ".txt":  "txt",
        ".md":   "md",
    }.get(ext, "txt")


def extract_text(file_path: str, source_type: str) -> str:
    if source_type == "pdf":
        import fitz
        doc = fitz.open(file_path)
        return "\n\n".join(page.get_text() for page in doc)

    elif source_type == "docx":
        from docx import Document
        doc = Document(file_path)
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    elif source_type in ("txt", "md"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    return ""


async def fetch_url_content(url: str) -> str:
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap
    return chunks


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    if not chunks:
        return []
    response = await openai_client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=chunks,
    )
    return [item.embedding for item in response.data]


async def ingest_document(
    document_id: str,
    file_path: str,
    filename: str,
    source_type: str,
) -> int:
    log.info("ingestion_start", document_id=document_id, filename=filename)

    if source_type == "url":
        text = await fetch_url_content(file_path)
    else:
        text = extract_text(file_path, source_type)

    if not text.strip():
        raise ValueError("No text could be extracted from document")

    raw_chunks = chunk_text(text)
    if not raw_chunks:
        raise ValueError("Document produced no chunks after splitting")

    log.info("chunks_created", document_id=document_id, count=len(raw_chunks))

    embeddings = await embed_chunks(raw_chunks)

    chunk_dicts = [
        {
            "text":        raw_chunks[i],
            "embedding":   embeddings[i],
            "chunk_index": i,
            "filename":    filename,
        }
        for i in range(len(raw_chunks))
    ]

    store = get_vector_store()
    await store.add_chunks(document_id, chunk_dicts)

    log.info("ingestion_complete", document_id=document_id, chunks=len(raw_chunks))
    return len(raw_chunks)
