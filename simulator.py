"""Simulador de mercado sintético unificado (6E / EURUSD).

Fuente única de datos simulados para auditar el ecosistema completo: el MISMO
tick que consume OrderFlowEngine (app.py) alimenta aquí la agregación de velas,
el footprint por nivel real, el volume profile, la serie CVD y las velas que el
motor SMC (pattern_engine) evalúa contra un PDH/PDL sintético de "sesión".

Principio de diseño: la simulación es determinista — los outputs dependen
SOLO de la secuencia (price, size, side, ts) que reciben por add_tick. Misma
semilla en el generador (mock_feed.gen_stream) -> misma secuencia -> mismas
velas/footprint/VP/CVD.

El acumulador de footprint usa las celdas de precio REALES (nivel redondeado
al step del instrumento por cada tick), de modo que el delta acumulado del
footprint coincide exactamente con el CVD del engine. Los contratos de salida
mantienen la MÁSMA forma que market_view / los endpoints para que ECharts y la
UI no cambien.

Modo puro: no importa app ni MT5 ni Databento.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import market_view as mv
import pattern_engine as pe

DEFAULT_TICKS_PER_CANDLE = 25
SESSION_FRAC = 0.4  # primera fracción de velas = "sesión pasada" -> PDH/PDL
MAX_CANDLES = 1500
MAX_TRADES = 4000
BASE_PRICE = 1.0985
PRICE_STEP = 0.00005


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _r(x, n=6):
    return round(float(x), n)


class MarketSimulator:
    """Agrega velas OHLC, footprint, VP y CVD desde un flujo de ticks sintéticos."""

    def __init__(self, symbol: str = "6E", ticks_per_candle: int = DEFAULT_TICKS_PER_CANDLE,
                 session_frac: float = SESSION_FRAC, normalize_ts: bool = False,
                 base_price: float = BASE_PRICE, price_step: float = PRICE_STEP):
        self.symbol = symbol
        self.ticks_per_candle = max(1, int(ticks_per_candle))
        self.session_frac = _clamp(float(session_frac), 0.1, 0.9)
        self._normalize = bool(normalize_ts)
        self.base_price = float(base_price)
        self.price_step = float(price_step)

        self._lock = threading.Lock()
        self._candles: deque = deque(maxlen=MAX_CANDLES)
        self._cur: Optional[dict] = None
        self._trades: deque = deque(maxlen=MAX_TRADES)
        self._vp: Dict[float, List[float]] = {}  # level -> [vol, bid, ask]
        self._cvd = 0.0
        self._cvd_history: deque = deque(maxlen=3000)
        self._cvd_bucket: Optional[int] = None
        self._total_vol = 0.0
        self._last_price: Optional[float] = None
        self._ts_offset = 0.0
        self.reset()

    def reset(self) -> None:
        """Reinicia todo el estado (usado al cambiar Live <-> Mock)."""
        with self._lock:
            self._candles.clear()
            self._cur = None
            self._trades.clear()
            self._vp.clear()
            self._cvd = 0.0
            self._cvd_history.clear()
            self._cvd_bucket = None
            self._total_vol = 0.0
            self._last_price = None
            self._ts_offset = 0.0

    # ------------------------------------------------------------------
    # Ingesta de ticks (el MISMO stream que alimenta OrderFlowEngine)
    # ------------------------------------------------------------------

    def add_tick(self, price: float, size: int, side: str, ts: float) -> None:
        """Acumula un trade en velas, footprint, VP y CVD (thread-safe)."""
        side_str = side.value if hasattr(side, "value") else side
        with self._lock:
            price = float(price)
            size = int(size)
            if self._last_price is None:
                self._ts_offset = time.time() - float(ts) if self._normalize else 0.0

            if self._cur is None:
                self._cur = {
                    "last_ts": float(ts),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0,
                    "ticks": 0,
                    "cells": {},  # round(price,5) -> [bid, ask]
                }
            c = self._cur
            c["last_ts"] = float(ts)
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
            c["volume"] += size
            c["ticks"] += 1

            level = round(price, 5)
            # Convención market_view / engine: side A = agresor comprador = ask.
            cell = c["cells"].setdefault(level, [0.0, 0.0])  # [bid, ask]
            if side_str == "A":
                cell[1] += size
            else:
                cell[0] += size

            vp_cell = self._vp.setdefault(level, [0.0, 0.0, 0.0])  # [vol, bid, ask]
            vp_cell[0] += size
            if side_str == "A":
                vp_cell[2] += size
            else:
                vp_cell[1] += size

            delta = size if side_str == "A" else -size
            self._cvd += delta
            self._total_vol += size
            self._last_price = price

            bucket = int(ts)
            if self._cvd_bucket is not None and bucket > self._cvd_bucket:
                if not self._cvd_history or self._cvd_history[-1]["time"] != self._cvd_bucket:
                    self._cvd_history.append(
                        {"time": self._cvd_bucket, "value": round(self._cvd, 2)}
                    )
            self._cvd_bucket = bucket

            self._trades.append({
                "ts": float(ts),
                "price": price,
                "size": size,
                "side": "A" if side_str == "A" else "B",
            })

            if c["ticks"] >= self.ticks_per_candle:
                self._close_cur()

    def _close_cur(self) -> None:
        c = self._cur
        c["volume"] = round(c["volume"], 2)
        c["time"] = self._ts(c["last_ts"])
        c.pop("last_ts", None)
        if c["high"] <= c["low"]:
            c["high"] = c["low"] = c["close"] = c["open"]
        self._candles.append(c)
        self._cur = None

    def _ts(self, ts: float) -> int:
        return int(ts + self._ts_offset)

    # ------------------------------------------------------------------
    # Lecturas (contratos idénticos a market_view / endpoints)
    # ------------------------------------------------------------------

    def candles(self, timeframe: str = "M15", bars: int = 300) -> List[dict]:
        """Velas OHLC agregadas del stream (shape to_candle), última en formación."""
        with self._lock:
            out = []
            for c in list(self._candles)[-max(1, min(bars, MAX_CANDLES)):]:
                out.append({
                    "time": c["time"],
                    "open": _r(c["open"]),
                    "high": _r(c["high"]),
                    "low": _r(c["low"]),
                    "close": _r(c["close"]),
                    "volume": c["volume"],
                })
            if self._cur is not None:
                c = self._cur
                out.append({
                    "time": self._ts(c["last_ts"]),
                    "open": _r(c["open"]),
                    "high": _r(c["high"]),
                    "low": _r(c["low"]),
                    "close": _r(c["close"]),
                    "volume": c["volume"],
                })
            return out

    def session_levels(self) -> Tuple[Optional[float], Optional[float]]:
        """PDH/PDL sintético: extremos de la primera `session_frac` de velas."""
        with self._lock:
            return self._session_levels_locked()

    def _session_levels_locked(self) -> Tuple[Optional[float], Optional[float]]:
        closed = list(self._candles)
        if len(closed) < 2:
            return None, None
        n = max(1, int(len(closed) * self.session_frac))
        past = closed[:n]
        pdh = max(c["high"] for c in past)
        pdl = min(c["low"] for c in past)
        return float(pdh), float(pdl)

    def patterns(self, symbol: str = "EURUSD", timeframe: str = "M15",
                 bars: int = 300) -> dict:
        """Análisis SMC (FVG/OB/Sweeps) sobre las velas simuladas + PDH/PDL."""
        candles = self.candles(timeframe, bars)
        pdh, pdl = self.session_levels()
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "candles": candles,
            "pdh": pdh,
            "pdl": pdl,
            "analysis": pe.analyze(candles, pdh, pdl, symbol=symbol.upper(),
                                   timeframe=timeframe.upper()),
        }

    def footprint(self, max_bars: int = 150, rows: int = 12) -> Optional[dict]:
        """Footprint por barra con celdas REALES del tick stream (delta == CVD)."""
        with self._lock:
            source = list(self._candles)[-max(1, min(max_bars, MAX_CANDLES)):]
            if self._cur is not None:
                source = source + [self._cur]
            if not source:
                return None

            bars = []
            step = mv._price_step(source[-1]["close"])
            for c in source:
                high, low, close, open_ = c["high"], c["low"], c["close"], c["open"]
                span = max(high - low, 0.0)
                span = span if high > low else max(step, 0.0)
                if high <= low:
                    levels = [{"price": _r(close), "bid": 0.0, "ask": 0.0, "delta": 0.0}]
                else:
                    n_levels = _clamp(int(math.ceil(span / step)), 6, rows or 24)
                    prices = [low + span * i / (n_levels - 1) for i in range(n_levels)]
                    levels = []
                    for p in prices:
                        cell = c["cells"].get(round(p, 5), (0.0, 0.0))
                        bid, ask = float(cell[0]), float(cell[1])
                        levels.append({
                            "price": _r(p, 5),
                            "bid": _r(bid),
                            "ask": _r(ask),
                            "delta": _r(ask - bid),
                        })
                ask_tot = sum(float(x[1]) for x in c["cells"].values())
                bid_tot = sum(float(x[0]) for x in c["cells"].values())
                bars.append({
                    "time": c.get("time", self._ts(c.get("last_ts", 0))),
                    "open": _r(open_), "high": _r(high), "low": _r(low),
                    "close": _r(close), "vol": round(float(c["volume"]), 2),
                    "delta": _r(ask_tot - bid_tot),
                    "levels": levels,
                })

            return {"source": "synthetic", "mode": "footprint", "step": step, "bars": bars}

    def heatmap(self, max_bars: int = 150, levels: int = 64) -> Optional[dict]:
        """Mapa de calor de liquidez recentrado en las velas simuladas."""
        candles = self.candles("M15", max_bars)
        return mv.liquidity_heatmap(candles, max_bars=max_bars, levels=levels)

    def event_bars(self, bar_type: str = "volbar", param: int = 500) -> Optional[dict]:
        """Barras por evento desde los ticks REALES simulados (volbar/tickbar/renko)."""
        with self._lock:
            ticks = [
                {"time": int(t["ts"]), "price": t["price"], "vol": float(t["size"])}
                for t in self._trades
            ]
            last_price = self._last_price
        if not ticks:
            return None

        mode = (bar_type or "volbar").lower()
        if mode == "renko":
            step = mv._price_step(last_price)
            brick = (float(param) if param and param > 0 else 5.0) * step
            bars = mv._renko(ticks, brick)
        elif mode in ("volbar", "tickbar"):
            bars = mv._aggregate(ticks, mode, int(param))
        else:
            return None
        if not bars:
            return None

        return {"source": "synthetic", "mode": "eventbars", "bar_type": mode.lower(),
                "param": int(param), "step": mv._price_step(last_price), "bars": bars}

    def vp(self, bins: int = 48, poc_pct: float = 70.0) -> Optional[dict]:
        """Volume Profile acumulado del stream (mismo contrato que /volume-profile)."""
        with self._lock:
            if not self._vp or self._total_vol <= 0:
                return None
            keys = sorted(self._vp.keys())
            lo, hi = keys[0], keys[-1]
            if hi <= lo:
                return None

            edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
            bin_vol = [0.0] * bins
            bin_bid = [0.0] * bins
            bin_ask = [0.0] * bins
            for level, cell in self._vp.items():
                idx = min(int((level - lo) / (hi - lo) * bins), bins - 1)
                bin_vol[idx] += cell[0]
                bin_bid[idx] += cell[1]
                bin_ask[idx] += cell[2]

            profile = []
            for i in range(bins):
                c = (edges[i] + edges[i + 1]) / 2.0
                profile.append({
                    "price": _r(c, 6),
                    "vol": round(bin_vol[i], 2),
                    "delta": round(bin_ask[i] - bin_bid[i], 2),
                })
            vol_arr = bin_vol
            poc_idx = max(range(bins), key=lambda i: vol_arr[i])
            poc = (edges[poc_idx] + edges[poc_idx + 1]) / 2.0
            threshold = self._total_vol * (poc_pct / 100.0)
            order = sorted(range(bins), key=lambda i: vol_arr[i], reverse=True)
            cum = 0.0
            in_val = []
            for bi in order:
                cum += vol_arr[bi]
                in_val.append(bi)
                if cum >= threshold:
                    break
            vah = max(((edges[i] + edges[i + 1]) / 2.0) for i in in_val)
            val = min(((edges[i] + edges[i + 1]) / 2.0) for i in in_val)

            return {
                "bins": bins,
                "profile": profile,
                "poc": _r(poc, 6),
                "vah": _r(vah, 6),
                "val": _r(val, 6),
                "source": "sim",
            }

    def cvd_series(self, since: Optional[float] = None) -> List[dict]:
        """Serie CVD acumulada { time, value } del stream simulado."""
        with self._lock:
            if since is None:
                return [dict(p) for p in self._cvd_history]
            cutoff = int(since)
            return [dict(p) for p in self._cvd_history if p["time"] >= cutoff]

    def last_price(self) -> Optional[float]:
        with self._lock:
            return self._last_price

    def state(self) -> dict:
        """Resumen ligero para el chip de fuente / auditoría."""
        with self._lock:
            pdh, pdl = self._session_levels_locked()
            return {
                "symbol": self.symbol,
                "ticks_per_candle": self.ticks_per_candle,
                "candles": len(self._candles) + (1 if self._cur is not None else 0),
                "trades": len(self._trades),
                "last_price": self._last_price,
                "cvd": round(self._cvd, 2),
                "total_vol": round(self._total_vol, 2),
                "pdh": pdh,
                "pdl": pdl,
            }