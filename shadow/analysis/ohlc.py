"""OHLC helpers — normalize Capital.com price bars into mid candles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 1e-12)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close >= self.open

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": self.time,
            "o": self.open,
            "h": self.high,
            "l": self.low,
            "c": self.close,
            "v": self.volume,
        }


def _mid(bid: float | None, ask: float | None) -> float | None:
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    return (bid + ask) / 2.0


def parse_capital_prices(raw: list[dict[str, Any]]) -> list[Candle]:
    candles: list[Candle] = []
    for bar in raw:
        o = _mid(
            (bar.get("openPrice") or {}).get("bid"),
            (bar.get("openPrice") or {}).get("ask"),
        )
        h = _mid(
            (bar.get("highPrice") or {}).get("bid"),
            (bar.get("highPrice") or {}).get("ask"),
        )
        l = _mid(
            (bar.get("lowPrice") or {}).get("bid"),
            (bar.get("lowPrice") or {}).get("ask"),
        )
        c = _mid(
            (bar.get("closePrice") or {}).get("bid"),
            (bar.get("closePrice") or {}).get("ask"),
        )
        if None in (o, h, l, c):
            continue
        candles.append(
            Candle(
                time=bar.get("snapshotTimeUTC") or bar.get("snapshotTime") or "",
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(bar.get("lastTradedVolume") or 0),
            )
        )
    return candles


def synthetic_trend_candles(
    n: int = 200,
    start: float = 1.0850,
    seed: int = 42,
) -> list[Candle]:
    """Deterministic synthetic EURUSD-like series for paper mode / tests."""
    import math
    import random

    rng = random.Random(seed)
    candles: list[Candle] = []
    price = start
    for i in range(n):
        # Mild uptrend with pullbacks + noise
        cycle = math.sin(i / 17) * 0.00035
        impulse = 0.00025 if (i % 40) in range(30, 36) else 0.0
        if (i % 55) in range(45, 52):
            impulse = -0.00028
        drift = 0.00002 + cycle + impulse
        noise = rng.uniform(-0.00008, 0.00008)
        o = price
        c = price + drift + noise
        h = max(o, c) + rng.uniform(0, 0.00012)
        l = min(o, c) - rng.uniform(0, 0.00012)
        # Occasional pin / rejection
        if i % 37 == 0:
            l = min(l, c - 0.00035)
        if i % 41 == 0:
            h = max(h, c + 0.00035)
        candles.append(
            Candle(
                time=f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00",
                open=round(o, 5),
                high=round(h, 5),
                low=round(l, 5),
                close=round(c, 5),
                volume=float(rng.randint(50, 400)),
            )
        )
        price = c
    return candles