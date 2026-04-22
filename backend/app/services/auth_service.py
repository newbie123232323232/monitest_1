import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_oauth_state_token,
    decode_access_token,
    decode_oauth_state_token,
    hash_password,
    hash_token_sha256,
    new_opaque_token,
    verify_password,
)
from app.integrations.mail import send_email_sync
from app.models.user import RefreshToken, User


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


async def register_user(session: AsyncSession, email: str, password: str) -> None:
    try:
        normalized_email = email.lower()
        q = await session.execute(select(User).where(User.email == normalized_email))
        existing = q.scalar_one_or_none()
        if existing and existing.is_verified:
            raise AuthError("email_taken", "Email already registered", 409)

        raw_verify = new_opaque_token()
        expires = datetime.now(UTC) + timedelta(hours=settings.email_verify_token_expire_hours)

        if existing:
            # Unverified account: refresh credentials + verification token instead of hard-failing.
            user = existing
            user.hashed_password = hash_password(password)
            user.email_verify_token_hash = hash_token_sha256(raw_verify)
            user.email_verify_expires_at = expires
            user.is_verified = False
        else:
            user = User(
                email=normalized_email,
                hashed_password=hash_password(password),
                is_verified=False,
                email_verify_token_hash=hash_token_sha256(raw_verify),
                email_verify_expires_at=expires,
            )
            session.add(user)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise AuthError("email_taken", "Email already registered", 409) from None

        base = str(settings.app_base_url).rstrip("/")
        verify_link = f"{base}/verify-email?token={raw_verify}"
        body = (
            f"Xác minh email MONI:\n\n{verify_link}\n\n"
            f"Link hết hạn sau {settings.email_verify_token_expire_hours} giờ."
        )
        try:
            await asyncio.to_thread(
                send_email_sync,
                "Xác minh email MONI",
                user.email,
                body,
            )
        except Exception as e:
            await session.rollback()
            raise AuthError(
                "smtp_failed",
                "Không gửi được email (SMTP). Kiểm tra SMTP trong .env hoặc dùng Swagger xem chi tiết lỗi.",
                503,
            ) from e

        await session.commit()
    except AuthError:
        raise
    except IntegrityError:
        await session.rollback()
        raise AuthError("email_taken", "Email already registered", 409) from None
    except SQLAlchemyError as e:
        await session.rollback()
        raise AuthError(
            "database_unavailable",
            "Không kết nối được PostgreSQL. Kiểm tra DATABASE_URL và máy chủ DB đang chạy.",
            503,
        ) from e


async def verify_email(session: AsyncSession, token: str) -> None:
    token_hash = hash_token_sha256(token)
    q = await session.execute(select(User).where(User.email_verify_token_hash == token_hash))
    user = q.scalar_one_or_none()
    if not user or not user.email_verify_expires_at:
        raise AuthError("invalid_token", "Invalid or expired verification token", 400)
    if user.email_verify_expires_at < datetime.now(UTC):
        raise AuthError("expired_token", "Verification token expired", 400)

    user.is_verified = True
    user.email_verify_token_hash = None
    user.email_verify_expires_at = None
    await session.commit()


async def login_password(session: AsyncSession, email: str, password: str) -> tuple[str, str]:
    try:
        q = await session.execute(select(User).where(User.email == email.lower()))
        user = q.scalar_one_or_none()
        if not user or not user.hashed_password:
            raise AuthError("invalid_credentials", "Invalid email or password", 401)
        if not verify_password(password, user.hashed_password):
            raise AuthError("invalid_credentials", "Invalid email or password", 401)
        if not user.is_verified:
            raise AuthError("email_not_verified", "Email not verified", 403)

        return await _issue_tokens(session, user)
    except AuthError:
        raise
    except SQLAlchemyError as e:
        await session.rollback()
        raise AuthError(
            "database_unavailable",
            "Không kết nối được PostgreSQL. Kiểm tra DATABASE_URL và máy chủ DB đang chạy.",
            503,
        ) from e


async def refresh_tokens(session: AsyncSession, refresh_raw: str) -> tuple[str, str]:
    th = hash_token_sha256(refresh_raw)
    q = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == th))
    row = q.scalar_one_or_none()
    if not row or row.revoked_at is not None:
        raise AuthError("invalid_refresh", "Invalid refresh token", 401)
    if row.expires_at < datetime.now(UTC):
        raise AuthError("expired_refresh", "Refresh token expired", 401)

    q2 = await session.execute(select(User).where(User.id == row.user_id))
    user = q2.scalar_one_or_none()
    if not user:
        raise AuthError("invalid_refresh", "Invalid refresh token", 401)

    row.revoked_at = datetime.now(UTC)
    await session.flush()
    return await _issue_tokens(session, user)


async def logout(session: AsyncSession, refresh_raw: str) -> None:
    th = hash_token_sha256(refresh_raw)
    q = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == th))
    row = q.scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()


async def _issue_tokens(session: AsyncSession, user: User) -> tuple[str, str]:
    access = create_access_token(user.id)
    raw_refresh = new_opaque_token()
    exp = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token_sha256(raw_refresh),
            expires_at=exp,
        )
    )
    await session.commit()
    return access, raw_refresh


def google_authorize_url() -> str:
    if not settings.google_oauth_client_id or not settings.google_oauth_redirect_uri:
        raise AuthError("oauth_not_configured", "Google OAuth not configured", 503)
    state = create_oauth_state_token()
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def google_oauth_callback(session: AsyncSession, code: str, state: str) -> tuple[str, str]:
    decode_oauth_state_token(state)
    if not settings.google_oauth_client_secret:
        raise AuthError("oauth_not_configured", "Google OAuth not configured", 503)

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        if r.status_code != 200:
            raise AuthError("oauth_token", "Google token exchange failed", 400)
        token_data = r.json()
        access = token_data.get("access_token")
        if not access:
            raise AuthError("oauth_token", "No access_token from Google", 400)

        u = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access}"},
            timeout=30.0,
        )
        if u.status_code != 200:
            raise AuthError("oauth_userinfo", "Google userinfo failed", 400)
        info = u.json()

    sub = info.get("sub")
    email = (info.get("email") or "").lower()
    if not sub or not email:
        raise AuthError("oauth_profile", "Google profile incomplete", 400)

    q = await session.execute(select(User).where(User.google_sub == sub))
    user = q.scalar_one_or_none()
    if user:
        return await _issue_tokens(session, user)

    q2 = await session.execute(select(User).where(User.email == email))
    existing = q2.scalar_one_or_none()
    if existing:
        if existing.google_sub and existing.google_sub != sub:
            raise AuthError("oauth_conflict", "Email linked to another account", 409)
        existing.google_sub = sub
        existing.is_verified = True
        await session.flush()
        return await _issue_tokens(session, existing)

    user = User(
        email=email,
        hashed_password=None,
        is_verified=True,
        google_sub=sub,
    )
    session.add(user)
    await session.flush()
    return await _issue_tokens(session, user)


async def get_user_by_token(session: AsyncSession, access_token: str) -> User:
    try:
        uid = decode_access_token(access_token)
    except ValueError as e:
        raise AuthError("invalid_token", str(e), 401) from e
    q = await session.execute(select(User).where(User.id == uid))
    user = q.scalar_one_or_none()
    if not user:
        raise AuthError("invalid_token", "User not found", 401)
    return user
