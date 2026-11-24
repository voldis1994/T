"""Market regimes / popular 1m scenarios."""

from __future__ import annotations

from typing import Any, Literal

from .ohlc import Candle
from .structure import StructureState
from .zones import Zone

Regime = Literal[
    "TREND",
    "RANGE",
    "BREAKOUT",
    "RETEST",
    "REVERSAL",
    "FAKEOUT",
    "COMPRESSION",
    "UNKNOWN",
]


def _range_bounds(candles: list[Candle], look: int = 40) -> tuple[float, float]:
    window = candles[-look:]
    return max(c.high for c in window), min(c.low for c in window)


def detect_regime(
    candles: list[Candle],
    structure: StructureState,
    zones: list[Zone],
    atr: float,
    confirmations: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(candles) < 30 or atr <= 0:
        return {"regime": "UNKNOWN", "side": None, "score": 0.0, "reason": "insufficient_data"}

    price = candles[-1].close
    hi, lo = _range_bounds(candles, 40)
    range_width = hi - lo
    recent = candles[-12:]
    recent_range = max(c.high for c in recent) - min(c.low for c in recent)

    # Compression / squeeze
    if recent_range < atr * 1.2:
        return {
            "regime": "COMPRESSION",
            "side": None,
            "score": 0.4,
            "reason": "volatility_squeeze",
            "range_high": hi,
            "range_low": lo,
        }

    # Range
    if structure.bias == "RANGE" and range_width < atr * 8:
        side = None
        if price >= hi - atr * 0.4:
            side = "SELL"
        elif price <= lo + atr * 0.4:
            side = "BUY"
        return {
            "regime": "RANGE",
            "side": side,
            "score": 0.55 if side else 0.35,
            "reason": "oscillating_between_bounds",
            "range_high": hi,
            "range_low": lo,
        }

    # Fakeout: wick beyond bound, close back inside
    c = candles[-1]
    if c.high > hi and c.close < hi - atr * 0.1:
        return {
            "regime": "FAKEOUT",
            "side": "SELL",
            "score": 0.7,
            "reason": "liquidity_sweep_high",
            "range_high": hi,
            "range_low": lo,
            "sweep": c.high,
        }
    if c.low < lo and c.close > lo + atr * 0.1:
        return {
            "regime": "FAKEOUT",
            "side": "BUY",
            "score": 0.7,
            "reason": "liquidity_sweep_low",
            "range_high": hi,
            "range_low": lo,
            "sweep": c.low,
        }

    # Breakout
    if c.close > hi + atr * 0.15 and c.body > atr * 0.8:
        return {
            "regime": "BREAKOUT",
            "side": "BUY",
            "score": 0.65,
            "reason": "impulsive_break_high",
            "level": hi,
        }
    if c.close < lo - atr * 0.15 and c.body > atr * 0.8:
        return {
            "regime": "BREAKOUT",
            "side": "SELL",
            "score": 0.65,
            "reason": "impulsive_break_low",
            "level": lo,
        }

    # Retest of broken level / zone
    for z in zones:
        if not z.active or z.touches < 1:
            continue
        if z.contains(price, buffer=atr * 0.25):
            dirs = [x["direction"] for x in confirmations]
            if z.kind == "demand" and ("BUY" in dirs or structure.bias == "BULL"):
                return {
                    "regime": "RETEST",
                    "side": "BUY",
                    "score": 0.75 * z.quality,
                    "reason": "demand_zone_retest",
                    "zone": z.to_dict(),
                }
            if z.kind == "supply" and ("SELL" in dirs or structure.bias == "BEAR"):
                return {
                    "regime": "RETEST",
                    "side": "SELL",
                    "score": 0.75 * z.quality,
                    "reason": "supply_zone_retest",
                    "zone": z.to_dict(),
                }

    # Reversal + CHOCH
    if structure.last_choch == "bullish":
        return {
            "regime": "REVERSAL",
            "side": "BUY",
            "score": 0.72,
            "reason": "choch_bullish",
        }
    if structure.last_choch == "bearish":
        return {
            "regime": "REVERSAL",
            "side": "SELL",
            "score": 0.72,
            "reason": "choch_bearish",
        }

    # Trend continuation / pullback
    if structure.bias == "BULL":
        near_hl = structure.last_hl and abs(price - structure.last_hl) < atr * 1.2
        in_demand = any(z.kind == "demand" and z.contains(price, atr * 0.3) for z in zones)
        if near_hl or in_demand or any(x["direction"] == "BUY" for x in confirmations):
            return {
                "regime": "TREND",
                "side": "BUY",
                "score": 0.68,
                "reason": "bull_pullback",
                "structure_level": structure.last_hl,
            }
        return {"regime": "TREND", "side": None, "score": 0.4, "reason": "bull_wait_pullback"}

    if structure.bias == "BEAR":
        near_lh = structure.last_lh and abs(price - structure.last_lh) < atr * 1.2
        in_supply = any(z.kind == "supply" and z.contains(price, atr * 0.3) for z in zones)
        if near_lh or in_supply or any(x["direction"] == "SELL" for x in confirmations):
            return {
                "regime": "TREND",
                "side": "SELL",
                "score": 0.68,
                "reason": "bear_pullback",
                "structure_level": structure.last_lh,
            }
        return {"regime": "TREND", "side": None, "score": 0.4, "reason": "bear_wait_pullback"}

    return {"regime": "UNKNOWN", "side": None, "score": 0.2, "reason": "no_clear_setup"}