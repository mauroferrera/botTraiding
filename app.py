import asyncio
import json
import math
import numpy as np
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import databento as db
import MetaTrader5 as mt5
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent as ag
import chartism_engine
import cot_service
import cvd_service
import ff_calendar as ff                                                   
import market_view                                                         
import mock_feed
import pattern_engine
import patterns_service
import risk_engine
import simulator
import smr_service
import store
import watcher

load_dotenv()

app = FastAPI(title="MT5 Dashboard & Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

# Usamos el ejecutor centralizado de patterns_service para evitar colisiones
run_mt5 = patterns_service._mt5_run


# ============================================================
# Order Flow Engine (6E Databento)
# ============================================================

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY", "")
OF_SYMBOL = "6E.c.0"
OF_DATASET = "GLBX.MDP3"
OF_EMA_WINDOW = 50
OF_ZSCORE_THRESHOLD = 2.5
OF_ABSORB_TRADES = 120
OF_ABSORB_VOL_MIN = 40
OF_ABSORB_RANGE_RATIO = 0.0004
OF_ABSORB_DELTA_RATIO = 0.25


class OrderFlowEngine:
    """Acumula metrics de order flow (CVD, spikes Z-score, absorción) de forma thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._volumes = deque(maxlen=200)
        self._ema = None
        self._ema_var = 0.0
        self.recent_trades = deque(maxlen=300)
        self.cvd = 0.0
        self.delta = 0.0
        self.buy_vol = 0.0
        self.sell_vol = 0.0
        self.total_vol = 0.0
        self.spike_count = 0
        self.alerts = deque(maxlen=60)
        self.last_price = None
        self.absorb_bins = {}
        self.zscore_threshold = OF_ZSCORE_THRESHOLD
        self.absorb_trades = OF_ABSORB_TRADES
        self.cvd_history = deque(maxlen=3000)
        self._cvd_bucket = None

    def update_settings(self, zscore_threshold=None, absorb_trades=None):
        with self._lock:
            if zscore_threshold is not None:
                self.zscore_threshold = round(max(0.1, float(zscore_threshold)), 2)
            if absorb_trades is not None:
                self.absorb_trades = int(max(20, min(absorb_trades, 300)))
            return self.settings_locked()

    def settings_locked(self):
        return {
            "zscore_threshold": self.zscore_threshold,
            "absorb_trades": self.absorb_trades,
        }

    def settings(self):
        with self._lock:
            return self.settings_locked()

    def reset(self):
        """Reinicia el estado del engine a cero (usado en cambios Live <-> Mock)."""
        with self._lock:
            self._volumes.clear()
            self._ema = None
            self._ema_var = 0.0
            self.recent_trades.clear()
            self.cvd_history.clear()
            self.alerts.clear()
            self.absorb_bins = {}
            self.cvd = 0.0
            self.delta = 0.0
            self.buy_vol = 0.0
            self.sell_vol = 0.0
            self.total_vol = 0.0
            self.spike_count = 0
            self.last_price = None
            self._cvd_bucket = None

    def _update_zscore(self, size):
        if self._ema is None:
            self._ema = float(size)
            self._ema_var = 0.0
            return 0.0
        alpha = 2.0 / (OF_EMA_WINDOW + 1)

        prev_ema = self._ema
        self._ema = alpha * size + (1 - alpha) * prev_ema
        var = (1 - alpha) * (self._ema_var + alpha * (size - prev_ema) ** 2)
        self._ema_var = var
        std = math.sqrt(max(var, 1e-12))
        if std == 0:
            return 0.0
        return (size - self._ema) / std

    def _detect_absorption(self, now_ts):
        trades = list(self.recent_trades)
        win = self.absorb_trades
        if len(trades) < 30 or len(trades) < win:
            return None
        window = trades[-win:]
        prices = [t["price"] for t in window]
        net_delta = sum((1 if t["side"] == "A" else -1) * t["size"] for t in window)
        buy = sum(t["size"] for t in window if t["side"] == "A")
        sell = sum(t["size"] for t in window if t["side"] == "B")
        high = max(prices)
        low = min(prices)
        mid = (high + low) / 2.0
        total = buy + sell
        if mid == 0:
            return None
        range_ratio = (high - low) / mid
        delta_ratio = abs(net_delta) / max(total, 1e-9)
        if total >= OF_ABSORB_VOL_MIN and range_ratio <= OF_ABSORB_RANGE_RATIO and delta_ratio <= OF_ABSORB_DELTA_RATIO:
            direction = "compra" if net_delta >= 0 else "venta"
            level = (high + low) / 2.0
            self.absorb_bins[round(level, 5)] = now_ts
            return {
                "level": level,
                "volume": total,
                "net_delta": net_delta,
                "buy_vol": buy,
                "sell_vol": sell,
                "range": high - low,
                "direction": direction,
            }
        return None

    def add_trade(self, price, size, side, ts):
        side_str = side.value if hasattr(side, "value") else side
        if side_str not in ("A", "B"):
            return None
        delta = size if side_str == "A" else -size
        with self._lock:
            self._volumes.append(size)
            zscore = self._update_zscore(size)
            self.cvd += delta
            self.delta = delta
            self.buy_vol += size if side_str == "A" else 0
            self.sell_vol += size if side_str == "B" else 0
            self.total_vol += size
            self.last_price = price

            trade = {
                "ts": ts,
                "price": price,
                "size": size,
                "side": "A" if side_str == "A" else "B",
            }
            self.recent_trades.append(trade)

            bucket = int(ts)
            if self._cvd_bucket is not None and bucket > self._cvd_bucket:
                last = self.cvd_history[-1] if self.cvd_history else None
                if last is None or last["time"] != self._cvd_bucket:
                    self.cvd_history.append({"time": self._cvd_bucket, "value": round(self.cvd, 2)})
            self._cvd_bucket = bucket

            is_spike = zscore >= self.zscore_threshold
            if is_spike:
                self.spike_count += 1

            absorption = self._detect_absorption(ts)

            payload = {
                "event": "trade",
                "symbol": OF_SYMBOL,
                "ts": ts,
                "price": price,
                "size": size,
                "side": "A" if side_str == "A" else "B",
                "delta": delta,
                "cvd": round(self.cvd, 2),
                "zscore": round(zscore, 2),
                "is_spike": is_spike,
                "total_vol": round(self.total_vol, 2),
                "buy_vol": round(self.buy_vol, 2),
                "sell_vol": round(self.sell_vol, 2),
            }
            if is_spike:
                payload["alert"] = "Spike institucional detectado"
            if absorption is not None:
                payload["absorption"] = absorption
                payload["alert"] = f"Absorción ({absorption['direction']}) en {absorption['level']:.5f}"
                self.alerts.append({
                    "ts": datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
                    **payload["absorption"],
                    "alert": payload["alert"],
                })
            return payload

    def snapshot(self):
        with self._lock:
            return {
                "symbol": OF_SYMBOL,
                "cvd": round(self.cvd, 2),
                "delta": round(self.delta, 2),
                "total_vol": round(self.total_vol, 2),
                "buy_vol": round(self.buy_vol, 2),
                "sell_vol": round(self.sell_vol, 2),
                "last_price": self.last_price,
                "spike_count": self.spike_count,
                "alerts": list(self.alerts),
                "ema": round(self._ema, 2) if self._ema is not None else None,
                "settings": self.settings_locked(),
            }

    def cvd_series(self, since=None):
        with self._lock:
            if since is None:
                return list(self.cvd_history)
            cutoff = int(since)
            return [p for p in self.cvd_history if p["time"] >= cutoff]


engine = OrderFlowEngine()


# Simulador de mercado sintético unificado: recibe el MISMO tick que `engine` y
# agrega velas/footprint/VP/CVD/PDH-PDL para que todas las vistas del dashboard
# respondan a la misma cinta simulada cuando el modo mock está activo.
sim = simulator.MarketSimulator(normalize_ts=True)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def send(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ws)

    async def broadcast(self, message: dict):
        with self._lock:
            targets = list(self.active)
        for ws in targets:
            await self.send(ws, message)


manager = ConnectionManager()


# ============================================================
# Control de conexión Databento (encender / apagar)
# ============================================================

DB_STATE = {
    "enabled": False,
    "connected": False,
    "mode": "live",
    "fixture": None,
    "listener_task": None,
    "runner_task": None,
    "_client": None,
}
_db_lock = threading.Lock()

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def _mock_allowed() -> bool:
    """El feed sintético se habilita con ORDERFLOW_ALLOW_MOCK=1 (default on)."""
    return os.getenv("ORDERFLOW_ALLOW_MOCK", "1").lower() in ("1", "true", "yes", "on")


def databento_status():
    with _db_lock:
        enabled = DB_STATE["enabled"]
        mode = DB_STATE["mode"]
        fixture = DB_STATE["fixture"]
        source = "mock" if enabled and mode == "mock" else ("live" if enabled else None)
        return {
            "enabled": enabled,
            "connected": DB_STATE["connected"],
            "symbol": OF_SYMBOL,
            "source": source,
            "mode": mode,
            "fixture": fixture,
            "mock_available": _mock_allowed(),
        }


def _set_client(client):
    with _db_lock:
        DB_STATE["_client"] = client


def _get_client():
    with _db_lock:
        return DB_STATE["_client"]


def _clamp_rate(rate):
    """Normaliza la velocidad de replay del feed mock (1..200 ticks/s)."""
    if rate is None:
        return None
    try:
        return max(1.0, min(float(rate), 200.0))
    except (TypeError, ValueError):
        return None


def _safe_rate(rate):
    """Parsea de forma segura la velocidad de replay enviada por el cliente."""
    return _clamp_rate(rate)


def _sim_active(symbol: Optional[str] = None) -> bool:
    """True si el feed sintético (mock 6E) está activo.

    Cuando lo está, las vistas de gráfico (EURUSD) y el canal order flow (6E)
    deben servirse desde el MarketSimulator y no desde MT5. `symbol` filtra por
    instrumento unificado (6E / EURUSD).
    """
    with _db_lock:
        if not DB_STATE["enabled"] or DB_STATE["mode"] != "mock":
            return False
    if symbol:
        s = (symbol or "").upper()
        if s not in ("6E", "6E.C.0", "EURUSD"):
            return False
    return True


def _cancel_task(task: Optional[asyncio.Task]):
    if task is not None and not task.done():
        task.cancel()


def start_databento(mode: str = "live", fixture: Optional[str] = None,
                    rate: Optional[float] = None):
    """Marca el feed como habilitado y arranca/relanza la tarea correspondiente.

    - mode="mock": feed sintético (mock_feed.py) sin Databento (resetea el
      engine y el MarketSimulator para un replay determinista y limpio).
    - mode="live": listener real de Databento (como el arranque histórico).
    Cambiar de modo o de fixture cancela la tarea previa.
    """
    mode = "mock" if (mode or "").lower() == "mock" else "live"
    if mode == "mock" and not _mock_allowed():
        return databento_status()
    with _db_lock:
        same = DB_STATE["enabled"] and mode == DB_STATE["mode"] and fixture == DB_STATE["fixture"]
        if not same:
            DB_STATE["enabled"] = True
            DB_STATE["mode"] = mode
            DB_STATE["fixture"] = fixture if mode == "mock" else None
            DB_STATE["connected"] = False
        task = DB_STATE["listener_task"]
        runner = DB_STATE["runner_task"]
    alive = (task is not None and not task.done()) or (runner is not None and not runner.done())
    if same and alive:
        return databento_status()
    _cancel_task(task)
    _cancel_task(runner)
    if not same:
        engine.reset()
        sim.reset()
    if _main_loop is None or _main_loop.is_closed():
        return databento_status()
    if mode == "mock":
        new_task = _main_loop.create_task(mock_listener(fixture, rate=rate))
        with _db_lock:
            DB_STATE["runner_task"] = new_task
            DB_STATE["listener_task"] = None
    else:
        new_task = _main_loop.create_task(databento_listener())
        with _db_lock:
            DB_STATE["listener_task"] = new_task
            DB_STATE["runner_task"] = None
    return databento_status()


async def stop_databento():
    """Corta el feed (Databento o mock) y detiene su reprocesamiento."""
    with _db_lock:
        DB_STATE["enabled"] = False
        DB_STATE["connected"] = False
        client = DB_STATE["_client"]
        task = DB_STATE["listener_task"]
        runner = DB_STATE["runner_task"]
    if client is not None:
        try:
            await asyncio.get_running_loop().run_in_executor(None, client.stop)
        except Exception:
            pass
    _cancel_task(task)
    _cancel_task(runner)
    return databento_status()


def stop_databento_sync():
    """Versión síncrona de stop para usar desde threads (executor)."""
    client = _get_client()
    if client is not None:
        try:
            client.stop()
        except Exception:
            pass


async def databento_listener():
    """Conecta al feed Live de Databento (6E) con reconexión automática,
    mientras `enabled` esté activo. La conexión síncrona corre en un hilo
    secundario para no bloquear el event loop de FastAPI."""
    global _main_loop
    loop = asyncio.get_running_loop()
    while True:
        with _db_lock:
            enabled = DB_STATE["enabled"]
        if not enabled:
            break
        try:
            client = db.Live(key=DATABENTO_API_KEY)
            _set_client(client)
            await asyncio.wait_for(
                loop.run_in_executor(None, _databento_run, client),
                timeout=300,
            )
        except asyncio.CancelledError:
            stop_databento_sync()
            _set_client(None)
            raise
        except Exception as exc:
            msg = str(exc)
            if "license" in msg.lower():
                # Sin licencia live de Databento: no re-insistir con el modo live.
                # Se notifica una vez y se cae automáticamente al feed sintético
                # (mock) para que la cinta siga operativa sin tocar el interruptor.
                await manager.broadcast({
                    "event": "status",
                    "state": "error",
                    "error": f"Live sin licencia Databento, activando feed sintético (mock): {msg}",
                })
                if not _mock_allowed():
                    with _db_lock:
                        DB_STATE["enabled"] = False
                else:
                    with _db_lock:
                        DB_STATE["enabled"] = True
                        DB_STATE["mode"] = "mock"
                        DB_STATE["connected"] = False
                        DB_STATE["fixture"] = None
                    new_task = _main_loop.create_task(mock_listener(fixture=None, rate=None))
                    with _db_lock:
                        DB_STATE["runner_task"] = new_task
                        DB_STATE["listener_task"] = None
            else:
                await manager.broadcast({"event": "status", "state": "error", "error": msg})
                with _db_lock:
                    DB_STATE["enabled"] = False
        finally:
            stop_databento_sync()
            _set_client(None)
            await manager.broadcast({"event": "feed", "status": databento_status()})
        break

    with _db_lock:
        DB_STATE["_client"] = None


async def mock_listener(fixture: Optional[str] = None, rate: Optional[float] = None,
                        loop_fixture: bool = True):
    """Feed sintético (mock) de 6E: reinyecta trades en el engine y los emite
    al WS. Nativo async (sin run_coroutine_threadsafe: no hay cliente Databento).

    Fuente según mock_feed.SCENARIOS[fixture]: generador con semilla (regímenes
    noise/spike/absorption/stress) o replay del .jsonl (fixture_*). Al agotar el
    fixture lo reinicia para permitir observarlo en caliente desde la UI.
    """
    scen = mock_feed.SCENARIOS.get(fixture) if fixture else None
    if scen is None:
        fixture, scen = "noise", mock_feed.SCENARIOS["noise"]
    regime = scen.get("regime") or "noise"
    if rate is None:
        rate = 50.0 if regime == "stress" else 20.0
    batch = 5 if regime == "stress" else 1
    interval = 1.0 / max(rate, 0.1)

    with _db_lock:
        DB_STATE["enabled"] = True
        DB_STATE["connected"] = True
        DB_STATE["mode"] = "mock"
        DB_STATE["fixture"] = fixture

    loop = asyncio.get_running_loop()
    try:
        await manager.broadcast({"event": "feed", "status": databento_status()})
        while True:
            if scen["kind"] == "fixture":
                source = mock_feed.replay(scen["path"])
            else:
                source = mock_feed.gen_stream(
                    regime=scen["regime"],
                    count=300,
                    seed=7,
                    base_price=1.0985,
                    price_step=0.00005,
                )
            buf: List[dict] = []
            for t in source:
                # MISMO ts para engine y sim: buckets de CVD y ventanas de
                # absorción alineados (antes el engine usaba time.time() y el
                # sim el ts del fixture -> series CVD divergentes en replay).
                now = time.time()
                payload = engine.add_trade(
                    price=t["price"],
                    size=t["size"],
                    side=t["side"],
                    ts=now,
                )
                # Misma cinta -> MarketSimulator (velas/footprint/VP/CVD/SMC).
                sim.add_tick(
                    price=t["price"],
                    size=t["size"],
                    side=t["side"],
                    ts=now,
                )
                if payload is not None:
                    buf.append(payload)
                    if batch <= 1:
                        await manager.broadcast(payload)
                if batch > 1 and len(buf) >= batch:
                    await manager.broadcast({"event": "batch", "trades": buf, "symbol": OF_SYMBOL})
                    buf = []
                await asyncio.sleep(interval)
            if not loop_fixture:
                break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await manager.broadcast({"event": "status", "state": "error", "error": str(exc)})
    finally:
        with _db_lock:
            if DB_STATE["runner_task"] is asyncio.current_task():
                DB_STATE["connected"] = False
                DB_STATE["enabled"] = False
                DB_STATE["runner_task"] = None
        await manager.broadcast({"event": "feed", "status": databento_status()})


def _is_enabled():
    with _db_lock:
        return DB_STATE["enabled"]


def _databento_run(client):
    client.add_callback(_on_record)
    # 6E.c.0 es simbología CONTINUA (mes frontal con rollover), NO raw:
    # requiere stype_in="continuous" (el default raw_symbol la rechazaría).
    client.subscribe(
        dataset=OF_DATASET,
        schema="trades",
        symbols=[OF_SYMBOL],
        stype_in="continuous",
    )
    client.start()
    with _db_lock:
        DB_STATE["connected"] = True
    loop = _main_loop
    if loop is not None and loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"event": "feed", "status": databento_status()}),
                loop,
            )
        except RuntimeError:
            pass
    try:
        client.block_for_close()
    except Exception:
        pass
    finally:
        with _db_lock:
            DB_STATE["connected"] = False
        try:
            client.stop()
        except Exception:
            pass


def _on_record(record):
    if not isinstance(record, db.TradeMsg):
        return
    price = record.price / db.FIXED_PRICE_SCALE
    payload = engine.add_trade(
        price=price,
        size=record.size,
        side=record.side,
        ts=record.ts_event / 1_000_000_000,
    )
    if payload is not None:
        loop = _main_loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)
            except RuntimeError:
                pass


def account_dict(info):
    return {
        "login": info.login,
        "name": info.name,
        "server": info.server,
        "company": info.company,
        "currency": info.currency,
        "leverage": info.leverage,
        "balance": info.balance,
        "equity": info.equity,
        "profit": info.profit,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "margin_level": info.margin_level,
    }


def get_account():
    return run_mt5(lambda: account_dict(mt5.account_info()))


def get_price(symbol):
    def _fetch():
        mt5.symbol_select(symbol, True)
        return mt5.symbol_info(symbol)
    si = run_mt5(_fetch)
    if si is None:
        return None
    return {"symbol": si.name, "bid": si.bid, "ask": si.ask, "last": si.last}


def build_chart_snapshot(symbol: str = "EURUSD", timeframe: str = "M15",
                         synthetic: Optional[bool] = None,
                         for_execution: bool = False) -> dict:
    """Snapshot técnico de la AI Chart Assistant: precio en vivo + PDH/PDL + análisis
    SMC + exportación del indicador. Usado por el endpoint y por el tool del agente.

    `synthetic`: fuerza (True) o bloquea (False) el uso del MarketSimulator.
    Por defecto (None) se activa automáticamente cuando el feed mock 6E está
    encendido. `for_execution=True` (watcher / auto-ejecución) SIEMPRE usa datos
    reales de MT5 para no ejecutar órdenes reales sobre cinta sintética.
    """
    symbol = (symbol or "EURUSD").upper()
    tf = (timeframe or "M15").upper()

    sim_data = False
    if not for_execution:
        sim_data = _sim_active(symbol) if synthetic is None else bool(synthetic)

    if sim_data:
        data = sim.patterns(symbol, tf, bars=300)
        sp = sim.last_price()
        quote = {"symbol": symbol, "bid": sp, "ask": sp, "last": sp} if sp is not None else None
    else:
        data = patterns_service.get_pattern_data(symbol, tf)
        if data is None:
            raise RuntimeError(f"Sin datos de '{symbol}' en Market Watch.")
        quote = get_price(symbol)

    export = None
    try:
        import mt5_export as me
        ex = me.latest_export(symbol=symbol, mode="Analyze Chart")
        export = ex["content"]
        if export and len(export) > 2000:
            export = export[:2000] + "\n…(resumen — usa la herramienta mt5_export_read para el detalle completo)"
    except Exception:
        export = None

    pdl, pdh = data.get("pdl"), data.get("pdh")
    current = (quote or {}).get("bid")
    full_candles = data.get("candles") or []
    candles = full_candles[-5:]

    snap = {
        "symbol": symbol,
        "timeframe": tf,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_price": current,
        "PDH": pdh,
        "PDL": pdl,
        "last_time": full_candles[-1]["time"] if full_candles else None,
        "distance_to_PDL_pips": round((current - pdl) * 10000, 1) if current is not None and pdl is not None else None,
        "distance_to_PDH_pips": round((pdh - current) * 10000, 1) if current is not None and pdh is not None else None,
        "recent_candles": [
            {
                "time": datetime.fromtimestamp(c["time"]).strftime("%H:%M"),
                "close": c["close"],
                "high": c["high"],
                "low": c["low"],
                "volume": c.get("volume"),
            }
            for c in candles
        ],
        "analysis": data.get("analysis"),
        "indicator_export": export,
    }

    # CVD: PRIORIDAD live (Databento 6E) vs sintético (tick volume MT5). El
    # selector elige y etiqueta la fuente real para no mentir en el label: la
    # serie live solo gana si hay >= 5 puntos recientes del feed conectado.
    # En modo simulador, la serie salida del propio stream sintético (la MISMA
    # que alimenta el footprint) reemplaza cualquier fuente de MT5.
    if sim_data:
        try:
            sim_cvd = sim.cvd_series()
        except Exception:
            sim_cvd = None
        if sim_cvd:
            snap["cvd"] = sim_cvd
            snap["cvd_source"] = "simulated (6E synthetic)"
            snap["cvd_warning"] = (
                "CVD simulado: acumulado del tick stream sintético del feed mock 6E. "
                "Cambia a modo live para datos reales."
            )
    else:
        try:
            cvd_points = cvd_service.get_cvd(symbol, tf, bars=30)
        except Exception:
            cvd_points = None
        live_cvd = None
        if bool((databento_status() or {}).get("connected")):
            try:
                live_cvd = engine.cvd_series(since=time.time() - 30 * 900)
            except Exception:
                live_cvd = None
        cvd_points, cvd_source, cvd_warning = cvd_service.pick_cvd_source(
            live_cvd, cvd_points, min_live_points=5
        )
        if cvd_points is not None:
            snap["cvd"] = cvd_points
            snap["cvd_source"] = cvd_source
            if cvd_warning:
                snap["cvd_warning"] = cvd_warning
            elif cvd_source == "synthetic (tick volume MT5)":
                snap["cvd_warning"] = (
                    "CVD sintético: acumulado de tick volume de MT5, no volumen real de "
                    "mercado (feed de Databento apagado). Tómese como proxy relativo."
                )

    # COT (CFTC): solo para EURUSD (contrato 6E) y solo si hay reporte almacenado.
    cot_report = None
    if symbol == "EURUSD":
        cot_report = cot_service.build_report(store.list_cot_reports())
        if cot_report is not None:
            snap["cot_macro_analysis"] = cot_report

    # Risk Engine (M1): Setup Score determinista para ambas direcciones, régimen,
    # killzone y niveles de invalidez estructural. Solo añade contexto; el gate de
    # ejecución se decide en validate_entry.
    try:
        cfg_r = store.get_trading_config()
        weights = json.loads(cfg_r.get("risk_weights") or "{}")
        kz_windows = json.loads(cfg_r.get("killzones") or "[]")
        patterns = (data.get("analysis") or {}).get("patterns")
        candle_data = data.get("candles") or []
        cvd_data = snap.get("cvd")

        # Divergencia SMR (DXY): si el feed del dólar cae, evalúa a neutro y el
        # score no se penaliza (el bono solo suma cuando se confirma).
        try:
            smr_data = smr_service.evaluate(
                symbol, tf, candles=candle_data,
            ) if ((cfg_r.get("data_sources") or {}).get("smr_dxy", True)) else None
        except Exception:
            smr_data = None
        snap["smr"] = smr_data or {
            "symbol": symbol, "timeframe": tf, "dxy_available": False,
            "dxy": {"last_close": None, "candles": 0, "source": "no data"},
            "bull": {"confirmed": False, "detail": "SMR no disponible (neutro).", "data": None},
            "bear": {"confirmed": False, "detail": "SMR no disponible (neutro).", "data": None},
        }

        bull = risk_engine.setup_score(
            {"direction": "BUY", "cot": cot_report, "cvd": cvd_data,
             "patterns": patterns, "candles": candle_data, "smr": smr_data},
            weights=weights, killzones=kz_windows)
        bear = risk_engine.setup_score(
            {"direction": "SELL", "cot": cot_report, "cvd": cvd_data,
             "patterns": patterns, "candles": candle_data, "smr": smr_data},
            weights=weights, killzones=kz_windows)
        snap["risk_engine"] = {
            "bull": bull,
            "bear": bear,
            "killzone": bull["components"]["killzone"],
            "regime": bull["regime"],
            "invalidation": {
                "BUY": risk_engine.invalidation_level(patterns, "BUY"),
                "SELL": risk_engine.invalidation_level(patterns, "SELL"),
            },
        }
    except Exception:
        pass

    return snap


def get_last_candle(symbol, tf):
    def _get():
        rates = mt5.copy_rates_from_pos(symbol.upper(), tf, 0, 1)
        if rates is None or len(rates) == 0:
            return None
        return to_candle(rates.tolist()[0], tf)

    return run_mt5(_get)


def get_positions():
    def _get():
        pos = mt5.positions_get() or []
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "price_current": p.price_current,
                "profit": p.profit,
                "swap": p.swap,
            }
            for p in pos
        ]

    return run_mt5(_get)


def _consolidate_deals(deals):
    """Agrupa deals de MT5 por position_id en operaciones colapsadas.

    Devuelve una operación por posición con la dirección y precio reales de
    ENTRADA (deal DEAL_ENTRY_IN) y el precio/hora de CIERRE (último deal del
    histórico), sumando profit/comisión/swap de todas las patas (parciales,
    swap diario, etc.). Usa sólos atributos y literales (constantes MT5
    DEAL_ENTRY_IN=0 / DEAL_TYPE_BUY=0 / DEAL_TYPE_SELL=1) para ser testeable
    sin terminal.
    """
    _IN = 0
    by_position = {}
    for d in deals:
        pid = getattr(d, "position_id", 0)
        if pid == 0:
            continue
        rec = by_position.setdefault(pid, {
            "entry": None, "exit": None,
            "profit": 0.0, "commission": 0.0, "swap": 0.0,
        })
        rec["profit"] += getattr(d, "profit", 0.0) or 0.0
        rec["commission"] += getattr(d, "commission", 0.0) or 0.0
        rec["swap"] += getattr(d, "swap", 0.0) or 0.0
        if getattr(d, "entry", None) == _IN:
            if rec["entry"] is None or getattr(d, "time", 0) < rec["entry"].time:
                rec["entry"] = d
        else:
            if rec["exit"] is None or getattr(d, "time", 0) >= rec["exit"].time:
                rec["exit"] = d
    return by_position


def _local_deal_time(t):
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


def get_history(days=7):
    def _get():
        now = datetime.now()
        deals = mt5.history_deals_get(now - timedelta(days=days), now) or []
        result = []
        for pid, rec in _consolidate_deals(deals).items():
            entry, exit = rec["entry"], rec["exit"]
            if entry is not None:
                direction = "BUY" if entry.type == _DEAL_TYPE_BUY else "SELL"
            elif exit is not None:
                direction = "BUY" if exit.type == _DEAL_TYPE_SELL else "SELL"
            else:
                continue
            lead = entry or exit
            t_close = exit.time if exit is not None else entry.time
            price_close = exit.price if exit is not None else entry.price
            result.append(
                {
                    "ticket": lead.ticket,
                    "position_id": pid,
                    "time": _local_deal_time(t_close),
                    "time_open": _local_deal_time(entry.time) if entry is not None else None,
                    "symbol": lead.symbol,
                    "type": direction,
                    "volume": entry.volume if entry is not None else exit.volume,
                    "price_open": entry.price if entry is not None else exit.price,
                    "price_close": price_close,
                    "price": price_close,
                    "profit": rec["profit"],
                    "commission": rec["commission"],
                    "swap": rec["swap"],
                }
            )
        result.sort(key=lambda x: x["time"], reverse=True)
        return result

    return run_mt5(_get)


@app.get("/")
def index():
    return FileResponse(
        "index.html",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _watcher_news_gate():
    """Gate de noticias para el pre-chequeo del watcher con la config activa.
    Si el calendario no responde, fail-open (no bloquea)."""
    try:
        cfg = store.get_trading_config() or {}
        ds = cfg.get("data_sources") or {}
        if not ds.get("news", True):
            return {"ok": True, "fail_open": True, "reason": "news desactivado", "event": None}
        return ff.news_gate(
            min_impact=cfg.get("news_gate_impact", "red"),
            buffer_min=float(cfg.get("news_buffer_min") or 15),
        )
    except Exception as exc:
        log.exception("error en news_gate del watcher")
        return {"ok": True, "fail_open": True, "reason": str(exc), "event": None}


@app.on_event("startup")
async def startup_event():
    global _main_loop, _ALERT_TASK, _WATCHER_TASK
    _main_loop = asyncio.get_running_loop()
    # No se conecta a Databento automáticamente: el usuario lo enciende con
    # el interruptor para no incurrir en costes sin querer.
    store.init_db()
    _ALERT_TASK = asyncio.create_task(alert_watcher())
    # Bot a la escucha (watcher): snapshot desde el pipeline real, emisor de
    # broadcasts por WebSocket y, si auto_execute está activo, ejecutor de órdenes.
    _WATCHER_TASK = asyncio.create_task(watcher.strategy_watcher(
        # for_execution=True: el watcher (que puede auto-ejecutar órdenes MT5
        # reales) SIEMPRE se alimenta de datos reales, nunca de la cinta
        # sintética del simulador.
        snapshot_builder=lambda sym, tf: build_chart_snapshot(sym, tf, for_execution=True),
        executor=_watcher_execute,
        broadcast=lambda payload: asyncio.create_task(manager.broadcast(payload)),
        io={"news_gate": _watcher_news_gate},
    ))
    # Provider de patrones SMC: cuando el feed mock 6E está activo, agente y
    # bitácora analizan las velas del MarketSimulator (PDH/PDL sintético).
    patterns_service.register_provider(
        lambda sym, tf, bars: sim.patterns(sym, tf, bars) if _sim_active(sym) else None
    )
    try:
        sync_trades()
    except Exception:
        pass  # MT5 puede no estar abierto; el usuario puede sincronizar manual
    # Primer arranque con COT: descarga CFTC en segundo plano (no bloquea el boot).
    if store.latest_cot_report() is None:
        threading.Thread(target=_cot_background_sync, daemon=True).start()


def _cot_background_sync():
    try:
        cot_service.sync()
    except Exception as exc:
        print(f"[cot] sync de arranque falló: {exc}")


def sync_trades():
    """Ingesta el historial de MT5 (deals por posición) en la tabla de trades."""
    history = get_history(days=365)
    rows = [
        {
            "ticket": d["ticket"],
            "symbol": d["symbol"],
            "action": d["type"],
            "volume": d["volume"],
            "price_open": d.get("price_open"),
            "price_close": d.get("price_close") or d.get("price"),
            "profit": d["profit"],
            "time_close": d["time"],
        }
        for d in history
    ]
    if rows:
        store.clear_trades()
        store.upsert_trades(rows)
    return store.list_trades(limit=200)


@app.get("/api/orderflow")
def api_orderflow():
    snap = engine.snapshot()
    snap["feed"] = databento_status()
    return snap


@app.get("/api/orderflow/feed")
def api_orderflow_feed_status():
    return databento_status()


class FeedControl(BaseModel):
    action: str
    mode: Optional[str] = None
    fixture: Optional[str] = None
    rate: Optional[float] = None


@app.post("/api/orderflow/feed")
async def api_orderflow_feed(body: FeedControl):
    action = (body.action or "").replace("feed_", "")
    if action == "start":
        start_databento(mode=body.mode, fixture=body.fixture, rate=_clamp_rate(body.rate))
        return databento_status()
    if action == "stop":
        return await stop_databento()
    return databento_status()


@app.get("/api/orderflow/fixtures")
def api_orderflow_fixtures():
    scenarios = [
        {
            "id": name,
            "kind": s["kind"],
            "regime": s.get("regime"),
            "path": s.get("path"),
        }
        for name, s in mock_feed.SCENARIOS.items()
    ]
    return {"mode": "mock", "mock_available": _mock_allowed(), "scenarios": scenarios}


class OrderFlowSettings(BaseModel):
    zscore_threshold: Optional[float] = None
    absorb_trades: Optional[int] = None


@app.post("/api/orderflow/settings")
async def api_orderflow_settings(body: OrderFlowSettings):
    updated = engine.update_settings(
        zscore_threshold=body.zscore_threshold,
        absorb_trades=body.absorb_trades,
    )
    asyncio.create_task(manager.broadcast({
        "event": "config",
        "settings": updated,
    }))
    return {"settings": updated}


@app.get("/api/orderflow/cvd")
def api_orderflow_cvd(since: Optional[float] = None):
    return engine.cvd_series(since=since)


@app.get("/api/analysis/cvd/{symbol}")
def api_analysis_cvd(symbol: str, timeframe: str = "M15", bars: int = 300):
    """CVD sintético (tick volume de MT5) para el símbolo/timeframe activo."""
    if _sim_active(symbol):
        points = sim.cvd_series()
        if not points:
            return JSONResponse(
                {"error": "Sin datos simulados todavía (arranca el feed mock y espera unos ticks)."},
                status_code=404,
            )
        return points
    try:
        points = cvd_service.get_cvd(symbol, timeframe, bars)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if points is None:
        return JSONResponse(
            {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
            status_code=404,
        )
    return points


@app.websocket("/ws/orderflow")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.send(websocket, {
        "event": "status",
        "state": "connected",
        "symbol": OF_SYMBOL,
        "settings": engine.settings(),
        "feed": databento_status(),
        "snapshot": engine.snapshot(),
    })
    ping_task = asyncio.create_task(ping_heartbeat(websocket))
    try:
        while True:
            try:
                raw = await websocket.receive_text()
                if raw and raw.startswith("{"):
                    data = json.loads(raw)
                    action = data.get("action")
                    if action == "update_settings" or data.get("type") == "settings":
                        updated = engine.update_settings(
                            zscore_threshold=data.get("zscore_threshold"),
                            absorb_trades=data.get("absorb_trades"),
                        )
                        await manager.broadcast({
                            "event": "config",
                            "settings": updated,
                        })
                    elif action == "feed_start":
                        start_databento(mode=data.get("mode"), fixture=data.get("fixture"),
                                        rate=_safe_rate(data.get("rate")))
                        await manager.broadcast({
                            "event": "feed",
                            "status": databento_status(),
                        })
                    elif action == "feed_stop":
                        await stop_databento()
                        await manager.broadcast({
                            "event": "feed",
                            "status": databento_status(),
                        })
            except (WebSocketDisconnect, Exception):
                break
    finally:
        ping_task.cancel()
        manager.disconnect(websocket)


async def ping_heartbeat(websocket: WebSocket):
    while True:
        await asyncio.sleep(15)
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            break


# ============================================================
# Alertas de gráfico (niveles persistentes colocados por el agente)
# ============================================================

_ALERT_TASK = None
_WATCHER_TASK = None


def _check_alert_conditions(alert, price):
    """Evalúa las condiciones extra de una alerta multicondición.

    `conditions` es una lista de {type: killzone|smc|ttl, ...}. TTL solo marca
    expiración (no bloquea); killzone/smc deben cumplirse TODAS para disparar.
    Devuelve (ok, reasons, expired).
    """
    conds = alert.get("conditions") or []
    reasons = []
    expired = False

    # TTL: expiración explícita o condicion tipo ttl con minutos. Se evalúa
    # ANTES del early-return para que alertas sin condiciones extra también
    # puedan expirar por TTL.
    expires_at = alert.get("expires_at")
    for c in conds:
        if isinstance(c, dict) and c.get("type") == "ttl" and c.get("minutes"):
            try:
                delta = timedelta(minutes=int(c["minutes"]))
                exp = datetime.fromisoformat(alert.get("created_at") or "")
            except (ValueError, TypeError):
                delta = exp = None
            if delta is not None and exp is not None:
                expires_at = exp + delta
                break
    if expires_at:
        try:
            if isinstance(expires_at, str):
                expires_at_dt = datetime.fromisoformat(expires_at)
            else:
                expires_at_dt = expires_at
            if expires_at_dt <= datetime.now():
                expired = True
        except (ValueError, TypeError):
            pass

    if not conds:
        return not expired, [], expired

    counts = {"killzone": 0, "smc": 0}
    satisfied = {"killzone": 0, "smc": 0}

    # Killzone: precio dentro de la ventana UTC configurada
    for c in conds:
        if not isinstance(c, dict) or c.get("type") != "killzone":
            continue
        counts["killzone"] += 1
        wins = json.loads(store.get_trading_config().get("killzones") or "[]")
        for w in wins:
            if c.get("name") and w.get("name") != c.get("name"):
                continue
            try:
                sh, sm = [int(x) for x in w["start"].split(":")]
                eh, em = [int(x) for x in w["end"].split(":")]
            except (KeyError, ValueError, AttributeError):
                continue
            now = datetime.now(timezone.utc)
            tmin = now.hour * 60 + now.minute
            smin, emin = sh * 60 + sm, eh * 60 + em
            if (smin <= tmin < emin) if emin >= smin else (tmin >= smin or tmin < emin):
                reasons.append(f"Killzone {w.get('name', '?')}")
                satisfied["killzone"] += 1
            break
        else:
            continue

    # SMC: patrón vivo (FVG/OB) cuya caja contiene el precio, o sweep reciente
    for c in conds:
        if not isinstance(c, dict) or c.get("type") != "smc":
            continue
        counts["smc"] += 1
        pat = (c.get("pattern") or "fvg").lower()
        side = c.get("side") or ""
        tf = alert.get("timeframe") or "M15"
        try:
            data = patterns_service.get_pattern_data(alert["symbol"], tf)
        except Exception:
            continue
        if not data:
            continue
        analysis = data.get("analysis") or {}
        patterns = analysis.get("patterns") or {}
        if pat in ("fvg", "order_blocks"):
            zones = (patterns.get("fvgs") or patterns.get(pat)) if pat == "fvg" else patterns.get(pat) or []
            match_side = ("bullish" in side, "bearish" in side)
            for z in zones:
                if any(match_side):
                    is_bull = "BULLISH" in (z.get("type") or "")
                    if match_side[0] and not is_bull:
                        continue
                    if match_side[1] and is_bull:
                        continue
                if z.get("bottom") <= price <= z.get("top"):
                    reasons.append(pattern_engine._ZONE_LABELS.get(z.get("type")) or z.get("type"))
                    satisfied["smc"] += 1
                    break
        elif pat == "sweep":
            sweeps = patterns.get("sweeps") or []
            for z in sweeps:
                if c.get("side") and c.get("side").lower() not in (z.get("type") or "").lower():
                    continue
                reasons.append("PDH Sweep" if z.get("type") == pattern_engine.PDH_SWEEP else "PDL Sweep")
                satisfied["smc"] += 1
                break

    ok = (
        not expired
        and satisfied["killzone"] == counts["killzone"]
        and satisfied["smc"] == counts["smc"]
    )
    return ok, reasons, expired


async def alert_watcher():
    """Cada pocos segundos compara los niveles activos con el precio en vivo.
    Cuando TODAS las condiciones se cumplen, lo marca como 'triggered' y lo
    propaga por WebSocket. Alerts sin condiciones extra se disparan con el cruce."""
    while True:
        await asyncio.sleep(5)
        try:
            alerts = store.list_chart_alerts(active_only=True)
            if not alerts:
                continue
            prices = {}
            for a in alerts:
                sym = a["symbol"]
                if sym not in prices:
                    quote = get_price(sym)
                    prices[sym] = (quote or {}).get("bid")
                bid = prices.get(sym)
                if bid is None:
                    continue
                side = a["side"]
                if side == "above":
                    hit = bid >= a["price"]
                elif side == "below":
                    hit = bid <= a["price"]
                else:
                    hit = abs(bid - a["price"]) <= max(a["price"] * 1e-4, 1e-5)
                if not hit:
                    continue
                ok, reasons, expired = _check_alert_conditions(a, bid)
                if expired:
                    store.set_chart_alert_status(a["id"], "cancelled")
                    asyncio.create_task(manager.broadcast({
                        "event": "chart_alert",
                        "type": "expired",
                        "alert": store.get_chart_alert(a["id"]),
                    }))
                    continue
                if ok:
                    store.set_chart_alert_status(a["id"], "triggered")
                    asyncio.create_task(manager.broadcast({
                        "event": "chart_alert",
                        "type": "triggered",
                        "conditions_met": reasons,
                        "alert": store.get_chart_alert(a["id"]),
                    }))
        except Exception:
            pass


@app.get("/api/chart/alerts", response_model=None)
def api_chart_alerts_list():
    return store.list_chart_alerts(active_only=False)


@app.delete("/api/chart/alerts/{aid}")
def api_chart_alert_delete(aid: int):
    alert = store.get_chart_alert(aid)
    if alert is None:
        return JSONResponse({"error": "Alerta no encontrada"}, status_code=404)
    store.set_chart_alert_status(aid, "cancelled")
    return {"deleted": aid}


@app.get("/api/cot/report")
def api_cot_report():
    """Último reporte COT (CFTC) del EURUSD si hay uno almacenado."""
    rep = cot_service.build_report(store.list_cot_reports())
    if rep is None:
        return JSONResponse({"error": "Sin datos COT almacenados."}, status_code=404)
    return rep


@app.post("/api/cot/refresh")
def api_cot_refresh():
    """Descarga el COT CFTC en vivo (TFF + Legacy, sin API key) y lo persiste."""
    rep = cot_service.sync()
    if rep is None:
        return JSONResponse(
            {"error": "No se pudo descargar el reporte COT de la CFTC (¿red?)."},
            status_code=502,
        )
    return rep


@app.get("/api/risk/setup")
def api_risk_setup(symbol: str = "EURUSD", timeframe: str = "M15"):
    """Setup Score determinista (bull/bear) + régimen + killzone + invalidez."""
    try:
        snapshot = build_chart_snapshot(symbol, timeframe)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if "risk_engine" not in snapshot:
        return JSONResponse({"error": "Risk engine no disponible para este snapshot."}, status_code=422)
    return {
        **snapshot["risk_engine"],
        "symbol": snapshot["symbol"],
        "timeframe": snapshot["timeframe"],
        "current_price": snapshot.get("current_price"),
        "time": snapshot["time"],
    }


def _nearest_entry_zone(patterns, price, direction, max_span=0.01):
    """Elige la zona (FVG/OB) más cercana donde entrar.

    - BUY  -> la zona que queda POR DEBAJO del precio (rebote alcista).
    - SELL -> la zona que queda POR ENCIMA (rechazo bajista).

    Devuelve {"price": float, "kind": str, "top": float, "bottom": float} o None.
    El 'entry' se toma del borde que mira al precio (BUY: bottom, SELL: top)."""
    if not patterns:
        return None
    zones = []
    for z in (patterns.get("fvgs") or []):
        z = dict(z)
        z["kind"] = z.get("type") or "FVG"
        zones.append(z)
    for z in (patterns.get("order_blocks") or []):
        z = dict(z)
        z["kind"] = z.get("type") or "OB"
        zones.append(z)
    if not zones:
        return None

    if direction == "BUY":
        cands = [z for z in zones if z["bottom"] < price]
        if not cands:
            return None
        z = max(cands, key=lambda z: z["bottom"])
        return {"price": z["bottom"], "kind": z["kind"], "top": z["top"], "bottom": z["bottom"]}
    cands = [z for z in zones if z["top"] > price]
    if not cands:
        return None
    z = min(cands, key=lambda z: z["top"])
    return {"price": z["top"], "kind": z["kind"], "top": z["top"], "bottom": z["bottom"]}


@app.get("/api/chart/setup-eval", response_model=None)
def api_chart_setup_eval(symbol: str = "EURUSD", timeframe: str = "M15", min_score: Optional[float] = None):
    """Evaluación determinista de setup (sin LLM): calcula Entry/SL/TP desde el Risk
    Engine y los patrones SMC, valida el R:R y devuelve overlays ECharts listos para
    dibujar la bandera de entrada + SL + TP. No ejecuta ninguna orden.

    El umbral sale de strategy.yaml (score.min_score); el query param opcional
    min_score solo sirve para sobreescribirlo puntualmente. Sin hardcode."""
    if min_score is None:
        try:
            min_score = float(store.get_trading_config().get("min_score") or 80.0)
        except (TypeError, ValueError):
            min_score = 80.0
    try:
        snapshot = build_chart_snapshot(symbol, timeframe)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    re_ = snapshot.get("risk_engine")
    if not re_:
        return JSONResponse({"error": "Risk engine no disponible para este snapshot."}, status_code=422)

    current = snapshot.get("current_price")
    patterns = ((snapshot.get("analysis") or {}).get("patterns")) or {}
    cfg = store.get_trading_config()
    sl_pips = float(cfg.get("sl_default_pips") or 15.0)
    tp_r = float(cfg.get("tp_ratio_r") or 2.0)

    # pip -> precio: usa digest de MT5 si está disponible, si no asume 5 dígitos.
    pip_price = 0.0001
    try:
        specs = get_specs(symbol)
        if specs:
            pip_price = float(specs.get("pip_price") or 0.0001)
    except Exception:
        pip_price = 0.0001

    bull, bear = re_.get("bull"), re_.get("bear")
    sides = []
    if bull:
        sides.append(("BUY", bull))
    if bear:
        sides.append(("SELL", bear))
    if not sides:
        return JSONResponse({"error": "Sin scores de risk engine."}, status_code=422)
    direction, best = max(sides, key=lambda s: s[1].get("score") or 0)
    score = best.get("score") or 0
    verdict = best.get("verdict") or ""

    # Nivel de invalidez estructural para el gate.
    invalidation = (re_.get("invalidation") or {}).get(direction)

    # Entrada desde la zona SMC más cercana; si no hay, el precio actual.
    zone = _nearest_entry_zone(patterns, current, direction) if current is not None else None
    entry = zone["price"] if zone else current
    entry_kind = zone["kind"] if zone else "market"

    # SL / TP numéricos.
    sl_dist = sl_pips * pip_price
    if direction == "BUY":
        sl = (entry - sl_dist) if entry is not None else None
        tp = (entry + sl_dist * tp_r) if (entry is not None and sl is not None) else None
    else:
        sl = (entry + sl_dist) if entry is not None else None
        tp = (entry - sl_dist * tp_r) if (entry is not None and sl is not None) else None

    reasons = []
    val = None
    try:
        val = risk_engine.validate_entry(
            entry=entry, sl=sl, target=tp, direction=direction,
            current_price=current, invalidate_level=invalidation, cfg=cfg,
        )
    except Exception as exc:
        val = {"approved": False, "rejected": True, "reasons": [f"risk_engine error: {exc}"]}

    approved = bool(score >= min_score and val and val.get("approved"))
    if not approved:
        if score < min_score:
            reasons.append(f"Score {score:.1f} < umbral {min_score:.0f}.")
        if val and val.get("reasons"):
            reasons.extend(val["reasons"])

    # Overlays ECharts (solo si hay setup aprobado).
    echarts = {"markLine": [], "markPoint": []}
    view = None
    last_time = snapshot.get("last_time")

    if approved and entry is not None and sl is not None and tp is not None:
        up = direction == "BUY"
        entry_color = "#2ee6a8" if up else "#ff5d6c"
        echarts["markPoint"].append({
            "coord": [last_time, entry],
            "value": f"{direction} {entry:.5f}",
            "symbol": "pin",
            "symbolSize": 26,
            "symbolOffset": [0, -8] if up else [0, 8],
            "itemStyle": {"color": entry_color, "borderColor": "#fff"},
            "label": {"show": True, "color": "#fff", "fontSize": 10, "fontWeight": 700, "formatter": f"{direction}"},
        })
        echarts["markLine"].append({
            "yAxis": entry,
            "label": {"show": True, "formatter": "Entry", "color": entry_color, "fontSize": 10, "position": "insideEndTop"},
            "lineStyle": {"color": entry_color, "width": 1.5, "type": "dashed", "opacity": 0.8},
        })
        echarts["markLine"].append({
            "yAxis": sl,
            "label": {"show": True, "formatter": "SL", "color": "#ff5d6c", "fontSize": 10, "position": "insideEndTop"},
            "lineStyle": {"color": "rgba(255,93,108,0.9)", "width": 1.5, "type": "dashed"},
        })
        echarts["markLine"].append({
            "yAxis": tp,
            "label": {"show": True, "formatter": "TP", "color": "#2ee6a8", "fontSize": 10, "position": "insideEndTop"},
            "lineStyle": {"color": "rgba(46,230,168,0.9)", "width": 1.5, "type": "dashed"},
        })
        lo = min(sl, tp, entry)
        hi = max(sl, tp, entry)
        view = {"start_time": (last_time - 3600) if last_time else None,
                "end_time": last_time, "price_min": lo, "price_max": hi}

    # News Blackout: información de la ventana de noticia para la UI (hard gate
    # real está en execute_market_trade y en el watcher). Fail-open si el
    # calendario no se puede leer.
    news_gate_res = {"ok": True, "fail_open": True, "reason": "no evaluado", "event": None}
    try:
        news_cfg = (store.get_trading_config().get("data_sources") or {}).get("news", True)
        if news_cfg:
            news_gate_res = ff.news_gate(
                min_impact=store.get_trading_config().get("news_gate_impact", "red"),
                buffer_min=float(store.get_trading_config().get("news_buffer_min") or 15),
            )
    except Exception as exc:
        news_gate_res = {"ok": True, "fail_open": True, "reason": str(exc), "event": None}
    news_blackout = bool(news_gate_res and not news_gate_res.get("ok"))

    return {
        "symbol": snapshot["symbol"],
        "timeframe": snapshot["timeframe"],
        "direction": direction,
        "score": score,
        "verdict": verdict,
        "current_price": current,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "entry_kind": entry_kind,
        "approved": approved,
        "news_blackout": news_blackout,
        "news_gate": news_gate_res.get("event"),
        "news_reason": news_gate_res.get("reason"),
        "reasons": reasons,
        "echarts": echarts,
        "view": view,
    }


class DrawingsBody(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    drawings: list = []


@app.get("/api/chart/drawings", response_model=None)
def api_chart_drawings_get(symbol: str = "EURUSD", timeframe: str = "M15"):
    """Dibujos manuales persistidos del gráfico para un symbol/timeframe."""
    return {
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe).upper(),
        "drawings": store.get_drawings(symbol, timeframe),
    }


@app.put("/api/chart/drawings", response_model=None)
def api_chart_drawings_put(body: DrawingsBody):
    """Reemplaza el set de dibujos del symbol/timeframe."""
    saved = store.save_drawings(body.symbol, body.timeframe, body.drawings or [])
    return {"status": "ok", "symbol": str(body.symbol).upper(), "timeframe": str(body.timeframe).upper(), "drawings": saved}


@app.delete("/api/chart/drawings", response_model=None)
def api_chart_drawings_delete(symbol: str = "EURUSD", timeframe: str = "M15"):
    """Borra los dibujos del symbol/timeframe."""
    store.delete_drawings(symbol, timeframe)
    return {"status": "ok", "symbol": str(symbol).upper(), "timeframe": str(timeframe).upper()}


@app.get("/api/risk/audit")
def api_risk_audit(symbol: str = "", verdict: str = "", limit: int = 100):
    """Post-mortem del risk engine (setup_log, append-only) + win-rate real por
    componente (solo setups con ticket vinculado y trade cerrado)."""
    entries = store.list_setup_log(limit=limit, verdict=verdict, symbol=symbol)

    # Resolver profit por ticket desde trades (cerradas + posiciones vivas).
    profit_by_ticket = {}
    for t in store.list_trades(limit=5000):
        profit_by_ticket[str(t.get("ticket"))] = t.get("profit")
    positions = {}
    try:
        for p in get_positions():
            positions[str(p.get("ticket"))] = p.get("profit")
    except Exception:
        positions = {}

    closed = []
    verified = []
    for e in entries:
        tk = e.get("trade_result", {}).get("ticket")
        if tk is None:
            continue
        profit = profit_by_ticket.get(str(tk), positions.get(str(tk)))
        if profit is None:
            continue
        broke = e.get("breakdown") or {}
        closed.append({
            "id": e["id"], "symbol": e["symbol"], "direction": e["direction"],
            "verdict": e["verdict"], "score": e["score"],
            "validated": e["validated"], "reject_reasons": e["reject_reasons"],
            "profit": profit, "win": profit > 0,
            "timestamp": e["timestamp"],
        })
        if e["validated"]:
            broke = e.get("breakdown") or {}
            verified.append({
                "breakdown": broke, "score": e["score"], "direction": e["direction"],
                "win": profit > 0, "profit": profit,
            })

    comp_keys = ["cot", "cvd_of", "smc", "killzone"]
    comp_stats = {k: {"avg": 0.0, "wins": 0, "total": 0, "win_rate": None} for k in comp_keys}
    for v in verified:
        for k in comp_keys:
            comp = (v["breakdown"] or {}).get(k) or {}
            value = comp.get("value")
            if value is None:
                continue
            comp_stats[k]["avg"] += float(value)
            comp_stats[k]["total"] += 1
            if v["win"]:
                comp_stats[k]["wins"] += 1
    for k in comp_keys:
        s = comp_stats[k]
        if s["total"]:
            s["avg"] = round(s["avg"] / s["total"], 2)
            s["win_rate"] = round(s["wins"] / s["total"] * 100.0, 1)

    total_wins = sum(1 for c in closed if c["win"])
    total_loss = sum(1 for c in closed if not c["win"])
    return {
        "count": len(entries),
        "entries": entries,
        "metrics": {
            "closed_linked": len(closed),
            "wins": total_wins,
            "losses": total_loss,
            "win_rate": round(total_wins / len(closed) * 100.0, 1) if closed else None,
        },
        "component_win_rate": comp_stats,
    }


@app.get("/api/account")
def api_account():
    return get_account()


@app.get("/api/positions")
def api_positions():
    return get_positions()


@app.get("/api/history")
def api_history(days: int = 7):
    return get_history(max(1, min(days, 365)))


@app.get("/api/price/{symbol}")
def api_price(symbol: str):
    if _sim_active(symbol):
        sp = sim.last_price()
        if sp is None:
            return JSONResponse(
                {"error": "Simulador sin precio (arranca el feed mock 6E)."},
                status_code=404,
            )
        return {"symbol": symbol.upper(), "bid": sp, "ask": sp, "last": sp}
    data = get_price(symbol.upper())
    if data is None:
        return JSONResponse(
            {"error": f"Símbolo '{symbol}' no disponible en Market Watch."},
            status_code=404,
        )
    return data


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

def to_candle(r, tf):
    return {
        "time": int(r[0]),
        "open": r[1],
        "high": r[2],
        "low": r[3],
        "close": r[4],
        "volume": r[5],
    }


@app.get("/api/candles/{symbol}")
def api_candles(symbol: str, timeframe: str = "M15", bars: int = 300):
    if _sim_active(symbol):
        candles = sim.candles(timeframe, bars)
        if not candles:
            return JSONResponse(
                {"error": "Sin velas de simulador (arranca el feed mock 6E)."},
                status_code=404,
            )
        return candles
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        return JSONResponse(
            {"error": f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."},
            status_code=400,
        )

    def _get():
        rates = mt5.copy_rates_from_pos(symbol.upper(), tf, 0, max(10, min(bars, 1000)))
        if rates is None or len(rates) == 0:
            return None
        return [to_candle(r, tf) for r in rates.tolist()]

    data = run_mt5(_get)
    if data is None:
        return JSONResponse(
            {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
            status_code=404,
        )
    return data


@app.get("/api/candle/last/{symbol}")
def api_candle_last(symbol: str, timeframe: str = "M15"):
    if _sim_active(symbol):
        candles = sim.candles(timeframe, 2)
        if not candles:
            return JSONResponse(
                {"error": "Sin velas de simulador (arranca el feed mock 6E)."},
                status_code=404,
            )
        return candles[-1]
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        return JSONResponse(
            {"error": f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."},
            status_code=400,
        )

    def _get():
        rates = mt5.copy_rates_from_pos(symbol.upper(), tf, 0, 1)
        if rates is None or len(rates) == 0:
            return None
        return to_candle(rates.tolist()[0], tf)

    data = run_mt5(_get)
    if data is None:
        return JSONResponse(
            {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
            status_code=404,
        )
    return data


@app.get("/api/analysis/patterns/{symbol}", response_model=None)
def api_analysis_patterns(symbol: str, timeframe: str = "M15", bars: int = 300):
    """Zonas SMC activas (FVG / Order Blocks / Liquidity Sweeps) para el frontend.

    En modo sim (feed mock 6E encendido) se analizan las velas del
    MarketSimulator contra el PDH/PDL sintético de la sesión simulada."""
    if _sim_active(symbol):
        data = sim.patterns(symbol, timeframe, bars)
        return {**data["analysis"], "pdh": data["pdh"], "pdl": data["pdl"]}
    try:
        data = patterns_service.get_pattern_data(symbol, timeframe, bars)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if data is None:
        return JSONResponse(
            {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
            status_code=404,
        )
    return {**data["analysis"], "pdh": data["pdh"], "pdl": data["pdl"]}


@app.get("/api/analysis/chartism/{symbol}", response_model=None)
def api_analysis_chartism(symbol: str, timeframe: str = "M15", bars: int = 300,
                          patterns: str = "all"):
    """Patrones chartistas clásicos (canales, triángulos, banderas, dobles, H&S).

    La lista `patterns` acepta una lista separada por comas: trend,triangle,flag,
    double,hns (o 'all'). Devuelve figuras en el mismo formato `drawing` que
    consume `tools.js` (line/hline/text), listas para el frontend.
    """
    try:
        data = patterns_service.get_pattern_data(symbol, timeframe, bars)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if data is None:
        return JSONResponse(
            {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
            status_code=404,
        )

    req = [p.strip().lower() for p in str(patterns).split(",") if p.strip()]
    invalid = [p for p in req if p not in chartism_engine.GROUPS and p != "all"]
    if invalid:
        return JSONResponse(
            {"error": f"Patrón(es) no válido(s): {', '.join(invalid)}. "
                      f"Usa: {', '.join(chartism_engine.GROUPS)} o 'all'."},
            status_code=400,
        )
    if req and req[-1] == "all":
        req = list(chartism_engine.GROUPS)

    return {
        "symbol": symbol.upper(),
        **chartism_engine.detect_all(data["candles"], req, timeframe.upper()),
    }


@app.get("/api/analysis/smr/{symbol}", response_model=None)
def api_analysis_smr(symbol: str, timeframe: str = "M15"):
    """Divergencia SMR (DXY) para el símbolo/timeframe: reglas alcista y bajista.

    Fuente del DXY: Yahoo Finance (DX-Y.NYB), gratis. Sin feed, degrada a neutro
    (confirmed=False) sin romper el dashboard."""
    try:
        result = smr_service.evaluate(symbol, timeframe)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return result


@app.get("/api/volume-profile/{symbol}", response_model=None)
def api_volume_profile(symbol: str, timeframe: str = "H1", bins: int = 48,
                       poc_pct: float = 70.0):
    """Volume Profile de sesión: ticks de MT5 con fallback a barras OHLCV.

    Devuelve {bins, profile: [{price, vol}], poc, vah, val, source}.
    - price: nivel central del bin
    - vol: volumen total del bin
    - poc: precio con mayor volumen (Point of Control)
    - vah/val: borde superior/inferior del valor (VAH/VAL) del `poc_pct`% del vol
    - source: 'ticks' o 'bars' (cómo se obtuvieron los datos)
    """
    symbol = symbol.upper()
    tf_map = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}
    tf = timeframe.upper()
    try:
        if _sim_active(symbol):
            res = sim.vp(bins=max(8, min(bins, 200)), poc_pct=poc_pct)
            if res is None:
                return JSONResponse(
                    {"error": "Sin datos de simulador (arranca el feed mock)."}, status_code=404,
                )
            return res
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        session_start = now - timedelta(minutes=tf_map.get(tf, 60) * 12)  # 12 sesiones hacia atrás como rango
        start_ts = session_start.timestamp()
        end_ts = now.timestamp()

        # Intentar ticks (copy_ticks_range); si el rango de sesión queda vacío
        # (p.ej. fin de semana) amplía a los últimos 3 días calendario.
        ticks = None
        try:
            ticks = run_mt5(lambda: mt5.copy_ticks_range(
                symbol, int(start_ts), int(end_ts), mt5.COPY_TICKS_ALL))
            if ticks is None or len(ticks) == 0:
                ticks = run_mt5(lambda: mt5.copy_ticks_range(
                    symbol, int(end_ts - 3 * 86400), int(end_ts), mt5.COPY_TICKS_ALL))
        except Exception:
            ticks = None

        if ticks is not None and len(ticks) > 100:
            ask_col = [n for n in (ticks.dtype.names or []) if n in ("ask", "bid", "last", "price")]
            if not ask_col:
                return JSONResponse({"error": "Estructura de ticks inesperada."}, status_code=500)
            col = ask_col[0]
            prices = ticks[col].astype(float)
            vol_col = "volume" if "volume" in (ticks.dtype.names or []) else None
            if vol_col is not None:
                volumes = ticks[vol_col].astype(float)
                if volumes.sum() == 0:
                    volumes = np.ones_like(prices)
            else:
                volumes = np.ones_like(prices)
            # Lado agresor aproximado: last >= bid -> compra (ask), last <= ask -> venta.
            names = ticks.dtype.names or []
            side = None
            if col == "last" and "bid" in names and "ask" in names:
                bid = ticks["bid"].astype(float)
                ask = ticks["ask"].astype(float)
                side = np.where(ticks[col] >= bid, 1.0,
                                np.where(ticks[col] <= ask, -1.0, 0.0))
            source = "ticks"
        else:
            # Fallback: copy_rates_from_pos (OHLCV)
            rates = run_mt5(lambda: mt5.copy_rates_from_pos(
                symbol, TIMEFRAMES.get(tf, mt5.TIMEFRAME_H1), 0, 200))
            if rates is None or len(rates) < 5:
                return JSONResponse(
                    {"error": f"No hay datos para '{symbol}' en Market Watch."},
                    status_code=404,
                )
            prices = []
            volumes = []
            side = []
            for r in rates:
                avg = (r["open"] + r["high"] + r["low"] + r["close"]) / 4.0
                vol = float(r["tick_volume"])
                prices.append(avg)
                volumes.append(vol)
                side.append(1.0 if r["close"] >= r["open"] else -1.0)
            prices = np.array(prices)
            volumes = np.array(volumes)
            side = np.array(side)
            source = "bars"

        lo = float(prices.min())
        hi = float(prices.max())
        if hi <= lo:
            return JSONResponse({"error": "Rango de precios insuficiente."}, status_code=400)
        edges = np.linspace(lo, hi, bins + 1)
        bin_vol = np.zeros(bins)
        bin_bid = np.zeros(bins)
        bin_ask = np.zeros(bins)
        for i, p in enumerate(prices):
            idx = min(int((p - lo) / (hi - lo) * bins), bins - 1)
            v = float(volumes[i]) if i < len(volumes) else 1.0
            bin_vol[idx] += v
            if side is not None:
                s = float(side[i])
                if s > 0:
                    bin_ask[idx] += v
                elif s < 0:
                    bin_bid[idx] += v
                else:
                    bin_ask[idx] += v * 0.5
                    bin_bid[idx] += v * 0.5
            else:
                bin_ask[idx] += v * 0.5
                bin_bid[idx] += v * 0.5
        bin_centers = ((edges[:-1] + edges[1:]) / 2.0).tolist()
        profile = [{"price": round(float(c), 6), "vol": round(float(v), 2),
                    "delta": round(float(a - b), 2)}
                   for c, v, a, b in zip(bin_centers, bin_vol, bin_ask, bin_bid)]

        # POC, VAH, VAL
        poc_idx = int(np.argmax(bin_vol))
        poc = bin_centers[poc_idx]
        total_vol = float(bin_vol.sum())
        if total_vol > 0:
            threshold = total_vol * (poc_pct / 100.0)
            sorted_bins = sorted(range(bins), key=lambda i: bin_vol[i], reverse=True)
            cum = 0.0
            in_val = []
            for bi in sorted_bins:
                cum += bin_vol[bi]
                in_val.append(bi)
                if cum >= threshold:
                    break
            vah = max(bin_centers[i] for i in in_val)
            val = min(bin_centers[i] for i in in_val)
        else:
            vah = hi
            val = lo

        return {
            "bins": bins,
            "profile": profile,
            "poc": round(poc, 6),
            "vah": round(vah, 6),
            "val": round(val, 6),
            "source": source,
        }

    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _market_view_candles(symbol: str, timeframe: str, bars: int):
    """Velas OHLCV via MT5 reutilizando to_candle (misma referencia que el grafico)."""
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        raise ValueError(
            f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."
        )

    def _get():
        rates = mt5.copy_rates_from_pos(symbol.upper(), tf, 0, max(10, min(bars, 1000)))
        if rates is None or len(rates) == 0:
            return None
        return [to_candle(r, tf) for r in rates.tolist()]

    return run_mt5(_get)


_TEST_FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "tests", "fixtures")


def _load_test_fixture(filename: str):
    """Carga un JSON de tests/fixtures/ (datos de control para auditoria visual)."""
    path = os.path.join(_TEST_FIXTURES_DIR, filename)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/analysis/footprint/{symbol}", response_model=None)
def api_footprint(symbol: str, timeframe: str = "M15", bars: int = 150,
                  bid_ratio: float = 0.6, rows: int = 12, mode: str = "live"):
    """Footprint / cluster chart por barra (modelo sintetico mientras no haya feed real).

    `mode=test` sirve el fixture de test (`tests/fixtures/footprint_extremes.json`)
    SIN tocar MT5 ni Market Watch: es la via de auditoria visual 1:1 que usa el
    mismo contrato de datos que la UI, para validar pared/gradiente/ruido."""
    try:
        if mode.lower() in ("test", "mock"):
            return _load_test_fixture("footprint_extremes.json") or JSONResponse(
                {"error": "Falta tests/fixtures/footprint_extremes.json."}, status_code=404,
            )
        if _sim_active(symbol):
            res = sim.footprint(
                max_bars=max(10, min(bars, 1000)), rows=max(6, min(rows, 24)),
            )
            if res is None:
                return JSONResponse(
                    {"error": "Sin datos de simulador (arranca el feed mock)."}, status_code=404,
                )
            return res
        candles = _market_view_candles(symbol, timeframe, bars)
        if not candles:
            return JSONResponse(
                {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
                status_code=404,
            )
        return market_view.footprint(
            candles, max_bars=max(10, min(bars, 1000)),
            bid_ratio=bid_ratio, rows=max(6, min(rows, 24)),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/analysis/heatmap/{symbol}", response_model=None)
def api_liquidity_heatmap(symbol: str, timeframe: str = "M15", bars: int = 150,
                          levels: int = 64, mode: str = "live"):
    """Mapa de calor de liquidez (pseudo-DOM) detras del precio (sintetico).

    `mode=test` sirve el fixture de test (`tests/fixtures/heatmap_extremes.json`)
    SIN tocar MT5 ni Market Watch: es la via de auditoria visual 1:1 que usa el
    mismo contrato de datos que la UI."""
    try:
        if mode.lower() in ("test", "mock"):
            return _load_test_fixture("heatmap_extremes.json") or JSONResponse(
                {"error": "Falta tests/fixtures/heatmap_extremes.json."}, status_code=404,
            )
        if _sim_active(symbol):
            res = sim.heatmap(
                max_bars=max(10, min(bars, 1000)), levels=max(32, min(levels, 128)),
            )
            if res is None or not res.get("data"):
                return JSONResponse(
                    {"error": "Sin datos de simulador (arranca el feed mock)."}, status_code=404,
                )
            return res
        candles = _market_view_candles(symbol, timeframe, bars)
        if not candles:
            return JSONResponse(
                {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
                status_code=404,
            )
        return market_view.liquidity_heatmap(
            candles, max_bars=max(10, min(bars, 1000)),
            levels=max(32, min(levels, 128)),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/analysis/eventbars/{symbol}", response_model=None)
def api_eventbars(symbol: str, timeframe: str = "M15", bars: int = 200,
                  mode: str = "volbar", param: int = 500, ticks: int = 160):
    """Barras por evento (volbar / tickbar / renko) desde OHLCV sintetico.

    `ticks` = ticks sinteticos generados por vela base: con bars=1000 y
    tickbar/param=500, 160 ticks/vela producen ~320 barras para que el
    gráfico no quede estirado con pocas velas."""
    try:
        if _sim_active(symbol):
            res = sim.event_bars(bar_type=mode, param=int(param))
            if res is None:
                return JSONResponse(
                    {"error": "Sin datos de simulador (arranca el feed mock)."}, status_code=404,
                )
            return res
        candles = _market_view_candles(symbol, timeframe, bars)
        if not candles:
            return JSONResponse(
                {"error": f"No hay datos de '{symbol.upper()}' en Market Watch."},
                status_code=404,
            )
        return market_view.event_bars(
            candles, bar_type=mode, param=int(param),
            ticks_per_candle=max(8, min(ticks, 960)),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/analysis/chart-assistant/{symbol}", response_model=None)
def api_analysis_chart_assistant(symbol: str, timeframe: str = "M15"):
    """Snapshot de la AI Chart Assistant (precio + SMC + exportación) para el botón del dashboard."""
    try:
        snapshot = build_chart_snapshot(symbol, timeframe)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return snapshot


async def stream_generator(symbol, tf):
    while True:
        try:
            if _sim_active(symbol):
                candles = sim.candles("M15", 2)
                candle = candles[-1] if candles else None
                sp = sim.last_price()
                quote = {"symbol": symbol.upper(), "bid": sp, "ask": sp, "last": sp} if sp is not None else None
            else:
                candle = get_last_candle(symbol, tf)
                quote = get_price(symbol)
            message = {
                "type": "candle",
                "symbol": symbol.upper(),
                "candle": candle,
                "quote": quote,
            }
        except RuntimeError as exc:
            message = {"type": "error", "message": str(exc)}
        yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
        await asyncio.sleep(1.0)


@app.get("/api/stream/{symbol}")
def api_stream(symbol: str, timeframe: str = "M15"):
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        return JSONResponse(
            {"error": f"Timeframe '{timeframe}' no válido. Usa M1..M30, H1, H4, D1 o W1."},
            status_code=400,
        )
    return StreamingResponse(
        stream_generator(symbol.upper(), tf),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD",
    "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "XAUUSD",
    "XAGUSD", "BTCUSD", "ETHUSD", "US30", "NAS100",
]

SYMBOL_ALIASES = {
    "oro": "XAUUSD", "gold": "XAUUSD",
    "plata": "XAGUSD", "silver": "XAGUSD",
    "bitcoin": "BTCUSD", "btc": "BTCUSD",
    "ethereum": "ETHUSD", "eth": "ETHUSD",
    "euro": "EURUSD", "dolar": None, "dólar": None,
}


def detect_symbol(message):
    lower = message.lower()
    for symbol in SYMBOLS:
        if symbol.lower() in lower:
            return symbol
    for alias, symbol in SYMBOL_ALIASES.items():
        if re.search(rf"\b{alias}\b", lower):
            return symbol
    return None


def fmt_money(value):
    if value is None:
        return "0.00"
    return f"{value:,.2f}"


def money(value, currency="$"):
    return f"{currency} {fmt_money(value)}"


def price_intent(message, acc):
    a = acc
    return (
        f"Balance: {money(a['balance'], a['currency'])}\n"
        f"Equity: {money(a['equity'], a['currency'])}\n"
        f"Ganancia/pérdida flotante: {money(a['profit'], a['currency'])}"
    )


def margin_intent(acc):
    a = acc
    level = f"{a['margin_level']:,.0f} %" if a["margin_level"] and a["margin_level"] > 0 else "sin posiciones abiertas"
    return (
        f"Margen usado: {money(a['margin'], a['currency'])}\n"
        f"Margen libre: {money(a['margin_free'], a['currency'])}\n"
        f"Nivel de margen: {level}"
    )


def profit_intent(acc):
    a = acc
    history = get_history(30)
    net = sum(d["profit"] for d in history)
    total_trades = len(history)
    wins = sum(1 for d in history if d["profit"] > 0)
    losses = sum(1 for d in history if d["profit"] < 0)
    return (
        f"Ganancia/pérdida flotante: {money(a['profit'], a['currency'])}\n"
        f"Resultado neto de los últimos 30 días: {money(net, a['currency'])}\n"
        f"Operaciones cerradas: {total_trades} (ganadoras {wins}, perdedoras {losses})"
    )


def positions_intent():
    positions = get_positions()
    if not positions:
        return "No tienes posiciones abiertas."
    lines = [f"Tienes {len(positions)} posición(es) abierta(s):"]
    for p in positions:
        lines.append(
            f"- {p['symbol']} {p['type']} x{p['volume']} "
            f"abierta en {p['price_open']:.5f}, actual {p['price_current']:.5f} "
            f"(ganancia {money(p['profit'])})."
        )
    lines.append(f"Total flotante: {money(sum(p['profit'] for p in positions))}")
    return "\n".join(lines)


def history_intent(days=7):
    history = get_history(days)
    if not history:
        return f"No hay operaciones cerradas en los últimos {days} días."
    total = sum(d["profit"] for d in history)
    lines = [f"Resumen de los últimos {days} días ({len(history)} operaciones):"]
    for d in history[:10]:
        lines.append(
            f"- {d['time']} {d['symbol']} {d['type']} x{d['volume']} "
            f"a {d['price']:.5f} -> {money(d['profit'])}"
        )
    if len(history) > 10:
        lines.append(f"... y {len(history) - 10} más.")
    lines.append(f"Resultado neto del período: {money(total)}")
    return "\n".join(lines)


def summary_intent(acc):
    a = acc
    positions = get_positions()
    return (
        f"Cuenta {a['login']} · {a['name']} · {a['server']} · {a['currency']}\n"
        f"Balance: {money(a['balance'], a['currency'])}\n"
        f"Equity: {money(a['equity'], a['currency'])}\n"
        f"Ganancia/pérdida flotante: {money(a['profit'], a['currency'])}\n"
        f"Margen libre: {money(a['margin_free'], a['currency'])}"
        f" ({a['margin_level']:,.0f} %)\n"
        f"Posiciones abiertas: {len(positions)}\n\n"
        "Puedes preguntarme por el balance, el margen, las posiciones, "
        "el historial de operaciones o el precio de un símbolo (EURUSD, oro, bitcoin...)."
    )


def chat_answer(message):
    msg = message.lower()
    acc = None

    def with_acc():
        nonlocal acc
        if acc is None:
            acc = get_account()
        return acc

    if any(word in msg for word in ["ayuda", "ayudame", "qué puedes hacer", "que puedes hacer", "que haces"]):
        return (
            "Puedo consultar tu terminal MetaTrader 5 en tiempo real.\n"
            "Prueba con:\n"
            "- 'balance' / 'equity' / 'margen'\n"
            "- 'posiciones abiertas'\n"
            "- 'historial de operaciones'\n"
            "- 'precio del EURUSD' / 'precio del oro'\n"
            "- 'ganancia' o 'profit'"
        )

    if re.search(r"\b(precio|price|cotizaci[oó]n|cotiza|valor|vale|cuesta)\b", msg):
        symbol = detect_symbol(msg)
        if symbol:
            price = get_price(symbol)
            if price is None:
                return f"No encontré el símbolo '{symbol}' en Market Watch."
            if price["bid"] == 0 and price["ask"] == 0:
                return (
                    f"El símbolo {symbol} no tiene cotización activa en este momento "
                    "(no está suscrito en Market Watch)."
                )
            return (
                f"Precio de {price['symbol']}:\n"
                f"Bid {price['bid']:.{5}f} / Ask {price['ask']:.{5}f}"
            )
        return (
            "¿Qué precio quieres consultar? Ejemplos: 'precio del EURUSD', "
            "'cuánto vale el oro' o 'cotización del BTCUSD'."
        )

    if re.search(r"\bmargen\b", msg):
        return margin_intent(with_acc())

    if re.search(r"\b(balance|saldo)\b", msg) and not re.search(r"\b(equity|fondo)\b", msg):
        return price_intent(msg, with_acc())

    if re.search(r"\b(equity|fondo|patrimonio)\b", msg):
        a = with_acc()
        return (
            f"Equity: {money(a['equity'], a['currency'])}\n"
            f"Balance: {money(a['balance'], a['currency'])}\n"
            f"Ganancia/pérdida flotante: {money(a['profit'], a['currency'])}"
        )

    if re.search(r"\b(historial|historia|ultim|últim|operaciones cerradas|deals)\b", msg):
        return history_intent(7)

    if re.search(r"\b(posici[oó]n|posiciones|abiertas)\b", msg):
        return positions_intent()

    if re.search(r"\b(profit|ganancia|beneficio|perdida|pérdida|resultado)\b", msg):
        return profit_intent(with_acc())

    if re.search(r"\b(precio global|todo|resumen|estado|situaci[oó]n|balance completo|general)\b", msg):
        return summary_intent(with_acc())

    if re.search(r"\b(hola|hi|buenas|que tal|qué tal)\b", msg):
        a = with_acc()
        return (
            f"¡Hola! Estoy conectado a tu cuenta MT5 {a['login']}.\n"
            f"Balance: {money(a['balance'], a['currency'])} · "
            f"Equity: {money(a['equity'], a['currency'])}.\n"
            "¿Qué quieres consultar?"
        )

    return summary_intent(with_acc())


class ChatMessage(BaseModel):
    message: str


@app.post("/api/chat")
def api_chat(body: ChatMessage):
    msg = (body.message or "").strip()
    if not msg:
        return {
            "reply": "Escribe una pregunta, por ejemplo: '¿cuál es mi balance?'",
            "intent": "empty",
        }
    try:
        reply = chat_answer(msg)
    except RuntimeError as exc:
        return {"reply": str(exc), "intent": "error"}
    except Exception as exc:
        return {"reply": f"Ocurrió un error: {exc}", "intent": "error"}
    return {"reply": reply, "intent": "answer"}


# ============================================================
# Agente IA (roles + streaming SSE)
# ============================================================

class AgentMessage(BaseModel):
    message: str
    role_id: str = "general"
    conversation_id: Optional[str] = None
    skip_tools: bool = False
    chart_image: Optional[str] = None


@app.post("/api/agent/message")
async def api_agent_message(body: AgentMessage):
    msg = (body.message or "").strip()
    if not msg:
        return JSONResponse({"error": "Mensaje vacío"}, status_code=400)
    role = store.get_role(body.role_id) or store.get_role("general")
    conv_id = body.conversation_id
    if not conv_id or store.get_conversation(conv_id) is None:
        conv = store.create_conversation(title=msg[:60], role_id=role["id"])
        conv_id = conv["id"]
    return StreamingResponse(
        ag.stream_agent(
            conv_id, role["id"], msg,
            skip_tools=body.skip_tools,
            chart_image=body.chart_image,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RoleBody(BaseModel):
    id: Optional[str] = None
    name: str
    system_prompt: str
    allowed_tools: list[str] = ["account_info", "positions_list", "history", "price", "now"]
    provider: str = "auto"
    model: str = ""


@app.get("/api/agent/roles", response_model=None)
def api_agent_roles_list():
    return store.list_roles()


@app.post("/api/agent/roles", response_model=None)
def api_agent_roles_create(body: RoleBody):
    rid = body.id or body.name.lower().replace(" ", "_")
    return store.upsert_role(rid, body.name, body.system_prompt, body.allowed_tools, body.provider, body.model)


@app.put("/api/agent/roles/{rid}", response_model=None)
def api_agent_roles_update(rid: str, body: RoleBody):
    role = store.get_role(rid)
    if role is None:
        return JSONResponse({"error": "Rol no encontrado"}, status_code=404)
    return store.upsert_role(rid, body.name, body.system_prompt, body.allowed_tools, body.provider, body.model)


@app.delete("/api/agent/roles/{rid}")
def api_agent_roles_delete(rid: str):
    store.delete_role(rid)
    return {"deleted": rid}


class ConversationBody(BaseModel):
    title: str = "Nueva conversación"
    role_id: str = "general"


@app.get("/api/agent/conversations", response_model=None)
def api_agent_conversations_list():
    return store.list_conversations()


@app.post("/api/agent/conversations", response_model=None)
def api_agent_conversations_create(body: ConversationBody):
    return store.create_conversation(body.title, body.role_id)


@app.get("/api/agent/conversations/{cid}/messages", response_model=None)
def api_agent_conversation_messages(cid: str):
    if store.get_conversation(cid) is None:
        return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
    return store.get_messages(cid, limit=200)


@app.delete("/api/agent/conversations/{cid}")
def api_agent_conversation_delete(cid: str):
    store.delete_conversation(cid)
    return {"deleted": cid}


# ============================================================
# Configuración del agente
# ============================================================

@app.get("/api/agent/config", response_model=None)
def api_agent_config_get():
    settings = store.get_settings()
    keys = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
    }
    return {
        "active_role_id": settings.get("active_role_id", "general"),
        "fallback_order": json.loads(settings.get("fallback_order", "[]")),
        "history_limit": int(settings.get("history_limit", "20")),
        "max_tool_rounds": int(settings.get("max_tool_rounds", "6")),
        "keys": keys,
        "any_key": any(keys.values()),
        "available_models": ag.resolve_model_chain(None),
    }


class AgentConfigBody(BaseModel):
    active_role_id: Optional[str] = None
    fallback_order: Optional[list[str]] = None
    history_limit: Optional[int] = None
    max_tool_rounds: Optional[int] = None


@app.post("/api/agent/config", response_model=None)
def api_agent_config_set(body: AgentConfigBody):
    if body.active_role_id and store.get_role(body.active_role_id):
        store.set_setting("active_role_id", body.active_role_id)
    if body.fallback_order:
        store.set_setting("fallback_order", json.dumps(body.fallback_order))
    if body.history_limit is not None:
        store.set_setting("history_limit", str(int(body.history_limit)))
    if body.max_tool_rounds is not None:
        store.set_setting("max_tool_rounds", str(int(body.max_tool_rounds)))
    return api_agent_config_get()


# ============================================================
# Journal / Bitácora
# ============================================================

def enrich_journal_entry(entry: dict) -> dict:
    """Auto-rellena poi_type/liquidity_swept cruzando la posición abierta (por ticket)
    con las zonas SMC, SOLO si el usuario no las especificó. Nunca lanza: si MT5 no
    está o no hay posición, deja los campos como estaban."""
    if entry.get("poi_type") and entry.get("liquidity_swept"):
        return entry
    ticket = entry.get("ticket")
    if not ticket:
        return entry

    def _lookup():
        pos = mt5.positions_get(ticket=int(ticket))
        return pos[0] if pos else None

    try:
        pos = run_mt5(_lookup)
    except Exception:
        return entry
    if pos is None:
        return entry

    try:
        cls = patterns_service.classify_entry(
            pos.symbol, patterns_service.DEFAULT_TIMEFRAME, pos.price_open, pos.time
        )
    except Exception:
        return entry

    if not entry.get("poi_type"):
        entry["poi_type"] = cls["poi_type"]
    if not entry.get("liquidity_swept"):
        entry["liquidity_swept"] = cls["liquidity_swept"]

    # Backfill de precios/tiempos del trade desde la posición MT5 (para el overlay)
    if not entry.get("entry_price"):
        entry["entry_price"] = getattr(pos, "price_open", None)
    if not entry.get("sl_price"):
        entry["sl_price"] = getattr(pos, "sl", None)
    if not entry.get("tp_price"):
        entry["tp_price"] = getattr(pos, "tp", None)
    if not entry.get("time_open"):
        entry["time_open"] = getattr(pos, "time", None)
    return entry


class JournalEntry(BaseModel):
    conversation_id: Optional[str] = None
    ticket: Optional[str] = None
    symbol: str = "EURUSD"
    action: Optional[str] = None
    poi_type: Optional[str] = None
    liquidity_swept: Optional[str] = None
    cme_confirmation: Optional[str] = None
    setup_json: dict = {}
    emotion: Optional[str] = None
    plan_compliance: Optional[bool] = None
    tags: list[str] = []
    notes: Optional[str] = None
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    time_open: Optional[int] = None
    time_close: Optional[int] = None


@app.get("/api/journal", response_model=None)
def api_journal_list(symbol: str = "", days: int = 0, limit: int = 50):
    return store.list_journal(symbol=symbol or None, days=days or None, limit=min(limit, 200))


@app.get("/api/journal/overlay", response_model=None)
def api_journal_overlay(symbol: str = "", days: int = 30):
    """Datos del journal listos para dibujar sobre el gráfico: por cada entrada
    con entry_price y time_open, la coordenada x (time) e y (price), línea de
    SL/TP y resultado (win/loss desde tp/sl frente a entry)."""
    entries = store.list_journal(symbol=symbol or None, days=days or None, limit=200)
    out = []
    for e in entries:
        ep = e.get("entry_price")
        to = e.get("time_open")
        if ep is None or to is None:
            continue
        sl, tp = e.get("sl_price"), e.get("tp_price")
        action = (e.get("action") or "").upper()
        result = None
        if tp is not None and ep is not None:
            result = "win" if (action == "BUY" and tp > ep) or (action == "SELL" and tp < ep) else "loss"
        guard = (sl, tp) if (sl is not None and tp is not None) else ((sl,) if sl is not None else ())
        for line_price in guard:
            if line_price is None:
                continue
            out.append({
                "id": f"j{e['id']}",
                "symbol": e["symbol"],
                "entry_time": to,
                "entry_price": ep,
                "line_price": line_price,
                "line_type": "sl" if line_price == sl else "tp",
                "result": result,
                "label": e.get("poi_type") or str(e.get("ticket") or e["id"]),
            })
    return out


@app.post("/api/journal", response_model=None)
def api_journal_create(body: JournalEntry):
    entry = body.model_dump()
    enrich_journal_entry(entry)
    return store.add_journal_entry(entry)


@app.get("/api/journal/{jid}", response_model=None)
def api_journal_get(jid: int):
    entry = store.get_journal_entry(jid)
    if entry is None:
        return JSONResponse({"error": "Entrada no encontrada"}, status_code=404)
    return entry


@app.put("/api/journal/{jid}", response_model=None)
def api_journal_update(jid: int, body: JournalEntry):
    if store.get_journal_entry(jid) is None:
        return JSONResponse({"error": "Entrada no encontrada"}, status_code=404)
    entry = body.model_dump()
    enrich_journal_entry(entry)
    return store.update_journal_entry(jid, entry)


@app.delete("/api/journal/{jid}")
def api_journal_delete(jid: int):
    store.delete_journal_entry(jid)
    return {"deleted": jid}


# ============================================================
# Trades (base de datos local)
# ============================================================

@app.get("/api/trades", response_model=None)
def api_trades_list(symbol: str = "", action: str = "", days: int = 0, limit: int = 200):
    return store.list_trades(
        symbol=symbol or None,
        action=action or None,
        days=days or None,
        limit=min(limit, 500),
    )


@app.post("/api/trades/sync")
def api_trades_sync():
    try:
        return {"count": len(sync_trades())}
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


# ============================================================
# Explorador de tablas de la base local (solo lectura)
# ============================================================

@app.get("/api/db/tables", response_model=None)
def api_db_tables():
    return store.list_db_tables()


@app.get("/api/db/tables/{table}", response_model=None)
def api_db_table(table: str, limit: int = 100):
    data = store.query_db_table(table, limit=min(limit, 500))
    if data is None:
        return JSONResponse({"error": f"Tabla '{table}' no existe"}, status_code=404)
    return data


# ============================================================
# Trading desde el dashboard (espejo de los EAs MQL5)
# ============================================================

_SF_FOK = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
_SF_IOC = getattr(mt5, "SYMBOL_FILLING_IOC", 2)
_ORDER_TYPE_BUY = getattr(mt5, "ORDER_TYPE_BUY", 0)
_ORDER_TYPE_SELL = getattr(mt5, "ORDER_TYPE_SELL", 1)
_POSITION_TYPE_BUY = getattr(mt5, "POSITION_TYPE_BUY", 0)
_TRADE_ACTION_DEAL = getattr(mt5, "TRADE_ACTION_DEAL", 1)
_DEAL_ENTRY_IN = getattr(mt5, "DEAL_ENTRY_IN", 0)
_DEAL_TYPE_BUY = getattr(mt5, "DEAL_TYPE_BUY", 0)
_DEAL_TYPE_SELL = getattr(mt5, "DEAL_TYPE_SELL", 1)

_RETCODE_OK = (10008, 10009, 10010)
_RETCODE_LABELS = {
    10004: "REQUOTE: el precio cambió al enviar. Reintenta.",
    10006: "RECHAZADA: el broker rechazó la petición.",
    10014: "Volumen inválido.",
    10015: "Precio inválido.",
    10016: "SL/TP inválidos (fuera de rango del broker o del símbolo).",
    10017: "Trading deshabilitado para este símbolo/cuenta.",
    10018: "El mercado está cerrado.",
    10019: "Margen insuficiente. Reduce el lote.",
    10020: "El precio cambió durante el envío.",
    10028: "El símbolo está bloqueado.",
    10029: "El símbolo está congelado.",
    10030: "Tipo de filling no soportado por el broker.",
    10031: "Sin conexión con el servidor de trading.",
    10036: "La posición ya está cerrada.",
}


def _dump(body):
    try:
        return body.model_dump(exclude_none=True)
    except AttributeError:
        return body.dict(exclude_none=True)


def _retcode_msg(code, comment):
    label = _RETCODE_LABELS.get(int(code), f"Código {int(code)}")
    extra = f" · {comment}" if comment else ""
    return f"{label}{extra}"


def _sym_info(symbol):
    """Devuelve (info, trade) soportando las distintas versiones del paquete MT5."""
    info = mt5.symbol_info(symbol)
    trade = None
    _st = getattr(mt5, "symbol_info_trade", None)
    if _st is not None:
        try:
            trade = _st(symbol)
        except Exception:
            trade = None
    return info, trade


def _sfield(info, trade, name, default):
    if trade is not None:
        v = getattr(trade, name, None)
        if v is not None:
            return v
    return getattr(info, name, default)


def get_specs(symbol):
    """Especificaciones de trading del símbolo: cotización, volúmenes, filling y pip."""
    def _get():
        info, trade = _sym_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return None
        filling_mask = int(_sfield(info, trade, "filling_mode", 0))
        fillings = [_m for _m in (_SF_FOK, _SF_IOC) if filling_mask & _m]
        if not fillings:
            fillings = [_SF_FOK, _SF_IOC]
        pip_price = info.point * 10.0
        return {
            "symbol": symbol,
            "digits": info.digits,
            "point": info.point,
            "pip_price": pip_price,
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "spread": info.spread,
            "volume_min": float(_sfield(info, trade, "volume_min", 0.01)),
            "volume_max": float(_sfield(info, trade, "volume_max", 0.01)),
            "volume_step": float(_sfield(info, trade, "volume_step", 0.01)) or 0.01,
            "contract_size": float(_sfield(info, trade, "trade_contract_size", 0.0)),
            "tick_value": float(_sfield(info, trade, "trade_tick_value", 0.0)),
            "tick_size": float(_sfield(info, trade, "trade_tick_size", 0.0)),
            "filling_mask": filling_mask,
            "filling_modes": fillings,
            "filling_labels": ["FOK" if m == _SF_FOK else "IOC" for m in fillings],
        }
    return run_mt5(_get)


def lot_suggestion(symbol, action, sl_pips):
    """Lote sugerido por riesgo % (espejo CalculateLotSize del EA) usando order_calc_*."""
    def _get():
        info, trade = _sym_info(symbol)
        account = mt5.account_info()
        tick = mt5.symbol_info_tick(symbol)
        if info is None or account is None or tick is None:
            return None
        order_type = _ORDER_TYPE_BUY if action == "BUY" else _ORDER_TYPE_SELL
        entry = tick.ask if action == "BUY" else tick.bid
        sl_dist = (float(sl_pips) or 0.0) * info.point * 10.0
        if sl_dist <= 0:
            return None
        sl_price = round(entry - sl_dist, info.digits) if action == "BUY" else round(entry + sl_dist, info.digits)
        step = float(_sfield(info, trade, "volume_step", 0.01)) or 0.01
        risk_budget = account.balance * float(store.get_trading_config()["risk_pct"]) / 100.0
        loss_1lot = mt5.order_calc_profit(order_type, symbol, 1.0, entry, sl_price)
        if loss_1lot is None or loss_1lot >= 0 or abs(loss_1lot) < 1e-12:
            return None
        lot = math.floor(risk_budget / abs(loss_1lot) / step) * step
        decimals = max(len(str(step).split(".")[1]) if "." in str(step) else 0, 1)
        lot = round(lot, decimals)
        vmin = float(_sfield(info, trade, "volume_min", 0.01))
        vmax = float(_sfield(info, trade, "volume_max", 0.01))
        lot = max(vmin, min(vmax, lot))
        margin = mt5.order_calc_margin(order_type, symbol, lot, entry)
        return {
            "lot": lot,
            "risk_budget": round(risk_budget, 2),
            "entry_price": entry,
            "sl_price": sl_price,
            "step": step,
            "volume_min": vmin,
            "volume_max": vmax,
            "margin": round(float(margin or 0.0), 2),
            "margin_free": account.margin_free,
            "sl_distance": sl_dist,
        }
    return run_mt5(_get)


def daily_risk_state():
    """Espejo de los límites del EA: DD diario (equity vs balance inicial del día,
    incluyendo comisiones + swap), operaciones abiertas hoy y gate prop-firm real
    (HWM diario/total + tope de ganancia) cuando prop_enabled."""
    cfg = store.get_trading_config()
    prev_prop = store.get_prop_state() if cfg.get("prop_enabled") else None
    now_utc = datetime.now(timezone.utc)

    def _get():
        account = mt5.account_info()
        if account is None:
            raise RuntimeError("No hay conexión con MetaTrader 5.")
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(start, now) or []
        realized = 0.0
        opened_today = set()
        for d in deals:
            if d.profit or d.commission or d.swap:
                realized += (d.profit or 0.0) + (d.commission or 0.0) + (d.swap or 0.0)
            if d.entry == _DEAL_ENTRY_IN and d.type in (_DEAL_TYPE_BUY, _DEAL_TYPE_SELL):
                opened_today.add(d.position_id)
        day_start_balance = account.balance - realized
        dd_daily = max(0.0, day_start_balance - account.equity)
        pct_dd = (dd_daily / day_start_balance * 100.0) if day_start_balance else 0.0
        trades_today = len(opened_today)

        reasons = []
        blocked = False
        max_fixed = float(cfg.get("loss_limit_fixed") or 0.0)
        max_pct = float(cfg.get("loss_limit_pct") or 0.0)
        max_trades = int(cfg.get("max_trades_day") or 0)
        if max_fixed > 0 and dd_daily >= max_fixed:
            blocked = True
            reasons.append(f"pérdida diaria ≥ ${max_fixed:,.0f} (DD actual ${dd_daily:,.2f})")
        if max_pct > 0 and pct_dd >= max_pct:
            blocked = True
            reasons.append(f"pérdida diaria ≥ {max_pct:.1f}% (DD actual {pct_dd:.2f}%)")
        if max_trades > 0 and trades_today >= max_trades:
            blocked = True
            reasons.append(f"máximo de {max_trades} operaciones/día alcanzado ({trades_today})")

        # Gate prop-firm real (M4): HWM diario + DD total + tope de ganancia.
        prop = risk_engine.prop_firm_state(
            equity=account.equity,
            day_start_balance=day_start_balance,
            prev_state=prev_prop,
            now=now_utc,
            cfg=cfg,
        )
        if prop["blocked"]:
            blocked = True
            reasons.extend(prop["reasons"])

        return {
            "balance": account.balance,
            "equity": account.equity,
            "day_start_balance": round(day_start_balance, 2),
            "realized_today": round(realized, 2),
            "dd_daily": round(dd_daily, 2),
            "dd_pct": round(pct_dd, 2),
            "trades_today": trades_today,
            "max_trades_day": max_trades,
            "max_loss_fixed": max_fixed,
            "max_loss_pct": max_pct,
            "prop_enabled": prop["enabled"],
            "prop_dd_daily_pct": prop["dd_daily_pct"],
            "prop_dd_total_pct": prop["dd_total_pct"],
            "prop_day_profit_pct": prop["day_profit_pct"],
            "prop_consistency_days": prop.get("consistency_days"),
            "blocked": blocked,
            "reasons": reasons,
            "_prop_state": prop["state"],
        }

    data = run_mt5(_get)
    if data.get("prop_enabled") and data.get("_prop_state"):
        store.set_prop_state(**data["_prop_state"])
    data.pop("_prop_state", None)
    return data


def _round_sl_price(sl_raw, action, entry, point, digits):
    sl = 0.0
    if sl_raw and sl_raw > 0:
        sl = entry - sl_raw if action == "BUY" else entry + sl_raw
        sl = round(sl, digits)
    return sl


def send_market_order(symbol, action, volume, sl_pips, tp_pips, magic=None, comment=None, deviation=None, invalidate_level=None):
    """Envía una orden de mercado al símbolo con llenado automático FOK → IOC.

    `invalidate_level` (nivel de invalidez estructural desde risk_engine) se
    calcula en el endpoint ANTES de entrar a la region MT5: mt5 solo se toca aqui."""
    symbol = symbol.upper()
    action = action.upper()
    cfg = store.get_trading_config()
    magic = int(magic if magic is not None else cfg.get("magic", 0))
    comment = comment or cfg.get("comment", "Web Exec")
    deviation = int(deviation if deviation is not None else cfg.get("deviation_points", 20))

    def _send():
        info, trade = _sym_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return {"ok": False, "error": f"Símbolo '{symbol}' no disponible o sin cotización en Market Watch."}

        order_type = _ORDER_TYPE_BUY if action == "BUY" else _ORDER_TYPE_SELL
        entry = tick.ask if action == "BUY" else tick.bid
        step = float(_sfield(info, trade, "volume_step", 0.01)) or 0.01
        decimals = max(len(str(step).split(".")[1]) if "." in str(step) else 0, 1)
        lot = round(math.floor(max(float(volume), 0.0) / step) * step, decimals)
        if lot <= 0:
            return {"ok": False, "error": "Volumen no válido."}
        vmin = float(_sfield(info, trade, "volume_min", 0.01))
        vmax = float(_sfield(info, trade, "volume_max", 0.01))
        if lot < vmin or lot > vmax:
            return {
                "ok": False,
                "error": f"Volumen {lot} fuera de rango [{vmin}, {vmax}] paso {step}.",
            }

        sl = _round_sl_price(float(sl_pips) * info.point * 10.0, action, entry, info.point, info.digits)
        tp = _round_sl_price(float(tp_pips) * info.point * 10.0, action, entry, info.point, info.digits)

        # Risk Engine (M1): gate determinista R:R + invalidez estructural + cabeza de
        # riesgo en dinero. Rechazo duro; cada disparo queda registrado en setup_log.
        account = mt5.account_info()
        loss_1lot = None
        if sl and sl > 0 and account is not None:
            loss_1lot = mt5.order_calc_profit(order_type, symbol, 1.0, entry, sl)
        cfg_g = store.get_trading_config()
        try:
            val = risk_engine.validate_entry(
                entry=entry, sl=sl, target=tp, direction=action,
                current_price=tick.bid if action == "BUY" else tick.ask,
                invalidate_level=invalidate_level, created_at=None, cfg=dict(cfg_g),
                balance=(account.balance if account is not None else None),
                risk_pct=cfg_g.get("risk_pct"), loss_per_lot=loss_1lot, lot=lot,
            )
        except Exception as exc:
            val = {"approved": True, "reasons": [f"risk_engine error: {exc}"]}
        try:
            store.log_setup({
                "symbol": symbol, "timeframe": patterns_service.DEFAULT_TIMEFRAME,
                "direction": action, "verdict": "",
                "score": 0.0, "breakdown": {"gate": val},
                "entry": entry, "sl": sl, "target": tp,
                "invalidate_level": invalidate_level, "validated": bool(val["approved"]),
                "reject_reasons": val.get("reasons") or [],
                "risk_state": {}, "trade_result": {},
            })
        except Exception:
            pass
        if not val["approved"]:
            vis = [r for r in val.get("reasons", []) if "error" not in r]
            vis = vis or val.get("reasons") or ["desconocido"]
            return {"ok": False, "error": "Rechazado por el risk engine: " + "; ".join(vis)}

        filling_mask = int(_sfield(info, trade, "filling_mode", 0))
        fillings = [_m for _m in (_SF_FOK, _SF_IOC) if filling_mask & _m]
        if not fillings:
            fillings = [_SF_FOK, _SF_IOC]

        last_error = None
        used_fills = set()
        for fill in list(fillings):
            if fill in used_fills:
                continue
            used_fills.add(fill)
            request = {
                "action": _TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order_type,
                "price": entry,
                "sl": sl,
                "tp": tp,
                "deviation": deviation,
                "magic": magic,
                "comment": comment,
                "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
                "type_filling": fill,
            }
            result = mt5.order_send(request)
            if result is None:
                last_error = "order_send devolvió None (revisa la conexión con la terminal)."
                continue
            if result.retcode in _RETCODE_OK:
                return {
                    "ok": True,
                    "symbol": symbol,
                    "action": action,
                    "volume": lot,
                    "price": entry,
                    "sl": sl,
                    "tp": tp,
                    "magic": magic,
                    "comment": comment,
                    "filling": "FOK" if fill == _SF_FOK else "IOC",
                    "ticket": result.order,
                    "deal": result.deal,
                    "retcode": result.retcode,
                }
            last_error = _retcode_msg(result.retcode, getattr(result, "comment", None))
            if result.retcode == 10030:  # INVALID_FILL → probar primero el otro modo y volver al cíclico
                other = _SF_IOC if fill == _SF_FOK else _SF_FOK
                if other not in used_fills:
                    fillings.append(other)
                continue
            if result.retcode not in (10004, 10020):  # REQUOTE / PRICE_CHANGED solo merecen reintento de fill
                break
        return {"ok": False, "error": last_error or "No se pudo ejecutar la orden."}
    return run_mt5(_send)


def close_position(ticket):
    """Cierra una posición abierta conservando su magic para no romper el conteo del EA.""" 
    def _close():
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return {"ok": False, "error": "La posición ya no está abierta."}
        pos = positions[0]
        info, trade = _sym_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if info is None or tick is None:
            return {"ok": False, "error": f"No hay cotización para cerrar '{pos.symbol}'."}
        order_type = _ORDER_TYPE_SELL if pos.type == _POSITION_TYPE_BUY else _ORDER_TYPE_BUY
        price = tick.bid if pos.type == _POSITION_TYPE_BUY else tick.ask
        cfg = store.get_trading_config()
        magic = int(pos.magic) if pos.magic else int(cfg.get("magic", 0))
        deviation = int(cfg.get("deviation_points", 20))
        filling_mask = int(_sfield(info, trade, "filling_mode", 0))
        fillings = [_m for _m in (_SF_FOK, _SF_IOC) if filling_mask & _m]
        if not fillings:
            fillings = [_SF_FOK, _SF_IOC]

        last_error = None
        used_fills = set()
        for fill in list(fillings):
            if fill in used_fills:
                continue
            used_fills.add(fill)
            request = {
                "action": _TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": pos.ticket,
                "price": price,
                "deviation": deviation,
                "magic": magic,
                "comment": "Web Close",
                "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
                "type_filling": fill,
            }
            result = mt5.order_send(request)
            if result is None:
                last_error = "order_send devolvió None (revisa la conexión con la terminal)."
                continue
            if result.retcode in _RETCODE_OK:
                return {
                    "ok": True,
                    "symbol": pos.symbol,
                    "action": "SELL" if order_type == _ORDER_TYPE_SELL else "BUY",
                    "volume": pos.volume,
                    "price": price,
                    "ticket": pos.ticket,
                    "deal": result.deal,
                    "filling": "FOK" if fill == _SF_FOK else "IOC",
                    "retcode": result.retcode,
                }
            last_error = _retcode_msg(result.retcode, getattr(result, "comment", None))
            if result.retcode == 10030:
                other = _SF_IOC if fill == _SF_FOK else _SF_FOK
                if other not in used_fills:
                    fillings.append(other)
                continue
            if result.retcode not in (10004, 10020):
                break
        return {"ok": False, "error": last_error or "No se pudo cerrar la posición."}
    return run_mt5(_close)


# ---- Endpoints ----

class TradeConfigBody(BaseModel):
    magic: Optional[int] = None
    comment: Optional[str] = None
    risk_pct: Optional[float] = None
    loss_limit_fixed: Optional[float] = None
    loss_limit_pct: Optional[float] = None
    max_trades_day: Optional[int] = None
    sl_default_pips: Optional[float] = None
    tp_ratio_r: Optional[float] = None
    deviation_points: Optional[int] = None
    symbols_allow: Optional[list] = None


@app.get("/api/trade/config", response_model=None)
def api_trade_config():
    cfg = store.get_trading_config()
    try:
        risk = daily_risk_state()
    except RuntimeError as exc:
        risk = {"blocked": False, "error": str(exc)}
    return {"config": cfg, "risk": risk, "strategy": store.get_config_summary()}


@app.post("/api/trade/config", response_model=None)
def api_trade_config_set(body: TradeConfigBody):
    cfg = store.get_trading_config()
    upd = _dump(body)
    for k, v in upd.items():
        if k == "symbols_allow":
            cfg[k] = [str(s).upper() for s in (v or [])]
        elif k in cfg:
            cfg[k] = v
    store.set_trading_config(cfg)
    return api_trade_config()


@app.get("/api/trade/info/{symbol}", response_model=None)
def api_trade_info(symbol: str):
    symbol = symbol.upper()
    try:
        spec = get_specs(symbol)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if spec is None:
        return JSONResponse({"error": f"Símbolo '{symbol}' no disponible en Market Watch."}, status_code=404)
    cfg = store.get_trading_config()
    default_sl = float(cfg.get("sl_default_pips", 15))
    try:
        suggest = {"BUY": lot_suggestion(symbol, "BUY", default_sl), "SELL": lot_suggestion(symbol, "SELL", default_sl)}
    except RuntimeError:
        suggest = {"BUY": None, "SELL": None}
    return {
        **spec,
        "config": {
            "magic": int(cfg.get("magic", 0)),
            "comment": cfg.get("comment", "Web Exec"),
            "risk_pct": float(cfg.get("risk_pct", 0.5)),
            "sl_default_pips": default_sl,
            "tp_ratio_r": float(cfg.get("tp_ratio_r", 2.0)),
        },
        "suggest": suggest,
    }


class TradeMarketBody(BaseModel):
    symbol: str
    action: str = "BUY"
    volume: Optional[float] = None
    sl_pips: Optional[float] = None
    tp_pips: Optional[float] = None
    magic: Optional[int] = None
    comment: Optional[str] = None
    deviation: Optional[int] = None


def execute_market_trade(symbol, action, volume=None, sl_pips=None, tp_pips=None,
                         magic=None, comment=None, deviation=None):
    """Ejecuta una orden de mercado con todas las barreras de riesgo (lista
    permitida, límites diarios, lote por riesgo, gate del risk engine).

    Compartido por /api/trade/market y por el watcher (auto_execute).
    Devuelve (result, status): result incluye 'ok': True en éxito.
    """
    symbol = (symbol or "").upper()
    action = (action or "").upper()
    if not symbol:
        return {"error": "Falta el símbolo."}, 400
    if action not in ("BUY", "SELL"):
        return {"error": "action debe ser BUY o SELL."}, 400

    cfg = store.get_trading_config()
    allow = cfg.get("symbols_allow") or []
    if allow and symbol not in allow:
        return {"error": f"Símbolo '{symbol}' no está en la lista permitida."}, 403

    try:
        risk = daily_risk_state()
    except RuntimeError as exc:
        return {"error": str(exc)}, 503
    if risk["blocked"]:
        return {"error": "Operar bloqueado por límites de riesgo: " + "; ".join(risk["reasons"])}, 403

    # Gate de noticias (hard). FAIL-OPEN: si el calendario no se puede leer NO se
    # bloquea (nunca quedarse sin operar por una caída de red o del proxy Jina).
    data_sources = cfg.get("data_sources") or {}
    if data_sources.get("news", True):
        try:
            gate = ff.news_gate(
                min_impact=cfg.get("news_gate_impact", "red"),
                buffer_min=float(cfg.get("news_buffer_min") or 15),
            )
        except Exception as exc:
            gate = {"ok": True, "fail_open": True, "reason": str(exc), "event": None}
        if not gate.get("ok"):
            try:
                store.log_setup({
                    "symbol": symbol, "timeframe": patterns_service.DEFAULT_TIMEFRAME,
                    "direction": (action or "BUY").upper(), "verdict": "IGNORED_NEWS",
                    "score": 0.0, "breakdown": {},
                    "entry": None, "sl": None, "target": None,
                    "invalidate_level": None, "validated": False,
                    "reject_reasons": [
                        "BLOCKED_BY_NEWS_GATE: " + str(gate.get("reason"))
                    ],
                    "risk_state": {}, "trade_result": {},
                })
            except Exception:
                pass
            return {
                "error": "Operar bloqueado por calendario económico: "
                + str(gate.get("reason")),
                "status": "BLOCKED_BY_NEWS_GATE",
                "news": gate.get("event"),
            }, 403

    if sl_pips is None:
        sl_pips = float(cfg.get("sl_default_pips", 15))
    sl_pips = float(sl_pips)
    if tp_pips is None:
        tp_pips = sl_pips * float(cfg.get("tp_ratio_r", 2.0))
    tp_pips = float(tp_pips)

    volume = float(volume) if volume else 0.0
    if volume <= 0:
        try:
            sug = lot_suggestion(symbol, action, sl_pips)
        except RuntimeError as exc:
            return {"error": str(exc)}, 503
        if sug is None:
            return {"error": "No se pudo calcular el lote por riesgo (revisa SL y cotización)."}, 400
        volume = sug["lot"]
        if sug.get("margin_free") is not None and sug.get("margin", 0) > sug.get("margin_free", 0):
            return {"error": "Margen libre insuficiente para el lote calculado."}, 400

    try:
        result = send_market_order(symbol, action, volume, sl_pips, tp_pips, magic=magic, comment=comment, deviation=deviation)
    except RuntimeError as exc:
        return {"error": str(exc)}, 503
    if not result["ok"]:
        return {"error": result["error"]}, 400
    try:
        store.link_last_setup(result.get("ticket"), symbol, result.get("price"), result.get("sl"), result.get("tp"))
    except Exception:
        pass
    try:
        sync_trades()
    except Exception:
        pass
    try:
        poi = patterns_service.classify_entry(
            symbol, patterns_service.DEFAULT_TIMEFRAME, result["price"], int(time.time())
        )
    except Exception:
        poi = {"poi_type": None, "liquidity_swept": None}
    try:
        risk_now = daily_risk_state()
    except Exception as exc:
        risk_now = {"error": str(exc)}
    return {**result, "poi": poi, "risk": risk_now}, 200


def _watcher_execute(symbol, action, sl_pips=None, tp_pips=None, volume=None):
    """Adaptador del watcher -> execute_market_trade (dict plano, sin status)."""
    result, status = execute_market_trade(
        symbol, action, volume=volume, sl_pips=sl_pips, tp_pips=tp_pips
    )
    return {**result, "status": status}


@app.post("/api/trade/market", response_model=None)
def api_trade_market(body: TradeMarketBody):
    result, status = execute_market_trade(
        body.symbol, body.action, volume=body.volume, sl_pips=body.sl_pips,
        tp_pips=body.tp_pips, magic=body.magic, comment=body.comment,
        deviation=body.deviation,
    )
    if status == 200:
        return result
    return JSONResponse(result, status_code=status)


@app.get("/api/watcher/status", response_model=None)
def api_watcher_status():
    """Config + estados vigentes del watcher (bot a la escucha)."""
    try:
        return watcher.watcher_status()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


class WatcherAutoExecuteBody(BaseModel):
    enabled: bool


@app.post("/api/watcher/auto-execute", response_model=None)
def api_watcher_auto_execute(body: WatcherAutoExecuteBody):
    """Conmuta y persiste el auto_execute del watcher (overrides el YAML)."""
    store.set_watcher_auto_execute(bool(body.enabled))
    return {"ok": True, "auto_execute": store.get_watcher_auto_execute()}


@app.post("/api/watcher/scan", response_model=None)
async def api_watcher_scan():
    """Dispara un ciclo de escaneo a mano y devuelve los eventos detectados."""
    events = watcher.scan_once(
        build_chart_snapshot,
        executor=_watcher_execute,
        broadcast=lambda payload: asyncio.create_task(manager.broadcast(payload)),
    )
    return {"ok": True, "events": events}


@app.post("/api/positions/{ticket}/close", response_model=None)
def api_position_close(ticket: int):
    try:
        result = close_position(ticket)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    if not result["ok"]:
        return JSONResponse({"error": result["error"]}, status_code=400)
    try:
        sync_trades()
    except Exception:
        pass
    return {**result, "risk": daily_risk_state()}


# ============================================================
# Research / Backtest (pipeline offline research/)
# ============================================================
# El pipeline vive en research/ y es deliberadamente ajeno al runtime
# (research/__init__.py: app/agent/watcher no importan nada de ahí). Por eso
# aquí se ejecuta como SUBPROCESO del mismo CLI (research/run_research.py):
# se respeta la separación, se reutiliza el mismo código y los resultados
# quedan en research/results compartidos con la consola.

_RESEARCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research")
_RESEARCH_RESULTS = os.path.join(_RESEARCH_DIR, "results")
_RESEARCH_CLI = os.path.join("research", "run_research.py")


class ResearchRunBody(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    days: int = 90


def _research_subprocess(args, timeout=900):
    code = subprocess.run(
        [sys.executable, _RESEARCH_CLI, *args],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return code.returncode == 0, (code.stdout or ""), (code.stderr or "")


def _research_payload_path(symbol, timeframe, kind):
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return os.path.join(_RESEARCH_RESULTS, f"{symbol}_{timeframe}_{day}_{kind}.json")


def _research_load_payload(symbol, timeframe, kind):
    path = _research_payload_path(symbol, timeframe, kind)
    if not os.path.exists(path):
        return None, f"No hay resultado '{kind}' de {symbol} {timeframe} en {path} (ejecuta antes)."
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh), None


@app.get("/api/research/runs", response_model=None)
def api_research_runs(kind: str = ""):
    """Lista los JSON de research/results (compartidos con el CLI)."""
    runs = []
    if os.path.isdir(_RESEARCH_RESULTS):
        for name in sorted(os.listdir(_RESEARCH_RESULTS), reverse=True):
            if not name.endswith(".json"):
                continue
            info = {"name": name, "kind": None, "mtime": None, "size": None}
            for k_ in ("bt", "cal", "val", "search"):
                if name.endswith(f"_{k_}.json"):
                    info["kind"] = k_
                    break
            if kind and info["kind"] != kind:
                continue
            p = os.path.join(_RESEARCH_RESULTS, name)
            try:
                st = os.stat(p)
                info["mtime"] = st.st_mtime
                info["size"] = st.st_size
            except OSError:
                pass
            runs.append(info)
    return {"runs": runs}


@app.post("/api/research/export", response_model=None)
def api_research_export(body: ResearchRunBody):
    """Exporta (o refresca) el histórico desde MT5 a research/data/. Necesita terminal abierta."""
    ok, out, err = _research_subprocess([
        "export", "--symbol", (body.symbol or "EURUSD").upper(),
        "--timeframe", (body.timeframe or "M15").upper(), "--days", str(max(1, int(body.days))),
    ])
    if not ok:
        return JSONResponse(
            {"error": (err or out or "falló el export. ¿Terminal MT5 abierta y con sesión?").strip()},
            status_code=500,
        )
    return {"ok": True, "stdout": out}


@app.post("/api/research/backtest", response_model=None)
def api_research_backtest(body: ResearchRunBody):
    symbol = (body.symbol or "EURUSD").upper()
    timeframe = (body.timeframe or "M15").upper()
    ok, out, err = _research_subprocess([
        "backtest", "--symbol", symbol, "--timeframe", timeframe,
        "--days", str(max(1, int(body.days))),
    ])
    if not ok:
        return JSONResponse({"error": (err or out or "falló el backtest").strip()}, status_code=500)
    payload, perr = _research_load_payload(symbol, timeframe, "bt")
    if perr:
        return JSONResponse({"error": perr, "stdout": out}, status_code=500)
    payload["saved"] = _research_payload_path(symbol, timeframe, "bt")
    return payload


@app.post("/api/research/calibrate", response_model=None)
def api_research_calibrate(body: ResearchRunBody):
    symbol = (body.symbol or "EURUSD").upper()
    timeframe = (body.timeframe or "M15").upper()
    ok, out, err = _research_subprocess([
        "calibrate", "--symbol", symbol, "--timeframe", timeframe,
        "--days", str(max(1, int(body.days))),
    ])
    if not ok:
        return JSONResponse({"error": (err or out or "falló calibrate").strip()}, status_code=500)
    payload, perr = _research_load_payload(symbol, timeframe, "cal")
    if perr:
        return JSONResponse({"error": perr, "stdout": out}, status_code=500)
    payload["saved"] = _research_payload_path(symbol, timeframe, "cal")
    return payload


@app.post("/api/research/validate", response_model=None)
def api_research_validate(body: ResearchRunBody):
    symbol = (body.symbol or "EURUSD").upper()
    timeframe = (body.timeframe or "M15").upper()
    ok, out, err = _research_subprocess([
        "validate", "--symbol", symbol, "--timeframe", timeframe,
        "--days", str(max(1, int(body.days))),
    ])
    if not ok:
        return JSONResponse({"error": (err or out or "validación con fallos").strip()}, status_code=500)
    payload, perr = _research_load_payload(symbol, timeframe, "val")
    if perr:
        return JSONResponse({"error": perr, "stdout": out}, status_code=500)
    payload["saved"] = _research_payload_path(symbol, timeframe, "val")
    return payload


class ResearchSearchBody(ResearchRunBody):
    grid: Optional[str] = None
    top: int = 5
    min_filled: int = 10


@app.post("/api/research/search", response_model=None)
def api_research_search(body: ResearchSearchBody):
    """Grid search Top-N. Solo calcula y reporta; NO escribe stratégia."""
    symbol = (body.symbol or "EURUSD").upper()
    timeframe = (body.timeframe or "M15").upper()
    args = [
        "search", "--symbol", symbol, "--timeframe", timeframe,
        "--days", str(max(1, int(body.days))),
        "--top", str(max(1, int(body.top))),
        "--min-filled", str(max(1, int(body.min_filled))),
    ]
    if body.grid:
        args += ["--grid", body.grid]
    ok, out, err = _research_subprocess(args, timeout=1200)
    if not ok:
        return JSONResponse({"error": (err or out or "grid search con fallos").strip()},
                            status_code=500)
    payload, perr = _research_load_payload(symbol, timeframe, "search")
    if perr:
        return JSONResponse({"error": perr, "stdout": out}, status_code=500)
    payload["saved"] = _research_payload_path(symbol, timeframe, "search")
    return payload


# ============================================================
# Fase 2: aplicar sugerencias (con backup y re-backtest)
# ============================================================

_APPLY_ALLOWED = {
    "min_score", "min_rr", "setup_ttl_minutes", "risk_weights",
    "sl_default_pips", "tp_ratio_r", "risk_pct", "reduced_risk_pct",
    "max_trades_day", "loss_limit_fixed", "loss_limit_pct",
}

_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


class ResearchApplyItem(BaseModel):
    key: str
    value: Any


class ResearchApplyBody(BaseModel):
    updates: list
    backup: bool = True
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    days: int = 90


@app.post("/api/research/apply", response_model=None)
def api_research_apply(body: ResearchApplyBody):
    """Aplica manualmente un diff de parámetros a strategy.yaml CON backup previo.

    Exige confirmación del usuario desde la UI (aquí solo se ejecuta lo que le
    llega ya aprobado). Valida whitelist, copia strategy.yaml a backups/, aplica
    via store.store.set_trading_config y re-corre el backtest para mostrar el
    antes/después.
    """
    updates: Dict[str, Any] = {}
    skipped = []
    for item in body.updates or []:
        key = str(item.get("key") or "").strip()
        if key not in _APPLY_ALLOWED:
            skipped.append({"key": key, "reason": "clave no permitida"})
            continue
        value = item.get("value")
        if key == "risk_weights" and not isinstance(value, dict):
            skipped.append({"key": key, "reason": "risk_weights debe ser dict"})
            continue
        if isinstance(value, (bool, type(None))):
            skipped.append({"key": key, "reason": f"tipo no válido: {type(value).__name__}"})
            continue
        try:
            if key != "risk_weights":
                value = float(value)
        except (TypeError, ValueError):
            skipped.append({"key": key, "reason": f"valor no numérico: {value!r}"})
            continue
        updates[key] = value
    if not updates:
        return JSONResponse({"error": "No hay cambios válidos para aplicar.", "skipped": skipped},
                            status_code=400)

    import strategy as _strategy  # noqa: PLC0415 - acceso al path del YAML

    before_config = {k: store.get_trading_config().get(k) for k in updates}

    os.makedirs(_BACKUP_DIR, exist_ok=True)
    backup_path = None
    if body.backup:
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.join(_BACKUP_DIR, f"strategy-{stamp}.yaml")
            with open(_strategy.STRATEGY_PATH, "r", encoding="utf-8") as fh_src:
                with open(backup_path, "w", encoding="utf-8") as fh_dst:
                    fh_dst.write(fh_src.read())
        except OSError as exc:
            return JSONResponse({"error": f"No pude hacer backup de strategy.yaml: {exc}"},
                                status_code=500)

    try:
        store.set_trading_config(updates)
    except Exception as exc:
        return JSONResponse({"error": f"Fallo al escribir strategy.yaml: {exc}"}, status_code=500)

    after_config = {k: store.get_trading_config().get(k) for k in updates}

    # Re-corre el backtest con la config NUEVA (mismo dataset) para el antes/después.
    symbol = (body.symbol or "EURUSD").upper()
    timeframe = (body.timeframe or "M15").upper()
    ok, out, err = _research_subprocess([
        "backtest", "--symbol", symbol, "--timeframe", timeframe,
        "--days", str(max(1, int(body.days))),
    ])
    if not ok:
        return {
            "ok": True, "applied": updates, "skipped": skipped,
            "backup_path": backup_path, "before_config": before_config,
            "after_config": after_config,
            "warning": "Config aplicada, pero el re-backtest falló: " + (err or out),
        }
    payload, perr = _research_load_payload(symbol, timeframe, "bt")
    if perr:
        payload = None
    return {
        "ok": True,
        "applied": updates,
        "skipped": skipped,
        "backup_path": backup_path,
        "before_config": before_config,
        "after_config": after_config,
        "after_payload": payload,
        "saved": _research_payload_path(symbol, timeframe, "bt"),
    }


# ============================================================
# Fase 4: audit de un trade simulado en el gráfico
# ============================================================


class ResearchAuditBody(BaseModel):
    saved: str
    signal_ts: float
    window_before: int = 90
    window_after: int = 60


@app.post("/api/research/audit", response_model=None)
def api_research_audit(body: ResearchAuditBody):
    """Reconstruye la instantánea exacta de un trade simulado para auditarlo.

    Usa el MISMO cfg del run guardado (payload JSON) y el dataset de
    research/data: el sim es determinista e invariante al look-ahead, así que la
    zona del patrón que gatilló `entry_kind` cuadra con la decisión original.
    Devuelve las velas alrededor de signal_ts + la caja del patrón + el plan.
    """
    name = os.path.basename(body.saved or "").replace("\\", "/")
    parts = name.rsplit("_", 3)  # SYM_TF_AAAAMMDD_kind.json
    if len(parts) != 4 or not name.endswith(".json"):
        return JSONResponse({"error": f"Nombre de run inválido: {body.saved}"}, status_code=400)
    symbol, timeframe, day, kind = parts
    run_path = os.path.join(_RESEARCH_RESULTS, name)
    if not os.path.exists(run_path):
        return JSONResponse({"error": f"No encuentro {name} en research/results."}, status_code=404)
    try:
        with open(run_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return JSONResponse({"error": f"No leo el run: {exc}"}, status_code=500)

    run = payload.get("run") or {}
    cfg = dict(run.get("cfg") or {})
    trades = run.get("trades") or []
    signal_ts = int(body.signal_ts)
    trade = next((t for t in trades if int(t.get("signal_ts") or 0) == signal_ts), None)
    if trade is None:
        return JSONResponse({"error": f"No hay trade con signal_ts {signal_ts} en {name}."},
                            status_code=404)

    try:
        from research import data as _rdata  # noqa: PLC0415
        from research import sim as _rsim  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - defensivo
        return JSONResponse({"error": f"Fallo al importar research: {exc}"}, status_code=500)

    ds = _rdata.load_dataset(symbol, timeframe, days=None)
    if ds is None or not ds["candles"]:
        return JSONResponse({"error": f"Sin dataset de {symbol} {timeframe} en research/data."},
                            status_code=500)
    candles = ds["candles"]
    times = [int(c["time"]) for c in candles]

    import bisect  # noqa: PLC0415
    i = bisect.bisect_right(times, signal_ts) - 1  # vela <= signal_ts
    if i < 0:
        return JSONResponse({"error": "signal_ts fuera del dataset."}, status_code=404)

    lookback = max(1, int(cfg.get("lookback") or 300))
    window = candles[max(0, i - lookback + 1): i + 1]
    close = float(candles[i]["close"])
    snap = _rsim.replicate_snapshot(window, close, cfg, int(candles[i]["time"]))
    patterns = (snap.get("analysis") or {}).get("patterns") or {}

    entry_kind = trade.get("entry_kind") or ""
    zone = None
    candidates = []
    for z in (patterns.get("fvgs") or []) + (patterns.get("order_blocks") or []):
        if z.get("type") == entry_kind and int(z.get("start_time") or 0) <= signal_ts:
            candidates.append(z)
    if candidates:
        live = [z for z in candidates if not z.get("mitigated")]
        best = live or candidates
        zone = max(best, key=lambda z: int(z.get("start_time") or 0))

    wb = max(5, int(body.window_before))
    wa = max(5, int(body.window_after))
    lo_idx = max(0, i - wb)
    hi_idx = min(len(candles), i + wa + 1)
    view = [{
        "time": int(c["time"]),
        "open": float(c["open"]), "high": float(c["high"]),
        "low": float(c["low"]), "close": float(c["close"]),
        "volume": float(c.get("volume") or 0.0),
    } for c in candles[lo_idx:hi_idx]]

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "run": name,
        "signal_ts": signal_ts,
        "tf_sec": run.get("tf_sec"),
        "zone": zone,
        "candles": view,
        "trade": {
            "id": trade.get("id"),
            "direction": trade.get("direction"),
            "score": trade.get("score"),
            "verdict": trade.get("verdict"),
            "killzone": trade.get("killzone"),
            "entry_kind": trade.get("entry_kind"),
            "status": trade.get("status"),
            "exit_reason": trade.get("exit_reason"),
            "plan": trade.get("plan"),
            "entry_price": trade.get("entry_price"),
            "exit_price": trade.get("exit_price"),
            "fill_ts": trade.get("fill_ts"),
            "exit_ts": trade.get("exit_ts"),
            "bars_pending": trade.get("bars_pending"),
            "bars_held": trade.get("bars_held"),
            "pnl_r": trade.get("pnl_r"),
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)