"""Servicio de patrones SMC: fetch de velas MT5 (TF + D1 para PDH/PDL), caché y
clasificación de operación para la bitácora.

Módulo intermedio compartido por app.py (endpoint, journal, market order) y por el
tool 'patterns' del agente. No importa app ni agent (evita ciclos).

Normalización de tiempos: los timestamps se construyen con `_ts()`, que se aplica
IDENTICAMENTE a las velas y a los patrones derivados. Así cajas/velas siempre quedan
en la misma referencia horizontal (si algún día se quiere restar el offset del broker
[UTC+2/+3], el cambio se hace solo aquí Y en app.to_candle, nunca en una sola de las dos).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import MetaTrader5 as mt5

import pattern_engine as pe

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}

# Espejo de app.run_mt5: única vía de acceso a MT5 (conexión + lock + executor).
_mt5_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5p")
_mt5_lock = threading.Lock()

CACHE_TTL = 10.0
_cache = {}
_cache_lock = threading.Lock()

DEFAULT_TIMEFRAME = "M15"
DEFAULT_BARS = 300


def _ts(raw: int) -> int:
    """Normalizador único de timestamps (velas Y patrones juntos)."""
    return int(raw)


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


def _mt5_run(fn):
    return _mt5_executor.submit(_mt5_call_lock, fn).result(timeout=30)


def _candle(r):
    return {
        "time": _ts(r[0]),
        "open": r[1],
        "high": r[2],
        "low": r[3],
        "close": r[4],
        "volume": r[5],
    }


def _fetch(symbol: str, timeframe: str, bars: int):
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1.")

    def _get():
        mt5.symbol_select(symbol, True)
        intraday = mt5.copy_rates_from_pos(symbol, tf, 0, max(10, min(bars, 1000)))
        d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)
        return intraday, d1

    try:
        intraday, d1 = _mt5_run(_get)
    except RuntimeError:
        return None
    if intraday is None or len(intraday) == 0:
        return None

    candles = [_candle(r) for r in intraday.tolist()]

    pdh = pdl = None
    if d1 is not None and len(d1) >= 2:
        past = d1.tolist()[:-1]  # excluye la vela D1 en formación de hoy
        if past:
            pdh = max(float(r[2]) for r in past)
            pdl = min(float(r[3]) for r in past)

    return {"candles": candles, "pdh": pdh, "pdl": pdl}


_PROVIDER = None


def register_provider(fn) -> None:
    """Registra un proveedor alternativo de velas/datos para get_pattern_data.

    Cuando está registrado y devuelve datos (no None), get_pattern_data lo usa
    ANTES de tocar MT5. app.py lo registra apuntando al MarketSimulator para que
    tool del agente, bitácora y endpoints que no hacen su propio branching se
    alimenten de la cinta sintética cuando el feed mock 6E está activo. fn es
    puro (no importa app): se inyecta una lambda. Devuelve None pa filtrarse a
    MT5 (mantiene el fallback histórico).
    """
    global _PROVIDER
    _PROVIDER = fn


def get_pattern_data(symbol: str, timeframe: str = DEFAULT_TIMEFRAME,
                     bars: int = DEFAULT_BARS) -> Optional[dict]:
    """Datos de patrones con caché TTL. Devuelve {"candles", "pdh", "pdl", "analysis"}
    o None si no hay datos. Lanza ValueError (tf inválido) / RuntimeError (sin MT5)."""
    symbol = (symbol or "").upper()
    tf = (timeframe or DEFAULT_TIMEFRAME).upper()
    key = (symbol, tf, int(bars))

    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["ts"] < CACHE_TTL:
            return hit["data"]

    provider = _PROVIDER
    if provider is not None:
        data = provider(symbol, tf, bars)
        if data is None:
            return None
    else:
        data = _fetch(symbol, tf, bars)
        if data is None:
            return None

    data["analysis"] = pe.analyze(
        data["candles"], data["pdh"], data["pdl"], symbol=symbol, timeframe=tf
    )

    with _cache_lock:
        _cache[key] = {"ts": now, "data": data}
    return data


def classify_entry(symbol: str, timeframe: str, entry_price: float,
                   entry_time: int) -> dict:
    """Clasifica un precio/hora de entrada contra las zonas detectadas (bitácora)."""
    data = get_pattern_data(symbol, timeframe)
    if data is None:
        return {"poi_type": None, "liquidity_swept": None}
    return pe.classify_entry(data["candles"], data["pdh"], data["pdl"],
                             float(entry_price), int(entry_time))


def clear_cache(symbol: Optional[str] = None, timeframe: Optional[str] = None):
    """Limpia la caché (explícito o por símbolo/timeframe)."""
    with _cache_lock:
        if symbol is None and timeframe is None:
            _cache.clear()
            return
        for k in list(_cache.keys()):
            if (symbol is None or k[0] == symbol.upper()) and \
               (timeframe is None or k[1] == timeframe.upper()):
                _cache.pop(k, None)