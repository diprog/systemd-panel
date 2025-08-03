import os
from pathlib import Path

from .config import CONFIG
from .auth import Auth
from .http import lower_headers, get_cookies, send_json, read_json, query_params
from .sse import start_sse, send_sse, end_sse
from . import systemd as sysd

# Single Auth/Sessions holder
AUTH = Auth(CONFIG.token_sha256, CONFIG.session_ttl)

STATIC_DIR = Path(__file__).with_suffix("").parent.parent / "static"


async def _serve_file(send, path: Path, content_type: str) -> None:
    """
    Serve a static file.

    :param send: ASGI send callable.
    :param path: Absolute path to file.
    :param content_type: MIME type.

    :returns: None.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        await send_json(send, 404, {"error": "not found"})
        return
    headers = [
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(data)).encode()),
        (b"cache-control", b"no-cache"),
    ]
    await send({"type": "http.response.start", "status": 200, "headers": headers})
    await send({"type": "http.response.body", "body": data})


async def app(scope, receive, send):
    """
    Minimal ASGI app with manual routing.

    :param scope: ASGI scope.
    :param receive: ASGI receive.
    :param send: ASGI send.

    :returns: None.
    """
    if scope["type"] != "http":
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"only http supported"})
        return

    method = scope["method"]
    path = scope["path"]
    headers = lower_headers(scope)
    cookies = get_cookies(headers)

    # ---------- Static ----------
    if method == "GET" and path == "/":
        index_path = STATIC_DIR / "index.html"
        return await _serve_file(send, index_path, "text/html; charset=utf-8")
    if method == "GET" and path == "/assets/app.js":
        js_path = STATIC_DIR / "app.js"
        return await _serve_file(send, js_path, "application/javascript; charset=utf-8")

    # ---------- Auth ----------
    if method == "GET" and path == "/api/auth/challenge":
        nonce = AUTH.make_nonce()
        return await send_json(send, 200, {"nonce": nonce})

    if method == "POST" and path == "/api/auth/login":
        data = await read_json(receive)
        nonce = data.get("nonce", "")
        client_hmac = data.get("hmac", "")
        sid = AUTH.verify_login(nonce, client_hmac)
        if not sid:
            return await send_json(send, 401, {"ok": False, "error": "invalid"})
        cookie = f"sid={sid}; HttpOnly; Path=/; SameSite=Lax"
        if CONFIG.cookie_secure:
            cookie += "; Secure"
        return await send_json(send, 200, {"ok": True}, extra_headers=[(b"set-cookie", cookie)])

    if method == "POST" and path == "/api/auth/logout":
        sid = cookies.get("sid")
        if sid:
            AUTH.revoke_sid(sid)
        cookie = "sid=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax"
        if CONFIG.cookie_secure:
            cookie += "; Secure"
        return await send_json(send, 200, {"ok": True}, extra_headers=[(b"set-cookie", cookie)])

    # All /api/** except /api/auth/** requires a valid session
    if path.startswith("/api/"):
        sid = cookies.get("sid")
        if not sid or not AUTH.validate_sid(sid):
            return await send_json(send, 401, {"ok": False, "error": "unauthorized"})

    # ---------- API ----------
    if method == "GET" and path == "/api/services":
        data = await sysd.services_snapshot(CONFIG.service_dir)
        return await send_json(send, 200, {"services": data})

    if method == "POST" and path.startswith("/api/service/"):
        parts = path.split("/")
        if len(parts) != 5:
            return await send_json(send, 404, {"ok": False, "error": "route"})
        unit, action = parts[3], parts[4]
        if not unit.endswith(".service"):
            return await send_json(send, 400, {"ok": False, "error": "bad unit"})
        if not await sysd.is_allowed_unit(unit, CONFIG.service_dir):
            return await send_json(send, 404, {"ok": False, "error": "unit not found"})
        if action == "start":
            rc, out, err = await sysd.start_unit(unit)
        elif action == "stop":
            rc, out, err = await sysd.stop_unit(unit)
        elif action == "restart":
            rc, out, err = await sysd.restart_unit(unit)
        else:
            return await send_json(send, 404, {"ok": False, "error": "bad action"})
        return await send_json(send, 200, {"ok": rc == 0, "code": rc, "stdout": out, "stderr": err})

    if method == "GET" and path == "/api/status/stream":
        await start_sse(send)
        try:
            async for snapshot in sysd.status_stream(CONFIG.service_dir):
                await send_sse(send, {"services": snapshot}, event="status")
        finally:
            await end_sse(send)
        return

    if method == "GET" and path == "/api/logs":
        params = query_params(scope)
        unit = params.get("unit", "")
        if not unit.endswith(".service"):
            return await send_json(send, 400, {"ok": False, "error": "bad unit"})
        if not await sysd.is_allowed_unit(unit, CONFIG.service_dir):
            return await send_json(send, 404, {"ok": False, "error": "unit not found"})
        lines = int(params.get("lines", "200"))
        await start_sse(send)
        try:
            async for line in sysd.journal_stream(unit, lines):
                await send_sse(send, {"line": line}, event="log")
        finally:
            await end_sse(send)
        return

    # Fallback
    return await send_json(send, 404, {"error": "not found"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host=CONFIG.bind, port=CONFIG.port, reload=False)
