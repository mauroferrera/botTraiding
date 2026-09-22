"""Tests puros de market_view.py (footprint, liquidity_heatmap, event_bars).

Modulo 100% offline: recibe velas OHLC dicts y devuelve datasets listos para el
frontend. Verifica estructura de salida, invariantes de volumen/delta y el
contrato `source == "synthetic"`.

Run:  python -m pytest tests/test_market_view.py -v
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import market_view  # noqa: E402


def _candles(n=60, seed=0, price=1.0900):
    """Velas OHLC realistas con tick_volume creciente."""
    out = []
    base = price + seed * 0.001
    for i in range(n):
        o = base + i * 0.0001
        c = o + (0.0003 if i % 2 == 0 else -0.0002)
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        out.append({
            "time": 1_700_000_000 + i * 900,
            "open": round(o, 5),
            "high": round(h, 5),
            "low": round(l, 5),
            "close": round(c, 5),
            "volume": float(100 + i),
        })
    return out


def _flat_candle():
    return {
        "time": 123,
        "open": 1.1000,
        "high": 1.1000,
        "low": 1.1000,
        "close": 1.1000,
        "volume": 50.0,
    }


class TestFootprint:
    def test_structure(self):
        out = market_view.footprint(_candles())
        assert out["source"] == "synthetic"
        assert out["mode"] == "footprint"
        assert out["step"] > 0
        bars = out["bars"]
        assert len(bars) == 60
        for b in bars:
            assert {"time", "open", "high", "low", "close", "vol", "delta", "levels"} <= set(b)
            assert b["levels"]

    def test_empty_returns_none(self):
        assert market_view.footprint([]) is None

    def test_max_bars_respected(self):
        out = market_view.footprint(_candles(200), max_bars=50)
        assert len(out["bars"]) == 50

    def test_levels_are_monotonic_within_bar(self):
        for b in market_view.footprint(_candles(), rows=20)["bars"]:
            prices = [lv["price"] for lv in b["levels"]]
            assert prices == sorted(prices)

    def test_delta_consistency(self):
        out = market_view.footprint(_candles(), bid_ratio=0.6)
        for b in out["bars"]:
            ask = sum(lv["ask"] for lv in b["levels"])
            bid = sum(lv["bid"] for lv in b["levels"])
            assert abs(b["delta"] - (ask - bid)) < 0.05

    def test_volume_is_preserved(self):
        out = market_view.footprint(_candles(), bid_ratio=0.6)
        for c, b in zip(_candles(), out["bars"]):
            total = sum(lv["ask"] + lv["bid"] for lv in b["levels"])
            assert abs(total - c["volume"]) <= max(0.6, c["volume"] * 0.03)

    def test_deterministic(self):
        candles = _candles(30)
        a = market_view.footprint(candles)
        b = market_view.footprint(candles)
        assert a["bars"] == b["bars"]

    def test_flat_candle_produces_single_level(self):
        out = market_view.footprint([_flat_candle()])
        assert len(out["bars"][0]["levels"]) == 1
        assert out["bars"][0]["delta"] == 0.0

    def test_buy_bias_favours_ask(self):
        candles = _candles()
        out = market_view.footprint(candles, bid_ratio=0.6)
        bull = [b for c, b in zip(candles, out["bars"]) if c["close"] >= c["open"]]
        assert bull and all(b["delta"] >= 0 for b in bull)


class TestLiquidityHeatmap:
    def test_structure(self):
        out = market_view.liquidity_heatmap(_candles(40))
        assert out["source"] == "synthetic"
        assert out["mode"] == "liquidity_heatmap"
        assert len(out["times"]) == 40
        assert len(out["ladder"]) == 64
        assert isinstance(out["data"], list) and out["data"]

    def test_coordinates_in_range(self):
        out = market_view.liquidity_heatmap(_candles(), levels=48)
        for t, i, v in out["data"]:
            assert 0 <= t < 60
            assert 0 <= i < 48
            assert 0 < v <= 2.5
            assert i % 1 == 0

    def test_empty_returns_none(self):
        assert market_view.liquidity_heatmap([]) is None

    def test_flat_price_does_not_crash(self):
        out = market_view.liquidity_heatmap([_flat_candle()] * 5)
        assert out["ladder"]
        assert len(out["times"]) == 5


class TestEventBars:
    def test_volbar_aggregates_volume(self):
        candles = _candles(50)
        out = market_view.event_bars(candles, bar_type="volbar", param=500)
        assert out["source"] == "synthetic"
        assert out["mode"] == "eventbars"
        assert out["bar_type"] == "volbar"
        total_vol = sum(b["volume"] for b in out["bars"])
        total_in = sum(c["volume"] for c in candles)
        assert abs(total_vol - total_in) <= 1.0
        # cada barra cerrada agruga ~param de volumen (con el overshoot del último tick)
        for b in out["bars"][:-1]:
            assert 500 <= b["volume"] <= 500 + 10

    def test_tickbar_aggregates_ticks(self):
        candles = _candles(30)
        out = market_view.event_bars(candles, bar_type="tickbar", param=16)
        # ~48 ticks por vela * 30 velas / 16 por barra
        assert len(out["bars"]) == pytest.approx(30 * 48 / 16, rel=0.2)

    def test_renko_bricks(self):
        candles = _candles(40)
        out = market_view.event_bars(candles, bar_type="renko", param=1)
        assert out["bar_type"] == "renko"
        step = out["step"]
        assert step > 0
        for b in out["bars"]:
            body = abs(b["close"] - b["open"])
            assert abs(body - step) < step * 1e-6
            assert b["high"] >= b["low"]

    def test_invalid_mode_returns_none(self):
        assert market_view.event_bars(_candles(), bar_type="nope", param=1) is None

    def test_empty_returns_none(self):
        assert market_view.event_bars([]) is None

    def test_volbar_at_least_one_bar(self):
        out = market_view.event_bars(_candles(5), bar_type="volbar", param=10000)
        assert out["bars"]


class TestHelpers:
    def test_price_step_scale(self):
        assert market_view._price_step(0.5) == 0.00001
        assert market_view._price_step(50.0) == 0.0001
        assert market_view._price_step(500.0) == 0.1
        assert market_view._price_step(5000.0) == 1.0
        assert market_view._price_step(50000.0) == 5.0

    def test_aggregate_param_floor(self):
        ticks = [{"time": 1, "price": 1.0, "vol": 1.0, "side": "buy"}]
        bars = market_view._aggregate(ticks, "volbar", 0)
        assert bars and bars[0]["volume"] == 1.0

    def test_renko_noop_for_zero_brick(self):
        assert market_view._renko([{"price": 1.0, "vol": 1.0}], 0) == []