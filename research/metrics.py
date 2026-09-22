"""research/metrics.py — métricas de una tanda de trades (puro, sin dependencias).

Recibe los trades del motor (research.sim) y agrega estadística útil para el
calibrador y el reporte: recuento por resultado, win rate, esperanza en R y pips,
profit factor, máximo drawdown de la curva de equity (tamaño de posición = riesgo
por trade), barras medias en pendiente/abierta, y desglose por dirección,
killzone y tipo de entrada.

Eventos sin fill (EXPIRED/CANCELLED) NO cuentan el pnl: se reportan por separado.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mini agregado sobre un subconjunto de trades."""
    closed = [t for t in trades if t.get("pnl_r") is not None]
    wins = [t for t in closed if t["pnl_r"] > 0]
    losses = [t for t in closed if t["pnl_r"] <= 0]
    n = len(trades)
    n_filled = len(closed)
    gross_win = sum(t["pnl_r"] for t in wins)
    gross_loss = -sum(t["pnl_r"] for t in losses)
    return {
        "n": n,
        "n_filled": n_filled,
        "n_expired": sum(1 for t in trades if t.get("status") == "EXPIRED"),
        "n_cancelled": sum(1 for t in trades if t.get("status") == "CANCELLED"),
        "n_open": sum(1 for t in trades if t.get("status") in ("OPEN", "PENDING")),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n_filled * 100.0) if n_filled else None,
        "expectancy_r": (sum(t["pnl_r"] for t in closed) / n_filled) if n_filled else None,
        "expectancy_pips": (sum(t["pnl_pips"] for t in closed) / n_filled) if n_filled else None,
        "avg_win_r": (sum(t["pnl_r"] for t in wins) / len(wins)) if wins else None,
        "avg_loss_r": (sum(t["pnl_r"] for t in losses) / len(losses)) if losses else None,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "max_dd_equity_pct": _max_dd_pct(trades),
        "avg_bars_pending": _avg(trades, "bars_pending") if n else None,
        "avg_bars_held": (_avg(trades, "bars_held")
                          if closed else None),
    }


def _max_dd_pct(trades: List[Dict[str, Any]]) -> Optional[float]:
    """DD máximo sobre la curva de equity (riesgo por trade = 1R con sizing)."""
    equity = 100.0
    peak = equity
    max_dd_pct = 0.0
    for t in trades:
        r = t.get("pnl_r")
        if r is None:
            continue
        # Tamaño de posición: 1R por trade -> equity *= (1 + r*risk_fraction).
        # Usamos un sizing unitario (fracción = 1%) para que el DD sea comparable
        # entre runs; el reporte final puede re-escalar con risk_pct real.
        size = 0.01
        equity *= (1.0 + float(r) * size)
        peak = max(peak, equity)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, (peak - equity) / peak * 100.0)
    return round(max_dd_pct, 2) if max_dd_pct else 0.0


def _avg(trades: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [float(t[key]) for t in trades if t.get(key) is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def compute_metrics(trades: List[Dict[str, Any]],
                    symbol: str = "EURUSD",
                    timeframe: str = "M15") -> Dict[str, Any]:
    """Agrega una tanda de trades del Sim en un dict de métricas plano."""
    trades = list(trades or [])
    total = _stats(trades)
    by_direction = {}
    for d in ("BUY", "SELL"):
        sub = [t for t in trades if t.get("direction") == d]
        if sub:
            by_direction[d] = _stats(sub)
    by_killzone: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        kz = str(t.get("killzone") or "?")
        sub = [x for x in trades if str(x.get("killzone") or "?") == kz]
        if kz not in by_killzone:
            by_killzone[kz] = _stats(sub)
    by_entry_kind: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        k = str(t.get("entry_kind") or "?")
        sub = [x for x in trades if str(x.get("entry_kind") or "?") == k]
        if k not in by_entry_kind:
            by_entry_kind[k] = _stats(sub)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        **total,
        "by_direction": by_direction,
        "by_killzone": by_killzone,
        "by_entry_kind": by_entry_kind,
    }