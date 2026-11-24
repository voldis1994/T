"""Market Fusion — validate data, build feature vector & confluence score."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .brackets import compute_brackets
from .candles import detect_confirmations
from .indicators import compute_indicators
from .ohlc import Candle
from .scenarios import detect_regime
from .structure import analyze_structure
from .zones import detect_zones


def _session_label(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    minutes = now.hour * 60 + now.minute
    london = 7 * 60 <= minutes <= 16 * 60
    ny = 12 * 60 <= minutes <= 21 * 60
    if london and ny:
        return "london_ny_overlap"
    if london:
        return "london"
    if ny:
        return "newyork"
    return "off"


class MarketFusion:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.analysis_cfg = config.get("analysis", {})
        self.risk_cfg = config.get("risk", {})

    def analyze(
        self,
        candles: list[Candle],
        *,
        peers: dict[str, Any] | None = None,
        news_risk: str = "ok",
        bid: float | None = None,
        ask: float | None = None,
    ) -> dict[str, Any]:
        if len(candles) < 40:
            return {
                "valid": False,
                "signal": "HOLD",
                "reason": "insufficient_candles",
                "confluence": 0.0,
            }

        indicators = compute_indicators(candles, self.analysis_cfg)
        atr = float(indicators.get("atr") or 0.0001)
        structure = analyze_structure(
            candles, lookback=int(self.analysis_cfg.get("swing_lookback", 3))
        )
        zones = detect_zones(
            candles,
            atr,
            max_base_bars=int(self.analysis_cfg.get("zone_max_base_bars", 12)),
            impulse_body_atr_mult=float(self.analysis_cfg.get("impulse_body_atr_mult", 1.4)),
            min_quality=float(self.analysis_cfg.get("zone_min_quality", 0.45)),
        )
        confirmations = detect_confirmations(candles, atr, self.analysis_cfg)
        regime = detect_regime(candles, structure, zones, atr, confirmations)

        price = candles[-1].close
        mid = price
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2
            spread = ask - bid
        else:
            spread = self.risk_cfg.get("spread_buffer_points", 0.00002)

        session = _session_label()
        prefer = self.config.get("sessions", {}).get("prefer_sessions", True)
        session_ok = (not prefer) or session != "off"

        # Confluence scoring (edge)
        score = 0.0
        reasons: list[str] = []

        side = regime.get("side")
        if side and regime.get("score", 0) >= 0.5:
            score += 0.25 * float(regime["score"])
            reasons.append(f"regime:{regime['regime']}")

        if confirmations and side:
            matching = [c for c in confirmations if c["direction"] == side]
            if matching:
                score += 0.2
                reasons.append("+".join(c["pattern"] for c in matching[:3]))

        if structure.last_bos and side:
            if (structure.last_bos == "bullish" and side == "BUY") or (
                structure.last_bos == "bearish" and side == "SELL"
            ):
                score += 0.15
                reasons.append(f"bos:{structure.last_bos}")

        if structure.last_choch and side:
            if (structure.last_choch == "bullish" and side == "BUY") or (
                structure.last_choch == "bearish" and side == "SELL"
            ):
                score += 0.15
                reasons.append(f"choch:{structure.last_choch}")

        zone_hit = next(
            (
                z
                for z in zones
                if z.active
                and z.contains(price, atr * 0.35)
                and ((z.kind == "demand" and side == "BUY") or (z.kind == "supply" and side == "SELL"))
            ),
            None,
        )
        if zone_hit:
            score += 0.15 * zone_hit.quality
            reasons.append(f"zone:{zone_hit.kind}:q{zone_hit.quality:.2f}")

        if indicators.get("ema_stack_bull") and side == "BUY":
            score += 0.08
            reasons.append("ema_bull")
        if indicators.get("ema_stack_bear") and side == "SELL":
            score += 0.08
            reasons.append("ema_bear")

        if session_ok:
            score += 0.05
            reasons.append(f"session:{session}")
        else:
            score *= 0.7
            reasons.append("off_session_penalty")

        if news_risk != "ok":
            score *= 0.4
            reasons.append(f"news:{news_risk}")

        # Peer alignment (simple)
        peer_bias = (peers or {}).get("bias")
        if peer_bias == "risk_on" and side == "BUY":
            score += 0.05
            reasons.append("peers_risk_on")
        elif peer_bias == "risk_off" and side == "SELL":
            score += 0.05
            reasons.append("peers_risk_off")

        min_score = float(self.analysis_cfg.get("confluence_min_score", 0.55))
        signal = "HOLD"
        brackets = None
        if side and score >= min_score and session_ok and news_risk == "ok":
            brackets = compute_brackets(
                regime,
                candles,
                structure,
                zones,
                atr,
                entry=mid,
                direction=side,
                buffer=float(self.risk_cfg.get("structure_buffer_points", 0.00005))
                + float(spread or 0),
                min_rr=float(self.risk_cfg.get("min_rr", 1.5)),
            )
            if brackets and brackets["rr"] >= float(self.risk_cfg.get("min_rr", 1.5)):
                signal = side
                reasons.append(f"rr:{brackets['rr']}")
            else:
                signal = "HOLD"
                reasons.append("rr_fail_or_no_bracket")
                score *= 0.5

        feature_vector = {
            "price": mid,
            "atr": atr,
            "rsi": indicators.get("rsi"),
            "structure_bias": structure.bias,
            "regime": regime.get("regime"),
            "regime_score": regime.get("score"),
            "zone_count": len(zones),
            "confirmations": len(confirmations),
            "confluence": round(score, 3),
            "session": session,
            "spread": spread,
        }

        return {
            "valid": True,
            "signal": signal,
            "confluence": round(score, 3),
            "reasons": reasons,
            "regime": regime,
            "structure": structure.to_dict(),
            "zones": [z.to_dict() for z in zones],
            "confirmations": confirmations,
            "indicators": {k: v for k, v in indicators.items() if k != "series"},
            "indicator_series": indicators.get("series", {}),
            "brackets": brackets,
            "session": session,
            "news_risk": news_risk,
            "peers": peers or {},
            "feature_vector": feature_vector,
            "price": mid,
            "spread": spread,
            "candles_tail": [c.to_dict() for c in candles[-120:]],
        }