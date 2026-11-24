"""Paper broker — realistic bid/ask, spread, slippage simulation."""

from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaperPosition:
    deal_id: str
    epic: str
    direction: str
    size: float
    level: float
    stop_level: float | None = None
    profit_level: float | None = None
    created_ts: float = field(default_factory=time.time)
    upl: float = 0.0

    def to_api_shape(self) -> dict[str, Any]:
        return {
            "position": {
                "dealId": self.deal_id,
                "epic": self.epic,
                "direction": self.direction,
                "size": self.size,
                "level": self.level,
                "upl": self.upl,
                "stopLevel": self.stop_level,
                "profitLevel": self.profit_level,
                "createdDateUTC": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.created_ts)),
            },
            "market": {"epic": self.epic, "bid": self.level, "offer": self.level},
        }


class PaperBroker:
    def __init__(self, balance: float = 10_000.0, spread: float = 0.00008) -> None:
        self.balance = balance
        self.deposit = balance
        self.spread = spread
        self.positions: dict[str, PaperPosition] = {}
        self.closed: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self.last_bid = 1.0850
        self.last_ask = 1.0850 + spread

    def set_quote(self, mid: float) -> None:
        half = self.spread / 2
        self.last_bid = mid - half
        self.last_ask = mid + half
        to_close: list[tuple[str, float, str]] = []
        for p in list(self.positions.values()):
            px = self.last_bid if p.direction == "BUY" else self.last_ask
            mult = 1 if p.direction == "BUY" else -1
            p.upl = (px - p.level) * mult * p.size
            if p.stop_level is not None:
                if p.direction == "BUY" and self.last_bid <= p.stop_level:
                    to_close.append((p.deal_id, self.last_bid, "SL"))
                    continue
                if p.direction == "SELL" and self.last_ask >= p.stop_level:
                    to_close.append((p.deal_id, self.last_ask, "SL"))
                    continue
            if p.profit_level is not None:
                if p.direction == "BUY" and self.last_bid >= p.profit_level:
                    to_close.append((p.deal_id, self.last_bid, "TP"))
                elif p.direction == "SELL" and self.last_ask <= p.profit_level:
                    to_close.append((p.deal_id, self.last_ask, "TP"))
        for deal_id, px, reason in to_close:
            self._close(deal_id, px, reason)

    def accounts(self) -> dict[str, Any]:
        upl = sum(p.upl for p in self.positions.values())
        return {
            "accounts": [
                {
                    "accountId": "PAPER",
                    "accountName": "SHADOW Paper",
                    "balance": {
                        "balance": self.balance + upl,
                        "deposit": self.deposit,
                        "profitLoss": upl + (self.balance - self.deposit),
                        "available": self.balance + upl,
                    },
                    "currency": "USD",
                }
            ]
        }

    def get_positions(self) -> list[dict[str, Any]]:
        return [p.to_api_shape() for p in self.positions.values()]

    def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        *,
        stop_level: float | None = None,
        profit_level: float | None = None,
    ) -> dict[str, Any]:
        direction = direction.upper()
        # Slippage
        slip = self.spread * 0.25
        level = (self.last_ask + slip) if direction == "BUY" else (self.last_bid - slip)
        deal_id = f"P-{next(self._ids)}-{uuid.uuid4().hex[:6]}"
        pos = PaperPosition(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            size=size,
            level=round(level, 5),
            stop_level=stop_level,
            profit_level=profit_level,
        )
        self.positions[deal_id] = pos
        return {"dealReference": f"o_{deal_id}", "dealId": deal_id}

    def update_position(
        self, deal_id: str, *, stop_level: float | None = None, profit_level: float | None = None
    ) -> dict[str, Any]:
        p = self.positions.get(deal_id)
        if not p:
            raise KeyError(deal_id)
        if stop_level is not None:
            p.stop_level = stop_level
        if profit_level is not None:
            p.profit_level = profit_level
        return {"dealId": deal_id, "status": "UPDATED"}

    def close_position(self, deal_id: str) -> dict[str, Any]:
        px = self.last_bid if self.positions[deal_id].direction == "BUY" else self.last_ask
        return self._close(deal_id, px, "MANUAL")

    def _close(self, deal_id: str, px: float, reason: str) -> dict[str, Any]:
        p = self.positions.pop(deal_id, None)
        if not p:
            return {}
        mult = 1 if p.direction == "BUY" else -1
        pnl = (px - p.level) * mult * p.size
        self.balance += pnl
        rec = {
            "dealId": deal_id,
            "epic": p.epic,
            "direction": p.direction,
            "size": p.size,
            "entry": p.level,
            "exit": px,
            "pnl": round(pnl, 2),
            "reason": reason,
            "ts": time.time(),
        }
        self.closed.append(rec)
        return rec

    def simulate_user_open(self, epic: str, direction: str = "BUY", size: float = 1000) -> dict:
        """Simulate user opening first trade in Capital.com app (handover trigger)."""
        return self.open_position(epic, direction, size)