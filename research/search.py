"""research/search.py — grid search determinista de parámetros.

Barre combinaciones de parámetros sobre el motor de backtest (research.sim) y
devuelve las N mejores configuraciones por un ranking transparente:

  1. Prioridad dura: al menos `min_filled` trades cerrados (muestra pequeña =
     ruido, se penaliza fuerte).
  2. Esperanza en R (mayor gana).
  3. Desempate: profit factor, luego menor max DD.

`n_approved` (ordenes aprobadas) y `n_filled` (fills) se exponen en cada fila
para que el usuario/auditor vea el coste de oportunidad de cada configuración.
Los resultados NUNCA se aplican solos: `search` solo ordena y guarda.
"""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Optional

from research import metrics as rm
from research import sim

_METRIC_KEYS = (
    "n", "n_filled", "n_expired", "n_cancelled", "wins", "losses",
    "win_rate", "expectancy_r", "expectancy_pips", "avg_win_r",
    "avg_loss_r", "profit_factor", "max_dd_equity_pct",
)

DEFAULT_GRID: Dict[str, List[Any]] = {
    "setup_ttl_minutes": [20, 30],
    "min_score": [65, 70, 75, 80],
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def row_rank(m: Dict[str, Any], min_filled: int = 10) -> float:
    """Ranking transparente de una fila de métricas (ver docstring del módulo)."""
    n_filled = int(m.get("n_filled") or 0)
    e = float(m.get("expectancy_r") or 0.0)
    pf = m.get("profit_factor")
    pf = float(pf) if pf is not None else 0.0
    dd = float(m.get("max_dd_equity_pct") or 0.0)
    if n_filled < min_filled:
        # Muestra insuficiente: abajo del ranking, pero ordenada por E dentro del grupo.
        return -1000.0 + e - dd / 100.0
    return e * 10.0 + _clamp(pf, 0.0, 3.0) - dd * 0.02


def search_grid(candles: List[Dict[str, Any]],
                base_cfg: Dict[str, Any],
                grid: Optional[Dict[str, List[Any]]] = None,
                top_n: int = 5,
                min_filled: int = 10,
                symbol: str = "EURUSD",
                timeframe: str = "M15") -> Dict[str, Any]:
    """Barre `grid` (dict param -> lista de valores) y devuelve el ranking Top-N.

    El producto cartesiano de `grid` se aplica sobre `base_cfg` (default_cfg de
    la config vigente). `top_n=1` devuelve el mejor + la configuración base como
    referencia para comparar.
    """
    grid = dict(grid or DEFAULT_GRID)
    keys = [k for k in grid if grid[k]]
    values = [grid[k] for k in keys]
    combos = [dict(zip(keys, vals)) for vals in product(*values)]
    baseline = {k: base_cfg.get(k) for k in keys}

    rows: List[Dict[str, Any]] = []
    for combo in combos:
        cfg = dict(base_cfg)
        cfg.update(combo)
        try:
            bt = sim.BarBacktest(candles, cfg=cfg)
            res = bt.run()
        except Exception as exc:  # defensivo: una combinación no rompe el barrido
            rows.append({"params": combo, "metrics": None, "rank": None,
                         "error": str(exc)})
            continue
        m = rm.compute_metrics(res["trades"], symbol=symbol, timeframe=timeframe)
        rows.append({
            "params": combo,
            "metrics": {k: m.get(k) for k in _METRIC_KEYS},
            "rank": round(row_rank(m, min_filled), 4),
            "underpowered": int(m.get("n_filled") or 0) < min_filled,
        })

    rows.sort(key=lambda r: (r.get("rank") is not None, r.get("rank", -1e9)),
              reverse=True)

    return {
        "base": baseline,
        "grid": grid,
        "combos": len(combos),
        "min_filled": int(min_filled),
        "total": len(rows),
        "results": rows[:max(1, int(top_n))],
    }