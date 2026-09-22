"""Tests del grid search (research/search.py)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from research import data as rdata
from research import search as rsearch
from research import sim
from tests.conftest import DEFAULT_KILLZONES, make_candles

T0 = int(datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).timestamp())


def _mk(count: int = 80, bias: str = "bullish", **kw):
    candles = make_candles(count=count, bias=bias, **kw)
    for i, c in enumerate(candles):
        c["time"] = T0 + i * 900
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


def _m(**over):
    m = {"n_filled": 12, "expectancy_r": 0.30, "profit_factor": 1.4,
         "max_dd_equity_pct": 3.0, "wins": 7, "losses": 5}
    m.update(over)
    return m


# ============================================================
# row_rank: ranking transparente
# ============================================================

class TestRowRank:

    def test_sample_gate_penalizes_hard(self):
        low = rsearch.row_rank(_m(n_filled=6, expectancy_r=1.0), min_filled=10)
        high = rsearch.row_rank(_m(n_filled=20, expectancy_r=1.0), min_filled=10)
        assert low < 0 and high > 0
        assert low < -900.0  # grupo de muestra insuficiente, muy abajo

    def test_higher_expectancy_ranks_first(self):
        a = rsearch.row_rank(_m(n_filled=10, expectancy_r=0.5))
        b = rsearch.row_rank(_m(n_filled=10, expectancy_r=0.1))
        assert a > b

    def test_tiebreak_profit_factor(self):
        a = rsearch.row_rank(_m(expectancy_r=0.2, profit_factor=2.2))
        b = rsearch.row_rank(_m(expectancy_r=0.2, profit_factor=1.1))
        assert a > b

    def test_penalty_for_drawdown(self):
        a = rsearch.row_rank(_m(max_dd_equity_pct=1.0))
        b = rsearch.row_rank(_m(max_dd_equity_pct=20.0))
        assert a > b


# ============================================================
# search_grid
# ============================================================

class TestSearchGrid:

    def test_enumerates_cartesian_and_sorts_desc(self):
        candles = _mk(80)
        out = rsearch.search_grid(
            candles, _cfg(),
            grid={"setup_ttl_minutes": [15, 20], "min_score": [50, 65]},
            top_n=4, min_filled=1)
        assert out["combos"] == 4
        assert out["total"] == 4
        assert out["grid"]["min_score"] == [50, 65]
        assert len(out["results"]) == 4
        ranks = [r["rank"] for r in out["results"]]
        assert ranks == sorted(ranks, reverse=True)

    def test_rows_include_params_metrics_and_flags(self):
        candles = _mk(80)
        out = rsearch.search_grid(
            candles, _cfg(), grid={"setup_ttl_minutes": [15]},
            top_n=1, min_filled=1)
        row = out["results"][0]
        assert row["params"] == {"setup_ttl_minutes": 15}
        assert row["metrics"]["win_rate"] is not None
        assert "expectancy_r" in row["metrics"]
        assert isinstance(row["rank"], float)
        assert "underpowered" in row
        assert "error" not in row

    def test_top_n_from_results_is_proportional(self):
        candles = _mk(80)
        out = rsearch.search_grid(
            candles, _cfg(),
            grid={"min_score": [50, 60, 70, 80]}, top_n=2, min_filled=1)
        assert len(out["results"]) == 2

    def test_base_reports_grid_baseline_values(self):
        candles = _mk(80)
        out = rsearch.search_grid(
            candles, _cfg(min_score=75.0),
            grid={"min_score": [50, 60]}, top_n=1, min_filled=1)
        assert out["base"] == {"min_score": 75.0}

    def test_product_order_symbol_timeframe_passthrough(self):
        candles = _mk(80)
        out = rsearch.search_grid(
            candles, _cfg(), grid={"min_score": [50]}, top_n=1, min_filled=1,
            symbol="GBPUSD", timeframe="H1")
        assert set(out["results"][0]["metrics"]) == set(rsearch._METRIC_KEYS)

    def test_defensive_on_exceptional_combo(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("combo roto")
        monkeypatch.setattr(sim, "BarBacktest", boom)
        candles = _mk(80)
        out = rsearch.search_grid(candles, _cfg(), grid={"min_score": [50]},
                                  top_n=1, min_filled=1)
        assert out["total"] == 1
        assert out["results"][0]["error"]
        assert out["results"][0]["metrics"] is None
        assert out["results"][0]["rank"] is None