"""CSRF double-submit cookie validation middleware.

Protects all mutating verbs (POST/PUT/PATCH/DELETE) under /api/v1/
by requiring that the X-CSRF-Token request header matches the csrf_token
cookie value (constant-time comparison).

Explicit path exemptions (see _CSRF_EXEMPT_PATHS):
- /api/v1/auth/login — session doesn't exist yet, no cookie to check
- /api/v1/auth/register — session doesn't exist yet, no cookie to check

Cookie-presence exemption (see skip-branch below):
- Requests that arrive without a csrf_token cookie are passed through.
  This covers unauthenticated flows (password-reset/request) where there
  is no session to protect. See the inline comment for scope constraints.

All GET/HEAD/OPTIONS requests are skipped as safe verbs per RFC 7231.
"""

import secrets

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    # refresh is called when the session (and thus csrf_token cookie) has expired
    "/api/v1/auth/refresh",
}

_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "x-csrf-token"


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        cookie_token = request.cookies.get(_CSRF_COOKIE, "")

        # Skip CSRF enforcement when the browser has no csrf_token cookie.
        # Scope assumption: the only unauthenticated mutating endpoint reachable
        # without a session cookie is /password-reset/request, which is already
        # anti-enumerated and gated by a 32-byte single-use token on /complete.
        # If a future endpoint is added that is (a) unauthenticated AND (b) has
        # meaningful side-effects beyond the reset flow, this skip-branch MUST
        # be revisited — add an explicit path exemption rather than relying on
        # the absence of a cookie.
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
