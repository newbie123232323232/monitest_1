from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import auth_rate_limiter
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services import auth_service as auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _http(e: auth.AuthError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})


def _enforce_auth_rate_limit(request: Request, action: str, subject: str | None = None) -> None:
    client_ip = request.client.host if request.client else "unknown"
    user_key = (subject or "").strip().lower()
    key = f"{action}:{client_ip}:{user_key}"
    result = auth_rate_limiter.allow(
        key=key,
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": f"Too many {action} attempts. Retry later.",
            },
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


@router.post("/register", response_model=MessageResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    _enforce_auth_rate_limit(request, "register", body.email)
    try:
        await auth.register_user(session, body.email, body.password)
    except auth.AuthError as e:
        raise _http(e) from e
    return MessageResponse(message="Check your email to verify your account.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email_post(body: VerifyEmailRequest, session: AsyncSession = Depends(get_db)) -> MessageResponse:
    try:
        await auth.verify_email(session, body.token)
    except auth.AuthError as e:
        raise _http(e) from e
    return MessageResponse(message="Email verified. You can sign in.")


@router.get("/verify-email", response_class=RedirectResponse)
async def verify_email_get(
    token: str = Query(..., min_length=10),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    base = str(settings.app_base_url).rstrip("/")
    try:
        await auth.verify_email(session, token)
        return RedirectResponse(url=f"{base}/verify-email?verified=1", status_code=302)
    except auth.AuthError:
        return RedirectResponse(url=f"{base}/verify-email?verified=0", status_code=302)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _enforce_auth_rate_limit(request, "login", body.email)
    try:
        access, refresh = await auth.login_password(session, body.email, body.password)
    except auth.AuthError as e:
        raise _http(e) from e
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _enforce_auth_rate_limit(request, "refresh")
    try:
        access, refresh = await auth.refresh_tokens(session, body.refresh_token)
    except auth.AuthError as e:
        raise _http(e) from e
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout", response_model=MessageResponse)
async def logout(body: LogoutRequest, session: AsyncSession = Depends(get_db)) -> MessageResponse:
    try:
        await auth.logout(session, body.refresh_token)
    except auth.AuthError as e:
        raise _http(e) from e
    return MessageResponse(message="Logged out.")


@router.get("/google")
async def google_start() -> RedirectResponse:
    try:
        url = auth.google_authorize_url()
    except auth.AuthError as e:
        raise _http(e) from e
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    base = str(settings.app_base_url).rstrip("/")
    if error:
        return RedirectResponse(url=f"{base}/auth/callback?error={quote(error)}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{base}/auth/callback?error=missing_params", status_code=302)
    try:
        access, refresh = await auth.google_oauth_callback(session, code, state)
    except auth.AuthError as e:
        return RedirectResponse(url=f"{base}/auth/callback?error={quote(e.code)}", status_code=302)

    frag = (
        f"access_token={quote(access)}&refresh_token={quote(refresh)}&token_type=bearer"
    )
    return RedirectResponse(url=f"{base}/auth/callback#{frag}", status_code=302)
