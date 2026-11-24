"""SHADOW BRAIN — decision gates → BUY / SELL / HOLD."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shadow.analysis.fusion import MarketFusion

logger = logging.getLogger("shadow.brain")


class ShadowBrain:
    def __init__(self, config: dict[str, Any], fusion: MarketFusion | None = None) -> None:
        self.config = config
        self.fusion = fusion or MarketFusion(config)
        self.log_path = Path(config.get("engine", {}).get("decision_log_path", "logs/decisions.jsonl"))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def decide(self, analysis: dict[str, Any], *, can_trade: bool) -> dict[str, Any]:
        gates: list[dict[str, Any]] = []

        def gate(name: str, ok: bool, detail: str = "") -> None:
            gates.append({"gate": name, "ok": ok, "detail": detail})

        gate("data_valid", bool(analysis.get("valid")), analysis.get("reason", "ok"))
        gate("regime_known", analysis.get("regime", {}).get("regime") not in (None, "UNKNOWN", "COMPRESSION"))
        gate("zone_or_confirm", bool(analysis.get("confirmations") or analysis.get("zones")))
        gate("news_ok", analysis.get("news_risk", "ok") == "ok", str(analysis.get("news_risk")))
        gate("session", analysis.get("session") != "off" or not self.config.get("sessions", {}).get("prefer_sessions", True))
        brackets = analysis.get("brackets")
        gate("brackets_rr", bool(brackets and brackets.get("rr", 0) >= self.config.get("risk", {}).get("min_rr", 1.5)))
        gate("handover_active", can_trade, "waiting for user first trade" if not can_trade else "active")

        all_ok = all(g["ok"] for g in gates) and analysis.get("signal") in ("BUY", "SELL")
        signal = analysis.get("signal", "HOLD") if all_ok else "HOLD"

        decision = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "confluence": analysis.get("confluence", 0),
            "regime": analysis.get("regime", {}).get("regime"),
            "structure": analysis.get("structure", {}).get("bias"),
            "reasons": analysis.get("reasons", []),
            "brackets": brackets,
            "gates": gates,
            "can_trade": can_trade,
            "feature_vector": analysis.get("feature_vector", {}),
        }
        self._append(decision)
        return decision

    def _append(self, decision: dict[str, Any]) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(decision, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision log: %s", exc)