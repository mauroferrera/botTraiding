#!/usr/bin/env python3
"""CLI runner for mock scenario tests with human-readable summary.

Usage:
  python tests/run_scenarios.py              # run all scenarios
  python tests/run_scenarios.py sweep_valid  # run one scenario by partial name

Produces a colored summary table showing each scenario's verdict, score, and
whether it was approved/rejected as expected.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 output on Windows consoles (characters like í/é/≥ otherwise fail)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure parent dir is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import risk_engine as re_mod
from conftest import (
    load_scenario, make_candles, make_cvd_from_candles,
    make_snapshot_from_scenario, DEFAULT_KILLZONES, SCENARIOS_DIR,
)

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run_scenario(name: str) -> dict:
    """Run a single scenario and return results."""
    sc = load_scenario(name)
    now = datetime.fromisoformat(sc["now_utc"].replace("Z", "+00:00"))
    kz = sc.get("killzones", DEFAULT_KILLZONES)
    cot = sc.get("cot")
    cvd = sc.get("cvd")
    patterns = sc.get("patterns", {"fvgs": [], "order_blocks": [], "sweeps": []})
    cfg = sc.get("cfg", {})
    direction = sc.get("direction", "BUY")

    candle_params = sc.get("candle_params", {})
    candles = make_candles(**candle_params)
    if "cvd" not in sc:
        cvd = make_cvd_from_candles(candles)

    inputs_base = {"cot": cot, "cvd": cvd, "patterns": patterns, "candles": candles}
    result = re_mod.setup_score(
        {**inputs_base, "direction": direction}, killzones=kz, now=now,
    )

    # validate_entry
    cp = sc.get("current_price", 1.1040)
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

    min_score = float(cfg.get("min_score") or 80.0)
    approved = bool(result["score"] >= min_score and val.get("approved"))

    return {
        "name": name,
        "description": sc.get("description", ""),
        "direction": direction,
        "time_utc": sc["now_utc"],
        "score": result["score"],
        "verdict": result["verdict"],
        "approved": approved,
        "killzone": result["components"]["killzone"],
        "cot_value": result["components"]["cot"]["value"],
        "cvd_value": result["components"]["cvd_of"]["value"],
        "smc_value": result["components"]["smc"]["value"],
        "validate": val,
        "expected_approved": sc.get("expected", {}).get("approved"),
    }


def print_result(r: dict, idx: int):
    """Print a single scenario result."""
    exp = r["expected_approved"]
    got = r["approved"]
    match = (exp is None) or (exp == got)
    status_color = GREEN if match else RED
    status = "PASS" if match else "FAIL"

    kz_name = r["killzone"].get("name") or "---"
    kz_inside = "IN" if r["killzone"].get("in_killzone") else "OUT"

    print(f"  {status_color}{BOLD}[{status}]{RESET} {r['name']}")
    print(f"       {r['description']}")
    print(
        f"       {CYAN}{r['time_utc']}{RESET} | "
        f"Dir={r['direction']} | KZ={kz_name} ({kz_inside}) | "
        f"Score={BOLD}{r['score']}{RESET} | Verdict={r['verdict']}"
    )
    print(
        f"       Components: COT={r['cot_value']:.2f} | "
        f"CVD={r['cvd_value']:.2f} | SMC={r['smc_value']:.2f} | "
        f"Killzone={r['killzone']['value']:.2f}"
    )

    approved_str = f"{GREEN}APPROVED{RESET}" if got else f"{RED}REJECTED{RESET}"
    print(f"       Decision: {approved_str}")

    if not match:
        print(
            f"       {RED}MISMATCH: expected={'APPROVED' if exp else 'REJECTED'}, "
            f"got={'APPROVED' if got else 'REJECTED'}{RESET}"
        )

    if r["validate"]["reasons"]:
        for reason in r["validate"]["reasons"]:
            print(f"         - {reason}")

    print()


def main():
    filter_name = sys.argv[1] if len(sys.argv) > 1 else None

    # Discover scenarios
    scenario_files = sorted(SCENARIOS_DIR.glob("*.json"))
    names = [f.stem for f in scenario_files]

    if filter_name:
        names = [n for n in names if filter_name in n]
        if not names:
            print(f"No scenarios matching '{filter_name}'")
            sys.exit(1)

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  MOCK SCENARIO TEST RUNNER{RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    results = []
    for name in names:
        try:
            r = run_scenario(name)
            results.append(r)
            print_result(r, len(results))
        except Exception as e:
            print(f"  {RED}[ERROR]{RESET} {name}: {e}\n")
            results.append({"name": name, "error": str(e)})

    # Summary
    passed = sum(1 for r in results if not r.get("error") and
                 (r.get("expected_approved") is None or r["expected_approved"] == r["approved"]))
    failed = sum(1 for r in results if r.get("error") or
                 (r.get("expected_approved") is not None and r["expected_approved"] != r["approved"]))
    total = len(results)

    print(f"{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"  Total: {total} | {GREEN}Passed: {passed}{RESET} | {RED}Failed: {failed}{RESET}")

    if failed:
        print(f"\n  {RED}Some scenarios FAILED. Review the output above.{RESET}")
        sys.exit(1)
    else:
        print(f"\n  {GREEN}All scenarios PASSED!{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
