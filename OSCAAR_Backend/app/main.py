from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import auth, query, documents, admin, health
from app.db.session import create_tables

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="OSCAAR",
    description="Open Source Cancer Analysis & Research — RAG API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.APP_ENV == "demo" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router,    prefix="/api/v1")
app.include_router(auth.router,      prefix="/api/v1/auth",      tags=["auth"])
app.include_router(query.router,     prefix="/api/v1/query",     tags=["query"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(admin.router,     prefix="/api/v1/admin",     tags=["admin"])
