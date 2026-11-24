"""Handover controller — wait for user's first Capital.com app trade, then take over."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("shadow.handover")


class HandoverController:
    """
    Workflow:
      1. Bot connects / waits in WAITING_HANDOVER
      2. User opens first trade in Capital.com mobile/desktop app
      3. Bot detects new position via GET /positions
      4. Bot attaches structural SL/TP and enters ACTIVE — manages market
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        manage_user_position: bool = True,
        on_handover: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.manage_user_position = manage_user_position
        self.on_handover = on_handover
        self.waiting = enabled
        self.active = not enabled
        self.baseline_deal_ids: set[str] = set()
        self.handover_deal_id: str | None = None
        self.handover_at: str | None = None
        self._baselined = False

    def reset(self) -> None:
        self.waiting = self.enabled
        self.active = not self.enabled
        self.baseline_deal_ids.clear()
        self.handover_deal_id = None
        self.handover_at = None
        self._baselined = False

    def seed_baseline(self, positions: list[dict[str, Any]]) -> None:
        ids = self._ids(positions)
        self.baseline_deal_ids = ids
        self._baselined = True
        logger.info("Handover baseline positions: %s", ids or "{}")

    def observe(self, positions: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not self.enabled or self.active:
            return None
        if not self._baselined:
            self.seed_baseline(positions)
            return None

        ids = self._ids(positions)
        new_ids = ids - self.baseline_deal_ids
        if not new_ids:
            return None

        # First new deal = user opened trade
        deal_id = sorted(new_ids)[0]
        pos = self._find(positions, deal_id)
        self.waiting = False
        self.active = True
        self.handover_deal_id = deal_id
        self.handover_at = datetime.now(timezone.utc).isoformat()
        event = {
            "event": "handover",
            "dealId": deal_id,
            "position": pos,
            "at": self.handover_at,
        }
        logger.info("HANDOVER — user trade detected dealId=%s", deal_id)
        if self.on_handover:
            self.on_handover(event)
        return event

    @staticmethod
    def _ids(positions: list[dict[str, Any]]) -> set[str]:
        out: set[str] = set()
        for item in positions:
            p = item.get("position") or item
            did = p.get("dealId")
            if did:
                out.add(str(did))
        return out

    @staticmethod
    def _find(positions: list[dict[str, Any]], deal_id: str) -> dict[str, Any] | None:
        for item in positions:
            p = item.get("position") or item
            if str(p.get("dealId")) == deal_id:
                return item
        return None