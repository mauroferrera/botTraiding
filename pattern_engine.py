"""Motor de detección de patrones SMC (Fair Value Gaps, Order Blocks, Liquidity Sweeps).

Algoritmos puros sobre velas OHLC: reciben una lista de dicts
[{"time": int, "open": float, "high": float, "low": float, "close": float}]
y devuelven estructuras JSON listas para el frontend. No dependen de MT5.

Convenciones SMC:
- Un FVG/OB queda MITIGADO cuando cualquier mecha posterior entra o cruza la zona
  (no solo el último cierre).
- Orden cronológico: `time` es el timestamp normalizado por el service (misma
  referencia que las velas del gráfico).
"""

from __future__ import annotations

from bisect import bisect_right
from typing import List

BULLISH_FVG = "BULLISH_FVG"
BEARISH_FVG = "BEARISH_FVG"
BULLISH_OB = "BULLISH_OB"
BEARISH_OB = "BEARISH_OB"
PDH_SWEEP = "PDH_SWEEP"
PDL_SWEEP = "PDL_SWEEP"

_ZONE_LABELS = {
    BULLISH_FVG: "Bullish FVG",
    BEARISH_FVG: "Bearish FVG",
    BULLISH_OB: "Bullish OB",
    BEARISH_OB: "Bearish OB",
}

_BOS_WINDOW = 5


def _r6(x):
    return round(float(x), 6)


def _swing_pivots(candles):
    """Índices de swing highs/lows con ventana _BOS_WINDOW a cada lado."""
    highs, lows = [], []
    n = len(candles)
    for i in range(_BOS_WINDOW, n - _BOS_WINDOW):
        seg_h = [candles[i + k]["high"] for k in range(-_BOS_WINDOW, _BOS_WINDOW + 1) if i + k != i]
        seg_l = [candles[i + k]["low"] for k in range(-_BOS_WINDOW, _BOS_WINDOW + 1) if i + k != i]
        if candles[i]["high"] >= max(seg_h):
            highs.append(i)
        if candles[i]["low"] <= min(seg_l):
            lows.append(i)
    return highs, lows


def _zone_mitigated(candles: List[dict], from_idx: int, top: float, bottom: float) -> bool:
    """True si alguna mecha (a partir de `from_idx`) entra o cruza el rango [bottom, top].

    Una zona se MITIGA en cuanto cualquier vela posterior penetra la caja (wick).
    """
    for c in candles[from_idx:]:
        if c["low"] <= top and c["high"] >= bottom:
            return True
    return False


def detect_fvgs(candles: List[dict]) -> List[dict]:
    """Fair Value Gaps de 3 velas (Bullish y Bearish).

    Solo devuelve zonas VIVAS (no mitigadas): se descartan los FVG cuya mecha
    de cualquier vela posterior entró/cruzó el rango. El tipo distingue
    BULLISH_FVG (alcista) de BEARISH_FVG (bajista).
    """
    out: List[dict] = []
    n = len(candles)
    for i in range(2, n):
        prev, cur = candles[i - 2], candles[i]
        if cur["low"] > prev["high"]:
            top, bottom, bullish = cur["low"], prev["high"], True
        elif cur["high"] < prev["low"]:
            top, bottom, bullish = prev["low"], cur["high"], False
        else:
            continue
        if _zone_mitigated(candles, i + 1, top, bottom):
            continue
        out.append({
            "type": BULLISH_FVG if bullish else BEARISH_FVG,
            "top": _r6(top),
            "bottom": _r6(bottom),
            "start_time": cur["time"],
        })
    return out


def _append_active_ob(out, candles, ob_idx, bos_idx, ob_type):
    ob = candles[ob_idx]
    top, bottom = ob["high"], ob["low"]
    # La mitigación se evalúa DESPUÉS de la vela de ruptura del BOS (bos_idx):
    # la propia vela de impulso sale de la zona por definición y no la mitiga.
    if _zone_mitigated(candles, bos_idx + 1, top, bottom):
        return
    out.append({
        "type": ob_type,
        "top": _r6(top),
        "bottom": _r6(bottom),
        "start_time": ob["time"],
    })


