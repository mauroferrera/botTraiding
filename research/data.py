"""research/data.py — export y caché offline de mercado (solo research).

Pipeline separado: nunca lo importa app/agent/watcher. El paso `export()` necesita
la terminal MT5 abierta (SOLO en ese momento); el resto del pipeline (cargar,
niveles diarios, sim) corre 100% offline sobre los CSV de `research/data/`.

Normalización de tiempos: idéntica a patterns_service._ts (identidad sobre el
timestamp del broker). La hora del broker se trata como UTC — la misma convención
que usa el resto del proyecto (killzone_score, etc.). Si algún día se quiere restar
el offset (UTC+2/+3), el cambio se hace aquí Y en el resto del proyecto, nunca en
una sola de las dos partes.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# MetaTrader5 es una dependencia opcional para este módulo: las funciones puras
# (to_candle, _iter_history, with_daily_levels, load_data) funcionan sin él.
_MT5_TF: Dict[str, int] = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 16385, "H4": 16388, "D1": 16408, "W1": 32769,
}

try:  # pragma: no cover - entorno con el paquete MetaTrader5
    import MetaTrader5 as _mt5
    TIMEFRAMES: Dict[str, int] = {
        k: int(getattr(_mt5, f"TIMEFRAME_{k}", v)) for k, v in _MT5_TF.items()
    }
except Exception:  # pragma: no cover - CI/Linux sin el paquete MT5
    _mt5 = None
    TIMEFRAMES = dict(_MT5_TF)

RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(RESEARCH_DIR, "data")

_CANDLE_FIELDS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
_BARS_PER_CHUNK = 1000

_mt5_lock = threading.RLock()
_mt5_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5r")


def _mt5_call(fn: Callable, timeout: float = 30.0):
    """Única vía de acceso a MT5 en este módulo (mirror de patterns_service)."""
    def _run():
        if _mt5 is None:
            raise RuntimeError(
                "El paquete MetaTrader5 no está disponible en este entorno."
            )
        if not _mt5.initialize():
            _mt5.shutdown()
            raise RuntimeError(
                "No hay conexión con MetaTrader 5. "
                "Asegúrate de que la terminal esté abierta y con sesión iniciada."
            )
        try:
            return fn()
        finally:
            _mt5.shutdown()
    return _mt5_executor.submit(_run).result(timeout=timeout)


# ============================================================
# Conversión y acceso a velas (parte pura)
# ============================================================

def _row_to_dict(r: list) -> Dict[str, Any]:
    return {
        "time": int(r[0]),
        "open": r[1],
        "high": r[2],
        "low": r[3],
        "close": r[4],
        "tick_volume": r[5],
        "spread": r[6] if len(r) > 6 else 0.0,
    }


def to_candle(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza una fila (dict con claves de _CANDLE_FIELDS) a vela interna."""
    return {
        "time": int(float(row["time"])),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["tick_volume"]),
        "spread": float(row["spread"]),
    }


# ============================================================
# Caminar hacia atrás el historial (puro, inyectable)
# ============================================================

def _iter_history(fetch: Callable[[int, int], List[list]],
                  now_ts: float, days: int, chunk: int = _BARS_PER_CHUNK):
    """Generador de filas crudas (listas) caminando de la vela actual hacia atrás.

    `fetch(pos, count)` devuelve <= count filas a partir del offset `pos`
    (0 = la más reciente) o una lista vacía al llegar al final del historial.
    Orden de salida: DESCENDENTE (nueva → vieja), natural del caminado hacia
    atrás; `export()` revierte a cronológico. Corta toda fila con
    `ts <= now_ts - days` (ventana EXCLUSIVA: solo velas dentro de los últimos
    `days` días) y deduplica por timestamp.
    """
    cutoff = float(now_ts) - float(days) * 86400.0
    pos = 0
    seen = set()
    while True:
        rows = fetch(pos, chunk) or []
        if not rows:
            return
        rows = sorted(rows, key=lambda r: int(r[0]), reverse=True)  # nueva → vieja
        advanced = False
        for r in rows:
            ts = int(r[0])
            if ts > float(now_ts):
                continue
            if ts <= cutoff:
                return
            if ts in seen:
                continue
            seen.add(ts)
            advanced = True
            yield r
        if not advanced or len(rows) < chunk:
            return
        pos += len(rows)


