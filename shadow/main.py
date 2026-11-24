"""SHADOW FastAPI server — API + professional dashboard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shadow.auth_store import registration_status, save_credentials
from shadow.config import ROOT, Settings, config, settings, state
from shadow.engine.runtime import ShadowRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("shadow")

DASHBOARD = Path(__file__).parent / "dashboard"
runtime: ShadowRuntime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime
    runtime = ShadowRuntime(config, settings)
    await runtime.start()
    logger.info("SHADOW started on epic=%s paper=%s", state.epic, state.paper)
    yield
    await runtime.stop()
    runtime = None


app = FastAPI(title="SHADOW Trading Robot", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=DASHBOARD / "static"), name="static")


class CredsBody(BaseModel):
    api_key: str = Field(min_length=4)
    identifier: str = Field(min_length=3)
    password: str = Field(min_length=4)
    env: str = "demo"
    epic: str | None = None
    size: float | None = None
    persist: bool = True


class HandoverBody(BaseModel):
    direction: str = Field(default="BUY", pattern="^(BUY|SELL)$")


class NewsBody(BaseModel):
    risk: str = Field(default="ok", pattern="^(ok|high|blocked)$")


async def _apply_credentials(body: CredsBody) -> dict[str, Any]:
    """Save (optional) + hot-reload runtime with new Capital.com session."""
    global runtime
    assert runtime

    if Settings._is_placeholder(body.api_key) or Settings._is_placeholder(body.identifier) or Settings._is_placeholder(body.password):
        return {
            "ok": False,
            "error": "placeholder_credentials",
            "message": "Ievadi īstos Capital.com API datus, nevis piemēra tekstu.",
        }

    if body.persist:
        save_credentials(
            api_key=body.api_key,
            identifier=body.identifier,
            password=body.password,
            env=body.env,
            epic=body.epic,
            size=body.size,
        )

    settings.capital_api_key = body.api_key.strip()
    settings.capital_identifier = body.identifier.strip()
    settings.capital_password = body.password.strip()
    settings.capital_env = body.env.strip().lower()
    if body.epic:
        settings.shadow_epic = body.epic.strip()
        config.setdefault("instrument", {})["epic"] = body.epic.strip()
    if body.size:
        settings.shadow_size = float(body.size)
        config.setdefault("risk", {})["default_size"] = float(body.size)

    await runtime.stop()
    runtime = ShadowRuntime(config, settings)
    await runtime.start()

    ok = bool(state.connected and not state.paper)
    return {
        "ok": ok,
        "connected": state.connected,
        "paper": state.paper,
        "message": state.message,
        "error": state.error,
        "registration": registration_status(settings),
        "persisted": body.persist,
        "env_path": str(ROOT / ".env") if body.persist else None,
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(DASHBOARD / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "version": "1.0.0", "mode": state.mode}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    assert runtime
    snap = runtime.snapshot()
    snap["registration"] = registration_status(settings)
    return snap


@app.get("/api/registration")
async def get_registration() -> dict[str, Any]:
    return {
        "ok": True,
        **registration_status(settings),
        "connected": state.connected,
        "paper": state.paper,
        "message": state.message,
        "error": state.error,
    }


@app.post("/api/register")
async def register_account(body: CredsBody) -> dict[str, Any]:
    """Dashboard self-registration: save API creds to .env and connect."""
    return await _apply_credentials(body)


@app.post("/api/credentials")
async def set_credentials(body: CredsBody) -> dict[str, Any]:
    """Alias for register — hot-reload credentials."""
    return await _apply_credentials(body)


@app.post("/api/handover/simulate")
async def simulate_handover(body: HandoverBody) -> dict[str, Any]:
    assert runtime
    return await runtime.simulate_handover(body.direction)


@app.post("/api/handover/reset")
async def reset_handover() -> dict[str, Any]:
    assert runtime
    return await runtime.reset_handover()


@app.post("/api/news")
async def set_news(body: NewsBody) -> dict[str, Any]:
    state.news_risk = body.risk
    return {"ok": True, "news_risk": state.news_risk}


@app.post("/api/stop")
async def stop_bot() -> dict[str, Any]:
    assert runtime
    await runtime.stop()
    return {"ok": True, "mode": state.mode}


@app.post("/api/start")
async def start_bot() -> dict[str, Any]:
    global runtime
    if runtime and state.mode not in ("idle",):
        return {"ok": True, "mode": state.mode, "message": "already running"}
    runtime = ShadowRuntime(config, settings)
    await runtime.start()
    return {"ok": True, "mode": state.mode}


@app.websocket("/ws")
async def ws_feed(ws: WebSocket) -> None:
    assert runtime
    await ws.accept()
    q = await runtime.subscribe()
    try:
        snap = runtime.snapshot()
        snap["registration"] = registration_status(settings)
        await ws.send_json(snap)
        while True:
            payload = await q.get()
            payload["registration"] = registration_status(settings)
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("ws end: %s", exc)
    finally:
        runtime.unsubscribe(q)


@app.exception_handler(Exception)
async def on_error(_, exc: Exception) -> JSONResponse:
    logger.exception("unhandled")
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "shadow.main:app",
        host=settings.shadow_host,
        port=settings.shadow_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
