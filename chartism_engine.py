"""Motor de detección de patrones CHARTISTAS clásicos (canales, triángulos,
banderas/banderines, doble techo/suelo y cabeza y hombros).

Algoritmos puros sobre velas OHLC (misma convención que `pattern_engine`):
reciben una lista de dicts
    [{"time": int, "open": float, "high": float, "low": float, "close": float, ...}]
y devuelven FIGURAS en el formato `drawing` que ya renderiza y persiste `tools.js`
en el frontend (line / hline / text, con tiempos en epoch y precios):

    {"tool": "line",  "t0": int, "p0": float, "t1": int, "p1": float, "group": "...", "text": "..."}
    {"tool": "hline", "p0": float, ...}
    {"tool": "text",  "t0": int, "p0": float, "text": "...", ...}

Sin scipy ni TA-Lib: los pivotes se detectan con ventana deslizante (`_pivots`)
y las líneas con regresión lineal simple (numpy.polyfit, ya en requirements).

Fase 1: solo detección + dibujo; el estado de la figura ("en formación" /
"roto ...") solo marca que el último cierre quedó dentro o fuera de la geometría.
Sin filtro de volumen/CVD todavía (fase 2).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

# Ventana deslizante de pivotes por temporalidad: más k = pivotes más estructurales.
PIVOT_K = {
    "M1": 3,
    "M5": 3,
    "M15": 4,
    "M30": 4,
    "H1": 5,
    "H4": 6,
    "D1": 7,
    "W1": 8,
}
DEFAULT_K = 5

GROUPS = ["trend", "triangle", "flag", "double", "hns"]

_GROUP_LABELS = {
    "trend": "Canal/Tendencia",
    "triangle": "Triángulo",
    "flag": "Bandera",
    "double": "Doble techo/suelo",
    "hns": "Cabeza y hombros",
}


def _r6(x):
    return round(float(x), 6)


# --------------------------------------------------------------------------- #
# Primitivas geométricas
# --------------------------------------------------------------------------- #

def _pivots(candles: List[dict], k: int):
    """Índices de swing highs/lows con ventana `k` a cada lado y cooldown de `k` velas."""
    n = len(candles)
    highs: List[int] = []
    lows: List[int] = []
    last_h = last_l = -k
    for i in range(k, n - k):
        if i - last_h > k:
            seg = [candles[i + j]["high"] for j in range(-k, k + 1) if j]
            if candles[i]["high"] >= max(seg):
                highs.append(i)
                last_h = i
        if i - last_l > k:
            seg = [candles[i + j]["low"] for j in range(-k, k + 1) if j]
            if candles[i]["low"] <= min(seg):
                lows.append(i)
                last_l = i
    return highs, lows


def _atr(candles: List[dict], n: int = 14) -> float:
    """Average True Range simple sobre las últimas `n` velas."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(
            c["high"] - c["low"],
            abs(c["high"] - p["close"]),
            abs(c["low"] - p["close"]),
        ))
    w = trs[-n:]
    return sum(w) / len(w)


