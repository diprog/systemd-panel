"""
Main ASGI entry point for the systemd panel.
"""
import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from auth import check_token
from models import ServiceStatus
from services import ServiceManager

# ------------------------------------------------------------------
app = FastAPI(title="systemd-panel", version="1.0.0")

# Static SPA -------------------------------------------------------
frontend_root = Path(__file__).resolve().parent.parent / "frontend" / "static"
app.mount("/static", StaticFiles(directory=frontend_root), name="static")
app.mount("/", StaticFiles(directory=frontend_root, html=True), name="spa")

# API helpers ------------------------------------------------------
svc = ServiceManager()


# ------------------------------------------------------------------
@app.post("/api/login")
async def login(credentials: dict) -> dict:
    """
    Accepts {"token": "<plain text token>"} and returns {"ok": bool}.
    """
    ok = check_token(credentials.get("token", ""))
    return {"ok": ok}


@app.get("/api/services")
async def list_services() -> list[ServiceStatus]:
    """
    Returns current status of every unit found in /etc/systemd/system.
    """
    return await svc.list_services()


@app.post("/api/services/{unit}/start")
async def start(unit: str) -> dict:
    await svc.action(unit, "start")
    return {"status": "ok"}


@app.post("/api/services/{unit}/stop")
async def stop(unit: str) -> dict:
    await svc.action(unit, "stop")
    return {"status": "ok"}


@app.post("/api/services/{unit}/restart")
async def restart(unit: str) -> dict:
    await svc.action(unit, "restart")
    return {"status": "ok"}


# ------------------------------------------------------------------
@app.websocket("/ws/logs/{unit}")
async def logs(websocket: WebSocket, unit: str):
    """
    Streams journalctl -fu <unit> to the connected WebSocket.
    The endpoint will silently close if the unit is invalid.
    """
    await websocket.accept()
    try:
        proc = await svc.tail_logs(unit)
        async for line in proc.stdout:
            await websocket.send_text(line.decode(errors="ignore"))
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()