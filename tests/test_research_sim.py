"""Tests del motor de backtesting (research/sim.py) y métricas (research/metrics.py)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from research import data as rdata
from research import metrics as rm
from research import sim
from tests.conftest import DEFAULT_KILLZONES, make_candles

ROOT = Path(__file__).parent.parent

T0 = int(datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).timestamp())


def _mk(count: int = 40, bias: str = "bullish", t0: int = T0, **kw):
    candles = make_candles(count=count, bias=bias, **kw)
    for i, c in enumerate(candles):
        c["time"] = t0 + i * 900
    return rdata.with_daily_levels(candles)


def _cfg(**over):
    cfg = sim.default_cfg(trading_cfg={})
    cfg.update({
        "risk_weights": {"cot": 0.0, "cvd_of": 100.0, "smc": 0.0,
                         "killzone": 0.0, "smr_dxy": 0.0},
        "killzones": DEFAULT_KILLZONES,
        "min_score": 50.0,
        "sl_default_pips": 10.0,
        "tp_ratio_r": 2.0,
        "setup_ttl_minutes": 15.0,
        "values_pip": 0.0001,
        "spread_pips": 1.0,
        "slippage_pips": 0.0,
        "lookback": 20,
    })
    cfg.update(over)
    return cfg


def _bt(candles=None, **over):
    return sim.BarBacktest(candles if candles is not None else _mk(6),
                           cfg=_cfg(**over))


def _gate(direction="BUY", entry=1.1000, sl=1.0990, tp=1.1020, inval=None):
    return {
        "direction": direction, "score": 80.0, "verdict": "ALTA_PROBABILIDAD",
        "killzone_name": "Londres", "entry_kind": "market",
        "entry": entry, "sl": sl, "tp": tp, "invalidate_level": inval,
        "current_price": entry, "reasons": [],
    }


def _bar(open_=1.1000, high=1.1005, low=1.0990, close=1.0995, t=1):
    return {"time": t, "open": open_, "high": high, "low": low, "close": close}


# ============================================================
# Fill de la orden pendiente (mecánica pura)
# ============================================================

class TestPendingMechanics:

    def test_buy_fill_executes_at_ask(self):
        bt = _bt()
        p = bt._new_pending(_gate(direction="BUY", entry=1.1000), T0, ttl_bars=3)
        bt._advance_pending(p, _bar(low=1.0990))
        assert p["filled"] is True
        assert bt.pip == 0.0001 and bt.spread == 0.0001
        assert p["entry_exec"] == pytest.approx(1.1000 + 0.00005)  # BUY compra a ask
        assert p["n_bars"] == 1

    def test_sell_fill_executes_at_bid(self):
        bt = _bt()
        p = bt._new_pending(_gate(direction="SELL", entry=1.1000), T0, ttl_bars=3)
        bt._advance_pending(p, _bar(high=1.1005))
        assert p["filled"] is True
        assert p["entry_exec"] == pytest.approx(1.1000 - 0.00005)  # SELL vende a bid

    def test_slippage_adverse_on_entry(self):
        bt = _bt(slippage_pips=2.0)
        p = bt._new_pending(_gate(direction="BUY", entry=1.1000), T0, ttl_bars=3)
        bt._advance_pending(p, _bar(low=1.0995))
        assert p["entry_exec"] == pytest.approx(1.1000 + 0.00005 + 0.00020)

    def test_no_touch_then_ttl_expiry(self):
        bt = _bt()
        p = bt._new_pending(_gate(direction="BUY", entry=1.1000), T0, ttl_bars=2)
        bt._advance_pending(p, _bar(low=1.1002))  # no toca
        assert p["filled"] is False and not p["done"]
        assert p["ttl_left"] == 1 and p["n_bars"] == 1
        bt._advance_pending(p, _bar(low=1.1001))
        assert p["done"] is True and p["result"] == "TTL_EXPIRY"

    def test_invalidation_cancels_before_fill_buy(self):
        bt = _bt()
        p = bt._new_pending(_gate(direction="BUY", entry=1.1000, inval=1.0990), T0, 3)
        bt._advance_pending(p, _bar(low=1.0988))  # bajo invalidez y tocaría entrada
        assert p["filled"] is False
        assert p["done"] is True and p["result"] == "INVALIDATED"

    def test_invalidation_cancels_before_fill_sell(self):
        bt = _bt()
        p = bt._new_pending(_gate(direction="SELL", entry=1.1000, inval=1.1010), T0, 3)
        bt._advance_pending(p, _bar(high=1.1012))
        assert p["filled"] is False
        assert p["done"] is True and p["result"] == "INVALIDATED"


# ============================================================
# Cierre de posición (SL-first con bid/ask)
# ============================================================

class TestPositionExits:

    def _pos(self, **gate_over):
        bt = _bt()
        p = bt._new_pending(_gate(**gate_over), T0, 3)
        p["filled"] = True
        p["entry_exec"] = bt._entry_exec(p["signal"]["direction"], p["signal"]["entry"])
        p["fill_ts"] = T0 + 900
        return bt, bt._open_position(p, _bar())

    def test_sl_first_when_both_touched_buy(self):
        bt, pos = self._pos(direction="BUY", sl=1.0990, tp=1.1030)
        bt._check_position_exit(pos, _bar(low=1.0985, high=1.1035))
        assert pos["closed"] is True and pos["exit_path"] == "SL"
        assert pos["exit_price"] == pytest.approx(1.0990 - 0.00005)  # BUY cierra a bid

    def test_tp_only_buy(self):
        bt, pos = self._pos(direction="BUY", sl=1.0990, tp=1.1030)
        bt._check_position_exit(pos, _bar(low=1.1000, high=1.1035))
        assert pos["exit_path"] == "TP"
        assert pos["exit_price"] == pytest.approx(1.1030 - 0.00005)

    def test_sl_sell_uses_ask(self):
        bt, pos = self._pos(direction="SELL", sl=1.1010, tp=1.0970)
        bt._check_position_exit(pos, _bar(high=1.1015, low=1.0965))
        assert pos["exit_path"] == "SL"
        assert pos["exit_price"] == pytest.approx(1.1010 + 0.00005)

    def test_no_exit_increments_held(self):
        bt, pos = self._pos(direction="BUY", sl=1.0990, tp=1.1030)
        bt._check_position_exit(pos, _bar(low=1.1000, high=1.1020))
        assert pos["closed"] is False and pos["bars_held"] == 1


# ============================================================
# TTL y config
# ============================================================

class TestSetup:

    def test_ttl_bars_15min(self):
        bt = _bt(candles=_mk(6, t0=T0), setup_ttl_minutes=15.0)
        assert bt._ttl_bars() == 1

    def test_ttl_bars_45min(self):
        bt = _bt(candles=_mk(6, t0=T0), setup_ttl_minutes=45.0)
        assert bt._ttl_bars() == 3

    def test_ttl_bars_floor_1(self):
        bt = _bt(candles=_mk(6, t0=T0), setup_ttl_minutes=0.5)
        assert bt._ttl_bars() == 1

    def test_requires_pdh_pdl(self):
        raw = make_candles(count=6)  # sin with_daily_levels
        with pytest.raises(ValueError):
            sim.BarBacktest(raw, cfg=_cfg())

    def test_default_cfg_overrides_win(self):
        c = sim.default_cfg(trading_cfg={"lookback": "10",
                                         "sl_default_pips": "8.0"})
        assert c["lookback"] == 10
        c2 = sim.default_cfg(trading_cfg={"sl_default_pips": "8.0"},
                             overrides={"sl_default_pips": 12.0})
        assert c2["sl_default_pips"] == 12.0


# ============================================================
# Invariante look-ahead
# ============================================================

class TestLookAhead:

    def test_gate_at_i_ignores_future(self):
        candles = _mk(count=50, bias="bullish")
        cfg = _cfg()
        i = 30
        g_full = sim.evaluate_at(candles, i, cfg)
        g_prefix = sim.evaluate_at(candles[: i + 1], i, cfg)
        assert g_full is not None and g_prefix is not None
        assert g_full["direction"] == g_prefix["direction"]
        assert g_full["score"] == g_prefix["score"]
        assert g_full["approved"] == g_prefix["approved"]

    def test_cvd_baseline_resets(self):
        candles = _mk(count=40, bias="bullish")
        win_a = sim._cvd_series(candles[:30])
        win_b = sim._cvd_series(candles[10:40])
        d0 = sim._candle_delta(candles[0]["open"], candles[0]["close"],
                               candles[0]["volume"])
        d10 = sim._candle_delta(candles[10]["open"], candles[10]["close"],
                                candles[10]["volume"])
        # Cada ventana acumula desde 0: no hereda baseline de antes ni de después.
        assert win_a[0]["value"] == pytest.approx(d0)
        assert win_b[0]["value"] == pytest.approx(d10)

    def test_gate_includes_signal_components(self):
        candles = _mk(count=50, bias="bullish")
        g = sim.evaluate_at(candles, 30, _cfg())
        assert g is not None
        assert isinstance(g.get("components"), dict)
        assert "smc" in g["components"]


# ============================================================
# Integración run()
# ============================================================

class TestRun:

    def test_run_structure_and_trade_fields(self):
        candles = _mk(count=60, bias="bullish")
        res = sim.BarBacktest(candles, cfg=_cfg()).run()
        assert res["n_bars"] == 60
        assert res["tf_sec"] == 900.0
        assert res["start_ts"] <= res["end_ts"]
        assert res["trades"]
        for t in res["trades"]:
            for key in ("id", "signal_ts", "direction", "score", "verdict",
                        "killzone", "entry_kind", "plan", "entry_price",
                        "exit_price", "status", "exit_reason",
                        "bars_pending", "pnl_pips", "pnl_r",
                        "signal_components"):
                assert key in t
            assert t["status"] in ("WIN", "LOSS", "EXPIRED", "CANCELLED",
                                   "OPEN", "PENDING")
            assert isinstance(t["signal_components"], dict)
            assert t["pnl_r"] is not None if t["status"] in ("WIN", "LOSS") else True

    def test_run_market_entry_fills_next_bar(self):
        candles = _mk(count=8, bias="bullish")
        res = sim.BarBacktest(candles, cfg=_cfg()).run()
        # Primeras barras están en killzone y CVD alcista -> la señal BUY se llena
        # en la vela siguiente (entry_kind market, orden viva 1 bar).
        assert any(t["entry_price"] is not None for t in res["trades"])


# ============================================================
# Métricas
# ============================================================

class TestMetrics:

    def _trades(self):
        return [
            {"status": "WIN", "pnl_r": 2.0, "pnl_pips": 24.0, "direction": "BUY",
             "killzone": "Londres", "entry_kind": "market",
             "bars_pending": 1, "bars_held": 5},
            {"status": "LOSS", "pnl_r": -1.0, "pnl_pips": -12.0, "direction": "BUY",
             "killzone": "Londres", "entry_kind": "market",
             "bars_pending": 1, "bars_held": 3},
            {"status": "LOSS", "pnl_r": -1.0, "pnl_pips": -12.0, "direction": "SELL",
             "killzone": "Londres", "entry_kind": "FVG",
             "bars_pending": 2, "bars_held": 4},
            {"status": "EXPIRED", "pnl_r": None, "pnl_pips": None, "direction": "BUY",
             "killzone": "Londres", "entry_kind": "market",
             "bars_pending": 2, "bars_held": None},
        ]

    def test_metrics_aggregate(self):
        m = rm.compute_metrics(self._trades())
        assert m["n"] == 4
        assert m["n_filled"] == 3
        assert m["n_expired"] == 1
        assert m["wins"] == 1 and m["losses"] == 2
        assert m["win_rate"] == pytest.approx(33.33, abs=0.01)
        assert m["expectancy_r"] == pytest.approx(0.0)
        assert m["expectancy_pips"] == pytest.approx(0.0)
        assert m["profit_factor"] == pytest.approx(1.0)
        assert m["avg_bars_held"] == pytest.approx(4.0)
        assert m["avg_bars_pending"] == pytest.approx(1.5)
        assert m["max_dd_equity_pct"] >= 0.0

    def test_metrics_empty(self):
        m = rm.compute_metrics([])
        assert m["n"] == 0
        assert m["win_rate"] is None

    def test_metrics_breakdowns(self):
        m = rm.compute_metrics(self._trades())
        assert m["by_direction"]["BUY"]["n"] == 3
        assert m["by_direction"]["SELL"]["n"] == 1
        assert m["by_entry_kind"]["FVG"]["n"] == 1
        assert m["by_killzone"]["Londres"]["n"] == 4


# ============================================================
# CLI backtest end-to-end (temp datadir)
# ============================================================

class TestCliBacktest:

    def test_backtest_end_to_end(self, tmp_path):
        candles = _mk(count=30, bias="bullish")
        data_dir = tmp_path / "data"
        res_dir = tmp_path / "results"
        data_dir.mkdir()
        csv_path = data_dir / "EURUSD_M15_90d_20260907.csv"
        rdata.write_csv(str(csv_path), candles)

        from research import run_research  # noqa: PLC0415
        argv = ["backtest", "--symbol", "EURUSD", "--timeframe", "M15",
                "--days", "90", "--lookback", "10",
                "--datadir", str(data_dir), "--outdir", str(res_dir)]
        rc = run_research.main(argv)
        assert rc == 0
        jsons = list(res_dir.glob("*.json"))
        assert len(jsons) == 1
        payload = json.load(open(jsons[0], encoding="utf-8"))
        assert payload["run"]["n_bars"] == 30
        assert payload["metrics"]["n"] >= 0