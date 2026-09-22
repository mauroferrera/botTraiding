"""Shared fixtures and data factories for Trading mock scenario tests.

Provides:
  - load_scenario(name): load JSON from tests/scenarios/
  - make_candles(base_price, count, bias, spread): deterministic OHLCV generation
  - make_cvd_from_candles(candles): convert candles to CVD [{time, value}] format
  - make_snapshot_from_scenario(scenario, current_price): build a full mock snapshot
    matching the shape that build_chart_snapshot() returns
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

DEFAULT_KILLZONES: List[Dict[str, str]] = [
    {"name": "Londres", "start": "08:00", "end": "11:00"},
    {"name": "Nueva York", "start": "13:00", "end": "16:00"},
]


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------

def load_scenario(name: str) -> Dict[str, Any]:
    """Load a scenario JSON by name (without .json extension)."""
    path = SCENARIOS_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Candle factory
# ---------------------------------------------------------------------------

def make_candles(
    base_price: float = 1.1030,
    count: int = 20,
    bias: str = "bullish",
    spread: float = 0.0003,
    seed_increment: float = 0.00015,
) -> List[Dict[str, Any]]:
    """Generate deterministic OHLCV candle array.

    bias:
      'bullish'  -> close > open (most candles), upward drift
      'bearish'  -> open > close (most candles), downward drift
      'neutral'  -> small bodies, equal up/down

    Returns list of {time, open, high, low, close, volume}.
    time is sequential epoch starting at 1000000 (arbitrary, tests don't use real time).
    """
    candles: List[Dict[str, Any]] = []
    price = base_price

    for i in range(count):
        t = 1_000_000 + i * 900  # 15-min spacing

        if bias == "bullish":
            drift = seed_increment * (0.8 + 0.4 * (i % 3) / 2)
            o = price
            c = price + drift
            h = c + spread * 0.4
            l = o - spread * 0.2
        elif bias == "bearish":
            drift = seed_increment * (0.8 + 0.4 * (i % 3) / 2)
            o = price
            c = price - drift
            h = o + spread * 0.2
            l = c - spread * 0.4
        else:
            o = price
            c = price + (spread * 0.1 if i % 2 == 0 else -spread * 0.1)
            h = max(o, c) + spread * 0.15
            l = min(o, c) - spread * 0.15

        candles.append({
            "time": t,
            "open": round(o, 5),
            "high": round(h, 5),
            "low": round(l, 5),
            "close": round(c, 5),
            "volume": 500 + i * 50,
        })
        price = c

    return candles


# ---------------------------------------------------------------------------
# CVD factory
# ---------------------------------------------------------------------------

def make_cvd_from_candles(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OHLCV candles to CVD [{time, value}].

    Simulates cumulative delta: positive when close > open, negative otherwise.
    The *slope* of the result is what the risk engine evaluates.
    """
    cumulative = 0.0
    points: List[Dict[str, Any]] = []
    for c in candles:
        body = c["close"] - c["open"]
        cumulative += body * 100_000  # scale to realistic CVD magnitudes
        points.append({"time": c["time"], "value": round(cumulative, 2)})
    return points


def make_flat_cvd(count: int = 20, base_value: float = 0.0) -> List[Dict[str, Any]]:
    """CVD series with zero slope (all values identical)."""
    return [{"time": 1_000_000 + i * 900, "value": base_value} for i in range(count)]


# ---------------------------------------------------------------------------
# Order-flow trades factory
# ---------------------------------------------------------------------------

def make_trades(
    count: int = 120,
    base_price: float = 1.0985,
    side_bias: Optional[float] = None,
    size_range: tuple = (4, 7),
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Generate deterministic order-flow trades [{ts, price, size, side}].

    side_bias = probability of "A" (buy aggressor). When None -> 50/50.
    `side` comes from a local random.Random(seed): same args -> same sequence.
    """
    rng = random.Random(seed)
    price = base_price
    trades: List[Dict[str, Any]] = []
    for i in range(count):
        side = "A" if rng.random() < (side_bias if side_bias is not None else 0.5) else "B"
        size = rng.randint(*size_range)
        price += rng.uniform(-base_price * 0.00004, base_price * 0.00004)
        trades.append({
            "ts": 1_700_000_000 + i,
            "price": round(price, 5),
            "size": size,
            "side": side,
        })
    return trades


def make_rising_cvd(count: int = 20, start: float = -500.0, step: float = 120.0) -> List[Dict[str, Any]]:
    """CVD series with clear positive slope."""
    return [{"time": 1_000_000 + i * 900, "value": round(start + i * step, 2)} for i in range(count)]


def make_falling_cvd(count: int = 20, start: float = 500.0, step: float = 120.0) -> List[Dict[str, Any]]:
    """CVD series with clear negative slope."""
    return [{"time": 1_000_000 + i * 900, "value": round(start - i * step, 2)} for i in range(count)]


# ---------------------------------------------------------------------------
# Snapshot builder (matches build_chart_snapshot shape)
# ---------------------------------------------------------------------------

def make_snapshot_from_scenario(
    scenario: Dict[str, Any],
    current_price: float = 1.1045,
    killzones: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build a full mock snapshot dict matching the shape build_chart_snapshot() returns.

    This is used by Layer 2 (setup_eval) and Layer 3 (agent_guard) tests.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import risk_engine as re_mod

    direction = scenario.get("direction", "BUY")
    now_str = scenario.get("now_utc", "2026-09-07T14:15:00Z")
    now_dt = datetime.fromisoformat(now_str.replace("Z", "+00:00"))

    kz = killzones or DEFAULT_KILLZONES
    cot = scenario.get("cot")
    cvd = scenario.get("cvd")
    patterns = scenario.get("patterns", {"fvgs": [], "order_blocks": [], "sweeps": []})

    # Generate candles from scenario params or use provided ones
    candle_params = scenario.get("candle_params", {})
    candles = make_candles(
        base_price=candle_params.get("base_price", current_price - 0.001),
        count=candle_params.get("count", 20),
        bias=candle_params.get("bias", "bullish"),
    )

    # Compute risk engine for both directions
    inputs_base = {"cot": cot, "cvd": cvd, "patterns": patterns, "candles": candles}
    bull = re_mod.setup_score({**inputs_base, "direction": "BUY"}, killzones=kz, now=now_dt)
    bear = re_mod.setup_score({**inputs_base, "direction": "SELL"}, killzones=kz, now=now_dt)

    best = bull if direction == "BUY" else bear
    invalidation = re_mod.invalidation_level(patterns, direction)

    # Compute entry / SL / TP
    cfg = scenario.get("cfg", {})
    sl_pips = float(cfg.get("sl_default_pips") or 15.0)
    tp_r = float(cfg.get("tp_ratio_r") or 2.0)
    pip_price = 0.0001

    if direction == "BUY":
        entry = current_price
        sl = round(entry - sl_pips * pip_price, 5)
        tp = round(entry + sl_pips * pip_price * tp_r, 5)
    else:
        entry = current_price
        sl = round(entry + sl_pips * pip_price, 5)
        tp = round(entry - sl_pips * pip_price * tp_r, 5)

    # Build the snapshot matching build_chart_snapshot() shape
    snap = {
        "symbol": scenario.get("symbol", "EURUSD"),
        "timeframe": scenario.get("timeframe", "M15"),
        "time": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "current_price": current_price,
        "PDH": round(current_price + 0.003, 5),
        "PDL": round(current_price - 0.003, 5),
        "recent_candles": [
            {"time": datetime.fromtimestamp(c["time"]).strftime("%H:%M"),
             "close": c["close"], "high": c["high"], "low": c["low"], "volume": c["volume"]}
            for c in candles[-5:]
        ],
        "analysis": {"patterns": patterns},
        "cvd": cvd,
        "cvd_source": "synthetic (tick volume MT5)",
        "cot_macro_analysis": cot,
        "risk_engine": {
            "bull": bull,
            "bear": bear,
            "killzone": bull["components"]["killzone"],
            "regime": bull["regime"],
            "invalidation": {
                "BUY": re_mod.invalidation_level(patterns, "BUY"),
                "SELL": re_mod.invalidation_level(patterns, "SELL"),
            },
        },
        "_test_entry": entry,
        "_test_sl": sl,
        "_test_tp": tp,
        "_test_direction": direction,
        "_test_invalidation": invalidation,
        "_test_best": best,
    }
    return snap


# ---------------------------------------------------------------------------
# Parametrized scenario fixture for pytest
# ---------------------------------------------------------------------------

ALL_SCENARIOS = [
    "sweep_valid_confluence",
    "trap_liquidity",
    "killzone_edge_1min",
    "no_rr_reject",
    "missing_cvd",
    "contradicting_cot",
]


@pytest.fixture(params=ALL_SCENARIOS)
def scenario_name(request):
    return request.param


@pytest.fixture
def scenario(scenario_name):
    return load_scenario(scenario_name)
