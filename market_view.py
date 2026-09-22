"""Vistas de mercado (footprint, heatmap de liquidez, barras por evento).

Modulo puro: recibe velas OHLC dicts y devuelve datasets listos para el frontend.
NO depende de MT5 ni de app/agent. Los datos son SINTETICOS (derivados de las
velas OHLC y su tick_volume) mientras el feed Databento live este inactivo.

Contrato de datos: `source` siempre es "synthetic" aqui. Cuando se active el feed
real (MBO/MBP-1 de Databento, futuro 6E) basta con sustituir el proveedor interno
por los ticks reales manteniendo el MISMO shape de salida; la UI no cambia.

Convencion de velas de entrada:
  [{"time": int, "open": float, "high": float, "low": float, "close": float,
    "volume": float}]
"""

from __future__ import annotations

import math
import random
from typing import List, Optional

DEFAULT_ROWS = 12
MAX_BARS = 300


def _price_step(price: float) -> float:
    """Granularidad de precio (paso) segun la magnitud del instrumento."""
    p = abs(float(price))
    if p < 1:
        return 0.00001
    if p < 100:
        return 0.0001
    if p < 1000:
        return 0.1
    if p < 10000:
        return 1.0
    return 5.0


def _r(x, n=6):
    return round(float(x), n)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- footprint

def footprint(candles: List[dict], max_bars: int = 150, bid_ratio: float = 0.6,
              rows: int = DEFAULT_ROWS) -> Optional[dict]:
    """Footprint / cluster chart por barra.

    Modelo sintetico: el tick_volume de la barra se divide en agresion compradora
    y vendedora segun la direccion de la vela (close vs open) y se distribuye a lo
    largo de su rango high-low con forma triangular centrada en el cierre.

    - `bid`: volumen en el lado bid (agresores vendedores).
    - `ask`: volumen en el lado ask (agresores compradores).
    - `delta` = ask - bid por nivel.
    """
    if not candles:
        return None
    sel = candles[-max_bars:]
    bars = []
    step = _price_step(sel[-1]["close"])
    rng = random.Random(hash(tuple(c["time"] for c in sel)) & 0xFFFFFFFF)

    for c in sel:
        high, low, close, open_ = c["high"], c["low"], c["close"], c["open"]
        vol = max(float(c.get("volume") or 0), 0.0)
        rng_span = max(high - low, step if high > low else 0.0)
        if high <= low:
            levels = [{"price": _r(close), "bid": 0.0, "ask": 0.0, "delta": 0.0}]
            bars.append({
                "time": int(c["time"]), "open": _r(open_), "high": _r(high),
                "low": _r(low), "close": _r(close), "vol": round(vol, 2),
                "delta": 0.0, "levels": levels,
            })
            continue

        n_levels = _clamp(int(math.ceil(rng_span / step)), 6, rows if rows else 24)
        prices = [low + rng_span * i / (n_levels - 1) for i in range(n_levels)]

        if vol <= 0:
            base_bid = base_ask = 0.0
        else:
            buy_ratio = bid_ratio if close >= open_ else 1.0 - bid_ratio
            base_ask = vol * buy_ratio
            base_bid = vol * (1.0 - buy_ratio)

        center = close
        half = rng_span * 0.65
        weights = []
        wsum = 0.0
        for p in prices:
            w = max(0.0, 1.0 - abs(p - center) / max(half, 1e-12)) + rng.random() * 0.15
            weights.append(w)
            wsum += w

        levels = []
        bid_total = ask_total = 0.0
        for p, w in zip(prices, weights):
            b = base_bid * (w / wsum) if wsum > 0 else 0.0
            a = base_ask * (w / wsum) if wsum > 0 else 0.0
            bid_total += b
            ask_total += a
            levels.append({"price": _r(p), "bid": _r(b), "ask": _r(a),
                           "delta": _r(a - b)})

        bars.append({
            "time": int(c["time"]), "open": _r(open_), "high": _r(high),
            "low": _r(low), "close": _r(close), "vol": round(vol, 2),
            "delta": _r(ask_total - bid_total), "levels": levels,
        })

    return {"source": "synthetic", "mode": "footprint", "step": step, "bars": bars}


