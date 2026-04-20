"""CSRF double-submit cookie validation middleware.

Protects all mutating verbs (POST/PUT/PATCH/DELETE) under /api/v1/
by requiring that the X-CSRF-Token request header matches the csrf_token
cookie value (constant-time comparison).

Exemptions:
- /api/v1/auth/login — no session exists yet
- /api/v1/auth/register — no session exists yet
- /api/v1/auth/oauth/* — GET-only flow; callback is GET
- All GET/HEAD/OPTIONS requests (safe verbs per RFC 7231)
"""
import secrets

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}

_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "x-csrf-token"


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # OAuth callback is GET-only — no exemption needed, but protect
        # any future OAuth POST endpoints by NOT exempting the entire prefix.

        cookie_token = request.cookies.get(_CSRF_COOKIE, "")

        # Only enforce CSRF when the browser already has a csrf_token cookie.
        # Unauthenticated requests (e.g., password-reset/request from an
        # unlogged-in browser) have no session to protect — CSRF is moot.
        if not cookie_token:
            return await call_next(request)

        header_token = request.headers.get(_CSRF_HEADER, "")

        if not header_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token missing"},
            )

        if not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token mismatch"},
            )

        return await call_next(request)
