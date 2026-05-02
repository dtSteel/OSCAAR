from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.user import User, Query, QuerySource, Document
from app.schemas.schemas import QueryRequest, QueryResponse, QuerySourceResponse
from app.services.rag_service import run_rag_pipeline
from app.services.injection_filter import sanitise_query
from app.core.dependencies import get_current_user

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def submit_query(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sanitised, was_flagged = sanitise_query(body.q, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"X-Error-Code": "QUERY_INJECTION"},
        )

    if was_flagged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query contains patterns that are not permitted",
            headers={"X-Error-Code": "QUERY_INJECTION"},
        )

    language = body.language or current_user.language

    try:
        result = await run_rag_pipeline(
            query=sanitised,
            top_k=body.top_k,
            response_format=body.response_format,
            language=language,
            user_id=current_user.id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector store unavailable",
            headers={"X-Error-Code": "VECTOR_STORE_DOWN"},
        )

    query_record = Query(
        user_id=current_user.id,
        query_text=sanitised,
        response_format=body.response_format,
        answer_text=result["answer"],
        confidence=result["confidence"],
        tokens_used=result["tokens_used"],
        top_k=body.top_k,
        language=language,
    )
    db.add(query_record)
    await db.flush()

    sources = []
    for chunk in result["sources"]:
        doc_result = await db.execute(
            select(Document).where(Document.id == chunk["document_id"])
        )
        doc = doc_result.scalar_one_or_none()

        qs = QuerySource(
            query_id=query_record.id,
            document_id=chunk["document_id"],
            chunk_index=chunk["chunk_index"],
            relevance_score=chunk["relevance_score"],
        )
        db.add(qs)

        sources.append(QuerySourceResponse(
            document_id=chunk["document_id"],
            filename=doc.filename if doc else chunk.get("filename", ""),
            chunk_index=chunk["chunk_index"],
            relevance_score=chunk["relevance_score"],
        ))

    await db.commit()

    return QueryResponse(
        query_id=query_record.id,
        query=sanitised,
        response_format=body.response_format,
        answer=result["answer"],
        sources=sources,
        confidence=result["confidence"],
        tokens_used=result["tokens_used"],
        created_at=query_record.created_at,
    )


@router.get("/history")
async def get_query_history(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    total_result = await db.execute(
        select(func.count(Query.id)).where(Query.user_id == current_user.id)
    )
    total = total_result.scalar()

    result = await db.execute(
        select(Query)
        .where(Query.user_id == current_user.id)
        .order_by(Query.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    queries = result.scalars().all()

    return {
        "items": [{"id": q.id, "query": q.query_text, "format": q.response_format,
                   "confidence": q.confidence, "created_at": q.created_at} for q in queries],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/{query_id}")
async def get_query(
    query_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Query).where(Query.id == query_id, Query.user_id == current_user.id)
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    return query


@router.delete("/{query_id}", status_code=204)
async def delete_query(
    query_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Query).where(Query.id == query_id, Query.user_id == current_user.id)
    )
    query = result.scalar_one_or_none()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    await db.delete(query)
    await db.commit()


@router.post("/suggest")
async def suggest_queries(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    return ["BRCA1 mutation mechanisms", "checkpoint inhibitors",
            "tumor microenvironment", "liquid biopsy", "CRISPR therapy"]
