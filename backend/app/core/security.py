import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """bcrypt trực tiếp — tránh passlib + bcrypt 4.x không tương thích."""
    data = plain.encode("utf-8")
    if len(data) > 72:
        data = data[:72]
    return bcrypt.hashpw(data, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def hash_token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire, "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("typ") != "access":
            raise JWTError("wrong token type")
        sub = payload.get("sub")
        if not sub:
            raise JWTError("missing sub")
        return uuid.UUID(sub)
    except (JWTError, ValueError) as e:
        raise ValueError("invalid token") from e


def create_oauth_state_token() -> str:
    expire = datetime.now(UTC) + timedelta(minutes=10)
    payload = {"typ": "oauth_state", "purpose": "google", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_oauth_state_token(token: str) -> None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("typ") != "oauth_state" or payload.get("purpose") != "google":
            raise JWTError("invalid state")
    except JWTError as e:
        raise ValueError("invalid state") from e
