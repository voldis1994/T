"""Core indicators used by SHADOW (EMA, ATR, RSI, ADX-lite)."""

from __future__ import annotations

from typing import Any

import numpy as np

from .ohlc import Candle


def _closes(candles: list[Candle]) -> np.ndarray:
    return np.array([c.close for c in candles], dtype=float)


def ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full_like(values, np.nan, dtype=float)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def atr(candles: list[Candle], period: int = 14) -> np.ndarray:
    n = len(candles)
    tr = np.zeros(n)
    for i in range(n):
        if i == 0:
            tr[i] = candles[i].high - candles[i].low
        else:
            tr[i] = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low - candles[i - 1].close),
            )
    out = np.full(n, np.nan)
    if n < period:
        return out
    out[period - 1] = tr[:period].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
    out = np.full_like(values, np.nan, dtype=float)
    if len(values) < period + 1:
        return out
    delta = np.diff(values)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def compute_indicators(candles: list[Candle], cfg: dict[str, Any]) -> dict[str, Any]:
    if len(candles) < 30:
        return {}
    closes = _closes(candles)
    a = atr(candles, int(cfg.get("atr_period", 14)))
    e_fast = ema(closes, int(cfg.get("ema_fast", 9)))
    e_slow = ema(closes, int(cfg.get("ema_slow", 21)))
    e_trend = ema(closes, int(cfg.get("ema_trend", 50)))
    r = rsi(closes, int(cfg.get("rsi_period", 14)))

    def last(arr: np.ndarray) -> float | None:
        for v in reversed(arr):
            if not np.isnan(v):
                return float(v)
        return None

    atr_v = last(a) or 0.0001
    return {
        "atr": atr_v,
        "ema_fast": last(e_fast),
        "ema_slow": last(e_slow),
        "ema_trend": last(e_trend),
        "rsi": last(r),
        "ema_stack_bull": bool(
            last(e_fast) and last(e_slow) and last(e_trend)
            and last(e_fast) > last(e_slow) > last(e_trend)
        ),
        "ema_stack_bear": bool(
            last(e_fast) and last(e_slow) and last(e_trend)
            and last(e_fast) < last(e_slow) < last(e_trend)
        ),
        "series": {
            "atr": [None if np.isnan(x) else float(x) for x in a[-80:]],
            "ema_fast": [None if np.isnan(x) else float(x) for x in e_fast[-80:]],
            "ema_slow": [None if np.isnan(x) else float(x) for x in e_slow[-80:]],
            "rsi": [None if np.isnan(x) else float(x) for x in r[-80:]],
        },
    }