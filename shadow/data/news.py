"""News risk gate — manual override + optional calendar hook.

High-impact windows should set state.news_risk to 'high' or 'blocked'
via POST /api/news or a future calendar poller.
"""

from __future__ import annotations

from datetime import datetime, timezone


def session_news_hint(now: datetime | None = None) -> str:
    """Conservative hint: Friday late / Sunday open often noisy — advisory only."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() == 4 and now.hour >= 20:
        return "high"
    if now.weekday() == 6 and now.hour < 23:
        return "high"
    return "ok"