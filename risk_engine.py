"""Motor de riesgo determinista (M1-M3).

Modulo PURO: no importa MT5, ni la app, ni los servicios de datos. Recibe toda la
entrada por parametros para poder probarse sin terminal abierta. Produce el Setup
Score (0-100), el regimen de mercado, la killzone y la validacion de entrada con
invalidez estructural, R:R minimo y TTL del setup.

Convenciones de direccion: "BUY" (long) o "SELL" (short).
Los pesos, umbrales, ventanas de killzone y TTL vienen de la config de trading y
se sobreescriben con estos defaults si faltan.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_WEIGHTS: Dict[str, float] = {
    "cot": 25.0,
    "cvd_of": 25.0,
    "smc": 30.0,
    "killzone": 20.0,
    "smr_dxy": 0.0,
}

DEFAULT_GRADE_THRESHOLDS: Dict[str, float] = {
    "alta": 80.0,
    "media": 60.0,
}

DEFAULT_KILLZONES: List[Dict[str, str]] = [
    {"name": "Londres", "start": "08:00", "end": "11:00"},
    {"name": "Nueva York", "start": "13:00", "end": "16:00"},
]

VERDICT_ALTA = "ALTA_PROBABILIDAD"
VERDICT_MEDIA = "MEDIA_PROBABILIDAD"
VERDICT_SIN = "SIN_OPERATIVA"

REGIME_EXPANSION = "expansion"
REGIME_RANGO = "rango"
REGIME_NEUTRAL = "neutro"


def _h_as_min(t: dtime) -> int:
    return t.hour * 60 + t.minute


def _parse_hhmm(value: str) -> Optional[dtime]:
    try:
        h, m = value.strip().split(":")
        return dtime(hour=int(h), minute=int(m))
    except (ValueError, AttributeError):
        return None


def killzone_score(windows: Optional[List[Dict[str, str]]] = None,
                   now: Optional[datetime] = None) -> Dict[str, Any]:
    """Valor del componente killzone: 1.0 dentro de una ventana, 0.25 fuera.

    Ventanas UTC como [{"name","start","end"}] con HH:MM. `now` se usa por
    parametro (pureza/testeable); si no se pasa, se toma datetime.now(timezone.utc).
    """
    wins = windows if windows is not None else DEFAULT_KILLZONES
    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    t = dtime(hour=dt.hour, minute=dt.minute, second=dt.second)
    tmin = _h_as_min(t)

    active = None
    for w in wins:
        start = _parse_hhmm(w.get("start", ""))
        end = _parse_hhmm(w.get("end", ""))
        if start is None or end is None:
            continue
        smin, emin = _h_as_min(start), _h_as_min(end)
        inside = (smin <= tmin < emin) if emin >= smin else (tmin >= smin or tmin < emin)
        if inside:
            active = w
            break

    if active is not None:
        return {
            "value": 1.0,
            "in_killzone": True,
            "name": active.get("name", "?") ,
            "detail": f"Dentro de la sesion {active.get('name', '?')} (ventana activa en UTC).",
        }
    return {
        "value": 0.25,
        "in_killzone": False,
        "name": None,
        "detail": "Fuera de ventanas de killzone (peso reducido).",
    }


def regime(candles: Optional[List[Dict[str, Any]]] = None,
           lookback: int = 60) -> Dict[str, Any]:
    """Clasifica el mercado en expansion / rango / neutro.

    Heuristica determinista: el ratio entre el rango total de la ventana y el
    tamano medio de los cuerpos. Ratios altos sugieren expansio/direccionalidad;
    bajos sugieren compresion/acumulacion.
    """
    cs = candles or []
    if not cs:
        return {"regime": REGIME_NEUTRAL, "detail": "Sin velas suficientes."}
    win = cs[-lookback:]
    if len(win) < 5:
        return {"regime": REGIME_NEUTRAL, "detail": "Velas insuficientes."}

    hi = max(c["high"] for c in win)
    lo = min(c["low"] for c in win)
    span = hi - lo
    avg_body = sum(abs(c["close"] - c["open"]) for c in win) / len(win)
    avg_wick = sum(c["high"] - c["low"] for c in win) / len(win)
    last = win[-1]
    close_last = last["close"]

    if span <= 0 or avg_body <= 0:
        return {"regime": REGIME_NEUTRAL, "detail": "Rango o cuerpo nulos (insuficiente)."}

    ratio = span / avg_body
    if ratio >= 6.0:
        reg = REGIME_EXPANSION
    elif ratio <= 3.0:
        reg = REGIME_RANGO
    else:
        reg = REGIME_NEUTRAL

    return {
        "regime": reg,
        "span": round(span, 6),
        "ratio": round(ratio, 2),
        "avg_body": round(avg_body, 6),
        "atr_pct": round(avg_wick / close_last * 100.0, 3) if close_last else 0.0,
        "detail": f"Rango/body = {ratio:.2f} ({reg}); ATR aproximado {avg_wick / close_last * 100:.2f}%.",
    }


def _trend_coef(values: List[float]) -> float:
    """Pendiente normalizada de una regresion lineal simple (indice vs valor)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0
    scale = max((abs(max(values)) + abs(min(values))) / 2.0, 1e-9)
    return (sxy / sxx) / scale


