"""research/calibrator.py — sugerencias de calibración contra strategy.yaml.

Puro y determinista: recibe la config simulada (cfg del run), los trades del
motor (research.sim) y (opcionalmente) la métrica (research.metrics), compara lo
observado contra umbrales fijos y devuelve una lista de SUGERENCIAS con la ruta
en strategy.yaml (score.*, execution.*, risk.*), valor actual, valor sugerido y
la razón. Las sugerencias NUNCA se aplican solas: `calibrate` imprime el diff y
el usuario decide si edita el YAML.

Reglas (heurísticas deterministas):
- TTL: si la mayoría de las órdenes aprobadas EXPIRAN sin tocar el nivel, alargar
  `score.setup_ttl_minutes` (el FVG no llega con la ventana actual).
- Umbral: con un mínimo de trades y esperanza en R negativa, subir
  `score.min_score` (filtrar señales marginales).
- Límite de pérdidas: el DD observado (curva de sizing 1%) se proyecta con el
  risk_pct vigente; si supera el límite (prop daily / loss_limit_pct / objetivo),
  sugerir bajar `risk.risk_pct`.
- Pesos: cada componente activo (peso > 0 en strategy.yaml) mide si discrimina
  entre ganadoras y perdedoras (media wins - media losses); delta positivo ->
  subir el peso, negativo -> bajarlo, renormalizando el total.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from research import metrics as rm

_COMPONENT_ORDER = ("cot", "cvd_of", "smc", "killzone", "smr_dxy")

# Ruta del key plano en el YAML jerárquico de strategy.yaml.
_YAML_PATH = {
    "min_score": ("score", "min_score"),
    "min_rr": ("score", "min_rr"),
    "setup_ttl_minutes": ("score", "setup_ttl_minutes"),
    "risk_weights": ("score", "weights"),
    "sl_default_pips": ("execution", "sl_default_pips"),
    "tp_ratio_r": ("execution", "tp_ratio_r"),
    "risk_pct": ("risk", "risk_pct"),
    "reduced_risk_pct": ("risk", "reduced_risk_pct"),
    "max_trades_day": ("risk", "max_trades_day"),
    "prop_max_dd_daily_pct": ("prop", "max_dd_daily_pct"),
    "prop_max_dd_total_pct": ("prop", "max_dd_total_pct"),
}

_DEFAULT_THRESHOLDS = {
    "min_approved": 8,         # órdenes aprobadas mínimas para hablar de ejecución
    "min_filled": 10,          # trades cerrados mínimos para hablar de edge
    "min_per_component": 6,    # wins y losses mínimos por componente
    "expiry_frac": 0.50,       # expired/(expired+filled) -> sugerir TTL
    "cancel_frac": 0.40,       # cancelled/(aprobadas) -> warning
    "ttl_step_min": 10.0,      # incremento TTL sugerido
    "ttl_max_min": 90.0,
    "min_score_step": 5.0,
    "expectancy_r_target": 0.15,
    "component_min_delta": 0.08,
    "component_delta_scale": 60.0,
    "component_delta_max": 15.0,
    "dd_target_daily_pct": 3.0,   # objetivo si el YAML no define límite
    "dd_headroom": 0.8,           # dispara cuando projected_dd > limite*0.8
    "dd_safe_factor": 0.6,        # risk_pct nuevo acota el DD a limite*0.6
    "high_conf_n": 15,
    "ok_conf_n": 8,
}


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # noqa: PLR0124 - rechaza NaN


def _confidence(samples: int, thr: Dict[str, Any]) -> str:
    if samples >= thr["high_conf_n"]:
        return "high"
    if samples >= thr["ok_conf_n"]:
        return "medium"
    return "low"


def _fmt(v: Any, digits: int = 2) -> Any:
    x = _num(v)
    if x is None:
        return v
    return round(x, digits)


# ============================================================
# Descomposición por componente (wins vs losses)
# ============================================================

def component_means(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Medias por componente en el lado señalado, separando wins y losses.

    Usa `signal_components` (dict componente -> valor [0..1] en el lado elegido
    cuando se abrió la señal). Devuelve por componente: n_wins, n_losses,
    wins_mean/losses_mean (None si no hay) y `delta` = wins_mean - losses_mean
    (None si falta uno de los bucket). Solo trades cerrados (pnl_r != None).
    """
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for t in trades:
        if t.get("pnl_r") is None:
            continue
        side = "wins" if t["pnl_r"] > 0 else "losses"
        for k, v in (t.get("signal_components") or {}).items():
            fv = _num(v)
            if fv is None:
                continue
            buckets.setdefault(k, {"wins": [], "losses": []})
            buckets[k][side].append(fv)
    out: Dict[str, Dict[str, Any]] = {}
    for k, b in buckets.items():
        wins, losses = b["wins"], b["losses"]
        wm = statistics.mean(wins) if wins else None
        lm = statistics.mean(losses) if losses else None
        out[k] = {
            "n_wins": len(wins),
            "n_losses": len(losses),
            "wins_mean": round(wm, 3) if wm is not None else None,
            "losses_mean": round(lm, 3) if lm is not None else None,
            "delta": round(wm - lm, 3) if wm is not None and lm is not None else None,
        }
    return out


