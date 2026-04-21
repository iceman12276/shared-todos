"""Unit tests for shared auth cookie helpers (Group D — CSRF cookie hoist)."""

from fastapi.responses import JSONResponse

from app.auth.cookies import SESSION_COOKIE_NAME, set_auth_cookies


def test_set_auth_cookies_sets_session_cookie() -> None:
    response = JSONResponse(content={})
    set_auth_cookies(response, "tok123")
    headers = response.headers.getlist("set-cookie")
    session_cookies = [h for h in headers if SESSION_COOKIE_NAME in h]
    assert len(session_cookies) == 1
    assert "tok123" in session_cookies[0]
    assert "HttpOnly" in session_cookies[0]


def test_set_auth_cookies_sets_csrf_cookie() -> None:
    response = JSONResponse(content={})
    set_auth_cookies(response, "tok123")
    headers = response.headers.getlist("set-cookie")
    csrf_cookies = [h for h in headers if "csrf_token" in h]
    assert len(csrf_cookies) == 1
    # csrf cookie must NOT be httpOnly so JS can read it
    assert "HttpOnly" not in csrf_cookies[0]


def test_set_auth_cookies_csrf_is_random() -> None:
    """Two calls must produce different CSRF tokens."""
    r1 = JSONResponse(content={})
    r2 = JSONResponse(content={})
    set_auth_cookies(r1, "tok")
    set_auth_cookies(r2, "tok")
    csrf1 = next(h for h in r1.headers.getlist("set-cookie") if "csrf_token" in h)
    csrf2 = next(h for h in r2.headers.getlist("set-cookie") if "csrf_token" in h)
    assert csrf1 != csrf2
