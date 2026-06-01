from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, Header, HTTPException

from .settings import settings
from .store import InMemoryStore

ADMIN_ROLES = frozenset({"super_admin", "ops", "reviewer", "readonly"})


def new_token_session_id() -> str:
    return str(uuid4())


def issue_token(
    subject: UUID | str,
    role: str,
    token_type: str = "access",
    session_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    expires_at = now + (timedelta(days=30) if token_type == "refresh" else timedelta(days=7))
    return jwt.encode(
        {
            "sub": str(subject),
            "role": role,
            "typ": token_type,
            "sid": session_id or new_token_session_id(),
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"})
    raw_token = authorization.removeprefix("Bearer ")
    try:
        claims = jwt.decode(raw_token, settings.jwt_secret, algorithms=["HS256"])
        claims["_raw_token"] = raw_token
        return claims
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"}) from exc


def ensure_token_active(claims: dict, db: InMemoryStore) -> None:
    if db.is_token_revoked(str(claims.get("jti"))) or db.is_token_session_revoked(str(claims.get("sid"))):
        raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"})


def ensure_token_type(claims: dict, token_type: str) -> None:
    if claims.get("typ") != token_type:
        raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"})


def get_store() -> InMemoryStore:
    raise RuntimeError("store dependency not configured")


def current_user_id(claims: dict = Depends(decode_token), db: InMemoryStore = Depends(get_store)) -> UUID:
    ensure_token_active(claims, db)
    ensure_token_type(claims, "access")
    if claims.get("role") != "user":
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
    return UUID(str(claims["sub"]))


def _current_admin_id_for_roles(claims: dict, db: InMemoryStore, allowed_roles: frozenset[str]) -> UUID:
    ensure_token_active(claims, db)
    ensure_token_type(claims, "access")
    if claims.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
    admin_id = UUID(str(claims["sub"]))
    if not db.is_admin_session_active(admin_id, claims.get("_raw_token")):
        raise HTTPException(status_code=401, detail={"code": 40101, "message": "unauthenticated"})
    admin_user = db.admin_users.get(admin_id)
    if not admin_user or admin_user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail={"code": 40301, "message": "forbidden"})
    return admin_id


def current_admin_id(claims: dict = Depends(decode_token), db: InMemoryStore = Depends(get_store)) -> UUID:
    return _current_admin_id_for_roles(claims, db, ADMIN_ROLES)


def require_admin_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(claims: dict = Depends(decode_token), db: InMemoryStore = Depends(get_store)) -> UUID:
        return _current_admin_id_for_roles(claims, db, allowed)

    return dependency
