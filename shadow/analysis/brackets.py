"""SL / TP distances for every 1m market regime (structural, not fixed pips)."""

from __future__ import annotations

from typing import Any

from .ohlc import Candle
from .structure import StructureState
from .zones import Zone


def compute_brackets(
    regime: dict[str, Any],
    candles: list[Candle],
    structure: StructureState,
    zones: list[Zone],
    atr: float,
    *,
    entry: float,
    direction: str,
    buffer: float = 0.00005,
    min_rr: float = 1.5,
) -> dict[str, Any] | None:
    if atr <= 0 or not direction:
        return None

    side = direction.upper()
    regime_name = regime.get("regime", "UNKNOWN")
    hi = regime.get("range_high")
    lo = regime.get("range_low")

    sl: float | None = None
    tp: float | None = None
    logic = ""

    if regime_name == "TREND":
        if side == "BUY":
            invalidation = structure.last_hl or min(c.low for c in candles[-8:])
            sl = invalidation - buffer
            tp1 = structure.last_hh or entry + atr * 2
            tp = max(tp1, entry + atr * 2)
            logic = "SL behind last HL; TP at prior HH / extension"
        else:
            invalidation = structure.last_lh or max(c.high for c in candles[-8:])
            sl = invalidation + buffer
            tp1 = structure.last_ll or entry - atr * 2
            tp = min(tp1, entry - atr * 2)
            logic = "SL behind last LH; TP at prior LL / extension"

    elif regime_name == "RANGE":
        if hi is None or lo is None:
            return None
        if side == "BUY":
            sl = lo - buffer - atr * 0.15
            tp = lo + (hi - lo) * 0.75
            logic = "SL outside range low; TP ~75% toward range high"
        else:
            sl = hi + buffer + atr * 0.15
            tp = hi - (hi - lo) * 0.75
            logic = "SL outside range high; TP ~75% toward range low"

    elif regime_name == "BREAKOUT":
        level = float(regime.get("level") or (hi if side == "BUY" else lo) or entry)
        brk = candles[-1]
        if side == "BUY":
            sl = min(level, brk.low) - buffer
            tp = entry + (entry - sl) * 2.2
            logic = "SL below breakout candle/level; measured move TP"
        else:
            sl = max(level, brk.high) + buffer
            tp = entry - (sl - entry) * 2.2
            logic = "SL above breakout candle/level; measured move TP"

    elif regime_name == "RETEST":
        z = regime.get("zone") or {}
        if side == "BUY":
            sl = float(z.get("bottom", entry - atr)) - buffer
            next_supply = next((x for x in zones if x.kind == "supply" and x.bottom > entry), None)
            tp = next_supply.bottom if next_supply else entry + atr * 2.5
            logic = "SL behind demand zone; TP next supply / 2.5ATR"
        else:
            sl = float(z.get("top", entry + atr)) + buffer
            next_demand = next((x for x in zones if x.kind == "demand" and x.top < entry), None)
            tp = next_demand.top if next_demand else entry - atr * 2.5
            logic = "SL behind supply zone; TP next demand / 2.5ATR"

    elif regime_name == "REVERSAL":
        if side == "BUY":
            sweep = min(c.low for c in candles[-6:])
            sl = sweep - buffer
            tp = entry + (entry - sl) * 2.0
            logic = "SL behind sweep low; TP 2R structural"
        else:
            sweep = max(c.high for c in candles[-6:])
            sl = sweep + buffer
            tp = entry - (sl - entry) * 2.0
            logic = "SL behind sweep high; TP 2R structural"

    elif regime_name == "FAKEOUT":
        sweep = float(regime.get("sweep") or 0)
        if side == "BUY":
            sl = (sweep or min(c.low for c in candles[-5:])) - buffer
            mid = ((hi or entry + atr) + (lo or entry - atr)) / 2
            tp = mid if mid > entry else entry + atr * 1.8
            logic = "SL below fakeout low; TP range mid / opposite"
        else:
            sl = (sweep or max(c.high for c in candles[-5:])) + buffer
            mid = ((hi or entry + atr) + (lo or entry - atr)) / 2
            tp = mid if mid < entry else entry - atr * 1.8
            logic = "SL above fakeout high; TP range mid / opposite"

    else:
        # Fallback structural
        if side == "BUY":
            sl = min(c.low for c in candles[-8:]) - buffer
            tp = entry + max(atr * 2, (entry - sl) * min_rr)
        else:
            sl = max(c.high for c in candles[-8:]) + buffer
            tp = entry - max(atr * 2, (sl - entry) * min_rr)
        logic = "fallback structural swing"

    if sl is None or tp is None:
        return None

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk < atr * 0.15:
        # Too tight — widen behind structure by ATR fraction
        if side == "BUY":
            sl = entry - atr * 0.6
        else:
            sl = entry + atr * 0.6
        risk = abs(entry - sl)
        reward = abs(tp - entry)

    rr = reward / risk if risk > 0 else 0.0
    if rr < min_rr:
        # Stretch TP to meet min R:R if structure allows
        if side == "BUY":
            tp = entry + risk * min_rr
        else:
            tp = entry - risk * min_rr
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0.0

    return {
        "entry": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "risk": round(risk, 5),
        "reward": round(reward, 5),
        "rr": round(rr, 2),
        "logic": logic,
        "regime": regime_name,
        "direction": side,
    }