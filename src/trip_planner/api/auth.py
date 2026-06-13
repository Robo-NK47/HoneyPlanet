"""Light shared-password auth — opt-in via APP_SECRET.

If ``APP_SECRET`` is unset (the local-dev default), auth is DISABLED and everything is open.
Set it in production to require the shared password at ``/login`` before viewing the plan,
chatting, or editing the task board. A successful login stores an HMAC token in an HttpOnly
cookie; the token carries no claims beyond "authenticated", which is all a two-person app needs.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from trip_planner.config import settings

COOKIE = "tp_auth"
router = APIRouter(tags=["auth"])


def auth_enabled() -> bool:
    return bool(settings.app_secret)


def _token() -> str:
    secret = (settings.app_secret or "").encode()
    return hmac.new(secret, b"trip-planner-auth-v1", hashlib.sha256).hexdigest()


def is_authed(request: Request) -> bool:
    if not auth_enabled():
        return True
    tok = request.cookies.get(COOKIE, "")
    return bool(tok and hmac.compare_digest(tok, _token()))


async def require_auth(request: Request) -> None:
    """FastAPI dependency for API routes: 401 unless authed (no-op when auth is disabled)."""
    if not is_authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")


_LOGIN_HTML = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Sign in</title><style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f1115;color:#e8eaed;
display:grid;place-items:center;height:100vh;margin:0}
form{background:#161a20;padding:24px;border-radius:12px;display:flex;flex-direction:column;
gap:10px;min-width:260px}
input{background:#0f1115;border:1px solid #2a2e35;color:#e8eaed;border-radius:6px;padding:8px}
button{background:#4c8bf5;color:#fff;border:0;border-radius:6px;padding:8px;cursor:pointer}
.err{color:#e05260;font-size:.85em}
</style></head><body><form method=post action=/login>
<b>\U0001f5fe Trip Planner</b>{err}
<input type=password name=secret placeholder="Shared password" autofocus>
<button>Sign in</button></form></body></html>"""


@router.get("/login", response_class=HTMLResponse)
async def login_form(bad: int = 0) -> HTMLResponse:
    err = "<div class=err>Wrong password.</div>" if bad else ""
    return HTMLResponse(_LOGIN_HTML.replace("{err}", err))


@router.post("/login")
async def login(secret: str = Form(...)) -> Response:
    if not auth_enabled() or hmac.compare_digest(secret, settings.app_secret or ""):
        resp = RedirectResponse("/plan", status_code=303)
        if auth_enabled():
            resp.set_cookie(
                COOKIE,
                _token(),
                httponly=True,
                samesite="lax",
                secure=not settings.debug,
                max_age=60 * 60 * 24 * 30,
            )
        return resp
    return RedirectResponse("/login?bad=1", status_code=303)


@router.post("/logout")
async def logout() -> Response:
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
