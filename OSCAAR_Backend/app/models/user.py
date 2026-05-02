import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, Float, Text, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

def utcnow():
    return datetime.now(timezone.utc)

def new_uuid():
    return str(uuid.uuid4())

# ── Users ──────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id:               Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    email:            Mapped[str]  = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name:        Mapped[str]  = mapped_column(String(200), nullable=False)
    hashed_password:  Mapped[str]  = mapped_column(String(255), nullable=False)
    role:             Mapped[str]  = mapped_column(Enum("researcher", "admin", name="user_role"), nullable=False, default="researcher")
    language:         Mapped[str]  = mapped_column(String(10), nullable=False, default="en")
    is_active:        Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    refresh_tokens:   Mapped[list["RefreshToken"]]      = relationship(back_populates="user", cascade="all, delete-orphan")
    reset_tokens:     Mapped[list["PasswordResetToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    documents:        Mapped[list["Document"]]           = relationship(back_populates="uploader")
    queries:          Mapped[list["Query"]]              = relationship(back_populates="user")
    audit_actions:    Mapped[list["AuditLog"]]           = relationship(back_populates="actor")
    emails:           Mapped[list["EmailLog"]]           = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id:           Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:      Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash:   Mapped[str]  = mapped_column(String(255), nullable=False)
    expires_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    user_agent:   Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address:   Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id:         Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:    Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str]  = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="reset_tokens")


# ── Documents ──────────────────────────────────────────
class Document(Base):
    __tablename__ = "documents"

    id:               Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    filename:         Mapped[str]  = mapped_column(String(512), nullable=False)
    source_type:      Mapped[str]  = mapped_column(Enum("pdf", "docx", "txt", "md", "url", name="source_type"), nullable=False)
    uploaded_by:      Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_size_bytes:  Mapped[int]  = mapped_column(Integer, nullable=False, default=0)
    chunk_count:      Mapped[int | None]  = mapped_column(Integer, nullable=True)
    status:           Mapped[str]  = mapped_column(Enum("pending", "processing", "indexed", "error", name="doc_status"), nullable=False, default="pending")
    error_message:    Mapped[str | None]  = mapped_column(Text, nullable=True)
    indexed_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploader:         Mapped["User"] = relationship(back_populates="documents")
    query_sources:    Mapped[list["QuerySource"]] = relationship(back_populates="document")


# ── Queries ────────────────────────────────────────────
class Query(Base):
    __tablename__ = "queries"

    id:              Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:         Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query_text:      Mapped[str]  = mapped_column(Text, nullable=False)
    response_format: Mapped[str]  = mapped_column(Enum("text", "chart", "slides", "citations", name="response_format"), nullable=False, default="text")
    answer_text:     Mapped[str | None]  = mapped_column(Text, nullable=True)
    confidence:      Mapped[str | None]  = mapped_column(Enum("high", "medium", "low", name="confidence_level"), nullable=True)
    tokens_used:     Mapped[int | None]  = mapped_column(Integer, nullable=True)
    top_k:           Mapped[int]  = mapped_column(Integer, nullable=False, default=5)
    language:        Mapped[str]  = mapped_column(String(10), nullable=False, default="en")
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    user:    Mapped["User"] = relationship(back_populates="queries")
    sources: Mapped[list["QuerySource"]] = relationship(back_populates="query", cascade="all, delete-orphan")


class QuerySource(Base):
    __tablename__ = "query_sources"

    id:              Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    query_id:        Mapped[str]   = mapped_column(String(36), ForeignKey("queries.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id:     Mapped[str]   = mapped_column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    chunk_index:     Mapped[int]   = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)

    query:    Mapped["Query"]    = relationship(back_populates="sources")
    document: Mapped["Document"] = relationship(back_populates="query_sources")


# ── Audit Log ──────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id:          Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    actor_id:    Mapped[str]  = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action:      Mapped[str]  = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id:   Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail:      Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address:  Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    actor: Mapped["User"] = relationship(back_populates="audit_actions")


# ── Email Log ──────────────────────────────────────────
class EmailLog(Base):
    __tablename__ = "email_log"

    id:             Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:        Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    template:       Mapped[str]  = mapped_column(String(100), nullable=False)
    language:       Mapped[str]  = mapped_column(String(10), nullable=False, default="en")
    to_address:     Mapped[str]  = mapped_column(String(320), nullable=False)
    status:         Mapped[str]  = mapped_column(Enum("queued", "sent", "bounced", "failed", name="email_status"), nullable=False, default="queued")
    mta_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped["User"] = relationship(back_populates="emails")
