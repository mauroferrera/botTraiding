"""research/validate.py — integridad y no-look-ahead de un dataset research.

Chequea un dataset cargado (research.data.load_dataset) ANTES de darle valor a
un backtest: tiempos monótonos y sin duplicados, presencia de PDH/PDL,
consistencia del timeframe y, sobre todo, la INVARIANTE de no-look-ahead:

  evaluate_at(candles, i, cfg) == evaluate_at(candles[:i+1], i, cfg)

es decir, la evaluación en el bar i NUNCA puede cambiar porque existan velas
posteriores. Se muestrean bares repartidos por el dataset (determinista).
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from research import sim

_GATE_FIELDS = ("direction", "score", "approved", "entry", "sl", "tp",
                "killzone_name", "entry_kind", "invalidate_level")

_DEFAULT_SAMPLE = 200


def _compare_gates(full: Optional[Dict[str, Any]],
                   prefix: Optional[Dict[str, Any]]) -> List[str]:
    if full is None and prefix is None:
        return []
    if full is None or prefix is None:
        return ["gate_presence"]
    mism = [f for f in _GATE_FIELDS
            if full.get(f) != prefix.get(f)]
    if (full.get("components") or {}) != (prefix.get("components") or {}):
        mism.append("components")
    return mism


def _sample_indices(n: int, sample: int, lookback: int) -> List[int]:
    """Índices repartidos uniformemente en [lookback, n-2] (determinista)."""
    lo = max(lookback, 0)
    hi = n - 2
    if hi <= lo:
        return []
    sample = max(1, min(int(sample), hi - lo + 1))
    step = (hi - lo) / sample
    return [lo + int(round(i * step)) for i in range(sample)]


def validate_dataset(candles: List[Dict[str, Any]], cfg: Dict[str, Any],
                     sample: int = _DEFAULT_SAMPLE) -> Dict[str, Any]:
    """Devuelve el dict de checks + mismatches (nunca lanza por contenido)."""
    candles = list(candles or [])
    n = len(candles)
    checks: Dict[str, bool] = {}
    warnings: List[str] = []

    times = [int(c["time"]) for c in candles]
    checks["monotonic"] = (n > 0 and all(times[i] > times[i - 1]
                                         for i in range(1, n)))

    checks["keys"] = n > 0 and all("pdh" in c and "pdl" in c for c in candles)

    tf_sec = None
    if n >= 2:
        diffs = [abs(times[i] - times[i - 1]) for i in range(1, n)]
        tf_sec = float(statistics.median(diffs))
        # Huecos > 2x el TF mediano = saltos por weekend/festivo. Normal hasta un
        # ~1% de las velas (13 fines de semana en 90d de M15 ≈ 13 huecos).
        irregular = [d for d in diffs if d > tf_sec * 2]
        checks["tf_consistent"] = len(irregular) <= max(5, int(n * 0.01))
        if len(irregular) > 0:
            warnings.append(
                f"{len(irregular)} focal de velas con huecos > {tf_sec:.0f}s "
                "(festivos/fin de semana; normal si es M15..H1)."
            )

    lookback = max(1, int(cfg.get("lookback", 300)))
    idx = _sample_indices(n, sample, lookback)
    mismatches: List[Dict[str, Any]] = []
    for i in idx:
        full = sim.evaluate_at(candles, i, cfg)
        prefix = sim.evaluate_at(candles[: i + 1], i, cfg)
        diffs = _compare_gates(full, prefix)
        if diffs:
            mismatches.append({"i": i, "ts": times[i], "fields": diffs,
                               "gate_full": full is not None,
                               "gate_prefix": prefix is not None})
    checks["lookahead"] = len(mismatches) == 0

    if n < max(lookback, 3):
        warnings.append(
            f"Solo {n} velas: menos de referencia usable con lookback {lookback}."
        )
    if not checks["monotonic"]:
        warnings.append("Tiempos no monótonos o con duplicados: revisa la fusión de CSV.")
    if not checks["keys"]:
        warnings.append("Algún bar sin pdh/pdl: no pasó por with_daily_levels/load_dataset.")

    return {
        "n_bars": n,
        "tf_sec": round(tf_sec, 1) if tf_sec else None,
        "lookahead_checked": len(idx),
        "lookahead_mismatches": mismatches,
        "checks": checks,
        "warnings": warnings,
    }


def summarize(result: Dict[str, Any]) -> str:
    """Una línea por check para el CLI."""
    labels = {
        "monotonic": "tiempos monótonos",
        "keys": "PDH/PDL por bar",
        "tf_consistent": "timeframe consistente",
        "lookahead": "no-look-ahead",
    }
    out = [f"  {result['n_bars']} velas"
           + (f" @ {result['tf_sec']:.0f}s" if result.get("tf_sec") else "")
           + f" | {result['lookahead_checked']} bares muestreados"]
    for k, label in labels.items():
        ok = result["checks"].get(k, False)
        out.append(f"  [{'OK' if ok else 'FALLO':>5}] {label}")
    for w in result.get("warnings") or []:
        out.append(f"  ! {w}")
    return "\n".join(out)