"""Optional password for the whole app (APP_PASSWORD). Off when unset.

Who has to log in: every request that arrives through the Cloudflare edge, recognised by the CF-Connecting-IP header
Cloudflare sets (and overwrites) on everything it forwards. Requests made on the host itself or on the internal Docker
network (health checks, the warm-cache timer, a read-only companion service) carry no such header and pass; the host
has no public address, so the edge is the only way in from outside.

A login sets an HttpOnly, Secure, SameSite=Lax cookie holding an HMAC of the password (changing the password logs
everyone out). Failed attempts are limited per client address."""
from __future__ import annotations
import hashlib, hmac, html, time
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from whycore.settings import settings

COOKIE = "whycore_session"
OPEN = {"/healthz", "/login", "/logout"}
MAX_FAILS, WINDOW = 8, 900                     # 8 wrong passwords per address per 15 minutes
_fails: dict[str, list[float]] = {}


def _token() -> str:
    return hmac.new(settings.app_password.encode(), f"session|{settings.app_name}".encode(), hashlib.sha256).hexdigest()


def _from_edge(request: Request) -> str | None:
    return request.headers.get("cf-connecting-ip")


def _authed(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token())


async def middleware(request: Request, call_next):
    if not settings.app_password or request.url.path in OPEN or not _from_edge(request) or _authed(request):
        return await call_next(request)
    if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login?next=" + request.url.path, status_code=303)
    return JSONResponse({"detail": "login required"}, status_code=401)


def _page(next_: str, error: str = "") -> HTMLResponse:
    nxt = html.escape(next_ if next_.startswith("/") and not next_.startswith("//") else "/")
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in</title><style>
 body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#0b0f17; color:#e4e8ef; font:14px/1.5 Inter, system-ui, sans-serif; }}
 form {{ width:min(340px, calc(100vw - 32px)); background:#10151f; border:1px solid #232a37; border-radius:10px; padding:24px; }}
 h1 {{ margin:0 0 4px; font-size:16px; font-weight:600; }} p {{ margin:0 0 16px; color:#9099a8; font-size:13px; }}
 input {{ width:100%; box-sizing:border-box; padding:9px 11px; border-radius:7px; border:1px solid #2a3243; background:#0b0f17; color:#e4e8ef; font:inherit; }}
 button {{ margin-top:12px; width:100%; padding:9px; border:0; border-radius:7px; background:#3e7bfa; color:#fff; font:600 14px Inter, sans-serif; cursor:pointer; }}
 .err {{ color:#e5484d; margin:10px 0 0; }}
</style></head><body><form method="post" action="/login"><h1>{html.escape(settings.app_name)}</h1><p>Enter the password to continue.</p>
<input type="hidden" name="next" value="{nxt}"><input type="password" name="password" autocomplete="current-password" autofocus required aria-label="Password">
<button>Sign in</button>{err}</form></body></html>""")


def login_page(next: str = "/") -> HTMLResponse:
    return _page(next)


async def login(request: Request):
    # parsed by hand: a plain urlencoded form does not need python-multipart
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8", "replace")).items()}
    ip = _from_edge(request) or (request.client.host if request.client else "?")
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < WINDOW]
    nxt = str(form.get("next") or "/")
    if len(recent) >= MAX_FAILS:
        return _page(nxt, "Too many attempts. Try again in a few minutes.")
    if not settings.app_password or not hmac.compare_digest(str(form.get("password") or "").encode(), settings.app_password.encode()):
        _fails[ip] = recent + [now]
        return _page(nxt, "Wrong password.")
    _fails.pop(ip, None)
    r = RedirectResponse(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/", status_code=303)
    r.set_cookie(COOKIE, _token(), max_age=7 * 86400, httponly=True, secure=True, samesite="lax")
    return r


def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(COOKIE)
    return r
