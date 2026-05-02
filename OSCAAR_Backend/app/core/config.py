from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # ── Application ────────────────────────────────────
    APP_ENV: str = "demo"
    APP_SECRET_KEY: str = "change-me-in-production"
    JWT_PRIVATE_KEY_PATH: str = "./keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/public.pem"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    LOG_LEVEL: str = "info"

    # ── Database ───────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./oscaar.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Vector store ───────────────────────────────────
    VECTOR_STORE: str = "chroma"
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    QDRANT_HOST: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "oscaar_documents"
    EMBED_CHUNK_SIZE: int = 512
    EMBED_CHUNK_OVERLAP: int = 64
    EMBED_TOP_K: int = 5

    # ── LLM and embeddings ─────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.1

    # ── Email ──────────────────────────────────────────
    EMAIL_BACKEND: str = "mailpit"
    EMAIL_FROM: str = "oscaar@oscaar.org"
    MAILPIT_SMTP_HOST: str = "localhost"
    MAILPIT_SMTP_PORT: int = 1025
    POSTAL_API_URL: str = ""
    POSTAL_API_KEY: str = ""

    # ── Storage ────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 50
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ── GeoIP ──────────────────────────────────────────
    GEOIP_DB_PATH: str = "./GeoLite2-Country.mmdb"

    # ── Celery ─────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_CONCURRENCY: int = 2
    BATCH_WATCH_DIR: str = "./batch_inbox"

    # ── Rate limiting ──────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 200

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

def get_jwt_private_key() -> str:
    with open(settings.JWT_PRIVATE_KEY_PATH, "r") as f:
        return f.read()

def get_jwt_public_key() -> str:
    with open(settings.JWT_PUBLIC_KEY_PATH, "r") as f:
        return f.read()
