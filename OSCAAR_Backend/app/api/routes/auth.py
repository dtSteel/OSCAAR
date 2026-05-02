from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.db.session import get_db
from app.models.user import User
from app.schemas.schemas import (
    RegisterRequest, LoginRequest, TokenPair, UserResponse,
    ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest,
    LanguageUpdateRequest,
)
from app.services.auth_service import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, verify_refresh_token, revoke_all_user_tokens,
    create_password_reset_token, verify_reset_token,
    get_user_by_email, get_user_by_id,
)
from app.services.email_service import send_welcome_email, send_password_reset_email
from app.services.geoip_service import detect_language_from_ip
from app.core.dependencies import get_current_user

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
            headers={"X-Error-Code": "EMAIL_EXISTS"},
        )

    language = body.language
    if language == "auto":
        client_ip = request.headers.get("X-Forwarded-For", request.client.host)
        ip = client_ip.split(",")[0].strip()
        language = detect_language_from_ip(ip)

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        language=language,
        role="researcher",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    try:
        await send_welcome_email(user.full_name, user.email, user.language)
    except Exception:
        pass

    await db.commit()
    return user


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"X-Error-Code": "INVALID_CREDENTIALS"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
            headers={"X-Error-Code": "ACCOUNT_DISABLED"},
        )

    user.last_login_at = datetime.now(timezone.utc)

    ua = request.headers.get("User-Agent")
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    raw_refresh = await create_refresh_token(db, user.id, user_agent=ua, ip_address=ip)

    access_token = create_access_token(user)

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/api/v1/auth",
    )

    await db.commit()
    return TokenPair(access_token=access_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    rt = await verify_refresh_token(db, raw_token)
    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await get_user_by_id(db, rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    rt.revoked_at = datetime.now(timezone.utc)
    new_raw = await create_refresh_token(db, user.id)
    access_token = create_access_token(user)

    response.set_cookie(
        key="refresh_token",
        value=new_raw,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/api/v1/auth",
    )

    await db.commit()
    return TokenPair(access_token=access_token)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await revoke_all_user_tokens(db, current_user.id)
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    await db.commit()


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, body.email)
    if user:
        raw_token = await create_password_reset_token(db, user.id)
        try:
            await send_password_reset_email(user.full_name, user.email, raw_token, user.language)
        except Exception:
            pass
        await db.commit()
    return {"sent": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    prt = await verify_reset_token(db, body.token)
    if not prt:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = await get_user_by_id(db, prt.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    prt.used_at = datetime.now(timezone.utc)
    await revoke_all_user_tokens(db, user.id)
    await db.commit()
    return {"reset": True}


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    await revoke_all_user_tokens(db, current_user.id)
    await db.commit()
    return {"changed": True}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/language", response_model=UserResponse)
async def update_language(
    body: LanguageUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.language = body.language
    await db.commit()
    await db.refresh(current_user)
    return current_user