# ============================================================
# Niveles diarios PDH/PDL (puro)
# ============================================================

def _utc_date(ts: int):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def with_daily_levels(candles: List[Dict[str, Any]],
                      prior_days: int = 2) -> List[Dict[str, Any]]:
    """Añade PDH/PDL por vela = máximo/mínimo de los `prior_days` días CERRADOS.

    Espejo del live: patterns_service usa el D1 pasado (excluye el día en
    formación) y toma max(high)/min(low) de las últimas 2-3 velas D1 completadas
    → `prior_days=2`. La vela del día en curso NUNCA aporta a su propio nivel.
    """
    ordered = sorted(candles, key=lambda c: int(c["time"]))
    completed: List[tuple] = []  # (day, high, low) cerrados; el más reciente al final
    cur: Optional[list] = None  # [day, high, low] del día en curso (incompleto)
    out: List[Dict[str, Any]] = []

    for c in ordered:
        key = _utc_date(c["time"])
        if cur is None:
            cur = [key, c["high"], c["low"]]
        elif key != cur[0]:
            completed.append((cur[0], cur[1], cur[2]))
            if len(completed) > prior_days:
                completed.pop(0)
            cur = [key, c["high"], c["low"]]
        else:
            cur[1] = max(cur[1], c["high"])
            cur[2] = min(cur[2], c["low"])

        if completed:
            pdh = max(h for _, h, _ in completed)
            pdl = min(l for _, _, l in completed)
        else:
            pdh = pdl = None
        out.append({**c, "pdh": pdh, "pdl": pdl})

    return out


# ============================================================
# CSV + caché
# ============================================================

def _stem(symbol: str, timeframe: str, days: int, now_ts: float) -> str:
    day = datetime.fromtimestamp(int(now_ts), tz=timezone.utc).strftime("%Y%m%d")
    return f"{symbol}_{timeframe}_{int(days)}d_{day}"


def write_csv(path: str, candles: List[Dict[str, Any]]) -> int:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CANDLE_FIELDS)
        writer.writeheader()
        for c in candles:
            writer.writerow({
                "time": int(c["time"]),
                "open": c["open"], "high": c["high"],
                "low": c["low"], "close": c["close"],
                "tick_volume": c["volume"], "spread": c.get("spread") or 0.0,
            })
    return len(candles)


