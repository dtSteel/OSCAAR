import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.models.user import User, Document
from app.schemas.schemas import DocumentResponse, URLIngestRequest, BatchJobResponse, CorpusStats
from app.services.ingestion_service import detect_source_type
from app.services.vector_store import get_vector_store
from app.tasks.celery_app import ingest_document_task, batch_ingest_task
from app.core.config import settings
from app.core.dependencies import get_current_user, get_current_admin

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type not supported. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
            headers={"X-Error-Code": "UNSUPPORTED_TYPE"},
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit",
            headers={"X-Error-Code": "FILE_TOO_LARGE"},
        )

    source_type = detect_source_type(file.filename)
    doc = Document(
        filename=file.filename,
        source_type=source_type,
        uploaded_by=current_user.id,
        file_size_bytes=len(content),
        status="pending",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    upload_path = Path(settings.UPLOAD_DIR) / current_user.id
    upload_path.mkdir(parents=True, exist_ok=True)
    file_path = upload_path / f"{doc.id}{ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    ingest_document_task.delay(doc.id, str(file_path), file.filename, source_type)

    await db.commit()
    return doc


@router.post("/upload-url", response_model=DocumentResponse, status_code=202)
async def upload_from_url(
    body: URLIngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = Document(
        filename=body.url,
        source_type="url",
        uploaded_by=current_user.id,
        file_size_bytes=0,
        status="pending",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    ingest_document_task.delay(doc.id, body.url, body.url, "url")
    await db.commit()
    return doc


@router.post("/batch", response_model=BatchJobResponse, status_code=202)
async def batch_ingest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    watch_dir = settings.BATCH_WATCH_DIR
    if not os.path.isdir(watch_dir):
        raise HTTPException(status_code=400, detail=f"Batch directory not found: {watch_dir}")

    files = [f for f in os.listdir(watch_dir)
             if Path(f).suffix.lower() in ALLOWED_EXTENSIONS]

    job = batch_ingest_task.delay(watch_dir)

    return BatchJobResponse(
        job_id=job.id,
        files_queued=len(files),
        message=f"Queued {len(files)} files for ingestion",
    )


@router.get("", )
async def list_documents(
    page: int = 1,
    size: int = 20,
    status_filter: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Document).where(Document.deleted_at.is_(None))
    if status_filter:
        query = query.where(Document.status == status_filter)

    total_result = await db.execute(
        select(func.count(Document.id)).where(Document.deleted_at.is_(None))
    )
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    docs = result.scalars().all()

    return {
        "items": [DocumentResponse.model_validate(d) for d in docs],
        "total": total, "page": page, "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/status", response_model=CorpusStats)
async def corpus_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document.status, func.count(Document.id), func.sum(Document.file_size_bytes))
        .where(Document.deleted_at.is_(None))
        .group_by(Document.status)
    )
    rows = result.all()

    stats = {"total_documents": 0, "indexed_documents": 0,
             "pending_documents": 0, "error_documents": 0, "total_storage_bytes": 0}

    for status_val, count, size in rows:
        stats["total_documents"] += count
        stats["total_storage_bytes"] += (size or 0)
        if status_val == "indexed":
            stats["indexed_documents"] = count
        elif status_val in ("pending", "processing"):
            stats["pending_documents"] += count
        elif status_val == "error":
            stats["error_documents"] = count

    return CorpusStats(**stats)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    store = get_vector_store()
    await store.delete_document(doc_id)

    from datetime import datetime, timezone
    doc.deleted_at = datetime.now(timezone.utc)
    await db.commit()
