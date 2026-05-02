import asyncio
import structlog
from celery import Celery
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

log = structlog.get_logger()

celery_app = Celery(
    "oscaar",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.CELERY_CONCURRENCY,
)


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_document_task(self, document_id: str, file_path: str, filename: str, source_type: str):
    from app.db.session import AsyncSessionLocal
    from app.models.user import Document
    from app.services.ingestion_service import ingest_document
    from sqlalchemy import select

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            doc = result.scalar_one_or_none()
            if not doc:
                log.error("document_not_found", document_id=document_id)
                return

            doc.status = "processing"
            await db.commit()

            try:
                chunk_count = await ingest_document(document_id, file_path, filename, source_type)
                doc.status = "indexed"
                doc.chunk_count = chunk_count
                doc.indexed_at = datetime.now(timezone.utc)
                await db.commit()
                log.info("task_complete", document_id=document_id, chunks=chunk_count)

            except Exception as exc:
                log.error("ingestion_failed", document_id=document_id, error=str(exc))
                doc.status = "error"
                doc.error_message = str(exc)[:500]
                await db.commit()
                raise self.retry(exc=exc)

    run_async(_run())


@celery_app.task
def batch_ingest_task(directory: str):
    import os
    from pathlib import Path
    from app.db.session import AsyncSessionLocal
    from app.models.user import Document
    from app.services.ingestion_service import detect_source_type

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

    async def _queue_files():
        async with AsyncSessionLocal() as db:
            queued = 0
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                ext = Path(fname).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS:
                    continue
                source_type = detect_source_type(fname)
                size = os.path.getsize(fpath)

                doc = Document(
                    filename=fname,
                    source_type=source_type,
                    file_size_bytes=size,
                    status="pending",
                )
                db.add(doc)
                await db.flush()

                ingest_document_task.delay(doc.id, fpath, fname, source_type)
                queued += 1

            await db.commit()
            log.info("batch_queued", directory=directory, files=queued)
            return queued

    return run_async(_queue_files())
