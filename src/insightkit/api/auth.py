"""JWT auth + RBAC + API-key exchange + rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from insightkit.config import Config
from insightkit.security.users import UserStore

ROLE_LEVEL = {"viewer": 1, "analyst": 2, "admin": 3}
ALGO = "HS256"


class RateLimiter:
    """Sliding-window rate limiter (in-memory, per user)."""

    def __init__(self, limit_per_min: int) -> None:
        self.limit = limit_per_min
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, user: str) -> bool:
        now = time.monotonic()
        window_start = now - 60
        hits = [h for h in self._hits[user] if h > window_start]
        if len(hits) >= self.limit:
            self._hits[user] = hits
            return False
        hits.append(now)
        self._hits[user] = hits
        return True


def create_jwt(cfg: Config, username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=cfg.api.jwt_expire_min),
    }
    return jwt.encode(payload, cfg.api.jwt_secret, algorithm=ALGO)


def _decode_jwt(cfg: Config, token: str) -> dict | None:
    try:
        claims = jwt.decode(token, cfg.api.jwt_secret, algorithms=[ALGO])
        return claims
    except jwt.PyJWTError:
        return None


def _role_sufficient(user_role: str, required: str) -> bool:
    return ROLE_LEVEL.get(user_role, 0) >= ROLE_LEVEL.get(required, 99)


async def get_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Authenticate via Bearer JWT or X-API-Key. Returns {username, role}."""
    cfg: Config = request.app.state.cfg
    limiter: RateLimiter = request.app.state.rate_limiter
    store = UserStore(cfg)

    username: str | None = None
    role: str | None = None

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        claims = _decode_jwt(cfg, token)
        if claims:
            username, role = claims.get("sub"), claims.get("role")
    elif x_api_key:
        user = await store.verify(x_api_key)
        if user:
            username, role = user["username"], user["role"]

    if not username or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not limiter.allow(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded"
        )
    return {"username": username, "role": role}


def require_role(required: str) -> Callable[..., dict]:
    """Dependency factory: require a role level (viewer < analyst < admin)."""

    def dep(auth: dict = Depends(get_auth)) -> dict:
        if not _role_sufficient(auth["role"], required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return auth

    return dep
