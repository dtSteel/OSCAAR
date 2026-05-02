import structlog
from anthropic import Anthropic
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.injection_filter import build_system_prompt, build_rag_prompt
from app.services.vector_store import get_vector_store

log = structlog.get_logger()

anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def embed_query(query: str) -> list[float]:
    response = await openai_client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=query,
    )
    return response.data[0].embedding


async def retrieve_chunks(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    store = get_vector_store()
    results = await store.search(query_embedding, top_k=top_k)
    return results


def calculate_confidence(chunks: list[dict]) -> str:
    if not chunks:
        return "low"
    scores = [c["relevance_score"] for c in chunks]
    avg = sum(scores) / len(scores)
    if avg >= 0.80:
        return "high"
    elif avg >= 0.60:
        return "medium"
    return "low"


async def generate_answer(
    query: str,
    context_chunks: list[dict],
    response_format: str = "text",
    language: str = "en",
) -> tuple[str, int]:
    system_prompt = build_system_prompt()
    user_prompt = build_rag_prompt(query, context_chunks)

    format_instruction = {
        "text":      "Provide a clear prose answer with citations.",
        "chart":     "Provide a JSON specification for a chart that visualises the key data from your answer, followed by a prose explanation.",
        "slides":    "Structure your answer as slide titles and bullet points suitable for a presentation.",
        "citations": "Provide a detailed citation list of all relevant sources with key quotes.",
    }.get(response_format, "Provide a clear prose answer with citations.")

    if language != "en":
        lang_instruction = f"\n\nRespond in the language with BCP-47 code: {language}"
    else:
        lang_instruction = ""

    response = anthropic_client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.LLM_MAX_TOKENS,
        system=system_prompt + f"\n\n{format_instruction}{lang_instruction}",
        messages=[{"role": "user", "content": user_prompt}],
        temperature=settings.LLM_TEMPERATURE,
    )

    answer = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    log.info("llm_response_generated",
             tokens=tokens_used,
             format=response_format,
             chunks_used=len(context_chunks))

    return answer, tokens_used


async def run_rag_pipeline(
    query: str,
    top_k: int = 5,
    response_format: str = "text",
    language: str = "en",
    user_id: str = None,
) -> dict:
    log.info("rag_pipeline_start", query_length=len(query), user_id=user_id)

    query_embedding = await embed_query(query)
    chunks = await retrieve_chunks(query_embedding, top_k=top_k)
    confidence = calculate_confidence(chunks)

    answer, tokens_used = await generate_answer(
        query=query,
        context_chunks=chunks,
        response_format=response_format,
        language=language,
    )

    log.info("rag_pipeline_complete",
             confidence=confidence,
             chunks_retrieved=len(chunks),
             tokens_used=tokens_used)

    return {
        "answer": answer,
        "sources": chunks,
        "confidence": confidence,
        "tokens_used": tokens_used,
    }
