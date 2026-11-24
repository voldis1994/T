"""Main SHADOW runtime loop — data → fusion → brain → execute."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadow.analysis.fusion import MarketFusion
from shadow.analysis.ohlc import parse_capital_prices, synthetic_trend_candles
from shadow.capital.client import CapitalClient
from shadow.config import AppState, Settings, state
from shadow.engine.brain import ShadowBrain
from shadow.engine.handover import HandoverController
from shadow.engine.paper import PaperBroker

logger = logging.getLogger("shadow.runtime")


class ShadowRuntime:
    def __init__(self, config: dict[str, Any], settings: Settings) -> None:
        self.config = config
        self.settings = settings
        self.fusion = MarketFusion(config)
        self.brain = ShadowBrain(config, self.fusion)
        self.handover = HandoverController(
            enabled=bool(config.get("handover", {}).get("enabled", True)),
            manage_user_position=bool(config.get("handover", {}).get("manage_user_position", True)),
            on_handover=self._on_handover,
        )
        self.paper = PaperBroker(balance=10_000.0)
        self.client: CapitalClient | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.candles = synthetic_trend_candles(240)
        self.trades_path = Path(config.get("engine", {}).get("trades_log_path", "logs/trades.jsonl"))
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        self._managed_deal_ids: set[str] = set()
        self._last_signal_bar: str | None = None
        self._pending_handover: dict[str, Any] | None = None
        self.subscribers: list[asyncio.Queue] = []

    @property
    def using_paper(self) -> bool:
        return self.client is None

    async def start(self) -> None:
        state.started_at = datetime.now(timezone.utc).isoformat()
        state.epic = self.config.get("instrument", {}).get("epic", self.settings.shadow_epic)
        state.paper = True
        state.mode = "waiting_handover" if self.handover.enabled else "active"
        state.message = "Gaida tavu pirmo treidu Capital.com app…" if self.handover.enabled else "Aktīvs"

        if self.settings.has_credentials:
            try:
                self.client = CapitalClient(
                    self.settings.capital_api_key,
                    self.settings.capital_identifier,
                    self.settings.capital_password,
                    self.settings.capital_base_url,
                )
                await self.client.login()
                state.connected = True
                state.paper = False
                await self._refresh_account()
                positions = await self.client.get_positions()
                self.handover.seed_baseline(positions)
                # Load real candles
                raw = await self.client.get_prices(
                    state.epic,
                    "MINUTE",
                    int(self.config.get("instrument", {}).get("history_bars", 300)),
                )
                parsed = parse_capital_prices(raw)
                if len(parsed) >= 40:
                    self.candles = parsed
                state.message = (
                    "Pieslēgts Capital.com. Atver pirmo treidu app — robots pārņems."
                    if self.handover.enabled
                    else "Pieslēgts Capital.com — aktīvs."
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Capital login failed — paper mode")
                state.error = f"API login failed: {exc}"
                state.paper = True
                state.connected = False
                state.message = "Paper režīms (API nav pieejams). Spied «Simulēt pirmo treidu»."
                self.client = None
        else:
            state.message = (
                "Paper režīms — ievadi API atslēgas iestatījumos. "
                "Vai spied «Simulēt pirmo treidu» lai redzētu handover."
            )

        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.client:
            await self.client.close()
            self.client = None
        state.mode = "idle"
        state.message = "Apturēts"

    async def simulate_handover(self, direction: str = "BUY") -> dict[str, Any]:
        """Dashboard button: pretend user opened first trade (only while waiting)."""
        if self.handover.active:
            msg = "Handover jau noticis — robots jau vada tirgu."
            state.message = msg
            await self._broadcast()
            return {
                "ok": False,
                "error": "handover_already_active",
                "message": msg,
                "dealId": self.handover.handover_deal_id,
            }
        if self.client:
            size = float(self.config.get("risk", {}).get("default_size", 1000))
            resp = await self.client.open_position(state.epic, direction, size)
            await asyncio.sleep(0.5)
            positions = await self.client.get_positions()
            event = self.handover.observe(positions)
            await self._refresh_state_positions(positions)
            if event:
                self._pending_handover = event
            await self._broadcast()
            return {"ok": True, "via": "api", "resp": resp, "handover": event}
        resp = self.paper.simulate_user_open(
            state.epic, direction, float(self.config["risk"]["default_size"])
        )
        positions = self.paper.get_positions()
        event = self.handover.observe(positions)
        await self._refresh_state_positions(positions)
        if event:
            await self._attach_brackets_to_handover(event)
        await self._broadcast()
        return {"ok": True, "via": "paper", "resp": resp, "handover": event}

    async def reset_handover(self) -> dict[str, Any]:
        """Test helper: clear paper positions and wait for handover again."""
        self.handover.reset()
        if self.using_paper:
            self.paper.positions.clear()
            self.paper.closed.clear()
        self._managed_deal_ids.clear()
        self._pending_handover = None
        state.mode = "waiting_handover"
        state.handover_detected_at = None
        state.open_positions = []
        state.message = "Gaida tavu pirmo treidu Capital.com app…"
        if self.using_paper:
            self.handover.seed_baseline([])
        elif self.client:
            positions = await self.client.get_positions()
            self.handover.seed_baseline(positions)
            await self._refresh_state_positions(positions)
        await self._broadcast()
        return {"ok": True, "mode": state.mode}

    def _on_handover(self, event: dict[str, Any]) -> None:
        state.mode = "active"
        state.handover_detected_at = event.get("at")
        state.message = f"HANDOVER — pārņemts deal {event.get('dealId')}. Robots vada tirgu."
        self._pending_handover = event

    async def _attach_brackets_to_handover(self, event: dict[str, Any]) -> None:
        if not self.handover.manage_user_position:
            return
        deal_id = event.get("dealId")
        if not deal_id:
            return
        pos = (event.get("position") or {}).get("position") or event.get("position") or {}
        direction = str(pos.get("direction") or "BUY").upper()
        entry = float(pos.get("level") or self.candles[-1].close)

        from shadow.analysis.brackets import compute_brackets
        from shadow.analysis.indicators import compute_indicators
        from shadow.analysis.structure import analyze_structure
        from shadow.analysis.zones import detect_zones

        analysis = self.fusion.analyze(self.candles)
        ind = compute_indicators(self.candles, self.config.get("analysis", {}))
        atr = float(ind.get("atr") or 0.0001)
        st = analyze_structure(self.candles)
        zones = detect_zones(self.candles, atr)
        regime_name = (analysis.get("regime") or {}).get("regime") or "TREND"
        # Always build structural brackets for the user's actual direction
        brackets = compute_brackets(
            {
                "regime": regime_name if regime_name not in ("UNKNOWN", "COMPRESSION") else "TREND",
                "range_high": (analysis.get("regime") or {}).get("range_high"),
                "range_low": (analysis.get("regime") or {}).get("range_low"),
                "level": (analysis.get("regime") or {}).get("level"),
                "sweep": (analysis.get("regime") or {}).get("sweep"),
                "zone": (analysis.get("regime") or {}).get("zone"),
            },
            self.candles,
            st,
            zones,
            atr,
            entry=entry,
            direction=direction,
            buffer=float(self.config.get("risk", {}).get("structure_buffer_points", 0.00005)),
            min_rr=float(self.config.get("risk", {}).get("min_rr", 1.5)),
        )
        if not brackets:
            logger.warning("no brackets for handover deal=%s dir=%s", deal_id, direction)
            return
        try:
            if self.client:
                await self.client.update_position(
                    str(deal_id), stop_level=brackets["sl"], profit_level=brackets["tp"]
                )
            else:
                self.paper.update_position(
                    str(deal_id), stop_level=brackets["sl"], profit_level=brackets["tp"]
                )
            self._managed_deal_ids.add(str(deal_id))
            # Refresh positions snapshot immediately so dashboard shows SL/TP
            if self.using_paper:
                await self._refresh_state_positions(self.paper.get_positions())
            state.message = (
                f"HANDOVER — pārņemts deal {deal_id}. "
                f"SL {brackets['sl']} TP {brackets['tp']} (R:R {brackets['rr']})."
            )
            self._log_trade(
                {
                    "event": "handover_brackets",
                    "dealId": deal_id,
                    "brackets": brackets,
                }
            )
            logger.info(
                "handover brackets attached deal=%s SL=%s TP=%s",
                deal_id,
                brackets["sl"],
                brackets["tp"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("attach brackets failed: %s", exc)

    async def _loop(self) -> None:
        interval = float(self.config.get("engine", {}).get("loop_seconds", 5))
        tick = 0
        while not self._stop.is_set():
            try:
                await self._tick(tick)
            except Exception as exc:  # noqa: BLE001
                logger.exception("tick error")
                state.error = str(exc)
            tick += 1
            await self._broadcast()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self, tick: int) -> None:
        # Refresh candles
        if self.client and tick % 2 == 0:
            try:
                raw = await self.client.get_prices(state.epic, "MINUTE", 200)
                parsed = parse_capital_prices(raw)
                if len(parsed) >= 40:
                    self.candles = parsed
                await self._refresh_account()
                positions = await self.client.get_positions()
                event = self.handover.observe(positions)
                if event:
                    self._pending_handover = event
                await self._refresh_state_positions(positions)
            except Exception as exc:  # noqa: BLE001
                logger.warning("live refresh: %s", exc)
                state.error = str(exc)
        else:
            # Paper: advance synthetic market slightly
            if self.using_paper:
                self._advance_paper_market()
            positions = self.paper.get_positions() if self.using_paper else state.open_positions
            if self.using_paper:
                event = self.handover.observe(positions)
                if event:
                    self._pending_handover = event
                await self._refresh_state_positions(positions)
                acc = self.paper.accounts()["accounts"][0]["balance"]
                state.account_balance = acc["balance"]
                state.account_available = acc["available"]
                state.account_pnl = acc["profitLoss"]

        bid = ask = None
        if self.using_paper:
            bid, ask = self.paper.last_bid, self.paper.last_ask
            state.bid, state.ask = bid, ask
            state.last_price = (bid + ask) / 2
            state.spread = ask - bid

        if self._pending_handover:
            event = self._pending_handover
            self._pending_handover = None
            await self._attach_brackets_to_handover(event)

        peers = self._peer_bias()
        analysis = self.fusion.analyze(
            self.candles, peers=peers, news_risk=state.news_risk, bid=bid, ask=ask
        )
        can_trade = self.handover.active or not self.handover.enabled
        decision = self.brain.decide(analysis, can_trade=can_trade)

        state.regime = analysis.get("regime", {}).get("regime", "UNKNOWN")
        state.structure = analysis.get("structure", {}).get("bias", "UNKNOWN")
        state.signal = decision["signal"]
        state.confluence = float(decision.get("confluence") or 0)
        state.zones = analysis.get("zones", [])
        state.indicators = analysis.get("indicators", {})
        state.peers = peers
        state.session = analysis.get("session", "off")
        state.candles = analysis.get("candles_tail", [])
        state.last_decision = decision
        state.decisions = (state.decisions + [decision])[-50:]
        if analysis.get("price"):
            state.last_price = analysis["price"]

        if decision["signal"] in ("BUY", "SELL") and can_trade:
            await self._maybe_execute(decision)

        state.stats = self._compute_stats()
        if self.handover.waiting:
            state.mode = "waiting_handover"
        elif self.handover.active:
            state.mode = "paper" if self.using_paper else "active"

    def _advance_paper_market(self) -> None:
        """Append a new synthetic bar so paper mode evolves."""
        import random

        last = self.candles[-1]
        rng = random.Random(int(last.close * 1e6) % 10_000)
        drift = rng.uniform(-0.00012, 0.00012)
        # Bias toward structure continuation occasionally
        if state.signal == "BUY":
            drift += 0.00003
        elif state.signal == "SELL":
            drift -= 0.00003
        o = last.close
        c = round(o + drift, 5)
        h = round(max(o, c) + rng.uniform(0, 0.0001), 5)
        l = round(min(o, c) - rng.uniform(0, 0.0001), 5)
        from shadow.analysis.ohlc import Candle

        self.candles.append(
            Candle(time=datetime.now(timezone.utc).isoformat(), open=o, high=h, low=l, close=c, volume=100)
        )
        self.candles = self.candles[-400:]
        self.paper.set_quote(c)

    async def _maybe_execute(self, decision: dict[str, Any]) -> None:
        brackets = decision.get("brackets")
        if not brackets:
            return
        # One entry per candle timestamp
        bar_t = self.candles[-1].time
        if bar_t == self._last_signal_bar:
            return
        # Avoid stacking if already in same direction
        positions = state.open_positions
        direction = decision["signal"]
        for item in positions:
            p = item.get("position") or item
            if p.get("direction") == direction and (p.get("epic") == state.epic or not p.get("epic")):
                return

        size = float(self.config.get("risk", {}).get("default_size", 1000))
        try:
            if self.client:
                resp = await self.client.open_position(
                    state.epic,
                    direction,
                    size,
                    stop_level=brackets["sl"],
                    profit_level=brackets["tp"],
                )
                ref = resp.get("dealReference")
                if ref:
                    conf = await self.client.confirm(ref)
                    resp["confirm"] = conf
            else:
                resp = self.paper.open_position(
                    state.epic,
                    direction,
                    size,
                    stop_level=brackets["sl"],
                    profit_level=brackets["tp"],
                )
            self._last_signal_bar = bar_t
            trade = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "signal": direction,
                "brackets": brackets,
                "resp": resp,
                "confluence": decision.get("confluence"),
                "regime": decision.get("regime"),
            }
            state.trades = (state.trades + [trade])[-100:]
            self._log_trade(trade)
            state.message = f"Atvērts {direction} @ {brackets['entry']} SL {brackets['sl']} TP {brackets['tp']}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("execute failed: %s", exc)
            state.error = f"Order failed: {exc}"

    async def _refresh_account(self) -> None:
        if not self.client:
            return
        data = await self.client.get_accounts()
        accounts = data.get("accounts") or []
        if not accounts:
            return
        preferred = next((a for a in accounts if a.get("preferred")), accounts[0])
        bal = preferred.get("balance") or {}
        state.account_balance = bal.get("balance")
        state.account_available = bal.get("available")
        state.account_pnl = bal.get("profitLoss")

    async def _refresh_state_positions(self, positions: list[dict[str, Any]]) -> None:
        state.open_positions = positions

    def _peer_bias(self) -> dict[str, Any]:
        # Lightweight heuristic without external calls in paper mode
        if len(self.candles) < 20:
            return {"bias": "neutral"}
        chg = self.candles[-1].close - self.candles[-20].close
        if chg > 0:
            return {"bias": "risk_on", "note": "short-term positive"}
        if chg < 0:
            return {"bias": "risk_off", "note": "short-term negative"}
        return {"bias": "neutral"}

    def _compute_stats(self) -> dict[str, Any]:
        closed = self.paper.closed if self.using_paper else []
        wins = [t for t in closed if t.get("pnl", 0) > 0]
        losses = [t for t in closed if t.get("pnl", 0) <= 0]
        return {
            "open": len(state.open_positions),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "winrate": round(len(wins) / max(len(closed), 1) * 100, 1),
            "net_pnl": round(sum(t.get("pnl", 0) for t in closed), 2),
            "signals": len(state.decisions),
            "mode": state.mode,
        }

    def _log_trade(self, trade: dict[str, Any]) -> None:
        try:
            with open(self.trades_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("trade log: %s", exc)

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    async def _broadcast(self) -> None:
        payload = state.model_dump()
        dead: list[asyncio.Queue] = []
        for q in self.subscribers:
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    def snapshot(self) -> dict[str, Any]:
        return state.model_dump()