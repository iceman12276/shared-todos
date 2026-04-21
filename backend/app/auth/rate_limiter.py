"""In-memory failed-login rate limiter.

Tracks failed login attempts per IP. After N failures within a window,
subsequent attempts raise 429.

This is an in-memory implementation suitable for v1 single-replica. For
multi-replica deployments, replace the _store dict with a Redis backend.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException, Request, status

from app.config import settings

_log = logging.getLogger("app.auth.rate_limiter")

# (ip, window_start) -> count of failed attempts
_store: dict[str, list[datetime]] = defaultdict(list)
_lock = Lock()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def record_failed_login(request: Request) -> None:
    """Record a failed login attempt for the request's IP."""
    ip = _client_ip(request)
    now = datetime.now(UTC)
    window = timedelta(seconds=settings.rate_limit_login_window_seconds)
    with _lock:
        attempts = _store[ip]
        # Evict expired entries
        _store[ip] = [t for t in attempts if now - t < window]
        _store[ip].append(now)


def check_login_rate_limit(request: Request) -> None:
    """Raise 429 if IP has exceeded the failed login threshold."""
    ip = _client_ip(request)
    now = datetime.now(UTC)
    window = timedelta(seconds=settings.rate_limit_login_window_seconds)
    with _lock:
        attempts = _store.get(ip, [])
        recent = [t for t in attempts if now - t < window]
        if len(recent) >= settings.rate_limit_login_attempts:
            _log.warning("rate-limit: login lockout triggered ip=%s attempts=%d", ip, len(recent))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again later.",
                headers={"Retry-After": str(settings.rate_limit_login_window_seconds)},
            )


def reset_failed_logins(request: Request) -> None:
    """Clear the failed login counter on successful login."""
    ip = _client_ip(request)
    with _lock:
        _store.pop(ip, None)
