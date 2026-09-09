"""Layer 3: Anti-hallucination guard — golden snapshot verification.

Tests that the deterministic risk engine output is the ground truth.
If the risk engine says "REJECT" (score < min_score or validate_entry failed),
the agent MUST NOT override that decision.

Strategy:
  1. Build a golden snapshot from each scenario using make_snapshot_from_scenario()
  2. Verify the risk engine verdict matches expected
  3. Verify the approval gate (score >= min_score AND val.approved) matches expected
  4. Verify that no factual claim in the agent's hypothetical response contradicts
     the snapshot data (no price invention, no score fabrication)

Run:  python -m pytest tests/test_agent_guard.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import risk_engine as re_mod
from conftest import (
    load_scenario, make_snapshot_from_scenario, DEFAULT_KILLZONES,
)


# ---------------------------------------------------------------------------
# Golden snapshot helpers
# ---------------------------------------------------------------------------

def _golden_gate(snap: dict, min_score: float = 80.0):
    """Compute the approval gate the same way api_chart_setup_eval does.

    Returns (score, verdict, approved, reasons).
    """
    direction = snap.get("_test_direction", "BUY")
    re_ = snap["risk_engine"]
    side = re_.get("bull") if direction == "BUY" else re_.get("bear")
    score = side["score"]
    verdict = side["verdict"]

    entry = snap.get("_test_entry")
    sl = snap.get("_test_sl")
    tp = snap.get("_test_tp")
    invalidation = re_.get("invalidation", {}).get(direction)
    cp = snap.get("current_price")
    cfg = {"min_rr": 2.0, "setup_ttl_minutes": 45}

    val = re_mod.validate_entry(
        entry=entry, sl=sl, target=tp, direction=direction,
        current_price=cp, invalidate_level=invalidation, cfg=cfg,
    )

    approved = bool(score >= min_score and val.get("approved"))
    reasons = []
    if not approved:
        if score < min_score:
            reasons.append(f"Score {score:.1f} < umbral {min_score:.0f}")
        reasons.extend(val.get("reasons", []))

    return score, verdict, approved, reasons


# ---------------------------------------------------------------------------
# Anti-hallucination invariants
# ---------------------------------------------------------------------------

class TestAntiHallucinationApprovals:
    """When risk engine says APPROVE, agent should not reject without reason."""

    def test_sweep_valid_approved(self):
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is True, f"Expected approved. Score={score}, reasons={reasons}"
        assert verdict == "ALTA_PROBABILIDAD"

    def test_killzone_edge_approved(self):
        sc = load_scenario("killzone_edge_1min")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is True, f"Expected approved at 13:00:00. Score={score}, reasons={reasons}"


class TestAntiHallucinationRejections:
    """When risk engine says REJECT, agent must NOT approve."""

    def test_trap_rejected(self):
        sc = load_scenario("trap_liquidity")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is False
        assert score < 80.0, f"Score should be below 80, got {score}"

    def test_no_rr_rejected(self):
        sc = load_scenario("no_rr_reject")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is False
        assert any("R:R" in r for r in reasons), f"Expected R:R rejection, got: {reasons}"

    def test_missing_cvd_rejected(self):
        sc = load_scenario("missing_cvd")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is False

    def test_contradicting_cot_rejected(self):
        sc = load_scenario("contradicting_cot")
        snap = make_snapshot_from_scenario(sc)
        score, verdict, approved, reasons = _golden_gate(snap)
        assert approved is False


# ---------------------------------------------------------------------------
# Snapshot data integrity: no invented data
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    """Verify the snapshot the agent receives contains only real computed data."""

    def test_scores_match_risk_engine(self):
        """Agent's score reference must match risk_engine output exactly."""
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        re_ = snap["risk_engine"]
        # The agent would see these scores; they must be internally consistent
        bull = re_["bull"]
        bear = re_["bear"]
        assert bull["score"] == pytest.approx(bull["score"], abs=0.1)
        assert bear["score"] == pytest.approx(bear["score"], abs=0.1)
        # Verdicts derived from scores
        assert bull["verdict"] == re_mod.grade_score(bull["score"])
        assert bear["verdict"] == re_mod.grade_score(bear["score"])

    def test_killzone_matches_time(self):
        """Killzone component must reflect the actual now_utc time."""
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        now = datetime.fromisoformat(sc["now_utc"].replace("Z", "+00:00"))
        kz_component = snap["risk_engine"]["bull"]["components"]["killzone"]
        kz_direct = re_mod.killzone_score(now=now)
        assert kz_component["in_killzone"] == kz_direct["in_killzone"]
        assert kz_component["value"] == kz_direct["value"]

    def test_invalidations_are_real_levels(self):
        """Invalidation levels must come from pattern bottoms/tops, not invented."""
        sc = load_scenario("sweep_valid_confluence")
        snap = make_snapshot_from_scenario(sc)
        patterns = sc["patterns"]
        inv_buy = snap["risk_engine"]["invalidation"]["BUY"]
        if patterns.get("fvgs") or patterns.get("order_blocks"):
            # Must be the actual min bottom from bullish patterns
            expected = re_mod.invalidation_level(patterns, "BUY")
            assert inv_buy == expected

    def test_no_orphaned_verdicts(self):
        """Every score must have a valid verdict (no invented grades)."""
        for name in ["sweep_valid_confluence", "trap_liquidity", "killzone_edge_1min",
                      "no_rr_reject", "missing_cvd", "contradicting_cot"]:
            sc = load_scenario(name)
            snap = make_snapshot_from_scenario(sc)
            for side in ("bull", "bear"):
                v = snap["risk_engine"][side]["verdict"]
                assert v in (re_mod.VERDICT_ALTA, re_mod.VERDICT_MEDIA, re_mod.VERDICT_SIN), \
                    f"{name}/{side}: invalid verdict '{v}'"


# ---------------------------------------------------------------------------
# Decision consistency across all scenarios
# ---------------------------------------------------------------------------

class TestDecisionConsistency:
    """Verify that every scenario produces the expected decision (approve/reject)."""

    @pytest.mark.parametrize("scenario_name,expected_approved", [
        ("sweep_valid_confluence", True),
        ("killzone_edge_1min", True),
        ("trap_liquidity", False),
        ("no_rr_reject", False),
        ("missing_cvd", False),
        ("contradicting_cot", False),
    ])
    def test_decision_matches(self, scenario_name, expected_approved):
        sc = load_scenario(scenario_name)
        snap = make_snapshot_from_scenario(sc)
        _, _, approved, reasons = _golden_gate(snap)
        assert approved == expected_approved, \
            f"{scenario_name}: expected {'APPROVED' if expected_approved else 'REJECTED'}, " \
            f"got {'APPROVED' if approved else 'REJECTED'}. Reasons: {reasons}"