def _regress(points) -> Optional[tuple]:
    """Regresión lineal simple → (slope, intercept, r2).

    Retorna None si hay menos de 2 puntos o si el ajuste es degenerado
    (x constante o rango de precios nulo), para que los detectores aborten la
    figura sin romper el endpoint.
    """
    if len(points) < 2:
        return None
    xs = np.asarray([p[0] for p in points], dtype=float)
    ys = np.asarray([p[1] for p in points], dtype=float)
    if np.ptp(xs) == 0 or np.ptp(ys) == 0:
        return None
    slope, intercept = np.polyfit(xs, ys, 1)
    pred = slope * xs + intercept
    ss_res = float(np.sum((ys - pred) ** 2))
    ss_tot = float(np.sum((ys - np.mean(ys)) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return float(slope), float(intercept), float(r2)


def _fit_fixed_slope(points: List[tuple], slope: float) -> Optional[float]:
    """Intercepto (centroide) para una serie de puntos con pendiente fija."""
    if not points:
        return None
    mi = sum(p[0] for p in points) / len(points)
    my = sum(p[1] for p in points) / len(points)
    return float(my - slope * mi)


def _reg_or_flat(points) -> Optional[tuple]:
    """`_regress` con fallback a línea horizontal si los precios son planos exactos.

    Un pivote en fase idéntica (datos muy limpios) da ajuste degenerado; la
    resistencia/soporte sigue siendo válida como nivel horizontal (slope 0).
    """
    reg = _regress(points)
    if reg is not None:
        return reg
    if points and len(points) >= 2:
        ys = [p[1] for p in points]
        if max(ys) == min(ys):
            return (0.0, float(ys[0]), 1.0)
    return None


def _mk_line(candles, i0, i1, slope, intercept, group: str, name: str = ""):
    i0 = max(i0, 0)
    i1 = min(i1, len(candles) - 1)
    return {
        "tool": "line",
        "t0": candles[i0]["time"],
        "p0": _r6(slope * i0 + intercept),
        "t1": candles[i1]["time"],
        "p1": _r6(slope * i1 + intercept),
        "group": group,
        "text": name or "",
    }


def _mk_hline(price: float, group: str, name: str = ""):
    return {"tool": "hline", "p0": _r6(price), "group": group, "text": name or ""}


def _mk_text(candles, idx, price, group: str, text: str):
    i = max(0, min(int(idx), len(candles) - 1)) if candles else 0
    return {"tool": "text", "t0": candles[i]["time"], "p0": _r6(price),
            "group": group, "text": text}


# --------------------------------------------------------------------------- #
# Detectores por figura. Cada uno devuelve (count, drawings).
# --------------------------------------------------------------------------- #

def _detect_trend(candles, k, tf):
    highs, lows = _pivots(candles, k)
    out: List[dict] = []
    if not highs and not lows:
        return 0, out
    atr = _atr(candles)
    atr = atr if atr and atr > 0 else 1e-9
    up_pts = [(i, candles[i]["high"]) for i in highs[-12:]]
    dn_pts = [(i, candles[i]["low"]) for i in lows[-12:]]
    reg_u = _reg_or_flat(up_pts)
    reg_d = _reg_or_flat(dn_pts)

    if reg_u and reg_d and len(up_pts) >= 3 and len(dn_pts) >= 3:
        slope = (reg_u[0] + reg_d[0]) / 2.0
        iu = _fit_fixed_slope(up_pts, slope)
        id_ = _fit_fixed_slope(dn_pts, slope)
        i0 = min(up_pts[0][0], dn_pts[0][0])
        i1 = max(up_pts[-1][0], dn_pts[-1][0])
        if iu is not None and id_ is not None and i1 > i0:
            pu1 = slope * i1 + iu
            pd1 = slope * i1 + id_
            if pu1 > pd1 and (pu1 - pd1) >= 0.3 * atr:
                label = "▲ alcista" if slope > 0 else ("▼ bajista" if slope < 0 else "lateral")
                out.append(_mk_line(candles, i0, i1, slope, iu, "trend"))
                out.append(_mk_line(candles, i0, i1, slope, id_, "trend"))
                out.append(_mk_text(candles, i0, slope * i0 + iu + 0.35 * atr,
                                    "trend", f"Canal {label} {tf}"))
                return 1, out

    # Fallback: líneas de tendencia individuales sobre una sola serie de pivotes.
    for reg, pts in ((reg_u, up_pts), (reg_d, dn_pts)):
        if reg and reg[2] >= 0.6 and len(pts) >= 3:
            i0, i1 = pts[0][0], pts[-1][0]
            out.append(_mk_line(candles, i0, i1, reg[0], reg[1], "trend"))
    return len(out), out


def _detect_triangle(candles, k, tf):
    highs, lows = _pivots(candles, k)
    n = len(candles)
    if len(highs) < 3 or len(lows) < 3:
        return 0, []
    atr = _atr(candles)
    atr = atr if atr and atr > 0 else 1e-9
    up_pts = [(i, candles[i]["high"]) for i in highs[-5:]]
    dn_pts = [(i, candles[i]["low"]) for i in lows[-5:]]
    reg_u = _reg_or_flat(up_pts)
    reg_d = _reg_or_flat(dn_pts)
    if not reg_u or not reg_d:
        return 0, []
    i_min = min(up_pts[0][0], dn_pts[0][0])
    i_max = max(up_pts[-1][0], dn_pts[-1][0])
    span = i_max - i_min
    if span <= 0 or reg_u[0] >= reg_d[0]:
        return 0, []

    xi = (reg_d[1] - reg_u[1]) / (reg_u[0] - reg_d[0])
    if xi < i_min - span * 0.2 or xi > i_max + span:
        return 0, []

    rng = span + 1
    sig = 0.6 * atr
    up_move = reg_d[0] * rng
    dn_move = reg_u[0] * rng
    if up_move > sig and dn_move < -sig:
        kind = "simétrico"
    elif up_move > sig:
        kind = "ascendente"
    elif dn_move < -sig:
        kind = "descendente"
    else:
        kind = "simétrico"

    i_last = n - 1
    up_last = reg_u[0] * i_last + reg_u[1]
    dn_last = reg_d[0] * i_last + reg_d[1]
    close = candles[i_last]["close"]
    if close > up_last:
        state = " · roto alcista"
    elif close < dn_last:
        state = " · roto bajista"
    else:
        state = " · en formación"

    out = [
        _mk_line(candles, i_min, i_max, reg_u[0], reg_u[1], "triangle"),
        _mk_line(candles, i_min, i_max, reg_d[0], reg_d[1], "triangle"),
    ]
    ia = max(0, min(int(round(xi)), n - 1))
    pa = reg_u[0] * ia + reg_u[1]
    out.append(_mk_text(candles, i_min, pa + 0.35 * atr, "triangle",
                        f"Triángulo {kind} {tf}{state}"))
    return 1, out


def _find_pole(candles, tail=60, max_len=90):
    """Asta (movimiento fuerte reciente) → (move, i_start, i_end, direction).

    Busca el par de velas con mayor |movimiento| cuyo extremo (i_end) esté dentro
    de las últimas `tail` velas. direction: +1 alcista (i_start=<bajo>, i_end=<alto>),
    -1 bajista (i_start=<alto>, i_end=<bajo>).
    """
    n = len(candles)
    best = None
    for i in range(0, n):
        jmax = min(n - 1, i + max_len)
        for j in range(i + 2, jmax + 1):
            if j < n - 1 - tail:
                continue
            up = candles[j]["high"] - candles[i]["low"]
            dn = candles[j]["low"] - candles[i]["high"]
            for mv, d in ((up, 1), (dn, -1)):
                if best is None or abs(mv) > abs(best[0]):
                    best = (mv, i, j, d)
    return best


def _detect_flag(candles, k, tf):
    n = len(candles)
    if n < 40:
        return 0, []
    atr = _atr(candles)
    if not atr or atr <= 0:
        return 0, []
    highs, lows = _pivots(candles, k)
    if len(highs) < 2 or len(lows) < 2:
        return 0, []

    best = _find_pole(candles)
    if best is None:
        return 0, []
    move, i0, i1, direc = best
    pole_h = abs(move)
    if pole_h < 1.5 * atr or (i1 - i0) < 3:
        return 0, []

    fh = [i for i in highs if i > i1]
    fl = [i for i in lows if i > i1]
    if len(fh) < 2 or len(fl) < 2:
        return 0, []
    fh_pts = [(i, candles[i]["high"]) for i in fh[-5:]]
    fl_pts = [(i, candles[i]["low"]) for i in fl[-5:]]
    reg_u = _reg_or_flat(fh_pts)
    reg_d = _reg_or_flat(fl_pts)
    if not reg_u or not reg_d:
        return 0, []

    fi0 = fh_pts[0][0]
    fi1 = n - 1
    span = max(fi1 - fi0, 1)
    if abs(reg_u[0] * span) > 0.35 * pole_h or abs(reg_d[0] * span) > 0.35 * pole_h:
        return 0, []

    top1 = reg_u[0] * fi1 + reg_u[1]
    bot1 = reg_d[0] * fi1 + reg_d[1]
    sep = top1 - bot1
    if sep < 0.15 * pole_h or sep > 0.7 * pole_h:
        return 0, []

    if reg_u[0] < reg_d[0]:
        name = "Banderín"
    else:
        name = "Bandera" if direc > 0 else "Bandera bajista"

    out: List[dict] = []
    # Asta (pole)
    if direc > 0:
        out.append({
            "tool": "line",
            "t0": candles[i0]["time"], "p0": _r6(candles[i0]["low"]),
            "t1": candles[i1]["time"], "p1": _r6(candles[i1]["high"]),
            "group": "flag", "text": "",
        })
    else:
        out.append({
            "tool": "line",
            "t0": candles[i0]["time"], "p0": _r6(candles[i0]["high"]),
            "t1": candles[i1]["time"], "p1": _r6(candles[i1]["low"]),
            "group": "flag", "text": "",
        })
    # Cuerpo del banderín/bandera
    out.append(_mk_line(candles, fi0, fi1, reg_u[0], reg_u[1], "flag"))
    out.append(_mk_line(candles, fi0, fi1, reg_d[0], reg_d[1], "flag"))
    out.append(_mk_text(candles, i1, top1 + 0.35 * atr, "flag", f"{name} {tf}"))
    return 1, out


def _find_double(candles, piv, oth, min_gap, max_gap, tol, side: str):
    """Busca el doble extremo más reciente. side='top' (highs) o 'bottom' (lows)."""
    ext = "high" if side == "top" else "low"
    n = len(piv)
    for j in range(n - 1, 0, -1):
        for i in range(j - 1, -1, -1):
            gap = piv[j] - piv[i]
            if gap < min_gap:
                continue
            if gap > max_gap:
                break
            if abs(candles[piv[i]][ext] - candles[piv[j]][ext]) > tol:
                continue
            between = [t for t in oth if piv[i] < t < piv[j]]
            if not between:
                continue
            level = (candles[piv[i]][ext] + candles[piv[j]][ext]) / 2.0
            if side == "top":
                neck = min(between, key=lambda t: candles[t]["low"])
            else:
                neck = max(between, key=lambda t: candles[t]["high"])
            return piv[i], piv[j], level, neck
    return None


def _detect_double(candles, k, tf):
    n = len(candles)
    if n < 30:
        return 0, []
    atr = _atr(candles)
    if not atr or atr <= 0:
        return 0, []
    highs, lows = _pivots(candles, k)
    tol = 0.5 * atr
    min_gap = max(k * 2, 3)
    max_gap = min(int(n * 0.5), 120)
    out: List[dict] = []

    top = _find_double(candles, highs, lows, min_gap, max_gap, tol, "top")
    if top:
        i1, i2, level, neck = top
        neck_lvl = candles[neck]["low"]
        state = " · roto" if candles[-1]["close"] < neck_lvl else ""
        out.append(_mk_hline(level, "double"))
        out.append(_mk_hline(neck_lvl, "double"))
        out.append(_mk_text(candles, (i1 + i2) // 2, level + 0.35 * atr, "double",
                            f"Doble techo {tf}{state}"))
        out.append(_mk_text(candles, neck, neck_lvl - 0.35 * atr, "double", "cuello"))

    bot = _find_double(candles, lows, highs, min_gap, max_gap, tol, "bottom")
    if bot:
        i1, i2, level, neck = bot
        neck_lvl = candles[neck]["high"]
        state = " · roto" if candles[-1]["close"] > neck_lvl else ""
        out.append(_mk_hline(level, "double"))
        out.append(_mk_hline(neck_lvl, "double"))
        out.append(_mk_text(candles, (i1 + i2) // 2, level - 0.35 * atr, "double",
                            f"Doble suelo {tf}{state}"))
        out.append(_mk_text(candles, neck, neck_lvl + 0.35 * atr, "double", "cuello"))

    count = 1 if (top or bot) else 0
    return count, out


def _detect_hns(candles, k, tf):
    n = len(candles)
    if n < 40:
        return 0, []
    atr = _atr(candles)
    tol = (0.5 * atr) if atr and atr > 0 else 1e-9
    highs, lows = _pivots(candles, k)
    min_gap = max(k * 2, 3)
    max_gap = min(int(n * 0.35), 60)

    for side in ("top", "bottom"):
        piv = highs if side == "top" else lows
        oth = lows if side == "top" else highs
        ext = "high" if side == "top" else "low"
        m = len(piv)
        for c in range(m - 1, 1, -1):
            for b in range(c - 1, 0, -1):
                if piv[c] - piv[b] > max_gap:
                    break
                for a in range(b - 1, -1, -1):
                    if piv[b] - piv[a] > max_gap:
                        break
                    i1, i2, i3 = piv[a], piv[b], piv[c]
                    if i2 - i1 < min_gap or i3 - i2 < min_gap:
                        continue
                    p1 = candles[i1][ext]
                    p2 = candles[i2][ext]
                    p3 = candles[i3][ext]
                    if side == "top":
                        head = p2 > p1 + tol * 0.3 and p2 > p3 + tol * 0.3
                        sh = abs(p1 - p3) <= tol
                    else:
                        head = p2 < p1 - tol * 0.3 and p2 < p3 - tol * 0.3
                        sh = abs(p1 - p3) <= tol
                    if not (head and sh):
                        continue

                    # Cuello: extremo contrario entre (i1,i2) y entre (i2,i3)
                    seg1 = candles[i1: i2 + 1]
                    seg2 = candles[i2: i3 + 1]
                    if side == "top":
                        n1 = min(seg1, key=lambda x: x["low"]) if seg1 else None
                        n2 = min(seg2, key=lambda x: x["low"]) if seg2 else None
                    else:
                        n1 = max(seg1, key=lambda x: x["high"]) if seg1 else None
                        n2 = max(seg2, key=lambda x: x["high"]) if seg2 else None
                    if not n1 or not n2:
                        continue
                    out = [
                        {
                            "tool": "line",
                            "t0": n1["time"], "p0": _r6(float(n1[ext])),
                            "t1": n2["time"], "p1": _r6(float(n2[ext])),
                            "group": "hns", "text": "",
                        },
                        _mk_text(candles, i1, float(p1) + (0.35 * atr if side == "top" else -0.35 * atr),
                                 "hns", "Hombro izq"),
                        _mk_text(candles, i2, float(p2) + (0.45 * atr if side == "top" else -0.45 * atr),
                                 "hns", "Cabeza"),
                        _mk_text(candles, i3, float(p3) + (0.35 * atr if side == "top" else -0.35 * atr),
                                 "hns", "Hombro der"),
                    ]
                    name = "H&S" if side == "top" else "H&S invertido"
                    imid = (i1 + i3) // 2
                    mid_price = (float(n1[ext]) + float(n2[ext])) / 2
                    if side == "top":
                        out.append(_mk_text(candles, imid, mid_price - 0.4 * atr, "hns",
                                            f"{name} {tf} · cuello"))
                    else:
                        out.append(_mk_text(candles, imid, mid_price + 0.4 * atr, "hns",
                                            f"{name} {tf} · cuello"))
                    return 1, out
    return 0, []


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #

def detect_all(candles: List[dict], patterns: Optional[list] = None,
               timeframe: str = "") -> dict:
    """JSON para el endpoint: {timeframe, patterns, drawings, summary}."""
    k = PIVOT_K.get(str(timeframe).upper(), DEFAULT_K)
    req: List[str] = []
    for p in (patterns or []):
        p = str(p).strip().lower()
        if p == "all":
            req = list(GROUPS)
            break
        if p in GROUPS and p not in req:
            req.append(p)

    drawings: List[dict] = []
    summary = {}
    for g in req:
        try:
            if g == "trend":
                cnt, items = _detect_trend(candles, k, timeframe)
            elif g == "triangle":
                cnt, items = _detect_triangle(candles, k, timeframe)
            elif g == "flag":
                cnt, items = _detect_flag(candles, k, timeframe)
            elif g == "double":
                cnt, items = _detect_double(candles, k, timeframe)
            elif g == "hns":
                cnt, items = _detect_hns(candles, k, timeframe)
            else:
                continue
        except Exception:
            cnt, items = 0, []
        drawings.extend(items)
        summary[g] = cnt

    if len(drawings) > 80:
        drawings = drawings[:80]

    return {
        "timeframe": str(timeframe).upper(),
        "patterns": req,
        "drawings": drawings,
        "summary": summary,
    }