# ---------------------------------------------------------- liquidity heatmap

def liquidity_heatmap(candles: List[dict], max_bars: int = 150, levels: int = 64,
                      sigma_frac: float = 0.18) -> Optional[dict]:
    """Mapa de calor de liquidez (pseudo-DOM) detras de la accion del precio.

    Modelo sintetico de dinero pasivo esperando en niveles clave:
      - horizonte de valor: las zonas mas transadas del rango (shape de un VP
        interno de la ventana) concentran liquidez;
      - el precio actual lleva una "cola" gaussiana alrededor del ultimo cierre;
      - los extremos de la sesion actuan como paredes de liquidez (PDH/PDL fake).

    Devuelve `times` (indice de barra -> timestamp), `ladder` (niveles de precio)
    y `data` como [[timeIdx, levelIdx, value]...] para la serie heatmap de ECharts.
    """
    if not candles:
        return None
    sel = candles[-max_bars:]
    lo = min(c["low"] for c in sel)
    hi = max(c["high"] for c in sel)
    if hi <= lo:
        hi = lo + 1e-9
    pad = (hi - lo) * 0.005
    lo, hi = lo - pad, hi + pad

    ladder = [lo + (hi - lo) * i / (levels - 1) for i in range(levels)]

    # VP interno: peso de cada nivel por volumen transado alrededor del precio medio.
    vp_weight = [0.0] * levels
    for c in sel:
        mid = (c["open"] + c["high"] + c["low"] + c["close"]) / 4.0
        rng_span = c["high"] - c["low"]
        if rng_span <= 0:
            continue
        vol = max(float(c.get("volume") or 0), 0.0)
        for i, p in enumerate(ladder):
            w = max(0.0, 1.0 - abs(p - mid) / (rng_span * 1.4))
            vp_weight[i] += vol * w
    v_max = max(vp_weight) or 1.0
    vp_norm = [w / v_max for w in vp_weight]

    sigma = (hi - lo) * sigma_frac
    sig2 = 2.0 * sigma * sigma
    data: List[list] = []
    times: List[int] = []
    for t, c in enumerate(sel):
        center = c["close"]
        times.append(int(c["time"]))
        near_lo = abs(center - lo) < (hi - lo) * 0.03
        near_hi = abs(center - hi) < (hi - lo) * 0.03
        for i, p in enumerate(ladder):
            v = 0.0
            if sig2 > 0:
                v += 0.65 * math.exp(-((p - center) ** 2) / sig2)
            v += 0.35 * vp_norm[i]
            if near_lo and p <= lo + (hi - lo) * 0.03:
                v += 0.8
            if near_hi and p >= hi - (hi - lo) * 0.03:
                v += 0.8
            if v > 0.02:
                data.append([t, i, _r(v, 4)])

    return {"source": "synthetic", "mode": "liquidity_heatmap", "times": times,
            "ladder": [_r(p) for p in ladder], "data": data}


# ----------------------------------------------------------------- event bars

def _simulate_ticks(candle: dict, n: int = 48) -> List[dict]:
    """Genera ticks sinteticos dentro de una vela (OHLC respetado), con seed estable."""
    rng = random.Random((candle["time"] ^ 0x9E3779B9) & 0xFFFFFFFF)
    o, h, l, cl = candle["open"], candle["high"], candle["low"], candle["close"]
    if h <= l:
        h = max(h, o) + 1e-9
        l = min(l, o) - 1e-9
    span = h - l
    vol = max(float(candle.get("volume") or 0), 1.0)

    prices = []
    prev = o
    p = o
    for k in range(1, n + 1):
        f = k / n
        drift = (cl - o) * f
        noise = (rng.random() - 0.5) * span * 0.7 * math.sqrt(f)
        p = min(max(o + drift + noise, l), h)
        prices.append(p)

    # Volumen por tick: mas peso donde mas tiempo pasa el precio (cerca del cierre).
    wsum = 0.0
    weights = []
    for p in prices:
        w = 1.0 + 1.5 * (1.0 - abs(p - cl) / max(span, 1e-12)) + rng.random()
        weights.append(w)
        wsum += w

    ticks = []
    for k, p in enumerate(prices):
        prev = prices[k - 1] if k > 0 else o
        side = "buy" if p >= prev else "sell"
        ticks.append({"time": int(candle["time"]) + k, "price": _r(p, 6),
                      "vol": round(vol * weights[k] / wsum, 6), "side": side})
    return ticks