# ============================================================
# Ajuste de pesos (renormalizado a 100)
# ============================================================

def _tune_weights(current: Dict[str, Any], means: Dict[str, Dict[str, Any]],
                  thr: Dict[str, Any]) -> Dict[str, Any]:
    total = sum(float(v) for v in current.values()) or 100.0
    new = {k: float(v) for k, v in current.items()}
    items: List[Dict[str, Any]] = []
    for comp in _COMPONENT_ORDER:
        w = new.get(comp, 0.0)
        if w <= 0:
            continue
        m = means.get(comp)
        if not m:
            continue
        if m["n_wins"] < thr["min_per_component"] or m["n_losses"] < thr["min_per_component"]:
            continue
        d = m.get("delta")
        if d is None or abs(d) < thr["component_min_delta"]:
            continue
        pts = int(round(max(-thr["component_delta_max"],
                            min(thr["component_delta_max"],
                                d * thr["component_delta_scale"]))))
        if not pts:
            continue
        items.append({
            "component": comp,
            "weight": round(w, 1),
            "delta_points": pts,
            "n_wins": m["n_wins"],
            "n_losses": m["n_losses"],
            "wins_mean": m["wins_mean"],
            "losses_mean": m["losses_mean"],
            "delta": m["delta"],
        })
        new[comp] = w + pts
    if not items:
        return {"weights": current, "items": []}
    snew = sum(new.values())
    if snew > 0:
        for k in new:
            new[k] = max(0.0, round(new[k] / snew * total, 1))
    return {"weights": new, "items": items}


# ============================================================
# Sugerencias
# ============================================================

