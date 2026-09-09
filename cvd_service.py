"""Servicio de CVD sintético basado en Tick Volume de MT5.

Mientras el feed live de Databento (6E) está pausado por falta de licencia, se
genera una curva de Cumulative Volume Delta (CVD) aproximada a partir de las
velas de MT5 del símbolo/timeframe activo (p. ej. EURUSD M15).

Modelo (por vela):
  - alcista (close > open):  delta =  +tick_volume * 0.6
  - bajista (close < open):  delta =  -tick_volume * 0.6
  - doji / neutral:          delta =   0
El CVD se acumula vela a vela para producir el array histórico { time, value }.

Nota de tiempos: se normaliza con `_ts()` (la misma referencia que las velas del
gráfico) para que la serie encaje horizontalmente en Lightweight Charts.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import MetaTrader5 as mt5

from patterns_service import TIMEFRAMES, _ts

# Espejo de app.run_mt5: única vía de acceso a MT5 (conexión + lock + executor).
_mt5_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5c")
_mt5_lock = threading.Lock()

CACHE_TTL = 5.0
_cache = {}
_cache_lock = threading.Lock()

DELTA_RATIO = 0.6  # flujo asumido de tick_volume por vela direccional


def _mt5_call_lock(fn):
    with _mt5_lock:
        if not mt5.initialize():
            mt5.shutdown()
            raise RuntimeError(
                "No hay conexión con MetaTrader 5. "
                "Asegúrate de que la terminal esté abierta y con sesión iniciada."
            )
        try:
            return fn()
        finally:
            mt5.shutdown()


def _candle_delta(r) -> float:
    """Delta sintético de una vela según su cuerpo y tick volume."""
    volume = float(r[5])  # tick_volume
    if volume <= 0:
        return 0.0
    if r[4] > r[1]:  # close > open
        return volume * DELTA_RATIO
    if r[4] < r[1]:  # close < open
        return -volume * DELTA_RATIO
    return 0.0  # doji / neutral


def _fetch(symbol: str, timeframe: str, bars: int) -> Optional[List[dict]]:
    tf = TIMEFRAMES.get((timeframe or "M15").upper())
    if tf is None:
        raise ValueError(
            f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."
        )

    def _get():
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, max(10, min(bars, 1000)))
        return rates.tolist() if rates is not None else None

    try:
        rows = _mt5_executor.submit(_mt5_call_lock, _get).result(timeout=30)
    except RuntimeError:
        return None
    if not rows:
        return None

    cvd = 0.0
    points: List[dict] = []
    for r in rows:
        cvd += _candle_delta(r)
        points.append({"time": _ts(r[0]), "value": round(cvd, 2)})
    return points


def get_cvd(symbol: str, timeframe: str = "M15", bars: int = 300) -> Optional[List[dict]]:
    """Serie CVD acumulada { time, value } con caché TTL.

    Devuelve None si no hay datos (MT5 cerrado / símbolo ausente).
    Lanza ValueError si el timeframe es inválido.
    """
    symbol = (symbol or "").upper()
    tf = (timeframe or "M15").upper()
    bars = max(10, min(int(bars), 1000))
    key = (symbol, tf, bars)

    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["ts"] < CACHE_TTL:
            return hit["data"]

    points = _fetch(symbol, tf, bars)
    if points is not None:
        with _cache_lock:
            _cache[key] = {"ts": now, "data": points}
    return points


def pick_cvd_source(live_points, synthetic_points, min_live_points=5):
    """Elige la fuente real del CVD para el snapshot del gráfico.

    Pura y testeable. Devuelve (points, source, warning).

    - Si hay serie live suficiente (>= min_live_points) gana la live.
    - Si la live es insuficiente/ausente pero la feed está conectada devuelve la
      sintética con warning (para no mentir en el label). Etiquetas:
      "live (Databento 6E)" / "synthetic (tick volume MT5)".
    """
    live = list(live_points) if live_points else []
    syn = list(synthetic_points) if synthetic_points else []

    if len(live) >= min_live_points:
        return live, "live (Databento 6E)", None
    if syn:
        if live:
            warning = (
                "feed live conectado pero sin suficientes puntos recientes "
                f"({len(live)}/{min_live_points}), se usa serie sintética MT5."
            )
        else:
            warning = None
        return syn, "synthetic (tick volume MT5)", warning
    return None, None, "sin datos de CVD disponibles"