def _aggregate(ticks: List[dict], mode: str, param: int) -> List[dict]:
    """Agrega ticks a barras por volumen (volbar) o por numero de ticks (tickbar)."""
    if param < 1:
        param = 1
    bars: List[dict] = []
    cur = None
    acc_vol = 0.0
    acc_n = 0
    for t in ticks:
        if cur is None:
            cur = {"time": t["time"], "open": t["price"], "high": t["price"],
                   "low": t["price"], "close": t["price"], "volume": 0.0}
        cur["high"] = max(cur["high"], t["price"])
        cur["low"] = min(cur["low"], t["price"])
        cur["close"] = t["price"]
        cur["volume"] += t["vol"]
        acc_vol += t["vol"]
        acc_n += 1
        done = acc_vol >= param if mode == "volbar" else acc_n >= param
        if done:
            cur["volume"] = round(cur["volume"], 2)
            bars.append(cur)
            cur = None
            acc_vol = 0.0
            acc_n = 0
    if cur:
        cur["volume"] = round(cur["volume"], 2)
        bars.append(cur)
    return bars


def _renko(ticks: List[dict], brick_size: float) -> List[dict]:
    """Rebuilds Renko: ladrillos de `brick_size`; solo se emiten ladrillos cerrados."""
    if brick_size <= 0:
        return []
    out: List[dict] = []
    last: Optional[float] = None
    pending: Optional[dict] = None

    for t in ticks:
        price, vol = t["price"], t["vol"]
        if last is None:
            last = price
            pending = {"time": t["time"], "open": price, "high": price,
                       "low": price, "close": price, "volume": vol}
            continue
        if pending:
            pending["high"] = max(pending["high"], price)
            pending["low"] = min(pending["low"], price)
            pending["close"] = price
            pending["volume"] += vol

        up = last + brick_size
        dn = last - brick_size
        while price >= up:
            if pending:
                pending["close"] = last + brick_size
                pending["high"] = max(pending["high"], pending["close"])
                pending["volume"] = round(pending["volume"], 2)
                out.append(pending)
                pending = None
            last = up
            up = last + brick_size
            dn = last - brick_size
        while price <= dn:
            if pending:
                pending["close"] = last - brick_size
                pending["low"] = min(pending["low"], pending["close"])
                pending["volume"] = round(pending["volume"], 2)
                out.append(pending)
                pending = None
            last = dn
            up = last + brick_size
            dn = last - brick_size
        if pending is None:
            pending = {"time": t["time"], "open": last, "high": price,
                       "low": price, "close": price, "volume": vol}
    return out


def event_bars(candles: List[dict], bar_type: str = "volbar", param: int = 500,
               ticks_per_candle: int = 48) -> Optional[dict]:
    """Barras por evento (volbar / tickbar / renko) desde OHLCV sintetico."""
    if not candles:
        return None
    ticks = []
    for c in candles:
        ticks.extend(_simulate_ticks(c, ticks_per_candle))
    if not ticks:
        return None

    mode = (bar_type or "volbar").lower()
    if mode == "renko":
        # param se interpreta en PASOS DE PRECIO (1 = una "casilla" de price step).
        step = _price_step(ticks[-1]["price"])
        brick = (float(param) if param and param > 0 else 5.0) * step
        bars = _renko(ticks, brick)
    elif mode in ("volbar", "tickbar"):
        bars = _aggregate(ticks, mode, int(param))
    else:
        return None

    return {"source": "synthetic", "mode": "eventbars", "bar_type": mode.lower(),
            "param": int(param), "step": _price_step(ticks[-1]["price"]),
            "bars": bars}