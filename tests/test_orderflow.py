"""Tests de Order Flow: fix de absorción, spikes Z-score, reset del engine y
mock feed (determinismo, replay y fixtures .jsonl).

100% offline: inyecta trades directamente en OrderFlowEngine (app.py) o
reproduce el feed sintético de mock_feed.py. No toca Databento ni MT5.

Run:  python -m pytest tests/test_orderflow.py -v
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import mock_feed  # noqa: E402
from app import OrderFlowEngine  # noqa: E402

from conftest import make_trades  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _feed(engine, trades):
    for t in trades:
        engine.add_trade(price=t["price"], size=t["size"], side=t["side"], ts=t["ts"])


def _feed_until_abs(engine, trades):
    """Inyecta trades hasta el primer evento de absorción (o agota la lista)."""
    for t in trades:
        payload = engine.add_trade(price=t["price"], size=t["size"], side=t["side"], ts=t["ts"])
        if payload and payload.get("absorption"):
            return engine, payload
    return engine, None


def _abs_with(trades, absorb_trades=20):
    eng = OrderFlowEngine()
    eng.update_settings(absorb_trades=absorb_trades)
    return _feed_until_abs(eng, trades)


class TestAbsorptionSideSplit:
    """Fase 1: buy/sell se computan por lado y total == buy + sell."""

    def test_full_window_asymmetric(self):
        # Patrón intercalado A(4), A(4), B(9): volumen asimétrico por lado pero
        # delta equilibrado en CUALQUIER ventana (|A-B|/total ~ 0.06 <= 0.25).
        trades = []
        for i in range(60):
            if i % 3 == 2:
                trades.append({"ts": 1e9 + i, "price": 1.0985, "size": 9, "side": "B"})
            else:
                trades.append({"ts": 1e9 + i, "price": 1.0985, "size": 4, "side": "A"})
        eng, payload = _abs_with(trades)
        assert payload is not None
        ab = payload["absorption"]
        assert ab["buy_vol"] != ab["sell_vol"]
        assert ab["buy_vol"] + ab["sell_vol"] == pytest.approx(ab["volume"])
        # invariante del engine tras consumir toda la ventana
        snap = eng.snapshot()
        assert abs(snap["buy_vol"] + snap["sell_vol"] - snap["total_vol"]) < 1e-6
        assert snap["buy_vol"] != snap["sell_vol"]

    def test_generated_70_30_split_snapshot(self):
        # 70% A / 30% B: el engine acumula por lado aunque el delta_ratio no cierre
        # la absorción. El fix garantiza buy != sell y buy + sell == total.
        trades = make_trades(count=150, side_bias=0.7, size_range=(4, 7), seed=3)
        eng = OrderFlowEngine()
        _feed(eng, trades)
        snap = eng.snapshot()
        buy = sum(t["size"] for t in trades if t["side"] == "A")
        sell = sum(t["size"] for t in trades if t["side"] == "B")
        assert snap["buy_vol"] != snap["sell_vol"]
        assert snap["buy_vol"] == pytest.approx(buy)
        assert snap["sell_vol"] == pytest.approx(sell)
        assert abs(snap["buy_vol"] + snap["sell_vol"] - snap["total_vol"]) < 1e-6


class TestZScoreSpike:
    def test_noise_does_not_spike(self):
        eng = OrderFlowEngine()
        _feed(eng, list(mock_feed.gen_stream("noise", count=300, seed=7)))
        assert eng.snapshot()["spike_count"] == 0

    def test_spike_regime_crosses_threshold(self):
        eng = OrderFlowEngine()
        _feed(eng, list(mock_feed.gen_stream("spike", count=300, seed=7)))
        assert eng.snapshot()["spike_count"] >= 1

    def test_spike_flag_on_individual_trade(self):
        eng = OrderFlowEngine()
        found = False
        for t in mock_feed.gen_stream("spike", count=300, seed=7):
            payload = eng.add_trade(price=t["price"], size=t["size"], side=t["side"], ts=t["ts"])
            if payload and payload.get("is_spike"):
                found = True
                break
        assert found
        assert eng.snapshot()["spike_count"] >= 1


class TestAbsorptionTrigger:
    def test_fixture_triggers_buy_direction(self):
        _, payload = _abs_with(mock_feed.load_fixture(str(FIXTURES / "orderflow_6e_absorption.jsonl")))
        assert payload is not None
        assert payload["absorption"]["direction"] == "compra"

    def test_sell_heavy_window_triggers_venta(self):
        # 24 ventas de 6 y 16 compras de 3 -> net_delta negativo, delta_ratio bajo.
        trades = ([{"ts": 1e9 + i, "price": 1.0985, "size": 6, "side": "B"} for i in range(24)]
                  + [{"ts": 1e9 + 24 + i, "price": 1.0985, "size": 3, "side": "A"} for i in range(16)])
        _, payload = _abs_with(trades)
        assert payload is not None
        assert payload["absorption"]["direction"] == "venta"


class TestMockDeterminism:
    def test_same_seed_same_stream(self):
        assert (list(mock_feed.gen_stream("noise", count=200, seed=7))
                == list(mock_feed.gen_stream("noise", count=200, seed=7)))

    def test_different_seed_differs(self):
        a = list(mock_feed.gen_stream("noise", count=200, seed=7))
        b = list(mock_feed.gen_stream("noise", count=200, seed=8))
        assert any(x != y for x, y in zip(a, b))

    def test_deterministic_across_regimes(self):
        for regime in ("noise", "spike", "absorption", "stress"):
            a = list(mock_feed.gen_stream(regime, count=100, seed=1))
            b = list(mock_feed.gen_stream(regime, count=100, seed=1))
            assert a == b, regime


class TestMockReplay:
    def test_replay_matches_load_fixture(self):
        path = str(FIXTURES / "orderflow_6e_noise.jsonl")
        assert list(mock_feed.replay(path)) == mock_feed.load_fixture(path)

    def test_replay_reproducible(self):
        path = str(FIXTURES / "orderflow_6e_spike.jsonl")
        assert list(mock_feed.replay(path)) == list(mock_feed.replay(path))

    def test_replay_ordered_ts(self):
        trades = list(mock_feed.replay(str(FIXTURES / "orderflow_6e_absorption.jsonl")))
        ts = [t["ts"] for t in trades]
        assert ts == sorted(ts)


class TestPayloadTs:
    """El payload del WS debe llevar `ts` (epoch secs) para que el chart order
    flow pinte la curva CVD en tiempo real (ofUpdateCvd usa data.ts en el eje X)."""

    def test_trade_payload_includes_ts(self):
        eng = OrderFlowEngine()
        p = eng.add_trade(price=1.0985, size=10, side="A", ts=1_700_000_123.0)
        assert p is not None
        assert p["ts"] == 1_700_000_123.0

    def test_batch_payloads_preserve_ts(self):
        eng = OrderFlowEngine()
        trades = make_trades(count=8, seed=2)
        payloads = []
        for t in trades:
            p = eng.add_trade(t["price"], t["size"], t["side"], t["ts"])
            if p is not None:
                payloads.append(p)
        assert len(payloads) == len(trades)
        for t, p in zip(trades, payloads):
            assert p["ts"] == t["ts"]


class TestEngineReset:
    def test_snapshot_zero_after_reset(self):
        eng = OrderFlowEngine()
        _feed(eng, make_trades(count=60, seed=5))
        assert eng.snapshot()["cvd"] != 0.0
        eng.reset()
        snap = eng.snapshot()
        assert snap["cvd"] == 0.0
        assert snap["delta"] == 0.0
        assert snap["total_vol"] == 0.0
        assert snap["buy_vol"] == 0.0
        assert snap["sell_vol"] == 0.0
        assert snap["spike_count"] == 0
        assert snap["last_price"] is None
        assert snap["alerts"] == []
        assert snap["ema"] is None

    def test_cvd_series_empty_after_reset(self):
        eng = OrderFlowEngine()
        _feed(eng, make_trades(count=60, seed=5))
        assert eng.cvd_series() != []
        eng.reset()
        assert eng.cvd_series() == []

    def test_engine_usable_after_reset(self):
        eng = OrderFlowEngine()
        _feed(eng, make_trades(count=30, seed=2))
        eng.reset()
        _, payload = _feed_until_abs(eng, make_trades(count=150, side_bias=0.7, size_range=(4, 7), seed=1))
        assert eng.snapshot()["cvd"] != 0.0
        assert payload is None or payload.get("absorption") is not None


class TestFixturesLoad:
    def test_noise_fixture_invariants(self):
        eng = OrderFlowEngine()
        _feed(eng, mock_feed.load_fixture(str(FIXTURES / "orderflow_6e_noise.jsonl")))
        snap = eng.snapshot()
        assert snap["spike_count"] == 0
        assert snap["alerts"] == []

    def test_spike_fixture_invariants(self):
        eng = OrderFlowEngine()
        _feed(eng, mock_feed.load_fixture(str(FIXTURES / "orderflow_6e_spike.jsonl")))
        assert eng.snapshot()["spike_count"] >= 1

    def test_absorption_fixture_invariants(self):
        trades = mock_feed.load_fixture(str(FIXTURES / "orderflow_6e_absorption.jsonl"))
        assert len(trades) >= 120
        eng = OrderFlowEngine()
        eng.update_settings(absorb_trades=20)
        payloads = [p for p in (eng.add_trade(t["price"], t["size"], t["side"], t["ts"]) for t in trades) if p]
        absorbs = [p for p in payloads if p.get("absorption")]
        assert absorbs
        assert {p["absorption"]["direction"] for p in absorbs} == {"compra"}
        snap = eng.snapshot()
        assert snap["buy_vol"] != snap["sell_vol"]
        assert abs(snap["buy_vol"] + snap["sell_vol"] - snap["total_vol"]) < 1e-6
        assert eng.absorb_bins

    def test_each_trade_shape(self):
        for name in ("orderflow_6e_noise.jsonl", "orderflow_6e_spike.jsonl", "orderflow_6e_absorption.jsonl"):
            for t in mock_feed.load_fixture(str(FIXTURES / name)):
                assert {"ts", "price", "size", "side"} <= set(t)
                assert t["side"] in ("A", "B")
                assert isinstance(t["size"], int)
                assert isinstance(t["price"], (int, float))