"""Confirmation candles: pin bar, engulfing, impulse, rejection series."""

from __future__ import annotations

from typing import Any

from .ohlc import Candle


def is_pin_bar(c: Candle, *, wick_ratio: float = 2.0, bullish_bias: bool | None = None) -> dict | None:
    body = max(c.body, 1e-12)
    if c.lower_wick >= wick_ratio * body and c.lower_wick > c.upper_wick:
        if bullish_bias is False:
            return None
        return {"pattern": "pin_bar", "direction": "BUY", "strength": c.lower_wick / c.range}
    if c.upper_wick >= wick_ratio * body and c.upper_wick > c.lower_wick:
        if bullish_bias is True:
            return None
        return {"pattern": "pin_bar", "direction": "SELL", "strength": c.upper_wick / c.range}
    return None


def is_engulfing(prev: Candle, cur: Candle, *, min_ratio: float = 1.0) -> dict | None:
    if cur.body < prev.body * min_ratio:
        return None
    if cur.bullish and not prev.bullish and cur.close >= prev.open and cur.open <= prev.close:
        return {"pattern": "engulfing", "direction": "BUY", "strength": cur.body / max(prev.body, 1e-12)}
    if not cur.bullish and prev.bullish and cur.close <= prev.open and cur.open >= prev.close:
        return {"pattern": "engulfing", "direction": "SELL", "strength": cur.body / max(prev.body, 1e-12)}
    return None


def is_impulse(c: Candle, atr: float, mult: float = 1.4) -> dict | None:
    if atr <= 0:
        return None
    if c.body >= atr * mult and c.body / c.range >= 0.6:
        return {
            "pattern": "impulse",
            "direction": "BUY" if c.bullish else "SELL",
            "strength": c.body / atr,
        }
    return None


def detect_confirmations(
    candles: list[Candle],
    atr: float,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(candles) < 3:
        return []
    wick_ratio = float(cfg.get("pin_wick_ratio", 2.0))
    engulf_ratio = float(cfg.get("engulf_min_body_ratio", 1.0))
    impulse_mult = float(cfg.get("impulse_body_atr_mult", 1.4))

    found: list[dict[str, Any]] = []
    cur = candles[-1]
    prev = candles[-2]

    for fn_result in (
        is_pin_bar(cur, wick_ratio=wick_ratio),
        is_engulfing(prev, cur, min_ratio=engulf_ratio),
        is_impulse(cur, atr, impulse_mult),
    ):
        if fn_result:
            found.append(fn_result)

    # Series of rejection wicks at same level
    window = candles[-5:]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    upper_rej = sum(1 for c in window if c.upper_wick > c.body and abs(c.high - hi) < atr * 0.3)
    lower_rej = sum(1 for c in window if c.lower_wick > c.body and abs(c.low - lo) < atr * 0.3)
    if upper_rej >= 2:
        found.append({"pattern": "rejection_series", "direction": "SELL", "strength": upper_rej / 5})
    if lower_rej >= 2:
        found.append({"pattern": "rejection_series", "direction": "BUY", "strength": lower_rej / 5})

    return found