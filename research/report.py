"""research/report.py — renderizado legible de una corrida de research.

Trabaja sobre el payload JSON del pipeline (run + metrics + breakdowns) tal como
lo escribe `backtest`/`calibrate`. `render_report()` devuelve un texto plano
tabular en UTF-8, apto para consola y `--out <archivo>`.

No toca strategy.yaml ni el runtime: es presentación pura.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DIR_HDR = {"WIN": "TP", "LOSS": "SL"}

_STATUS_ORDER = ("WIN", "LOSS", "EXPIRED", "CANCELLED", "OPEN", "PENDING")


def _human_ts(ts) -> str:
    if ts is None:
        return "-"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(ts)


def _fmt(v: Any, width: int = 8) -> str:
    if v is None:
        return "-" * width if width else "-"
    if isinstance(v, float):
        txt = f"{v:.4f}" if abs(v) >= 1 or v == 0 else f"{v:.6f}"
    else:
        txt = str(v)
    return (txt + " " * width)[:width]


def render_trades_table(trades: List[Dict[str, Any]], max_rows: int = 60) -> str:
    hdr = ["#", "hora", "dir", "st", "entrada", "salida", "pnlR", "pnlP",
           "pend.", "abierta", "KZ", "tipo"]
    rows = [hdr, ["-"] * len(hdr)]
    closed = [t for t in trades if t.get("status") in ("WIN", "LOSS")]
    events = [t for t in trades if t.get("status") not in ("WIN", "LOSS")]
    shown = closed + events
    truncated = len(shown) - max_rows
    if truncated > 0:
        shown = shown[:max_rows]
    for t in shown:
        status = t.get("status") or "?"
        exit_r = _DIR_HDR.get(status, t.get("exit_reason") or status)
        rows.append([
            str(t.get("id")),
            _human_ts(t.get("signal_ts")),
            str(t.get("direction")),
            exit_r,
            _fmt(t.get("entry_price")),
            _fmt(t.get("exit_price")),
            _fmt(t.get("pnl_r")),
            _fmt(t.get("pnl_pips")),
            str(t.get("bars_pending")),
            (str(t.get("bars_held")) if t.get("bars_held") is not None else "-"),
            str(t.get("killzone") or "-"),
            str(t.get("entry_kind") or "-"),
        ])
    widths = [max(len(r[i]) for r in rows) for i in range(len(hdr))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows]
    if truncated > 0:
        lines.append(f"  ... {truncated} trades más")
    return "\n".join(lines)


def _metrics_block(m: Dict[str, Any]) -> List[str]:
    def p(rows: List[List[str]]) -> List[str]:
        w = [max(len(c[0]) for c in rows), max(len(c[1]) for c in rows)]
        return [c[0].ljust(w[0]) + "  " + c[1].rjust(w[1]) for c in rows]

    rows = [
        ["aprobadas", f"{m.get('n', 0)}  (filled {m.get('n_filled', 0)} / "
                      f"expired {m.get('n_expired', 0)} / "
                      f"cancelled {m.get('n_cancelled', 0)} / "
                      f"open {m.get('n_open', 0)})"],
        ["win rate", f"{m['win_rate']:.1f}%  ({m.get('wins', 0)}/{m.get('n_filled', 0)})"
                     if m.get("win_rate") is not None else "n/d"],
        ["expectancy", f"{m['expectancy_r']:+.2f}R  ({m['expectancy_pips']:+.1f} pips)"
                       if m.get("expectancy_r") is not None else "n/d"],
        ["avg win/loss", (f"{m['avg_win_r']:.2f}R / {m['avg_loss_r']:.2f}R"
                          if m.get("avg_win_r") is not None
                          and m.get("avg_loss_r") is not None else "n/d")],
        ["profit factor", f"{m['profit_factor']:.2f}"
                          if m.get("profit_factor") is not None else "n/d"],
        ["max DD (1%)", f"{m.get('max_dd_equity_pct', 0.0)}%"],
        ["barras pend./abierta", f"{m.get('avg_bars_pending')} / {m.get('avg_bars_held')}"],
    ]
    return p(rows)


def _breakdown_block(breakdowns: Dict[str, Any]) -> List[str]:
    lines = []
    for label, by in (("por dirección", breakdowns.get("by_direction")),
                      ("por killzone", breakdowns.get("by_killzone")),
                      ("por tipo entrada", breakdowns.get("by_entry_kind"))):
        if not by:
            continue
        lines.append(label)
        for k, b in by.items():
            wr = f"{b['win_rate']:.1f}%" if b.get("win_rate") is not None else "n/d"
            ex = f"{b['expectancy_r']:+.2f}R" if b.get("expectancy_r") is not None else "n/d"
            lines.append(f"  {str(k):<12} n={b.get('n', 0):<4}"
                         f" filled={b.get('n_filled', 0):<4}"
                         f" WR {wr:<6} E={ex}")
    return lines


def _suggest_block(suggestions: Optional[List[Dict[str, Any]]],
                   warnings: Optional[List[str]]) -> List[str]:
    lines = []
    if warnings:
        lines.append("AVISOS")
        for w in warnings:
            lines.append(f"  ! {w}")
    if not suggestions:
        return lines
    lines.append("SUGERENCIAS vs strategy.yaml (no se aplican solas)")
    lines.append(f"  {'clave':<22} {'actual':<18} {'sugerido':<18} confianza")
    for s in suggestions:
        cur = s.get("current")
        sug = s.get("suggested")
        if isinstance(cur, dict) or isinstance(sug, dict):
            lines.append(f"  {s['key']:<22} (ver items)   confianza: {s.get('confidence')}")
        else:
            lines.append(f"  {s['key']:<22} {str(cur):<18} {str(sug):<18} {s.get('confidence')}")
        lines.append(f"      {s.get('path')}  ->  {s.get('reason')}")
        for it in s.get("items") or []:
            lines.append(
                f"      · {it['component']:<8} peso {it['weight']:>5} "
                f"delta {it['delta_points']:+d}  "
                f"(wins {it['n_wins']}/{it['wins_mean']} · "
                f"loss {it['n_losses']}/{it['losses_mean']})")
    return lines


def render_report(run: Dict[str, Any], metrics: Dict[str, Any],
                  breakdowns: Optional[Dict[str, Any]] = None,
                  suggestions: Optional[List[Dict[str, Any]]] = None,
                  warnings: Optional[List[str]] = None,
                  max_rows: int = 40) -> str:
    """Devuelve el reporte completo en texto plano a partir del payload del run."""
    tf_sec = run.get("tf_sec") or 0
    tf_label = f"{tf_sec:.0f}s" if tf_sec else "-"
    cfg = run.get("cfg") or {}
    lookback = cfg.get("lookback")
    hdr = (f"Backtest {metrics.get('symbol', '?')} {metrics.get('timeframe', '?')}  "
           f"{run.get('n_bars', 0)} velas @ {tf_label}  "
           f"[{_human_ts(run.get('start_ts'))} → {_human_ts(run.get('end_ts'))}]")
    pip = run.get("pip") or 0.0001
    rules = (f"spread {run.get('spread', 0.0) / pip:<6.2f} pips · "
             f"slippage {run.get('slip', 0.0) / pip:<6.2f} pips · "
             f"TTL {run.get('ttl_bars', '-')} velas · "
             f"lookback {lookback if lookback is not None else '-'}")
    out = [
        hdr,
        rules,
        "=" * max(len(hdr), len(rules)),
        "",
        *[f"  {k}" for k in _metrics_block(metrics or {})],
        "",
        *_breakdown_block(breakdowns or {}),
        "",
        "TRADES",
        render_trades_table((run.get("trades") or []), max_rows=max_rows),
        "",
        *_suggest_block(suggestions, warnings),
        "",
    ]
    return "\n".join(out)


def render_payload(payload: Dict[str, Any], max_rows: int = 40) -> str:
    """Cómodo: render_producto del JSON tal cual lo guarda backtest/calibrate."""
    return render_report(
        run=payload.get("run") or {},
        metrics=payload.get("metrics") or {},
        breakdowns=payload.get("breakdowns"),
        suggestions=payload.get("suggestions"),
        warnings=payload.get("warnings"),
        max_rows=max_rows,
    )