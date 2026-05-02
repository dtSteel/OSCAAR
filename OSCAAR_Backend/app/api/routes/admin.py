from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.user import User, Document, Query, AuditLog
from app.schemas.schemas import UserResponse, RoleUpdateRequest
from app.services.auth_service import get_user_by_id
from app.services.email_service import send_email
from app.core.dependencies import get_current_admin

router = APIRouter()


async def write_audit(db, actor_id, action, target_type=None, target_id=None, detail=None, ip=None):
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=ip,
    )
    db.add(log)


@router.get("/users")
async def list_users(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar()

    result = await db.execute(
        select(User).order_by(User.created_at.desc())
        .offset((page - 1) * size).limit(size)
    )
    users = result.scalars().all()

    return {
        "items": [UserResponse.model_validate(u) for u in users],
        "total": total, "page": page, "size": size,
        "pages": (total + size - 1) // size,
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query_count_result = await db.execute(
        select(func.count(Query.id)).where(Query.user_id == user_id)
    )
    doc_count_result = await db.execute(
        select(func.count(Document.id)).where(Document.uploaded_by == user_id)
    )

    return {
        **UserResponse.model_validate(user).model_dump(),
        "query_count": query_count_result.scalar(),
        "document_count": doc_count_result.scalar(),
    }


@router.patch("/users/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    await write_audit(db, current_user.id, "USER_DISABLED", "user", user_id, ip=ip)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/enable", response_model=UserResponse)
async def enable_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    await write_audit(db, current_user.id, "USER_ENABLED", "user", user_id, ip=ip)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    ip = request.headers.get("X-Forwarded-For", request.client.host)
    await write_audit(db, current_user.id, "USER_DELETED", "user", user_id,
                      detail={"email": user.email}, ip=ip)
    await db.delete(user)
    await db.commit()


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = body.role
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    await write_audit(db, current_user.id, "ROLE_CHANGED", "user", user_id,
                      detail={"old_role": old_role, "new_role": body.role}, ip=ip)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/reports/usage")
async def usage_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    total_queries = (await db.execute(select(func.count(Query.id)))).scalar()
    total_users   = (await db.execute(select(func.count(User.id)))).scalar()
    total_docs    = (await db.execute(
        select(func.count(Document.id)).where(Document.deleted_at.is_(None))
    )).scalar()

    return {
        "total_queries": total_queries,
        "total_users": total_users,
        "total_documents": total_docs,
    }


@router.get("/reports/audit")
async def audit_log(
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    total = (await db.execute(select(func.count(AuditLog.id)))).scalar()
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.created_at))
        .offset((page - 1) * size).limit(size)
    )
    logs = result.scalars().all()

    return {
        "items": [{"id": l.id, "action": l.action, "actor_id": l.actor_id,
                   "target_type": l.target_type, "target_id": l.target_id,
                   "detail": l.detail, "created_at": l.created_at} for l in logs],
        "total": total, "page": page, "size": size,
    }


@router.post("/email/test")
async def test_email(
    request: Request,
    current_user: User = Depends(get_current_admin),
):
    try:
        await send_email(
            to_address=current_user.email,
            template="welcome",
            language=current_user.language,
            context={"full_name": current_user.full_name, "login_url": "https://www.oscaar.org"},
        )
        return {"sent": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email failed: {str(e)}")


@router.get("/health")
async def system_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    import time

    results = {}

    # Database
    try:
        t = time.time()
        await db.execute(select(func.count(User.id)))
        results["database"] = {"status": "ok", "latency_ms": round((time.time() - t) * 1000, 1)}
    except Exception as e:
        results["database"] = {"status": "error", "detail": str(e)}

    # Vector store
    try:
        store = __import__("app.services.vector_store", fromlist=["get_vector_store"]).get_vector_store()
        health = await store.health_check()
        results["vector_store"] = health
    except Exception as e:
        results["vector_store"] = {"status": "error", "detail": str(e)}

    # Redis
    try:
        import redis
        from app.core.config import settings
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        results["redis"] = {"status": "ok"}
    except Exception as e:
        results["redis"] = {"status": "error", "detail": str(e)}

    results["email"]   = {"status": "ok", "backend": __import__("app.core.config", fromlist=["settings"]).settings.EMAIL_BACKEND}
    results["storage"] = {"status": "ok"}

    return results
