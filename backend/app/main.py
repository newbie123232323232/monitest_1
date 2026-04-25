import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_jwt_secret_policy()
    if settings.app_env == "development" and settings.is_public_api_host and not settings.allow_insecure_dev_mode_on_public:
        raise RuntimeError("Refusing to run development mode on a public API host")
    yield
    await engine.dispose()


docs_url = "/docs"
openapi_url = "/openapi.json"
if settings.app_env == "production" and not settings.expose_docs_in_production:
    docs_url = None
    openapi_url = None

middleware: list[Middleware] = []
if settings.app_env == "production":
    middleware.append(Middleware(TrustedHostMiddleware, allowed_hosts=[settings.public_api_host, "localhost", "127.0.0.1"]))
    if settings.enforce_https_redirect:
        middleware.append(Middleware(HTTPSRedirectMiddleware))

app = FastAPI(
    title="MONI API",
    lifespan=lifespan,
    docs_url=docs_url,
    openapi_url=openapi_url,
    redoc_url=None,
    middleware=middleware,
)

# Dev: SPA nên dùng Vite proxy (/api → backend) để không cần CORS. Nếu vẫn gọi thẳng :8010, cho phép * (không credentials).
if settings.app_env == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api/v1")


def _default_code_for_status(status_code: int) -> str:
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
    }
    return mapping.get(status_code, f"http_{status_code}")


def _message_from_detail(detail: object, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict) and isinstance(first.get("msg"), str):
            return first["msg"]
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg
    return fallback


@app.exception_handler(HTTPException)
async def api_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    status_code = int(exc.status_code)
    detail = exc.detail
    code = _default_code_for_status(status_code)
    if isinstance(detail, dict):
        d_code = detail.get("code")
        if isinstance(d_code, str) and d_code.strip():
            code = d_code
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": _message_from_detail(detail, fallback=f"HTTP {status_code}"),
        },
    )


@app.exception_handler(RequestValidationError)
async def api_validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": _message_from_detail(exc.errors(), fallback="Validation failed"),
        },
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    docs_paths = {"/docs", "/openapi.json", "/docs/oauth2-redirect"}
    if request.url.path in docs_paths:
        # Swagger UI needs JS/CSS assets; strict API CSP would make docs blank.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


if settings.app_env == "development":

    @app.exception_handler(Exception)
    async def dev_unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        """Unhandled exceptions -> standardized payload + traceback in development."""
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": str(exc) or type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
        )


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "moni-api"}