def suggest(cfg: Dict[str, Any], trades: List[Dict[str, Any]],
            metrics: Optional[Dict[str, Any]] = None,
            baseline: Optional[Dict[str, Any]] = None,
            thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Devuelve {suggestions, warnings} frente al strategy.yaml actual.

    `cfg` es la config del run simulado (default_cfg + overrides CLI), `baseline`
    es la config plana VIGENTE (strategy.yaml/store) contra la que se compara
    (por defecto la misma `cfg`). thresholds ajusta las reglas (tests/experimentos).
    """
    trades = list(trades or [])
    m = metrics or rm.compute_metrics(trades)
    thr = dict(_DEFAULT_THRESHOLDS)
    if thresholds:
        thr.update(thresholds)
    base = dict(baseline) if baseline is not None else dict(cfg)

    approved = int(m.get("n") or 0)
    filled = int(m.get("n_filled") or 0)
    expired = int(m.get("n_expired") or 0)
    cancelled = int(m.get("n_cancelled") or 0)

    def _base_num(key: str) -> Optional[float]:
        return _num(base.get(key)) or _num(cfg.get(key))

    suggestions: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # 1) TTL: demasiadas aprobadas expiran sin tocar el nivel.
    if approved >= thr["min_approved"] and (expired + filled) > 0:
        frac = expired / (expired + filled)
        if frac > thr["expiry_frac"]:
            current_ttl = _num(cfg.get("setup_ttl_minutes")) or 0.0
            step = thr["ttl_step_min"]
            proposed = min(current_ttl + step, thr["ttl_max_min"])
            baseline_ttl = _num(base.get("setup_ttl_minutes"))
            if baseline_ttl is None or proposed > baseline_ttl + 1e-9:
                suggestions.append({
                    "key": "setup_ttl_minutes",
                    "path": _YAML_PATH["setup_ttl_minutes"],
                    "current": _fmt(current_ttl, 0),
                    "suggested": _fmt(proposed, 0),
                    "delta": _fmt(proposed - current_ttl, 0),
                    "reason": (f"{expired} de {expired + filled} órdenes deciden sin fill "
                               f"expiran ({(frac * 100):.0f}%) -> la entrada no alcanza el "
                               f"nivel con el TTL actual."),
                    "confidence": _confidence(expired, thr),
                })

    # 2) Cancelaciones estructurales: warning informativo.
    if cancelled and approved and (cancelled / approved) > thr["cancel_frac"]:
        warnings.append(
            f"{cancelled} de {approved} aprobadas se cancelan por invalidez "
            f"estructural ({(cancelled / approved * 100):.0f}%). Revisa la invalidez "
            "o sube min_score para filtrar señales marginales.")

    # 3) Edge negativo -> subir min_score.
    exp_r = _num(m.get("expectancy_r"))
    if filled >= thr["min_filled"] and exp_r is not None and exp_r < thr["expectancy_r_target"]:
        proposed = (_num(cfg.get("min_score")) or 0.0) + thr["min_score_step"]
        base_ms = _num(base.get("min_score"))
        if base_ms is not None and proposed <= base_ms + 1e-9:
            pass  # ya está al menos tan estricto
        elif proposed <= 100.0:
            suggestions.append({
                "key": "min_score",
                "path": _YAML_PATH["min_score"],
                "current": _fmt(_num(cfg.get("min_score")) or 0.0, 1),
                "suggested": _fmt(proposed, 1),
                "delta": _fmt(thr["min_score_step"], 1),
                "reason": (f"Esperanza {exp_r:+.2f}R tras {filled} trades "
                           f"(umbral objetivo {thr['expectancy_r_target']:.2f}R)."),
                "confidence": _confidence(filled, thr),
            })

    # 4) Drawdown proyectado -> bajar risk_pct.
    dd1 = _num(m.get("max_dd_equity_pct")) or 0.0
    risk_pct = _base_num("risk_pct") or 1.0
    if dd1 > 0 and risk_pct > 0:
        limit = (_num(base.get("prop_max_dd_daily_pct"))
                 or _num(base.get("loss_limit_pct"))
                 or thr["dd_target_daily_pct"])
        projected = dd1 * risk_pct
        if projected > limit * thr["dd_headroom"]:
            proposed = max(0.1, round(limit * thr["dd_safe_factor"] / dd1, 1))
            if proposed < risk_pct:
                suggestions.append({
                    "key": "risk_pct",
                    "path": _YAML_PATH["risk_pct"],
                    "current": _fmt(risk_pct, 1),
                    "suggested": _fmt(proposed, 1),
                    "delta": _fmt(proposed - risk_pct, 1),
                    "reason": (f"DD {dd1:.2f}% con sizing 1% proyectado a "
                               f"{projected:.2f}% con risk_pct {risk_pct:.1f}% "
                               f"(límite {limit:.1f}%)."),
                    "confidence": _confidence(filled, thr),
                })

    # 5) Pesos: discrimina por componente (solo activos con muestra suficiente).
    base_weights = base.get("risk_weights")
    if isinstance(base_weights, str):
        import json  # noqa: PLC0415
        try:
            base_weights = json.loads(base_weights)
        except (json.JSONDecodeError, TypeError):
            base_weights = None
    if not isinstance(base_weights, dict):
        cfg_w = cfg.get("risk_weights")
        base_weights = cfg_w if isinstance(cfg_w, dict) else {}
    means = component_means(trades)
    tuned = _tune_weights(dict(base_weights), means, thr)
    if tuned["items"]:
        min_samples = min(min(it["n_wins"], it["n_losses"]) for it in tuned["items"])
        suggestions.append({
            "key": "risk_weights",
            "path": _YAML_PATH["risk_weights"],
            "current": {k: _fmt(v, 1) for k, v in base_weights.items()},
            "suggested": {k: _fmt(v, 1) for k, v in tuned["weights"].items()},
            "delta": {it["component"]: it["delta_points"] for it in tuned["items"]},
            "items": tuned["items"],
            "reason": "Pesos ajustados por el delta observado (wins_mean - losses_mean).",
            "confidence": _confidence(min_samples, thr),
        })

    return {"suggestions": suggestions, "warnings": warnings}