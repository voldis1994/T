"""Supply / Demand zones from base → impulse (1m methodology)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .ohlc import Candle

ZoneKind = Literal["supply", "demand"]


@dataclass
class Zone:
    kind: ZoneKind
    top: float
    bottom: float
    created_at: int
    impulse_strength: float
    quality: float
    touches: int = 0
    active: bool = True
    mitigated: bool = False
    base_start: int = 0
    base_end: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def width(self) -> float:
        return self.top - self.bottom

    def contains(self, price: float, buffer: float = 0.0) -> bool:
        return self.bottom - buffer <= price <= self.top + buffer

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "top": round(self.top, 5),
            "bottom": round(self.bottom, 5),
            "mid": round(self.mid, 5),
            "width": round(self.width, 5),
            "quality": round(self.quality, 3),
            "impulse": round(self.impulse_strength, 3),
            "touches": self.touches,
            "active": self.active,
            "mitigated": self.mitigated,
            "created_at": self.created_at,
        }


def _avg_body(candles: list[Candle], start: int, end: int) -> float:
    slice_ = candles[start:end]
    if not slice_:
        return 0.0
    return sum(c.body for c in slice_) / len(slice_)


def _is_base(candles: list[Candle], i: int, atr: float, max_bars: int) -> tuple[int, int] | None:
    """Find a compact base ending at i (inclusive) before an impulse starts after i."""
    if atr <= 0:
        return None
    best: tuple[int, int] | None = None
    for length in range(2, max_bars + 1):
        start = i - length + 1
        if start < 0:
            break
        window = candles[start : i + 1]
        hi = max(c.high for c in window)
        lo = min(c.low for c in window)
        if hi - lo > atr * 1.8:
            continue
        avg_body = sum(c.body for c in window) / len(window)
        if avg_body > atr * 0.55:
            continue
        wick_noise = sum(c.upper_wick + c.lower_wick for c in window) / len(window)
        if wick_noise > atr * 0.9:
            continue
        best = (start, i)
    return best


def detect_zones(
    candles: list[Candle],
    atr: float,
    *,
    max_base_bars: int = 12,
    impulse_body_atr_mult: float = 1.4,
    min_quality: float = 0.45,
) -> list[Zone]:
    zones: list[Zone] = []
    if len(candles) < 20 or atr <= 0:
        return zones

    i = 5
    while i < len(candles) - 3:
        base = _is_base(candles, i, atr, max_base_bars)
        if not base:
            i += 1
            continue
        b0, b1 = base
        # Impulse after base
        impulse_bars = candles[b1 + 1 : b1 + 1 + 4]
        if len(impulse_bars) < 2:
            i += 1
            continue
        move_up = impulse_bars[-1].close - candles[b1].close
        move_down = candles[b1].close - impulse_bars[-1].close
        bodies = sum(c.body for c in impulse_bars) / len(impulse_bars)
        strong = bodies >= atr * impulse_body_atr_mult * 0.7

        kind: ZoneKind | None = None
        if move_up >= atr * impulse_body_atr_mult and strong:
            kind = "demand"
        elif move_down >= atr * impulse_body_atr_mult and strong:
            kind = "supply"

        if kind:
            top = max(c.high for c in candles[b0 : b1 + 1])
            bottom = min(c.low for c in candles[b0 : b1 + 1])
            width = top - bottom
            # Quality: clean base, strong impulse, narrow zone
            width_score = max(0.0, 1.0 - (width / (atr * 2.5)))
            impulse_score = min(1.0, max(move_up, move_down) / (atr * 3))
            wick_score = 1.0 - min(
                1.0,
                sum(c.upper_wick + c.lower_wick for c in candles[b0 : b1 + 1])
                / max(len(candles[b0 : b1 + 1]) * atr, 1e-12),
            )
            quality = 0.4 * impulse_score + 0.35 * width_score + 0.25 * wick_score
            if quality >= min_quality:
                zones.append(
                    Zone(
                        kind=kind,
                        top=top,
                        bottom=bottom,
                        created_at=b1,
                        impulse_strength=max(move_up, move_down) / atr,
                        quality=quality,
                        base_start=b0,
                        base_end=b1,
                        meta={"impulse_end": b1 + len(impulse_bars)},
                    )
                )
            i = b1 + len(impulse_bars)
            continue
        i += 1

    # Touch counting + mitigation
    price = candles[-1].close
    for z in zones:
        for c in candles[z.created_at + 1 :]:
            if z.contains(c.low) or z.contains(c.high) or z.contains(c.close):
                z.touches += 1
        # Mitigated if price closed deep through zone opposite side
        if z.kind == "demand" and price < z.bottom:
            z.mitigated = True
            z.active = False
        if z.kind == "supply" and price > z.top:
            z.mitigated = True
            z.active = False
        # First touch preferred
        if z.touches > 3:
            z.quality *= 0.7

    # Keep freshest active high-quality
    active = [z for z in zones if z.active]
    active.sort(key=lambda z: (z.quality, z.created_at), reverse=True)
    return active[:12]