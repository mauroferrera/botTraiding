"""Servicio SMR / Divergencia DXY (Smart Money Reversal).

Lee el Indoice del Dolar (DX-Y.NYB, Yahoo Finance) gratis — sin Databento — con
cache TTL, alinea las velas del EURUSD (o 6E) con las del DXY en la misma
temporalidad y aplica la regla de divergencia SMT/SMR:

  SMR alcista (BUY) :  EURUSD rompe su minimo previo (LL/Sweep) Y el DXY NO
                       hace nuevo maximo (no HH).
  SMR bajista (SELL):  EURUSD rompe su maximo previo (LH/Sweep) Y el DXY NO
                       hace nuevo minimo (no LL).

La falta de simetria DXY es la huella institucional de acumulacion/distribucion
y reduce fakeouts: el euro barre liquidez pero el dolar NO confirma la ruptura.

Modulo intermedio: importa patterns_service (velas EURUSD via MT5) y yfinance.
NO importa app ni agent (evita ciclos). `detect_smr` es pura y testeable sin red.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import yfinance as yf

import patterns_service

DXY_TICKER = "DX-Y.NYB"
DXY_SOURCE = "yahoo: DX-Y.NYB"

CACHE_TTL = 120.0
DISK_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               ".dxy_cache.json")
_caches: dict = {}
_cache_lock = threading.Lock()

_PERIOD = {
    "M1": "5d",
    "M5": "14d",
    "M15": "14d",
    "M30": "14d",
    "H1": "40d",
    "H4": "60d",
    "D1": "1y",
    "W1": "5y",
}

_INTERVALS = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "60m",
    "H4": "4h",
    "D1": "1d",
    "W1": "1wk",
}

DEFAULT_TIMEFRAME = "M15"
DEFAULT_LOOKBACK = 8


# ============================================================
# Feed DXY (Yahoo Finance, sin API key)
# ============================================================

def _valid_timeframe(timeframe: str) -> str:
    tf = (timeframe or DEFAULT_TIMEFRAME).upper()
    if tf not in _INTERVALS:
        raise ValueError(f"Timeframe '{timeframe}' no valido. Usa M1..M30, H1, H4, D1 o W1.")
    return tf


def _fetch_dxy(timeframe: str = DEFAULT_TIMEFRAME) -> List[Dict[str, Any]]:
    """Descarga velas OHLCV de DX-Y.NYB (Yahoo) en el timeframe pedido."""
    tf = _valid_timeframe(timeframe)
    interval = _INTERVALS[tf]
    period = _PERIOD[tf]
    df = yf.Ticker(DXY_TICKER).history(period=period, interval=interval, auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError(f"Sin datos de {DXY_TICKER} (Yahoo {interval}).")
    candles = []
    for idx, row in df.iterrows():
        try:
            ts = int(idx.timestamp())
        except (OverflowError, ValueError):
            continue
        candles.append({
            "time": ts,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0.0) or 0.0),
        })
    return candles


def _load_disk_cache():
    """Carga el caché a disco (copias M15/M1..H4) para sobrevivir a rate-limits
    de Yahoo. Devuelve dict {tf: [candles]} o {} ante cualquier error."""
    try:
        with open(DISK_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_disk_cache(tf: str, candles: List[Dict[str, Any]]):
    try:
        data = _load_disk_cache()
        data[tf] = candles
        tmp = DISK_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, DISK_CACHE_FILE)
    except Exception:
        pass


def get_dxy_candles(timeframe: str = DEFAULT_TIMEFRAME,
                    bars: int = 300,
                    ttl: float = CACHE_TTL) -> Optional[List[Dict[str, Any]]]:
    """Velas del DXY con cache TTL en memoria + copia a disco (fallback ante
    rate-limit de Yahoo). Devuelve la ultima `bars` o None si todos fallan."""
    tf = _valid_timeframe(timeframe)
    key = ("dxy", tf, int(bars))
    now = time.time()
    with _cache_lock:
        hit = _caches.get(key)
        if hit and now - hit["ts"] < ttl:
            return hit["data"]
        stale = hit

    try:
        candles = _fetch_dxy(tf)
    except Exception:
        candles = None

    if not candles and stale is not None:
        return stale["data"]
    if not candles:
        disk = _load_disk_cache().get(tf)
        if disk:
            data = disk[-int(max(10, min(bars, 1000))):] if disk else []
            with _cache_lock:
                _caches[key] = {"ts": now, "data": data}
            return data or None
        return None

    data = candles[-int(max(10, min(bars, 1000))):] if candles else []
    with _cache_lock:
        _caches[key] = {"ts": now, "data": data}
    _save_disk_cache(tf, data)
    return data or None


# ============================================================
# Detector de divergencia (puro, testeable)
# ============================================================

def _swing_break(window: List[Dict[str, Any]], prev: List[Dict[str, Any]],
                 side: str) -> Dict[str, Any]:
    """¿El ultimo candle rompe un extremo previo?

    side 'low'  -> la vela actual hace un nuevo minimo (break por debajo del
                   minimo de las `prev` velas).
    side 'high' -> la vela actual hace un nuevo maximo (break por encima del
                   maximo de las `prev` velas).
    """
    cur = window[-1]
    if side == "low":
        prev_extreme = min(c["low"] for c in prev)
        break_price = cur["low"]
        margin = prev_extreme - break_price
        return {
            "broke": bool(margin > 0),
            "margin": round(float(margin), 6),
            "level": round(float(prev_extreme), 6),
            "price": round(float(break_price), 6),
        }
    prev_extreme = max(c["high"] for c in prev)
    break_price = cur["high"]
    margin = break_price - prev_extreme
    return {
        "broke": bool(margin > 0),
        "margin": round(float(margin), 6),
        "level": round(float(prev_extreme), 6),
        "price": round(float(break_price), 6),
    }


def detect_smr(eurusd_candles: Optional[List[Dict[str, Any]]],
               dxy_candles: Optional[List[Dict[str, Any]]],
               direction: str = "BUY",
               lookback: int = DEFAULT_LOOKBACK) -> Dict[str, Any]:
    """Divergencia SMR alcista (BUY) o bajista (SELL) sobre las ultimas N velas.

    - BUY : EURUSD barre el minimo previo (LL) Y el DXY NO quiebra su maximo
            previo (no HH) -> acumulacion institucional de largos.
    - SELL: EURUSD barre el maximo previo (LH) Y el DXY NO quiebra su minimo
            previo (no LL) -> distribuicion institucional de cortos.

    Devuelve {"confirmed", "detail", "data"} siempre (nunca lanza).
    """
    d = str(direction or "BUY").upper()
    if d not in ("BUY", "SELL"):
        raise ValueError(f"direction debe ser BUY o SELL, no '{direction}'.")

    if not eurusd_candles:
        return _not_confirmed("Sin velas de EURUSD/6E.", None)
    if not dxy_candles:
        return _not_confirmed("Sin datos del DXY (feed degradado a neutro).", None)

    n = max(2, int(lookback))
    eu = list(eurusd_candles)
    dxy = list(dxy_candles)
    if len(eu) < n + 1 or len(dxy) < n + 1:
        return _not_confirmed(
            f"Velas insuficientes (EUR {len(eu)} / DXY {len(dxy)}; max {n}+1).", None)

    eu_win, eu_prev = eu[-n - 1:], eu[-n - 1:-1]
    dxy_win, dxy_prev = dxy[-n - 1:], dxy[-n - 1:-1]

    if d == "BUY":
        eu_break = _swing_break(eu_win, eu_prev, "low")   # minimo previo (LL)
        dxy_break = _swing_break(dxy_win, dxy_prev, "high")  # maximo previo (HH)
        label = "alcista"
    else:
        eu_break = _swing_break(eu_win, eu_prev, "high")  # maximo previo (LH)
        dxy_break = _swing_break(dxy_win, dxy_prev, "low")   # minimo previo (LL)
        label = "bajista"

    data = {
        "eurusd": eu_break,
        "dxy": dxy_break,
        "lookback": n,
        "direction": d,
    }
    confirmed = bool(eu_break["broke"]) and not bool(dxy_break["broke"])
    if confirmed:
        detail = (
            f"Divergencia SMR {label}: EURUSD quiebra {'minimo' if d == 'BUY' else 'maximo'} "
            f"previo ({eu_break['price']:.5f}) y el DXY NO quiebra su "
            f"{'maximo' if d == 'BUY' else 'minimo'} previo ({dxy_break['level']:.3f})."
        )
    else:
        detail = (
            f"Sin divergencia SMR: EURUSD {'quiebra' if eu_break['broke'] else 'NO quiebra'} "
            f"su {'minimo' if d == 'BUY' else 'maximo'} previo y el DXY "
            f"{'quiebra' if dxy_break['broke'] else 'NO quiebra'} el suyo."
        )
    return {"confirmed": confirmed, "detail": detail, "data": data}


def _not_confirmed(reason: str, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {"confirmed": False, "detail": reason, "data": data}


# ============================================================
# Evaluacion completa (feed DXY + velas EURUSD)
# ============================================================

def evaluate(symbol: str = "EURUSD",
             timeframe: str = DEFAULT_TIMEFRAME,
             candles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Evaluacion SMR para ambas direcciones.

    `candles` (opcional) evita re-fetch de MT5 cuando el llamador ya los tiene
    (p.ej. build_chart_snapshot). Devuelve siempre un dict estable; ante fallos
    del feed DXY, ambas direcciones degradan a neutro (confirmed=False).
    """
    sym = (symbol or "EURUSD").upper()
    tf = _valid_timeframe(timeframe)

    eu = candles
    if eu is None or not eu:
        try:
            data = patterns_service.get_pattern_data(sym, tf)
            eu = (data or {}).get("candles") or []
        except Exception:
            eu = []

    dxy_candles = get_dxy_candles(tf)
    dxy_close = None
    if dxy_candles:
        dxy_close = dxy_candles[-1]["close"]

    bull = detect_smr(eu, dxy_candles, "BUY")
    bear = detect_smr(eu, dxy_candles, "SELL")

    return {
        "symbol": sym,
        "timeframe": tf,
        "dxy_available": bool(dxy_candles),
        "dxy": {
            "last_close": dxy_close,
            "candles": len(dxy_candles or []),
            "source": DXY_SOURCE,
        },
        "bull": bull,
        "bear": bear,
    }


def clear_cache(timeframe: Optional[str] = None):
    with _cache_lock:
        if timeframe is None:
            _caches.clear()
            return
        tf = timeframe.upper()
        for k in list(_caches.keys()):
            if k[0] == "dxy" and k[1] == tf:
                _caches.pop(k, None)
    try:
        if timeframe is None:
            os.remove(DISK_CACHE_FILE)
        else:
            data = _load_disk_cache()
            data.pop(tf, None)
            with open(DISK_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
    except Exception:
        pass