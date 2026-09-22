"""Tests del validador de dataset (research/validate.py)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from research import data as rdata
from research import validate as rval
from tests.conftest import DEFAULT_KILLZONES, make_candles

T0 = int(datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).timestamp())


def _mk(count: int = 60, bias: str = "bullish"):
    candles = make_candles(count=count, bias=bias)
    for i, c in enumerate(candles):
        c["time"] = T0 + i * 900
    return rdata.with_daily_levels(candles)


def _cfg(**over):
    cfg = {
        "min_score": 50.0, "min_rr": 2.0, "setup_ttl_minutes": 15.0,
        "sl_default_pips": 10.0, "tp_ratio_r": 2.0,
        "risk_weights": {"cot": 0.0, "cvd_of": 100.0, "smc": 0.0,
                         "killzone": 0.0, "smr_dxy": 0.0},
        "killzones": DEFAULT_KILLZONES,
        "values_pip": 0.0001, "spread_pips": 1.0, "slippage_pips": 0.0,
        "lookback": 20,
    }
    cfg.update(over)
    return cfg


class TestValidateDataset:

    def test_clean_dataset_passes(self):
        v = rval.validate_dataset(_mk(60), _cfg(), sample=10)
        assert all(v["checks"].values())
        assert v["lookahead_checked"] > 0
        assert v["lookahead_mismatches"] == []
        assert v["tf_sec"] == pytest.approx(900.0)

    def test_duplicate_times_detected(self):
        candles = _mk(20)
        candles.append(dict(candles[-1]))
        v = rval.validate_dataset(candles, _cfg())
        assert v["checks"]["monotonic"] is False

    def test_out_of_order_detected(self):
        candles = _mk(20)
        candles[7], candles[9] = candles[9], candles[7]
        v = rval.validate_dataset(candles, _cfg())
        assert v["checks"]["monotonic"] is False

    def test_missing_pdh_pdl_detected(self):
        raw = make_candles(count=20)  # sin with_daily_levels
        v = rval.validate_dataset(raw, _cfg())
        assert v["checks"]["keys"] is False

    def test_lookahead_mismatch_detected(self, monkeypatch):
        import research.sim as sim  # noqa: PLC0415

        candles = _mk(60)
        orig = sim.evaluate_at

        def contaminated(candles_, i, cfg_):
            if i + 1 < len(candles_):
                leak = list(candles_)
                leak[i] = dict(candles_[i + 1])  # el "current" usa una vela del FUTURO
                return orig(leak, i, cfg_)
            return orig(candles_, i, cfg_)

        monkeypatch.setattr(rval.sim, "evaluate_at", contaminated)
        v = rval.validate_dataset(candles, _cfg(), sample=10)
        assert v["checks"]["lookahead"] is False
        assert v["lookahead_mismatches"], "debe detectar al menos una fuga"

    def test_empty_dataset(self):
        v = rval.validate_dataset([], _cfg())
        assert v["checks"]["monotonic"] is False
        assert v["checks"]["keys"] is False

    def test_summarize_lines(self):
        v = rval.validate_dataset(_mk(60), _cfg(), sample=5)
        s = rval.summarize(v)
        assert "no-look-ahead" in s and "[   OK]" in s


class TestSampleIndices:

    def test_indices_in_range_and_spread(self):
        idx = rval._sample_indices(100, 10, lookback=20)
        assert idx == sorted(idx)
        assert all(20 <= i <= 97 for i in idx)
        assert len(idx) == 10

    def test_small_series_returns_empty(self):
        assert rval._sample_indices(10, 5, lookback=20) == []