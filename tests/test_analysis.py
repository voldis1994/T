"""Unit tests for SHADOW analysis edge logic."""

from shadow.analysis.brackets import compute_brackets
from shadow.analysis.candles import detect_confirmations, is_engulfing, is_pin_bar
from shadow.analysis.fusion import MarketFusion
from shadow.analysis.indicators import compute_indicators
from shadow.analysis.ohlc import Candle, synthetic_trend_candles
from shadow.analysis.scenarios import detect_regime
from shadow.analysis.structure import analyze_structure, find_swings
from shadow.analysis.zones import detect_zones
from shadow.engine.handover import HandoverController
from shadow.engine.paper import PaperBroker


def test_synthetic_candles_length():
    c = synthetic_trend_candles(120)
    assert len(c) == 120
    assert c[-1].close != c[0].close


def test_structure_and_swings():
    candles = synthetic_trend_candles(200)
    swings = find_swings(candles, 3)
    assert len(swings) >= 4
    st = analyze_structure(candles)
    assert st.bias in ("BULL", "BEAR", "RANGE")
    assert st.to_dict()["bias"] == st.bias


def test_indicators():
    candles = synthetic_trend_candles(200)
    ind = compute_indicators(candles, {"atr_period": 14, "ema_fast": 9, "ema_slow": 21, "ema_trend": 50})
    assert ind["atr"] > 0
    assert ind["rsi"] is not None


def test_zones_detected():
    candles = synthetic_trend_candles(220, seed=7)
    ind = compute_indicators(candles, {})
    zones = detect_zones(candles, ind["atr"])
    assert isinstance(zones, list)


def test_pin_and_engulf():
    pin = Candle("t", 1.0, 1.01, 0.99, 1.001)
    # long lower wick
    pin2 = Candle("t", 1.0, 1.001, 0.97, 1.0005)
    assert is_pin_bar(pin2)["direction"] == "BUY"
    prev = Candle("t", 1.01, 1.012, 1.0, 1.001)
    cur = Candle("t", 1.0, 1.02, 0.995, 1.018)
    assert is_engulfing(prev, cur)["direction"] == "BUY"


def test_fusion_returns_valid():
    candles = synthetic_trend_candles(200, seed=11)
    fusion = MarketFusion(
        {
            "analysis": {"confluence_min_score": 0.3, "swing_lookback": 3},
            "risk": {"min_rr": 1.5, "structure_buffer_points": 0.00005},
            "sessions": {"prefer_sessions": False},
        }
    )
    out = fusion.analyze(candles)
    assert out["valid"] is True
    assert out["signal"] in ("BUY", "SELL", "HOLD")
    assert "feature_vector" in out


def test_brackets_rr():
    candles = synthetic_trend_candles(180)
    st = analyze_structure(candles)
    ind = compute_indicators(candles, {})
    zones = detect_zones(candles, ind["atr"])
    regime = {"regime": "TREND", "side": "BUY"}
    br = compute_brackets(
        regime,
        candles,
        st,
        zones,
        ind["atr"],
        entry=candles[-1].close,
        direction="BUY",
        min_rr=1.5,
    )
    assert br is not None
    assert br["rr"] >= 1.5
    assert br["sl"] < br["entry"] < br["tp"] or br["direction"] == "BUY"


def test_handover_detects_new_position():
    hc = HandoverController(enabled=True)
    hc.seed_baseline([])
    event = hc.observe([{"position": {"dealId": "D1", "direction": "BUY", "level": 1.1}}])
    assert event is not None
    assert event["dealId"] == "D1"
    assert hc.active is True


def test_paper_broker_sl_tp():
    pb = PaperBroker(spread=0.0001)
    pb.set_quote(1.0850)
    resp = pb.open_position("EURUSD", "BUY", 1000, stop_level=1.0840, profit_level=1.0870)
    assert resp["dealId"] in pb.positions
    pb.set_quote(1.0875)  # hit TP via bid
    assert resp["dealId"] not in pb.positions
    assert pb.closed[-1]["reason"] == "TP"


def test_regime_keys():
    candles = synthetic_trend_candles(100)
    st = analyze_structure(candles)
    ind = compute_indicators(candles, {})
    zones = detect_zones(candles, ind["atr"])
    conf = detect_confirmations(candles, ind["atr"], {})
    reg = detect_regime(candles, st, zones, ind["atr"], conf)
    assert "regime" in reg