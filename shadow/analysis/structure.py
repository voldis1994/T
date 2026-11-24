"""Market structure: swings, HH/HL/LH/LL, BOS, CHOCH."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .ohlc import Candle

SwingType = Literal["high", "low"]


@dataclass
class Swing:
    index: int
    price: float
    kind: SwingType
    time: str = ""


@dataclass
class StructureState:
    bias: str = "RANGE"  # BULL | BEAR | RANGE
    swings: list[Swing] = field(default_factory=list)
    last_bos: str | None = None  # bullish | bearish
    last_choch: str | None = None
    last_hh: float | None = None
    last_hl: float | None = None
    last_lh: float | None = None
    last_ll: float | None = None
    labels: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bias": self.bias,
            "last_bos": self.last_bos,
            "last_choch": self.last_choch,
            "last_hh": self.last_hh,
            "last_hl": self.last_hl,
            "last_lh": self.last_lh,
            "last_ll": self.last_ll,
            "swings": [
                {"i": s.index, "price": s.price, "kind": s.kind, "t": s.time}
                for s in self.swings[-12:]
            ],
            "labels": self.labels[-20:],
        }


def find_swings(candles: list[Candle], lookback: int = 3) -> list[Swing]:
    swings: list[Swing] = []
    n = len(candles)
    if n < lookback * 2 + 1:
        return swings
    for i in range(lookback, n - lookback):
        window_h = [candles[j].high for j in range(i - lookback, i + lookback + 1)]
        window_l = [candles[j].low for j in range(i - lookback, i + lookback + 1)]
        if candles[i].high == max(window_h) and window_h.count(candles[i].high) == 1:
            swings.append(Swing(i, candles[i].high, "high", candles[i].time))
        if candles[i].low == min(window_l) and window_l.count(candles[i].low) == 1:
            swings.append(Swing(i, candles[i].low, "low", candles[i].time))
    # chronological already; remove consecutive same-kind keeping extreme
    cleaned: list[Swing] = []
    for s in swings:
        if cleaned and cleaned[-1].kind == s.kind:
            if s.kind == "high" and s.price >= cleaned[-1].price:
                cleaned[-1] = s
            elif s.kind == "low" and s.price <= cleaned[-1].price:
                cleaned[-1] = s
        else:
            cleaned.append(s)
    return cleaned


def analyze_structure(candles: list[Candle], lookback: int = 3) -> StructureState:
    state = StructureState()
    swings = find_swings(candles, lookback)
    state.swings = swings
    if len(swings) < 4:
        return state

    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    labels: list[dict[str, Any]] = []
    for i in range(1, len(highs)):
        tag = "HH" if highs[i].price > highs[i - 1].price else "LH"
        labels.append({"kind": tag, "price": highs[i].price, "i": highs[i].index})
        if tag == "HH":
            state.last_hh = highs[i].price
        else:
            state.last_lh = highs[i].price
    for i in range(1, len(lows)):
        tag = "HL" if lows[i].price > lows[i - 1].price else "LL"
        labels.append({"kind": tag, "price": lows[i].price, "i": lows[i].index})
        if tag == "HL":
            state.last_hl = lows[i].price
        else:
            state.last_ll = lows[i].price
    state.labels = sorted(labels, key=lambda x: x["i"])

    # Bias from last 3 labels
    recent = [x["kind"] for x in state.labels[-6:]]
    bull = recent.count("HH") + recent.count("HL")
    bear = recent.count("LH") + recent.count("LL")
    if bull >= bear + 2:
        state.bias = "BULL"
    elif bear >= bull + 2:
        state.bias = "BEAR"
    else:
        state.bias = "RANGE"

    # BOS / CHOCH vs last opposite swing
    price = candles[-1].close
    if highs and lows:
        last_high = highs[-1].price
        last_low = lows[-1].price
        prev_high = highs[-2].price if len(highs) > 1 else last_high
        prev_low = lows[-2].price if len(lows) > 1 else last_low

        if state.bias == "BULL" and price < prev_low:
            state.last_choch = "bearish"
            state.bias = "BEAR"
        elif state.bias == "BEAR" and price > prev_high:
            state.last_choch = "bullish"
            state.bias = "BULL"
        elif price > last_high and state.bias != "BEAR":
            state.last_bos = "bullish"
        elif price < last_low and state.bias != "BULL":
            state.last_bos = "bearish"

        # Fresh BOS on close beyond prior swing
        if len(candles) >= 2:
            prev_close = candles[-2].close
            if prev_close <= prev_high < price:
                state.last_bos = "bullish"
            if prev_close >= prev_low > price:
                state.last_bos = "bearish"

    return state