def cot_component(cot: Optional[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    """Coincidencia del macro_bias COT con la direccion del setup.

    Sentinelas sin datos: el componente vale 0 y detalla la ausencia (el maximo
    del score baja de forma honesta).
    """
    if not cot:
        return {"value": 0.0, "detail": "Sin reporte COT (fuera de EURUSD o sin sync)."}
    bias = str(cot.get("macro_bias") or "NEUTRAL").upper()
    index = cot.get("cot_index_26w")
    if bias == "BULLISH":
        value = 1.0 if direction == "BUY" else 0.15
    elif bias == "BEARISH":
        value = 1.0 if direction == "SELL" else 0.15
    else:
        value = 0.6
    idx_txt = f"{index:.1f}%" if isinstance(index, (int, float)) else "n/d"
    return {
        "value": round(value, 2),
        "detail": f"macro_bias={bias} ({idx_txt}): {'a favor' if value >= 0.8 else ('en contra' if value <= 0.2 else 'neutral')}.",
    }


def cvd_component(cvd: Optional[List[Dict[str, Any]]], direction: str) -> Dict[str, Any]:
    """Pendiente del CVD a favor de la direccion del setup."""
    if not cvd or len(cvd) < 5:
        return {"value": 0.0, "detail": "Sin serie CVD suficiente."}
    values = [float(p.get("value", 0.0)) for p in cvd]
    slope = _trend_coef(values)
    want_up = direction == "BUY"
    if abs(slope) < 1e-6:
        value = 0.4
    elif (slope > 0) == want_up:
        value = 0.8 + min(0.2, abs(slope) * 2.0)
    else:
        value = 0.15
    return {
        "value": round(value, 2),
        "slope": round(slope, 6),
        "detail": f"Pendiente CVD {'alcista' if slope > 0 else 'bajista'} ({slope:+.6f}): {'a favor' if value >= 0.8 else ('en contra' if value <= 0.2 else 'neutral')}.",
    }


def _bull_keys(patterns: Dict[str, Any], direction: str) -> Dict[str, Any]:
    bullish_side = direction == "BUY"
    fvg_key = "BULLISH_FVG" if bullish_side else "BEARISH_FVG"
    ob_key = "BULLISH_OB" if bullish_side else "BEARISH_OB"
    sweep_key = "PDL_SWEEP" if bullish_side else "PDH_SWEEP"
    opposed_fvg = "BEARISH_FVG" if bullish_side else "BULLISH_FVG"
    opposed_ob = "BEARISH_OB" if bullish_side else "BULLISH_OB"

    fvgs = [z for z in patterns.get("fvgs", []) if z.get("type") == fvg_key]
    obs = [z for z in patterns.get("order_blocks", []) if z.get("type") == ob_key]
    sweeps = [s for s in patterns.get("sweeps", []) if s.get("type") == sweep_key]
    opposed = (
        len([z for z in patterns.get("fvgs", []) if z.get("type") == opposed_fvg])
        + len([z for z in patterns.get("order_blocks", []) if z.get("type") == opposed_ob])
    )
    return {
        "fvgs": fvgs,
        "obs": obs,
        "sweeps": sweeps,
        "opposed": opposed,
        "sweep_key": sweep_key,
    }


def smc_component(patterns: Optional[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    """Confluencia SMC: FVG + Order Block + Liquidity Sweep a favor de la direccion."""
    pat = patterns or {}
    if not any(k in pat for k in ("fvgs", "order_blocks", "sweeps")):
        return {"value": 0.0, "detail": "Sin estructura SMC."}

    k = _bull_keys(pat, direction)
    has_fvg, has_ob, has_sweep = bool(k["fvgs"]), bool(k["obs"]), bool(k["sweeps"])
    if has_fvg and has_ob and has_sweep:
        value, why = 1.0, "FVG + OB + Sweep a favor"
    elif has_fvg and (has_ob or has_sweep):
        value, why = 0.7, ("FVG + " + ("OB" if has_ob else "Sweep") + " a favor")
    elif has_fvg or has_ob or has_sweep:
        value, why = 0.5, ("OB" if has_ob else ("FVG" if has_fvg else str(k["sweep_key"]))) + " a favor"
    else:
        value, why = 0.15, "Sin confluencia a favor"

    if has_sweep and k["opposed"] > 0:
        value = max(0.0, value - 0.1)

    return {
        "value": round(value, 2),
        "detail": why + f" (contrapartida estructural: {k['opposed']}).",
    }


def grade_score(score: float) -> str:
    if score >= DEFAULT_GRADE_THRESHOLDS["alta"]:
        return VERDICT_ALTA
    if score >= DEFAULT_GRADE_THRESHOLDS["media"]:
        return VERDICT_MEDIA
    return VERDICT_SIN


def invalidation_level(patterns: Optional[Dict[str, Any]], direction: str) -> Optional[float]:
    """Nivel de invalidez estructural: para BUY, el menor bottom de zonas alcistas
    vivas (FVG/OB); para SELL, el mayor top de las bajistas. None sin estructura."""
    pat = patterns or {}
    if direction == "BUY":
        lows = [float(z["bottom"]) for z in pat.get("fvgs", []) if z.get("type") == "BULLISH_FVG"]
        lows += [float(z["bottom"]) for z in pat.get("order_blocks", []) if z.get("type") == "BULLISH_OB"]
        return min(lows) if lows else None
    highs = [float(z["top"]) for z in pat.get("fvgs", []) if z.get("type") == "BEARISH_FVG"]
    highs += [float(z["top"]) for z in pat.get("order_blocks", []) if z.get("type") == "BEARISH_OB"]
    return max(highs) if highs else None


def smr_component(smr: Optional[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    """Confluencia SMA/SMR via divergencia con el DXY.

    `smr` viene de smr_service.evaluate() con claves "bull"/"bear". Solo la
    divergencia confirmada aporta valor (1.0); sin divergencia o sin feed el
    componente es neutro (0.0) — nunca penaliza el score por falta de dato,
    que es el contrato explicito del bono (sumar solo si se confirma).
    """
    side = "bull" if str(direction).upper() == "BUY" else "bear"
    info = (smr or {}).get(side) or {}
    if info.get("confirmed"):
        return {
            "value": 1.0,
            "confirmed": True,
            "detail": f"Divergencia SMR {side} confirmada: {info.get('detail') or 'con DXY'}.",
        }
    if smr:
        return {
            "value": 0.0,
            "confirmed": False,
            "detail": info.get("detail") or "Sin divergencia SMR (neutro).",
        }
    return {
        "value": 0.0,
        "confirmed": False,
        "detail": "Sin lectura SMR/DXY (neutro).",
    }


def setup_score(inputs: Dict[str, Any],
                weights: Optional[Dict[str, float]] = None,
                killzones: Optional[List[Dict[str, str]]] = None,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """Setup Score 0-100 con breakdown de los componentes.

    inputs:
      direction  ("BUY"/"SELL")
      cot        reporte COT o None
      cvd        serie CVD o None
      patterns   {"fvgs","order_blocks","sweeps",...} o None
      candles    velas OHLC o None
      smr        resultado de smr_service.evaluate() o None
    weights: {"cot","cvd_of","smc","killzone","smr_dxy"} en puntos; si no suman
    100 se normalizan al total efectivo.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items() if v is not None})
    total_w = sum(max(0.0, v) for v in w.values()) or 1.0

    direction = str(inputs.get("direction") or "BUY").upper()
    kz = killzone_score(killzones, now)
    cot = cot_component(inputs.get("cot"), direction)
    cvd = cvd_component(inputs.get("cvd"), direction)
    smc = smc_component(inputs.get("patterns"), direction)
    smr = smr_component(inputs.get("smr"), direction)

    comps = {
        "cot": {**cot, "weight": w["cot"]},
        "cvd_of": {**cvd, "weight": w["cvd_of"]},
        "smc": {**smc, "weight": w["smc"]},
        "killzone": {"value": kz["value"], "weight": w["killzone"],
                     "detail": kz["detail"], "in_killzone": kz["in_killzone"],
                     "name": kz["name"]},
        "smr_dxy": {**smr, "weight": w["smr_dxy"]},
    }
    score = sum(c["value"] * c["weight"] for c in comps.values()) / total_w * 100.0

    return {
        "score": round(score, 1),
        "verdict": grade_score(score),
        "components": comps,
        "regime": regime(inputs.get("candles")),
        "weight_total": round(total_w, 1),
        "computed_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def validate_entry(
    entry: float,
    sl: float,
    target: Optional[float],
    direction: str,
    current_price: Optional[float] = None,
    invalidate_level: Optional[float] = None,
    created_at: Optional[float] = None,
    now: Optional[float] = None,
    cfg: Optional[Dict[str, Any]] = None,
    balance: Optional[float] = None,
    risk_pct: Optional[float] = None,
    loss_per_lot: Optional[float] = None,
    lot: Optional[float] = None,
) -> Dict[str, Any]:
    """Valida la entrada antes de ejecutar: R:R minimo, invalidez estructural y TTL.

    - R:R: exige (|target-entry| / |entry-sl|) >= min_rr (default 2.0).
    - Invalidez: si current_price cruzo invalidate_level (BUY <= nivel, SELL >=
      nivel) el setup murio y se rechaza con score 0.
    - TTL: si now - created_at > ttl_minutes el setup expiro.
    - Cabeza de riesgo: si se pasan loss_per_lot y lot, verifica que la perdida
      maxima no exceda balance*risk_pct/100.
    """
    c = dict(cfg or {})
    min_rr = float(c.get("min_rr") or 2.0)
    ttl_min = float(c.get("setup_ttl_minutes") or 45.0)
    now_ts = now if now is not None else datetime.now(timezone.utc).timestamp()

    rejected = False
    reasons: List[str] = []

    if sl is None or entry is None:
        rejected = True
        reasons.append("Faltan entry/SL para validar.")
    else:
        dist_s = abs(float(entry) - float(sl))
        if target is not None and dist_s > 0:
            rr = abs(float(target) - float(entry)) / dist_s
            if rr + 1e-9 < min_rr:
                rejected = True
                reasons.append(f"R:R {rr:.2f} < minimo {min_rr:.2f}.")

    if invalidate_level is not None and current_price is not None:
        if direction == "BUY" and current_price <= float(invalidate_level):
            rejected = True
            reasons.append(
                f"Estructura rota: precio {current_price} cruzo la invalidez BUY {invalidate_level}."
            )
        elif direction == "SELL" and current_price >= float(invalidate_level):
            rejected = True
            reasons.append(
                f"Estructura rota: precio {current_price} cruzo la invalidez SELL {invalidate_level}."
            )

    if created_at is not None:
        age_min = (now_ts - float(created_at)) / 60.0
        if age_min > ttl_min:
            rejected = True
            reasons.append(f"Setup expirado (TTL {ttl_min:.0f} min; edad {age_min:.1f} min).")

    if (loss_per_lot is not None and lot is not None
            and balance is not None and risk_pct is not None and risk_pct > 0):
        max_risk = float(balance) * float(risk_pct) / 100.0
        loss = abs(float(loss_per_lot)) * float(lot)
        if loss > max_risk * (1.0 + 1e-9):
            rejected = True
            reasons.append(
                f"Riesgo ${loss:.2f} excede el presupuesto ${max_risk:.2f} ({risk_pct}%)."
            )

    return {
        "approved": not rejected,
        "rejected": rejected,
        "reasons": reasons,
        "entry": entry,
        "sl": sl,
        "target": target,
        "direction": direction,
    }


def prop_firm_state(equity, day_start_balance, prev_state=None, now=None, cfg=None):
    """Enforcement real del modo prop-firm (HWM diario + total + tope ganancia).

    Modulo PURO: recibe equity, el balance de inicio de dia y el estado previo
    persistido; devuelve las porcentajes consumidos, si queda bloqueado y el
    estado siguiente a persistir. Sin MT5 ni red.

    Reglas:
      - baseline (HWM total) se crea en la primera llamada con la equity actual.
      - HWM diario se resetea con el balance de inicio de dia cuando cambia el dia.
      - Bloquea si DD diario >= prop_max_dd_daily_pct, DD total >=
        prop_max_dd_total_pct, o ganancia del dia >= prop_max_profit_day_pct.
      - Si prop_enabled es False -> estado neutro (nada bloquea, sin persistir).
    """
    c = dict(cfg or {})
    enabled = bool(c.get("prop_enabled"))
    max_dd_daily = float(c.get("prop_max_dd_daily_pct") or 2.0)
    max_dd_total = float(c.get("prop_max_dd_total_pct") or 6.0)
    max_profit_day = float(c.get("prop_max_profit_day_pct") or 1.5)
    consistency_days = int(c.get("prop_consistency_days") or 0)

    if not enabled:
        return {
            "enabled": False,
            "blocked": False,
            "reasons": [],
            "dd_daily_pct": None,
            "dd_total_pct": None,
            "day_profit_pct": None,
            "state": None,
        }

    dt = now if now is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    today = dt.date().isoformat()
    prev = prev_state or {}

    baseline_equity = float(prev["baseline_equity"]) if prev.get("baseline_equity") is not None else round(float(equity), 4)
    baseline_day = prev.get("baseline_day") or today
    total_peak = float(prev["total_peak"]) if prev.get("total_peak") is not None else baseline_equity
    total_peak = max(total_peak, float(equity))

    day_start = float(day_start_balance) if day_start_balance is not None else float(equity)
    if prev.get("day_peak") is None or prev.get("day_peak_day") != today:
        day_peak, day_peak_day = day_start, today
    else:
        day_peak, day_peak_day = max(float(prev["day_peak"]), float(equity)), today

    dd_daily = max(0.0, day_peak - float(equity))
    dd_total = max(0.0, total_peak - float(equity))
    dd_daily_pct = dd_daily / day_peak * 100.0 if day_peak > 0 else 0.0
    dd_total_pct = dd_total / total_peak * 100.0 if total_peak > 0 else 0.0
    day_profit = float(equity) - day_start
    day_profit_pct = day_profit / day_start * 100.0 if day_start > 0 else 0.0

    reasons: List[str] = []
    if dd_daily_pct >= max_dd_daily - 1e-9:
        reasons.append(
            f"DD diario prop {dd_daily_pct:.2f}% >= tope {max_dd_daily:.2f}% "
            f"(HWM del día {day_peak:.2f})."
        )
    if dd_total_pct >= max_dd_total - 1e-9:
        reasons.append(
            f"DD total prop {dd_total_pct:.2f}% >= tope {max_dd_total:.2f}% "
            f"(HWM total {total_peak:.2f})."
        )
    if max_profit_day > 0 and day_profit > 0 and day_profit_pct >= max_profit_day - 1e-9:
        reasons.append(
            f"Ganancia del día {day_profit_pct:.2f}% >= tope de consistencia {max_profit_day:.2f}%."
        )

    return {
        "enabled": True,
        "blocked": bool(reasons),
        "reasons": reasons,
        "dd_daily_pct": round(dd_daily_pct, 2),
        "dd_total_pct": round(dd_total_pct, 2),
        "day_profit_pct": round(day_profit_pct, 2),
        "consistency_days": consistency_days,
        "state": {
            "baseline_equity": round(baseline_equity, 4),
            "baseline_day": baseline_day,
            "day_peak": round(day_peak, 4),
            "day_peak_day": day_peak_day,
            "total_peak": round(total_peak, 4),
        },
    }