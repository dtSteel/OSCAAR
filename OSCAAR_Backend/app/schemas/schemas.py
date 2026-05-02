from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional, List
import re

# ── Auth schemas ───────────────────────────────────────
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    language: str = "auto"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Full name is required")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v


class LanguageUpdateRequest(BaseModel):
    language: str


# ── User response schemas ──────────────────────────────
class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    language: str
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


# ── Query schemas ──────────────────────────────────────
class QueryRequest(BaseModel):
    q: str
    response_format: str = "text"
    top_k: int = 5
    language: Optional[str] = None

    @field_validator("q")
    @classmethod
    def query_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty")
        if len(v) > 2000:
            raise ValueError("Query too long — maximum 2000 characters")
        return v.strip()

    @field_validator("response_format")
    @classmethod
    def valid_format(cls, v):
        allowed = {"text", "chart", "slides", "citations"}
        if v not in allowed:
            raise ValueError(f"response_format must be one of {allowed}")
        return v


class QuerySourceResponse(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    relevance_score: float

    class Config:
        from_attributes = True


class QueryResponse(BaseModel):
    query_id: str
    query: str
    response_format: str
    answer: str
    sources: List[QuerySourceResponse]
    confidence: Optional[str]
    tokens_used: Optional[int]
    created_at: datetime


# ── Document schemas ───────────────────────────────────
class DocumentResponse(BaseModel):
    id: str
    filename: str
    source_type: str
    file_size_bytes: int
    chunk_count: Optional[int]
    status: str
    error_message: Optional[str]
    indexed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class URLIngestRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def valid_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class BatchJobResponse(BaseModel):
    job_id: str
    files_queued: int
    message: str


class CorpusStats(BaseModel):
    total_documents: int
    indexed_documents: int
    pending_documents: int
    error_documents: int
    total_storage_bytes: int


# ── Admin schemas ──────────────────────────────────────
class UserDetailResponse(UserResponse):
    query_count: int = 0
    document_count: int = 0


class RoleUpdateRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v):
        if v not in {"researcher", "admin"}:
            raise ValueError("Role must be 'researcher' or 'admin'")
        return v


class Page(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int


# ── Health schema ──────────────────────────────────────
class ServiceHealth(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    database: ServiceHealth
    vector_store: ServiceHealth
    redis: ServiceHealth
    email: ServiceHealth
    storage: ServiceHealth