def read_csv(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({k: r.get(k) for k in _CANDLE_FIELDS})
    return rows


# ============================================================
# Export (necesita terminal solo aquí)
# ============================================================

def export(symbol: str = "EURUSD", timeframe: str = "M15", days: int = 90,
           outdir: Optional[str] = None, now_ts: Optional[float] = None,
           fetch: Optional[Callable[[int, int], List[list]]] = None) -> Dict[str, Any]:
    """Exporta histórico paginado del símbolo a research/data/ (CSV + meta).

    `now_ts` y `fetch` se inyectan para tests (fetch con pos/count). Devuelve un
    dict con path/bars/rango/metata. Requiere terminal MT5 si no se pasa fetch.
    """
    symbol = (symbol or "EURUSD").upper()
    timeframe = (timeframe or "M15").upper()
    if timeframe not in TIMEFRAMES:
        raise ValueError(
            f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."
        )
    days = max(1, int(days))
    outdir = outdir or DATA_DIR
    os.makedirs(outdir, exist_ok=True)
    now = now_ts if now_ts is not None else time.time()

    def _real_fetch(pos: int, count: int) -> List[list]:
        return _mt5_call(
            lambda: _mt5.copy_rates_from_pos(
                symbol, TIMEFRAMES[timeframe], pos, count
            ).tolist()
        )

    def _real_meta() -> Dict[str, Any]:
        info = _mt5_call(lambda: _mt5.symbol_info(symbol))
        if not info:
            raise RuntimeError(f"'{symbol}' no existe en el Market Watch.")
        point = float(getattr(info, "point", 0.0) or 0.0)
        return {
            "point": point,
            "digits": int(getattr(info, "digits", 5)),
            "pip_price": point * 10.0,
        }

    use_fetch = fetch or _real_fetch
    rows = list(_iter_history(use_fetch, now, days))
    if not rows:
        raise RuntimeError(
            "No se obtuvo historial. ¿Terminal abierta y con sesión iniciada, "
            "y símbolo presente en Market Watch?"
        )
    rows.sort(key=lambda r: int(r[0]))
    candles = [to_candle(_row_to_dict(r)) for r in rows]

    stem = _stem(symbol, timeframe, days, now)
    csv_path = os.path.join(outdir, stem + ".csv")
    write_csv(csv_path, candles)
    bars = len(candles)

    # Meta de contrato (point/digits) solo se consulta en export real (fetch
    # inyectado = entorno de test: defaults). Ante cualquier fallo, defaults.
    meta = {"point": 0.0, "digits": 5, "pip_price": 0.0}
    if fetch is None:
        try:
            meta.update(_real_meta())
        except RuntimeError:
            pass
    meta.update({
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "bars": bars,
        "first_time": candles[0]["time"],
        "last_time": candles[-1]["time"],
        "exported_utc": datetime.now(timezone.utc).isoformat(),
    })
    meta_path = os.path.join(outdir, f"{symbol}_{timeframe}_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    return {
        "path": csv_path,
        "meta_path": meta_path,
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "bars": bars,
        "first_time": candles[0]["time"],
        "last_time": candles[-1]["time"],
    }


# ============================================================
# Carga offline (sin MT5)
# ============================================================

def load_data(symbol: str = "EURUSD", timeframe: str = "M15", days: Optional[int] = None,
              datadir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fusiona todos los CSV del símbolo/timeframe (dedup por time) en memoria.

    Devuelve {"candles": [...], "meta": {...}} o None sin archivos. Si `days`,
    recorta a la ventana más reciente. Corre sin terminal MT5.
    """
    symbol = (symbol or "EURUSD").upper()
    timeframe = (timeframe or "M15").upper()
    datadir = datadir or DATA_DIR

    meta: Dict[str, Any] = {}
    meta_path = os.path.join(datadir, f"{symbol}_{timeframe}_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (json.JSONDecodeError, OSError):
            meta = {}

    pattern = os.path.join(datadir, f"{symbol}_{timeframe}_*d_*.csv")
    paths = sorted(glob.glob(pattern))
    if not paths:
        return None

    merged: Dict[int, Dict[str, Any]] = {}
    for p in paths:
        for row in read_csv(p):
            c = to_candle(row)
            merged[int(c["time"])] = c

    candles = [merged[t] for t in sorted(merged)]
    if days and days > 0 and candles:
        cutoff = int(candles[-1]["time"]) - int(days) * 86400
        candles = [c for c in candles if int(c["time"]) > cutoff]

    return {"candles": candles, "meta": meta}


def load_dataset(symbol: str = "EURUSD", timeframe: str = "M15",
                 days: Optional[int] = None, datadir: Optional[str] = None,
                 prior_days: int = 2) -> Optional[Dict[str, Any]]:
    """load_data() + with_daily_levels() en un solo paso. None sin datos."""
    d = load_data(symbol, timeframe, days=days, datadir=datadir)
    if d is None:
        return None
    d["candles"] = with_daily_levels(d["candles"], prior_days=prior_days)
    return d