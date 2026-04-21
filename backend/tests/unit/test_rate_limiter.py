"""Unit tests for rate limiter client IP resolution (HIGH-7 — XFF trust control)."""

from unittest.mock import MagicMock

import pytest


def _make_request(xff: str | None = None, client_host: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = client_host
    headers: dict[str, str] = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    req.headers = headers
    return req


def test_client_ip_returns_direct_ip_when_trust_proxy_false() -> None:
    """When trust_proxy=False (default), XFF header must be ignored."""
    from app.auth.rate_limiter import _client_ip

    req = _make_request(xff="10.0.0.1", client_host="1.2.3.4")
    assert _client_ip(req) == "1.2.3.4"


def test_client_ip_returns_xff_when_trust_proxy_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """When trust_proxy=True, leftmost XFF value is used as client IP."""
    import app.auth.rate_limiter as rl
    from app.auth.rate_limiter import _client_ip

    monkeypatch.setattr(rl, "_TRUST_PROXY", True)
    req = _make_request(xff="203.0.113.5, 10.0.0.1", client_host="10.0.0.1")
    assert _client_ip(req) == "203.0.113.5"


def test_client_ip_fallback_when_no_client_and_trust_proxy_false() -> None:
    """When no client object and trust_proxy=False, return 'unknown'."""
    from app.auth.rate_limiter import _client_ip

    req = MagicMock()
    req.client = None
    req.headers = {}
    assert _client_ip(req) == "unknown"


def test_client_ip_no_xff_with_trust_proxy_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """When trust_proxy=True but no XFF header, fall back to TCP peer."""
    import app.auth.rate_limiter as rl
    from app.auth.rate_limiter import _client_ip

    monkeypatch.setattr(rl, "_TRUST_PROXY", True)
    req = _make_request(xff=None, client_host="5.6.7.8")
    assert _client_ip(req) == "5.6.7.8"
