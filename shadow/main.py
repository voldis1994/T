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

from shadow.config import config, settings, state
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
    api_key: str
    identifier: str
    password: str
    env: str = "demo"
    epic: str | None = None
    size: float | None = None


class HandoverBody(BaseModel):
    direction: str = Field(default="BUY", pattern="^(BUY|SELL)$")


class NewsBody(BaseModel):
    risk: str = Field(default="ok", pattern="^(ok|high|blocked)$")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(DASHBOARD / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "version": "1.0.0", "mode": state.mode}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    assert runtime
    return runtime.snapshot()


@app.post("/api/handover/simulate")
async def simulate_handover(body: HandoverBody) -> dict[str, Any]:
    assert runtime
    return await runtime.simulate_handover(body.direction)


@app.post("/api/handover/reset")
async def reset_handover() -> dict[str, Any]:
    assert runtime
    return await runtime.reset_handover()


@app.post("/api/credentials")
async def set_credentials(body: CredsBody) -> dict[str, Any]:
    """Hot-reload credentials and reconnect (saved in process memory only)."""
    global runtime
    assert runtime
    settings.capital_api_key = body.api_key
    settings.capital_identifier = body.identifier
    settings.capital_password = body.password
    settings.capital_env = body.env
    if body.epic:
        settings.shadow_epic = body.epic
        config.setdefault("instrument", {})["epic"] = body.epic
    if body.size:
        settings.shadow_size = body.size
        config.setdefault("risk", {})["default_size"] = body.size
    await runtime.stop()
    runtime = ShadowRuntime(config, settings)
    await runtime.start()
    return {"ok": True, "connected": state.connected, "paper": state.paper, "message": state.message}


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
        await ws.send_json(runtime.snapshot())
        while True:
            payload = await q.get()
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