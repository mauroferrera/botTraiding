"""Layer 2: Full setup evaluation flow with mocked MT5 and services.

Tests the combined setup_score + validate_entry flow as api_chart_setup_eval
would execute it, but without running the HTTP server or importing app.py.

Validates:
  - Score gate (min_score) + validate_entry gate (R:R, invalidation, TTL)
  - Entry/SL/TP computation from scenario params
  - Both directions evaluated, best one selected
  - Killzone override works

Run:  python -m pytest tests/test_setup_eval.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import risk_engine as re_mod
from conftest import (
    load_scenario, make_candles, make_snapshot_from_scenario, DEFAULT_KILLZONES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def evaluate_setup(scenario, current_price=None):
    """Simulate the core logic of api_chart_setup_eval.

    Returns dict with: direction, score, verdict, approved, val, reasons.
    """
    now = datetime.fromisoformat(scenario["now_utc"].replace("Z", "+00:00"))
    kz = scenario.get("killzones", DEFAULT_KILLZONES)
    cot = scenario.get("cot")
    cvd = scenario.get("cvd")
    patterns = scenario.get("patterns", {"fvgs": [], "order_blocks": [], "sweeps": []})
    cfg = scenario.get("cfg", {})
    min_score = float(cfg.get("min_score") or 80.0)
    direction = scenario.get("direction", "BUY")

    candle_params = scenario.get("candle_params", {})
    candles = make_candles(**candle_params)
    cvd = scenario.get("cvd")  # None (or absent) explicitly means "no CVD data"

    inputs_base = {"cot": cot, "cvd": cvd, "patterns": patterns, "candles": candles}
    bull = re_mod.setup_score({**inputs_base, "direction": "BUY"}, killzones=kz, now=now)
    bear = re_mod.setup_score({**inputs_base, "direction": "SELL"}, killzones=kz, now=now)

    sides = []
    if bull:
        sides.append(("BUY", bull))
    if bear:
        sides.append(("SELL", bear))
    sel_direction, best = max(sides, key=lambda s: s[1].get("score") or 0)
    score = best.get("score") or 0
    verdict = best.get("verdict") or ""

    # Use the scenario's requested direction, not auto-selected
    # (matching what the agent would do: it picks the direction it sees)
    if direction == "BUY":
        sel = bull
    else:
        sel = bear
    score = sel["score"]
    verdict = sel["verdict"]

    # Entry/SL/TP
    cp = current_price or scenario.get("current_price", 1.1040)
    sl_pips = float(cfg.get("sl_default_pips") or 15.0)
    tp_r = float(cfg.get("tp_ratio_r") or 2.0)
    pip_price = 0.0001

    if direction == "BUY":
        entry = cp
        sl = round(entry - sl_pips * pip_price, 5)
        tp = round(entry + sl_pips * pip_price * tp_r, 5)
    else:
        entry = cp
        sl = round(entry + sl_pips * pip_price, 5)
        tp = round(entry - sl_pips * pip_price * tp_r, 5)

    invalidation = re_mod.invalidation_level(patterns, direction)

    val = re_mod.validate_entry(
        entry=entry, sl=sl, target=tp, direction=direction,
        current_price=cp, invalidate_level=invalidation, cfg=cfg,
    )

    approved = bool(score >= min_score and val and val.get("approved"))
    reasons = []
    if not approved:
        if score < min_score:
            reasons.append(f"Score {score:.1f} < umbral {min_score:.0f}.")
        if val and val.get("reasons"):
            reasons.extend(val["reasons"])

    return {
        "direction": direction,
        "score": score,
        "verdict": verdict,
        "approved": approved,
        "val": val,
        "reasons": reasons,
        "entry": entry,
        "sl": sl,
        "tp": tp,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSetupEvalSweepValid:
    """sweep_valid_confluence: should be APPROVED."""

    def test_approved(self):
        sc = load_scenario("sweep_valid_confluence")
        r = evaluate_setup(sc)
        assert r["approved"] is True, f"Expected approved. Score={r['score']}, reasons={r['reasons']}"

    def test_score_above_threshold(self):
        sc = load_scenario("sweep_valid_confluence")
        r = evaluate_setup(sc)
        assert r["score"] >= 80.0

    def test_verdict_alta(self):
        sc = load_scenario("sweep_valid_confluence")
        r = evaluate_setup(sc)
        assert r["verdict"] == "ALTA_PROBABILIDAD"


class TestSetupEvalTrap:
    """trap_liquidity: should be REJECTED (low score, wrong killzone, wrong COT)."""

    def test_rejected(self):
        sc = load_scenario("trap_liquidity")
        r = evaluate_setup(sc)
        assert r["approved"] is False

    def test_score_below_threshold(self):
        sc = load_scenario("trap_liquidity")
        r = evaluate_setup(sc)
        assert r["score"] < 80.0


class TestSetupEvalKillzoneEdge:
    """killzone_edge_1min: should be APPROVED (inside NY at 13:00:00)."""

    def test_approved(self):
        sc = load_scenario("killzone_edge_1min")
        r = evaluate_setup(sc)
        assert r["approved"] is True, f"Expected approved at 13:00:00. Score={r['score']}"

    def test_killzone_inside(self):
        sc = load_scenario("killzone_edge_1min")
        now = datetime.fromisoformat(sc["now_utc"].replace("Z", "+00:00"))
        kz = re_mod.killzone_score(now=now)
        assert kz["in_killzone"] is True


class TestSetupEvalNoRR:
    """no_rr_reject: score good but R:R 1.5 < 2.0 → REJECTED."""

    def test_rejected(self):
        sc = load_scenario("no_rr_reject")
        r = evaluate_setup(sc)
        assert r["approved"] is False

    def test_rr_rejection_reason(self):
        sc = load_scenario("no_rr_reject")
        r = evaluate_setup(sc)
        # validate_entry should produce an R:R rejection
        assert any("R:R" in reason for reason in r["reasons"]), \
            f"Expected R:R in reasons, got: {r['reasons']}"


class TestSetupEvalMissingCVD:
    """missing_cvd: no CVD data → CVD component = 0, score reduced."""

    def test_cvd_component_zero(self):
        sc = load_scenario("missing_cvd")
        now = datetime.fromisoformat(sc["now_utc"].replace("Z", "+00:00"))
        candles = make_candles(**sc["candle_params"])
        r = re_mod.setup_score(
            {"direction": "BUY", "cot": sc["cot"], "cvd": None,
             "patterns": sc["patterns"], "candles": candles},
            killzones=sc.get("killzones", DEFAULT_KILLZONES), now=now,
        )
        assert r["components"]["cvd_of"]["value"] == 0.0

    def test_rejected(self):
        sc = load_scenario("missing_cvd")
        r = evaluate_setup(sc)
        assert r["approved"] is False


class TestSetupEvalContradictingCOT:
    """contradicting_cot: strong SMC but COT against → score reduced."""

    def test_cot_penalized(self):
        sc = load_scenario("contradicting_cot")
        now = datetime.fromisoformat(sc["now_utc"].replace("Z", "+00:00"))
        candles = make_candles(**sc["candle_params"])
        r = re_mod.setup_score(
            {"direction": "BUY", "cot": sc["cot"], "cvd": sc["cvd"],
             "patterns": sc["patterns"], "candles": candles},
            killzones=sc.get("killzones", DEFAULT_KILLZONES), now=now,
        )
        assert r["components"]["cot"]["value"] <= 0.20

    def test_rejected(self):
        sc = load_scenario("contradicting_cot")
        r = evaluate_setup(sc)
        assert r["approved"] is False


# ---------------------------------------------------------------------------
# Snapshot-level tests (full snapshot dict, like build_chart_snapshot produces)
# ---------------------------------------------------------------------------

class TestSnapshotShape:
    """Verify the mock snapshot has the same shape as build_chart_snapshot()."""

    def test_has_risk_engine(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        assert "risk_engine" in snap
        assert "bull" in snap["risk_engine"]
        assert "bear" in snap["risk_engine"]

    def test_has_cvd(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        assert "cvd" in snap
        assert isinstance(snap["cvd"], list)

    def test_has_patterns(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        assert "analysis" in snap
        assert "patterns" in snap["analysis"]

    def test_both_directions_scored(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        re_ = snap["risk_engine"]
        assert re_["bull"]["score"] > 0
        assert re_["bear"]["score"] > 0

    def test_invalidation_levels_computed(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        inv = snap["risk_engine"]["invalidation"]
        assert "BUY" in inv
        assert "SELL" in inv
        assert inv["BUY"] is not None  # we have bullish patterns


# ---------------------------------------------------------------------------
# Entry computation sanity
# ---------------------------------------------------------------------------

class TestEntryComputation:
    def test_buy_entry_equals_price(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc, current_price=1.1040)
        assert snap["_test_entry"] == 1.1040
        assert snap["_test_sl"] < snap["_test_entry"]
        assert snap["_test_tp"] > snap["_test_entry"]

    def test_sell_entry_equals_price(self):
        sc = load_scenario("trap_liquidity")
        sc["direction"] = "SELL"
        snap = make_snapshot_from_scenario(sc, current_price=1.1040)
        assert snap["_test_entry"] == 1.1040
        assert snap["_test_sl"] > snap["_test_entry"]
        assert snap["_test_tp"] < snap["_test_entry"]

    def test_rr_ratio_with_defaults(self):
        """With 15 pips SL and tp_ratio_r=2.0, R:R should be exactly 2.0."""
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc, current_price=1.1040)
        entry = snap["_test_entry"]
        sl = snap["_test_sl"]
        tp = snap["_test_tp"]
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / risk if risk > 0 else 0
        assert abs(rr - 2.0) < 0.01, f"Expected R:R ~2.0, got {rr}"