def detect_order_blocks(candles: List[dict]) -> List[dict]:
    """Order Block: última vela contraria previa al impulso que rompe estructura (BOS).

    Solo devuelve OBs VIVOS: se descartan los que cualquier vela posterior haya
    vuelto a penetrar (mitigados).
    """
    out: List[dict] = []
    n = len(candles)
    highs, lows = _swing_pivots(candles)
    last_sh = None  # (precio, índice) del último swing high confirmado
    last_sl = None  # (precio, índice) del último swing low confirmado
    seen_obs: set = set()  # evita repetir el mismo OB en cada candle de BOS

    hi_p, lo_p = 0, 0
    for i in range(max(_BOS_WINDOW, 1), n):
        # Avanzar pivotes confirmados hasta antes de i
        while hi_p < len(highs) and highs[hi_p] < i:
            if last_sh is None or candles[highs[hi_p]]["high"] >= last_sh[0]:
                last_sh = (candles[highs[hi_p]]["high"], highs[hi_p])
            hi_p += 1
        while lo_p < len(lows) and lows[lo_p] < i:
            if last_sl is None or candles[lows[lo_p]]["low"] <= last_sl[0]:
                last_sl = (candles[lows[lo_p]]["low"], lows[lo_p])
            lo_p += 1

        if last_sh and candles[i]["close"] > last_sh[0]:
            ob_idx = _last_opposite_candle(candles, i, _BOS_WINDOW, up=True)
            if ob_idx is not None and ob_idx not in seen_obs:
                _append_active_ob(out, candles, ob_idx, i, BULLISH_OB)
                seen_obs.add(ob_idx)
        elif last_sl and candles[i]["close"] < last_sl[0]:
            ob_idx = _last_opposite_candle(candles, i, _BOS_WINDOW, up=False)
            if ob_idx is not None and ob_idx not in seen_obs:
                _append_active_ob(out, candles, ob_idx, i, BEARISH_OB)
                seen_obs.add(ob_idx)
    return out


def _last_opposite_candle(candles, before_idx: int, window: int, up: bool) -> int | None:
    """Última vela en dirección contrastaria al impulso, previa al BOS.

    up=True  → impulso alcista → la OB es la última vela BAJISTA.
    up=False → impulso bajista → la OB es la última vela ALCISTA.
    """
    start = max(0, before_idx - window)
    for j in range(before_idx - 1, start - 1, -1):
        c = candles[j]
        if up and c["close"] < c["open"]:
            return j
        if (not up) and c["close"] > c["open"]:
            return j
    return None


def detect_sweeps(candles: List[dict], pdh: float | None, pdl: float | None) -> List[dict]:
    """Liquidity Sweeps: mecha que supera PDH/PDL y cierra de vuelta dentro del rango."""
    out: List[dict] = []
    for c in candles:
        if pdh is not None and c["high"] > pdh and c["close"] < pdh:
            out.append({
                "type": PDH_SWEEP,
                "price_level": _r6(pdh),
                "wick_extreme": _r6(c["high"]),
                "time": c["time"],
            })
        elif pdl is not None and c["low"] < pdl and c["close"] > pdl:
            out.append({
                "type": PDL_SWEEP,
                "price_level": _r6(pdl),
                "wick_extreme": _r6(c["low"]),
                "time": c["time"],
            })
    return out


def analyze(candles: List[dict], pdh: float | None, pdl: float | None,
            symbol: str = "", timeframe: str = "") -> dict:
    """JSON completo por endpoint: fvgs + order_blocks + sweeps."""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "patterns": {
            "fvgs": detect_fvgs(candles),
            "order_blocks": detect_order_blocks(candles),
            "sweeps": detect_sweeps(candles, pdh, pdl),
        },
    }


def classify_entry(candles: List[dict], pdh: float | None, pdl: float | None,
                   entry_price: float, entry_time: int) -> dict:
    """Cruza el precio/hora de entrada con las zonas detectadas (para bitácora).

    Devuelve {"poi_type": str|None, "liquidity_swept": str|None}.
    """
    n = len(candles)
    j = bisect_right([c["time"] for c in candles], entry_time) - 1
    if j < 0:
        return {"poi_type": None, "liquidity_swept": None}

    parts: List[str] = []

    for fg in detect_fvgs(candles):
        if fg["start_time"] <= candles[j]["time"] and fg["bottom"] <= entry_price <= fg["top"]:
            parts.append(_ZONE_LABELS[fg["type"]])
    for ob in detect_order_blocks(candles):
        if ob["start_time"] <= candles[j]["time"] and ob["bottom"] <= entry_price <= ob["top"]:
            parts.append(_ZONE_LABELS[ob["type"]])

    swept = None
    for sw in detect_sweeps(candles[: j + 1], pdh, pdl):
        idx = _index_of_time(candles, sw["time"])
        if idx is not None and j - idx <= 8:
            swept = "PDH Sweep" if sw["type"] == PDH_SWEEP else "PDL Sweep"
            break

    return {
        "poi_type": " + ".join(dict.fromkeys(parts)) or None,
        "liquidity_swept": swept,
    }


def _index_of_time(candles, ts):
    for i, c in enumerate(candles):
        if c["time"] == ts:
            return i
    return None