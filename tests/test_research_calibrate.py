"""Tests del calibrador (research/calibrator.py) y del reporte (research/report.py)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from research import calibrator
from research import report as rreport


def _trade(status="WIN", pnl=2.0, comps=None, direction="BUY",
           killzone="Londres", entry_kind="market", bars_pending=1, bars_held=4,
           entry=1.1000, exit_=1.1020, signal_ts=123, fill_ts=124, exit_ts=125):
    pnl_pips = (exit_ - entry) * 10000.0 if exit_ else None
    return {
        "id": 1, "signal_ts": signal_ts, "fill_ts": fill_ts, "exit_ts": exit_ts,
        "direction": direction, "score": 80.0, "verdict": "ALTA_PROBABILIDAD",
        "killzone": killzone, "entry_kind": entry_kind,
        "plan": {"entry": entry, "sl": None, "tp": None},
        "entry_price": entry if status != "EXPIRED" else None,
        "exit_price": exit_ if status in ("WIN", "LOSS") else None,
        "status": status, "exit_reason": ("TP" if status == "WIN" else
                                          "SL" if status == "LOSS" else status),
        "bars_pending": bars_pending,
        "bars_held": bars_held if status in ("WIN", "LOSS") else None,
        "pnl_pips": round(pnl_pips, 2) if status in ("WIN", "LOSS") else None,
        "pnl_r": pnl if status in ("WIN", "LOSS") else None,
        "reasons": [],
        "signal_components": comps or {},
    }


def _cfg(**over):
    cfg = {
        "min_score": 70.0, "min_rr": 2.0, "setup_ttl_minutes": 20.0,
        "sl_default_pips": 12.0, "tp_ratio_r": 2.0,
        "risk_weights": {"cot": 0.0, "cvd_of": 20.0, "smc": 50.0,
                         "killzone": 30.0, "smr_dxy": 0.0},
        "killzones": [], "values_pip": 0.0001, "spread_pips": 1.0,
        "slippage_pips": 0.0, "lookback": 300, "cvd_bars": 30,
    }
    cfg.update(over)
    return cfg


def _metrics(**over):
    m = {
        "symbol": "EURUSD", "timeframe": "M15",
        "n": 10, "n_filled": 6, "n_expired": 2, "n_cancelled": 1, "n_open": 1,
        "wins": 4, "losses": 2, "win_rate": 66.7, "expectancy_r": 0.5,
        "expectancy_pips": 6.0, "avg_win_r": 2.0, "avg_loss_r": -1.0,
        "profit_factor": 4.0, "max_dd_equity_pct": 2.0,
        "avg_bars_pending": 1.2, "avg_bars_held": 4.0,
    }
    m.update(over)
    return m


# ============================================================
# component_means
# ============================================================

class TestComponentMeans:

    def test_groups_wins_losses_and_delta(self):
        trades = [
            _trade(pnl=2.0, comps={"smc": 0.8, "cvd_of": 0.9}),
            _trade(pnl=2.0, comps={"smc": 0.7, "cvd_of": 0.8}),
            _trade(pnl=-1.0, comps={"smc": 0.2, "cvd_of": 0.9}),
            _trade(pnl=-1.0, comps={"smc": 0.4, "cvd_of": 0.8}),
        ]
        m = calibrator.component_means(trades)
        assert m["smc"]["n_wins"] == 2
        assert m["smc"]["n_losses"] == 2
        assert m["smc"]["wins_mean"] == pytest.approx(0.75)
        assert m["smc"]["losses_mean"] == pytest.approx(0.30)
        assert m["smc"]["delta"] == pytest.approx(0.45)
        # cvd no discrimina entre wins y losses (misma media) -> delta ~0
        assert abs(m["cvd_of"]["delta"]) < 0.02

    def test_ignores_non_filled(self):
        trades = [_trade(status="EXPIRED", pnl=None,
                         comps={"smc": 0.9})]
        assert calibrator.component_means(trades) == {}

    def test_delta_none_when_one_bucket_missing(self):
        trades = [_trade(pnl=2.0, comps={"smc": 0.8}),
                  _trade(pnl=2.0, comps={"smc": 0.7})]
        m = calibrator.component_means(trades)
        assert m["smc"]["delta"] is None
        assert m["smc"]["losses_mean"] is None


# ============================================================
# suggest(): reglas
# ============================================================

class TestSuggestRules:

    def test_ttl_suggestion_when_expiry_dominates(self):
        m = _metrics(n=10, n_filled=2, n_expired=8, n_cancelled=0, n_open=0)
        cal = calibrator.suggest(_cfg(), [], metrics=m)
        keys = [s["key"] for s in cal["suggestions"]]
        assert "setup_ttl_minutes" in keys
        s = next(s for s in cal["suggestions"] if s["key"] == "setup_ttl_minutes")
        assert s["current"] == 20 and s["suggested"] == 30
        assert s["path"] == ("score", "setup_ttl_minutes")

    def test_no_ttl_when_expiry_is_minority(self):
        m = _metrics(n=10, n_filled=8, n_expired=2)
        cal = calibrator.suggest(_cfg(), [], metrics=m)
        assert "setup_ttl_minutes" not in [s["key"] for s in cal["suggestions"]]

    def test_ttl_skipped_when_already_above(self):
        m = _metrics(n=10, n_filled=2, n_expired=8)
        base = _cfg(setup_ttl_minutes=45.0)
        cal = calibrator.suggest(_cfg(), [], metrics=m, baseline=base)
        assert "setup_ttl_minutes" not in [s["key"] for s in cal["suggestions"]]

    def test_min_score_when_negative_expectancy(self):
        m = _metrics(n_filled=12, expectancy_r=-0.40, wins=3, losses=9)
        cal = calibrator.suggest(_cfg(), [], metrics=m)
        s = next(s for s in cal["suggestions"] if s["key"] == "min_score")
        assert s["delta"] == 5.0
        assert s["current"] == 70.0 and s["suggested"] == 75.0

    def test_no_min_score_when_positive_expectancy(self):
        m = _metrics(n_filled=12, expectancy_r=0.40)
        cal = calibrator.suggest(_cfg(), [], metrics=m)
        assert "min_score" not in [s["key"] for s in cal["suggestions"]]

    def test_risk_pct_reduction_under_drawdown(self):
        m = _metrics(max_dd_equity_pct=5.0)
        base = _cfg(risk_weights={}, setup_ttl_minutes=20.0)  # baseline con risk_pct
        base["risk_pct"] = 2.0
        cal = calibrator.suggest(_cfg(), [], metrics=m, baseline=base)
        s = next(s for s in cal["suggestions"] if s["key"] == "risk_pct")
        assert s["current"] == 2.0
        assert s["suggested"] < 2.0

    def test_cancel_warning(self):
        m = _metrics(n=10, n_filled=4, n_expired=1, n_cancelled=5)
        cal = calibrator.suggest(_cfg(), [], metrics=m)
        assert any("invalidez" in w for w in cal["warnings"])

    def test_empty_input_no_suggestions(self):
        cal = calibrator.suggest(_cfg(), [])
        assert cal["suggestions"] == []
        assert cal["warnings"] == []


# ============================================================
# suggest(): pesos por componente
# ============================================================

class TestWeightTuning:

    W = {"cot": 0.0, "cvd_of": 20.0, "smc": 50.0, "killzone": 30.0, "smr_dxy": 0.0}

    def _trades(self, wins=8, losses=8):
        trades = [_trade(pnl=2.0, comps={"smc": 0.8, "cvd_of": 0.5})
                  for _ in range(wins)]
        trades += [_trade(pnl=-1.0, comps={"smc": 0.2, "cvd_of": 0.5})
                   for _ in range(losses)]
        return trades

    def test_weights_tuned_and_renormalized(self):
        trades = self._trades()
        means = calibrator.component_means(trades)
        tuned = calibrator._tune_weights(self.W, means,
                                         calibrator._DEFAULT_THRESHOLDS)
        assert tuned["items"]
        smc = next(i for i in tuned["items"] if i["component"] == "smc")
        assert smc["delta_points"] == 15
        w = tuned["weights"]
        assert sum(w.values()) == pytest.approx(100.0, abs=0.5)
        assert w["smc"] > self.W["smc"]
        assert w["cvd_of"] < self.W["cvd_of"]  # renormalizado a la baja
        assert all(v >= 0 for v in w.values())

    def test_no_tuning_when_no_discrimination(self):
        trades = [_trade(pnl=2.0, comps={"smc": 0.5}) for _ in range(8)]
        trades += [_trade(pnl=-1.0, comps={"smc": 0.5}) for _ in range(8)]
        means = calibrator.component_means(trades)
        tuned = calibrator._tune_weights(self.W, means,
                                         calibrator._DEFAULT_THRESHOLDS)
        assert tuned["items"] == []
        assert tuned["weights"] == self.W

    def test_inactive_component_never_tuned(self):
        trades = [_trade(pnl=2.0, comps={"smr_dxy": 0.9}) for _ in range(8)]
        trades += [_trade(pnl=-1.0, comps={"smr_dxy": 0.1}) for _ in range(8)]
        tuned = calibrator._tune_weights(self.W,
                                         calibrator.component_means(trades),
                                         calibrator._DEFAULT_THRESHOLDS)
        assert tuned["items"] == []
        assert tuned["weights"] == self.W

    def test_low_sample_small_delta_ignored(self):
        trades = [_trade(pnl=2.0, comps={"smc": 0.9}) for _ in range(2)]
        trades += [_trade(pnl=-1.0, comps={"smc": 0.1}) for _ in range(2)]
        tuned = calibrator._tune_weights(self.W,
                                         calibrator.component_means(trades),
                                         calibrator._DEFAULT_THRESHOLDS)
        assert tuned["items"] == []

    def test_weights_suggestion_in_suggest(self):
        trades = self._trades()
        m = _metrics(n_filled=16, wins=8, losses=8, expectancy_r=0.5,
                     max_dd_equity_pct=1.0)
        base = dict(_cfg(risk_weights=dict(self.W)))
        cal = calibrator.suggest(_cfg(risk_weights=dict(self.W)), trades,
                                 metrics=m, baseline=base)
        s = next(s for s in cal["suggestions"] if s["key"] == "risk_weights")
        assert s["path"] == ("score", "weights")
        assert sum(s["suggested"].values()) == pytest.approx(100.0, abs=0.5)
        assert s["items"][0]["component"] == "smc"


# ============================================================
# report.py
# ============================================================

class TestReport:

    def test_render_report_contains_blocks_and_rows(self):
        res = {
            "n_bars": 100, "tf_sec": 900.0, "ttl_bars": 1,
            "pip": 0.0001, "spread": 0.00005, "slip": 0.0,
            "start_ts": 0, "end_ts": 90000, "cfg": {"lookback": 300},
            "trades": [_trade(status="WIN"), _trade(status="LOSS")],
        }
        m = _metrics()
        breakdowns = {"by_direction": {}, "by_killzone": {}, "by_entry_kind": {}}
        text = rreport.render_report(res, m, breakdowns)
        assert "Backtest EURUSD M15" in text
        assert "TRADES" in text
        assert "TP" in text and "SL" in text

    def test_table_truncated_row_keeps_columns(self):
        trades = [_trade(pnl=2.0 if i % 2 == 0 else -1.0,
                         comps={"smc": 0.5}) for i in range(50)]
        res = {"n_bars": 1, "tf_sec": 900.0, "ttl_bars": 1, "pip": 0.0001,
               "spread": 0.0, "slip": 0.0, "start_ts": 0, "end_ts": 1,
               "cfg": {}, "trades": trades}
        m = _metrics()
        text = rreport.render_report(res, m, {}, max_rows=10)
        assert "trades más" in text

    def test_render_payload_with_suggestions(self):
        payload = {
            "run": {"n_bars": 1, "tf_sec": 900, "ttl_bars": 1, "pip": 0.0001,
                    "spread": 0.0, "slip": 0.0, "start_ts": 0, "end_ts": 1,
                    "cfg": {}, "trades": []},
            "metrics": _metrics(),
            "breakdowns": {"by_direction": {}, "by_killzone": {},
                           "by_entry_kind": {}},
            "suggestions": [{
                "key": "setup_ttl_minutes", "path": ("score", "setup_ttl_minutes"),
                "current": 20, "suggested": 30, "delta": 10,
                "reason": "test", "confidence": "medium",
            }],
            "warnings": ["aviso de prueba"],
        }
        text = rreport.render_payload(payload)
        assert "AVISOS" in text and "aviso de prueba" in text
        assert "SUGERENCIAS" in text and "setup_ttl_minutes" in text