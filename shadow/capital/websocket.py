"""Capital.com WebSocket market data (quotes + OHLC).

Uses streaming tokens from REST session. Falls back gracefully if WS unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("shadow.capital.ws")

QuoteHandler = Callable[[dict[str, Any]], Awaitable[None]]
OhlcHandler = Callable[[dict[str, Any]], Awaitable[None]]


class CapitalWebSocket:
    def __init__(
        self,
        base_url: str,
        cst: str,
        security_token: str,
        *,
        on_quote: QuoteHandler | None = None,
        on_ohlc: OhlcHandler | None = None,
    ) -> None:
        # REST host → WS host pattern used by Capital.com streaming
        host = base_url.replace("https://", "").replace("http://", "")
        self.ws_url = f"wss://{host}/connect"
        self.cst = cst
        self.security_token = security_token
        self.on_quote = on_quote
        self.on_ohlc = on_ohlc
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.connected = False
        self.last_quote: dict[str, Any] | None = None

    async def start(self, epics: list[str], resolutions: list[str] | None = None) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(epics, resolutions or ["MINUTE"]))

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.connected = False

    async def _run(self, epics: list[str], resolutions: list[str]) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.ws_url,
                    additional_headers={
                        "CST": self.cst,
                        "X-SECURITY-TOKEN": self.security_token,
                    },
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    self.connected = True
                    backoff = 1.0
                    logger.info("WebSocket connected")
                    for epic in epics:
                        await ws.send(
                            json.dumps(
                                {
                                    "destination": "marketData.subscribe",
                                    "payload": {"epics": [epic]},
                                }
                            )
                        )
                        for res in resolutions:
                            await ws.send(
                                json.dumps(
                                    {
                                        "destination": "OHLCMarketData.subscribe",
                                        "payload": {
                                            "epics": [epic],
                                            "resolutions": [res],
                                            "type": "classic",
                                        },
                                    }
                                )
                            )
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        dest = msg.get("destination") or msg.get("status")
                        payload = msg.get("payload") or msg
                        if dest in ("quote", "marketData.quote") or "bid" in payload:
                            self.last_quote = payload
                            if self.on_quote:
                                await self.on_quote(payload)
                        elif dest in ("ohlc.event", "OHLCMarketData.event") or "o" in payload:
                            if self.on_ohlc:
                                await self.on_ohlc(payload)
            except ConnectionClosed as exc:
                logger.warning("WS closed: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("WS error: %s", exc)
            self.connected = False
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)