"""Tests de los endpoints de investigación (app.py): aplicar config y audit."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app import (ResearchApplyBody, ResearchAuditBody, api_research_apply,
                 api_research_audit)
from tests.conftest import make_candles

T0 = int(datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc).timestamp())
WS = {"cot": 0.0, "cvd_of": 20.0, "smc": 50.0, "killzone": 30.0, "smr_dxy": 0.0}


def _mk(count: int = 80, bias: str = "bullish"):
    candles = make_candles(count=count, bias=bias)
    for i, c in enumerate(candles):
        c["time"] = T0 + i * 900
    import research.data as rdata  # noqa: PLC0415
    return rdata.with_daily_levels(candles)


def _payload(cfg: dict, trades: list) -> dict:
    return {"run": {"cfg": cfg, "tf_sec": 900.0, "trades": trades}}


def _trade(signal_ts: int) -> dict:
    return {
        "id": 1, "signal_ts": signal_ts, "fill_ts": signal_ts + 900,
        "exit_ts": signal_ts + 2700, "direction": "BUY", "score": 80.0,
        "verdict": "ALTA_PROBABILIDAD", "killzone": "Londres",
        "entry_kind": "BULLISH_FVG", "status": "WIN", "exit_reason": "TP",
        "plan": {"entry": 1.1000, "sl": 1.0988, "tp": 1.1024,
                 "invalidate": 1.0993},
        "entry_price": 1.1000, "exit_price": 1.1024,
        "bars_pending": 1, "bars_held": 2, "pnl_r": 2.0,
        "signal_components": {"smc": 0.9},
    }


# ============================================================
# /api/research/apply
# ============================================================

class TestApply:
    """Fase 2: aplicar diff con whitelist, backup y re-backtest."""

    def _patch_env(self, tmp_path, monkeypatch):
        import app as app_mod
        import strategy

        live = {"min_score": 70.0, "min_rr": 2.0,
                "setup_ttl_minutes": 20.0, "risk_pct": 0.5}

        def get_cfg():
            return dict(live)

        def set_cfg(cfg):
            for k, v in cfg.items():
                live[k] = v

        backup_src = tmp_path / "strategy.yaml"
        backup_src.write_text("# config de prueba\nmin_score: 70\n",
                              encoding="utf-8")

        monkeypatch.setattr(app_mod.store, "get_trading_config", get_cfg)
        monkeypatch.setattr(app_mod.store, "set_trading_config", set_cfg)
        monkeypatch.setattr(strategy, "STRATEGY_PATH", str(backup_src))
        m = {"ok": []}
        monkeypatch.setattr(app_mod, "_research_subprocess",
                            lambda args: (True, "ok", ""))
        monkeypatch.setattr(app_mod, "_research_load_payload",
                            lambda s, t, k: ({"saved": "x"}, None))
        monkeypatch.setattr(app_mod, "_research_payload_path",
                            lambda s, t, k: "x")
        monkeypatch.setattr(app_mod, "_BACKUP_DIR", str(tmp_path / "backups"))
        return app_mod, m

    def test_applies_whitelisted_and_skips_forbidden(self, tmp_path, monkeypatch):
        app_mod, m = self._patch_env(tmp_path, monkeypatch)
        body = ResearchApplyBody(updates=[
            {"key": "min_score", "value": 75.0},
            {"key": "risk." , "value": 1.0},
            {"key": "min_rr", "value": "abc"},
            {"key": "risk_weights", "value": WS},
        ], symbol="EURUSD", timeframe="M15", days=90)
        r = api_research_apply(body)
        assert r["ok"] is True
        assert r["before_config"]["min_score"] == 70.0
        assert r["after_config"]["min_score"] == 75.0
        assert r["after_config"]["risk_weights"] == WS
        assert r["after_payload"]["saved"] == "x"
        keys = [s["key"] for s in r["skipped"]]
        assert keys == ["risk.", "min_rr"]
        assert r["backup_path"]

    def test_forbidden_only_returns_400(self, tmp_path, monkeypatch):
        app_mod, m = self._patch_env(tmp_path, monkeypatch)
        body = ResearchApplyBody(updates=[{"key": "risk.", "value": 1.0}])
        r = api_research_apply(body)
        assert getattr(r, "status_code", None) == 400


# ============================================================
# /api/research/audit
# ============================================================

class TestAudit:
    """Fase 4: reconstrucción determinista del trade para auditarlo."""

    def _patch_env(self, tmp_path, monkeypatch):
        import app as app_mod
        import research.data as rdata
        import research.sim as sim

        results = tmp_path / "results"
        results.mkdir()
        cfg = {"lookback": 20, "min_score": 70.0}
        payload = _payload(cfg, [_trade(T0 + 100 * 900)])
        (results / "EURUSD_M15_20260914_bt.json").write_text(
            json.dumps(payload), encoding="utf-8")

        monkeypatch.setattr(app_mod, "_RESEARCH_RESULTS", str(results))
        monkeypatch.setattr(rdata, "load_dataset",
                            lambda s, t, days: {"candles": _mk(200)})

        zone = {"type": "BULLISH_FVG", "top": 1.1010, "bottom": 1.1002,
                "start_time": T0 + 99 * 900, "mitigated": False,
                "validated": True}

        def fake_snapshot(window, current, cfg_, ts):
            return {"current_price": current,
                    "analysis": {"patterns": {"fvgs": [zone],
                                              "order_blocks": []}},
                    "risk_engine": {"bull": {}, "bear": {},
                                    "killzone": {}, "regime": "London"}}

        monkeypatch.setattr(sim, "replicate_snapshot", fake_snapshot)
        return app_mod

    def test_audit_returns_trade_zone_and_candles(self, tmp_path, monkeypatch):
        self._patch_env(tmp_path, monkeypatch)
        body = ResearchAuditBody(saved="EURUSD_M15_20260914_bt.json",
                                 signal_ts=float(T0 + 100 * 900),
                                 window_before=30, window_after=20)
        r = api_research_audit(body)
        assert r["symbol"] == "EURUSD"
        assert r["tf_sec"] == 900.0
        assert r["trade"]["entry_kind"] == "BULLISH_FVG"
        assert r["trade"]["status"] == "WIN"
        assert r["zone"]["top"] == 1.1010
        assert r["zone"]["start_time"] == T0 + 99 * 900
        assert len(r["candles"]) >= 50
        assert r["candles"][0]["time"] <= body.signal_ts <= r["candles"][-1]["time"]
        assert r["trade"]["plan"]["tp"] == 1.1024

    def test_missing_signal_ts_404(self, tmp_path, monkeypatch):
        self._patch_env(tmp_path, monkeypatch)
        body = ResearchAuditBody(saved="EURUSD_M15_20260914_bt.json",
                                 signal_ts=float(T0))
        r = api_research_audit(body)
        assert getattr(r, "status_code", None) == 404

    def test_unknown_run_404(self, tmp_path, monkeypatch):
        self._patch_env(tmp_path, monkeypatch)
        body = ResearchAuditBody(saved="EURUSD_M15_20250101_bt.json",
                                 signal_ts=1.0)
        r = api_research_audit(body)
        assert getattr(r, "status_code", None) == 404