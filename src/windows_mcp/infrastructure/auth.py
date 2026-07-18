"""Bearer token and OAuth authentication middleware for HTTP transports."""

from __future__ import annotations

import ipaddress
import logging
import secrets
from datetime import datetime
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


logger = logging.getLogger(__name__)


_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/.well-known/oauth-authorization-server",
        "/oauth/register",
        "/oauth/authorize",
        "/oauth/token",
    }
)

_BEARER_PREFIX = "Bearer "


class AuthKeyMiddleware(BaseHTTPMiddleware):
    """Require Bearer token on all non-public paths.

    Accepts either the static auth_key or, when oauth_validator is provided,
    a valid OAuth access token as a fallback.
    """

    def __init__(
        self, app: ASGIApp, *, auth_key: str, oauth_validator: Callable[[str], bool] | None = None
    ) -> None:
        super().__init__(app)
        self._key = auth_key.encode("utf-8")
        self.oauth_validator = oauth_validator

    async def dispatch(self, request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        client_ip = request.client.host if request.client else "unknown"

        if not auth_header.startswith(_BEARER_PREFIX):
            self._log_failure("missing or malformed Authorization header", client_ip)
            return JSONResponse(
                {"error": "Missing or invalid Authorization header. Expected: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[len(_BEARER_PREFIX) :]
        if not token:
            self._log_failure("empty bearer token", client_ip)
            return JSONResponse(
                {"error": "Missing or invalid Authorization header. Expected: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_bytes = token.encode("utf-8")
        if secrets.compare_digest(token_bytes, self._key):
            return await call_next(request)

        if self.oauth_validator and self.oauth_validator(token):
            return await call_next(request)

        self._log_failure("invalid token", client_ip)
        return JSONResponse(
            {"error": "Invalid authentication token"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _log_failure(self, reason: str, client_ip: str) -> None:
        """Log a failed authentication attempt with the source IP and timestamp."""
        logger.warning(
            "Authentication failed: %s from %s at %s",
            reason,
            client_ip,
            datetime.now().isoformat(),
        )


class OAuthOnlyMiddleware(BaseHTTPMiddleware):
    """Authenticate via OAuth Bearer tokens only (no static API key configured)."""

    def __init__(self, app: ASGIApp, *, oauth_validator: Callable[[str], bool]) -> None:
        super().__init__(app)
        self.oauth_validator = oauth_validator

    async def dispatch(self, request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if self.oauth_validator(token):
                return await call_next(request)

        return JSONResponse({"error": "Unauthorized"}, status_code=401)


def is_loopback_host(host: str) -> bool:
    """Return True if host refers only to a loopback interface."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
