"""research/sim.py — motor de backtest offline (réplica del gate live).

Replica el kernel del runtime SIN tocar app.py ni MT5:

- El snapshot se reconstruye exactamente como `build_chart_snapshot` (bloque Risk
  Engine): mismo `pattern_engine.analyze`, mismo `risk_engine.setup_score` (pesos
  y killzones de la config), mismo CVD sintético a partir de tick_volume, con COT
  y SMR estáticos (default None = neutro, no penalizan).
- El gate es EXACTAMENTE `watcher.evaluate_gate` (el mismo código live): dirección,
  score, killzone, plan entry/SL/TP y validación de entrada con invalidez estructural
  y R:R mínimo.
- Fill: orden límite activa durante `ttl_bars` velas (setup_ttl_minutes), con modelo
  bid/ask (spread) y slippage adverso en entrada y salida. Convención SL-first:
  dentro de un bar, si toca SL y TP, gana el SL (sin optimismo). Si el precio cruza
  la invalidez estructural mientras la orden sigue activa, se cancela.
- Invariante look-ahead: tooda evaluación en el bar i usa SOLO velas <= ts_i: ventana
  deslizante cerrada en i, PDH/PDL del día anterior ya adjuntos (research.data),
  CVD acumulado desde el inicio de la ventana (espejo de cvd_service._fetch).
  `evaluate_at()` expone el gate de un bar concreto para el test de no-contaminación.

Módulo del pipeline research: NUNCA lo importa el runtime (app/agent/watcher).
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pattern_engine
import risk_engine
import watcher

PIP_DEFAULT = 0.0001
SPREAD_PIPS_DEFAULT = 1.0
SLIPPAGE_PIPS_DEFAULT = 0.0
LOOKBACK_DEFAULT = 300
CVD_BARS_DEFAULT = 30
CVD_DELTA_RATIO = 0.6


# ============================================================
# Config (espejo de la live + opciones de simulación)
# ============================================================

def load_trading_cfg() -> Dict[str, Any]:
    """Config de trading vigente: store (UI) con fallback a strategy.yaml."""
    try:
        import store  # noqa: PLC0415 - import perezoso: store abre sqlite
        tcfg = dict(store.get_trading_config() or {})
    except Exception:  # pragma: no cover - entorno sin DB seed
        tcfg = {}
    if not tcfg:
        try:
            from strategy import get_trading_config  # noqa: PLC0415
            tcfg = dict(get_trading_config() or {})
        except Exception:  # pragma: no cover - defensivo
            tcfg = {}
    return tcfg


def default_cfg(overrides: Optional[Dict[str, Any]] = None,
                trading_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Config plana del backtest: espejo de la live + defaults de simulación.

    Claves que no existen en strategy.yaml (solo sim): spread_pips (coste bid/ask),
    slippage_pips (adverso en entrada y salida), lookback (velas de la ventana
    deslizante), cvd_bars (ventana del CVD sintético), values_pip (tamaño del pip),
    cot/smr (datos estáticos; None = neutro).
    """
    tcfg = dict(trading_cfg) if trading_cfg is not None else load_trading_cfg()
    weights: Dict[str, float] = {}
    try:
        weights = json.loads(tcfg.get("risk_weights") or "{}")
    except (json.JSONDecodeError, TypeError):
        weights = {}
    kz: List[Dict[str, Any]] = []
    try:
        kz = json.loads(tcfg.get("killzones") or "[]")
    except (json.JSONDecodeError, TypeError):
        kz = []

    def _f(key, default):
        try:
            return float(tcfg.get(key) or default)
        except (TypeError, ValueError):
            return default

    cfg: Dict[str, Any] = {
        "min_score": _f("min_score", 70.0),
        "min_rr": _f("min_rr", 2.0),
        "setup_ttl_minutes": _f("setup_ttl_minutes", 20.0),
        "sl_default_pips": _f("sl_default_pips", 12.0),
        "tp_ratio_r": _f("tp_ratio_r", 2.0),
        "risk_weights": weights,
        "killzones": kz,
        "values_pip": _f("values_pip", PIP_DEFAULT),
        "spread_pips": _f("spread_pips", SPREAD_PIPS_DEFAULT),
        "slippage_pips": _f("slippage_pips", SLIPPAGE_PIPS_DEFAULT),
        "lookback": int(_f("lookback", LOOKBACK_DEFAULT)),
        "cvd_bars": int(_f("cvd_bars", CVD_BARS_DEFAULT)),
        "cot": tcfg.get("cot"),
        "smr": tcfg.get("smr"),
    }
    if overrides:
        cfg.update(overrides)
    return cfg


# ============================================================
# CVD sintético (espejo de cvd_service sobre el prefijo)
# ============================================================

def _candle_delta(open_: float, close: float, volume: float,
                  ratio: float = CVD_DELTA_RATIO) -> float:
    if volume <= 0:
        return 0.0
    if close > open_:
        return volume * ratio
    if close < open_:
        return -volume * ratio
    return 0.0


def _cvd_series(window: List[Dict[str, Any]],
                ratio: float = CVD_DELTA_RATIO) -> List[Dict[str, Any]]:
    """Serie CVD sintética {time, value} acumulada desde el inicio de la ventana.

    Espejo de cvd_service._fetch (acumula desde 0 sobre las velas pedidas): el
    baseline de la ventana NUNCA se toma de velas futuras ni de un acumulado global.
    """
    acc = 0.0
    points: List[Dict[str, Any]] = []
    for c in window:
        acc += _candle_delta(c["open"], c["close"], float(c.get("volume") or 0.0), ratio)
        points.append({"time": int(c["time"]), "value": round(acc, 2)})
    return points


# ============================================================
# Réplica del snapshot live (solo bloque Risk Engine)
# ============================================================

def replicate_snapshot(candles: List[Dict[str, Any]], current: float,
                       cfg: Dict[str, Any], ts: int) -> Dict[str, Any]:
    """Reconstruye el snapshot Risk Engine de build_chart_snapshot (sin MT5).

    `candles` = ventana deslizante CERRADA en `ts` (todas <= ts) → sin look-ahead.
    `current` = precio mid (close de la última vela de la ventana). PDH/PDL se toman
    de la vela (los adjunta research.data.with_daily_levels, que solo usa días
    CERRADOS anteriores). Cot/smr llegan desde cfg (None = neutro).
    """
    last = candles[-1]
    patterns = (pattern_engine.analyze(
        candles, last.get("pdh"), last.get("pdl")).get("patterns") or {})
    cvd_bars = max(3, int(cfg.get("cvd_bars", CVD_BARS_DEFAULT)))
    cvd = _cvd_series(candles[-cvd_bars:])
    now = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    weights = cfg.get("risk_weights") or {}
    kz = cfg.get("killzones")
    common = {"cot": cfg.get("cot"), "cvd": cvd,
              "patterns": patterns, "candles": candles, "smr": cfg.get("smr")}
    bull = risk_engine.setup_score(dict(common, direction="BUY"),
                                   weights=weights, killzones=kz, now=now)
    bear = risk_engine.setup_score(dict(common, direction="SELL"),
                                   weights=weights, killzones=kz, now=now)
    return {
        "current_price": current,
        "analysis": {"patterns": patterns},
        "risk_engine": {
            "bull": bull,
            "bear": bear,
            "killzone": bull["components"]["killzone"],
            "regime": bull["regime"],
            "invalidation": {
                "BUY": risk_engine.invalidation_level(patterns, "BUY"),
                "SELL": risk_engine.invalidation_level(patterns, "SELL"),
            },
        },
    }


def evaluate_at(candles: List[Dict[str, Any]], i: int,
                cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Gate determinista en el bar i usando SOLO velas <= ts_i (invariante look-ahead).

    Devuelve el dict de watcher.evaluate_gate o None (sin risk_engine). Clave para
    el test de no-contaminación: añadir velas futuras no cambia este resultado.
    """
    lookback = max(1, int(cfg.get("lookback", LOOKBACK_DEFAULT)))
    window = candles[max(0, i - lookback + 1): i + 1]
    snap = replicate_snapshot(window, float(candles[i]["close"]), cfg,
                              int(candles[i]["time"]))
    gate = watcher.evaluate_gate(snap, cfg, cfg.get("values_pip"))
    if gate is not None:
        side = "bull" if gate["direction"] == "BUY" else "bear"
        comps = (snap.get("risk_engine") or {}).get(side, {}).get("components")
        gate["components"] = dict(comps or {})
    return gate


# ============================================================
# Motor (BarBacktest)
# ============================================================

def _tf_seconds(candles: List[Dict[str, Any]], fallback: float = 900.0) -> float:
    diffs = [int(candles[k]["time"]) - int(candles[k - 1]["time"])
             for k in range(1, len(candles))]
    diffs = [d for d in diffs if d > 0]
    return statistics.median(diffs) if diffs else fallback


class BarBacktest:
    """Simulador vela a vela sobre velas con PDH/PDL adjuntos.

    Entrada: `candles` con research.data.with_daily_levels (claves pdh/pdl), y un
    `cfg` de sim (default_cfg()). La salida `run()` lista los trades (dicts) en orden
    de señal, incluyendo los aprobados que nunca se llenaron (EXPIRED/CANCELLED).
    """

    def __init__(self, candles: List[Dict[str, Any]],
                 cfg: Optional[Dict[str, Any]] = None,
                 tf_sec: Optional[float] = None):
        if not candles:
            raise ValueError("Sin velas para simular.")
        self.candles = sorted(candles, key=lambda c: int(c["time"]))
        if "pdh" not in self.candles[0] or "pdl" not in self.candles[0]:
            raise ValueError(
                "Velas sin PDH/PDL: usa research.data.with_daily_levels o load_dataset."
            )
        self.cfg = cfg if cfg is not None else default_cfg()
        self.tf_sec = float(tf_sec) if tf_sec else _tf_seconds(self.candles)
        self.pip = float(self.cfg.get("values_pip") or PIP_DEFAULT)
        self.spread = float(self.cfg.get("spread_pips") or 0.0) * self.pip
        self.slip = float(self.cfg.get("slippage_pips") or 0.0) * self.pip

    # -- helpers de ejecución ------------------------------------------------

    def _ttl_bars(self) -> int:
        ttl_min = float(self.cfg.get("setup_ttl_minutes") or 20.0)
        return max(1, math.ceil(ttl_min * 60.0 / self.tf_sec))

    def _bid(self, price: float) -> float:
        return price - self.spread / 2.0

    def _ask(self, price: float) -> float:
        return price + self.spread / 2.0

    def _entry_exec(self, direction: str, level: float) -> float:
        # BUY compra a ask; SELL vende a bid; slippage adverso encima.
        if direction == "BUY":
            return self._ask(level) + self.slip
        return self._bid(level) - self.slip

    def _exit_exec(self, direction: str, level: float) -> float:
        # BUY cierra a bid; SELL cierra a ask.
        if direction == "BUY":
            return self._bid(level) - self.slip
        return self._ask(level) + self.slip

    # -- nuevo setup pendiente ------------------------------------------------

    def _new_pending(self, gate: Dict[str, Any], ts: int, ttl_bars: int,
                     n_bars: int = 0) -> Dict[str, Any]:
        return {
            "signal": {
                "signal_ts": int(ts),
                "direction": gate["direction"],
                "score": gate["score"],
                "verdict": gate["verdict"],
                "killzone": gate.get("killzone_name") or "",
                "entry_kind": gate.get("entry_kind") or "market",
                "entry": gate["entry"],
                "sl": gate["sl"],
                "tp": gate["tp"],
                "invalidate": gate.get("invalidate_level"),
                "current_price": gate.get("current_price"),
                "reasons": list(gate.get("reasons") or []),
                "components": dict(gate.get("components") or {}),
            },
            "ttl_left": int(ttl_bars),
            "n_bars": int(n_bars),
            "filled": False,
            "done": False,
        }

    def _advance_pending(self, pending: Dict[str, Any], bar: Dict[str, Any]) -> None:
        """Un bar de vida de la orden pendiente: invalidez -> fill -> TTL."""
        sig = pending["signal"]
        direction = sig["direction"]
        inval = sig.get("invalidate")
        # 1) Cruce de invalidez estructural mientras la orden sigue viva.
        bar_bid_low = self._bid(float(bar["low"]))
        bar_ask_high = self._ask(float(bar["high"]))
        if inval is not None:
            if direction == "BUY" and bar_bid_low <= float(inval):
                pending["done"], pending["result"] = True, "INVALIDATED"
                return
            if direction == "SELL" and bar_ask_high >= float(inval):
                pending["done"], pending["result"] = True, "INVALIDATED"
                return
        # 2) Fill (toca el nivel con la mecha del lado correspondiente).
        if direction == "BUY" and bar_bid_low <= float(sig["entry"]):
            pending["filled"] = True
            pending["entry_exec"] = self._entry_exec(direction, float(sig["entry"]))
            pending["fill_ts"] = int(bar["time"])
            pending["n_bars"] += 1
            return
        if direction == "SELL" and bar_ask_high >= float(sig["entry"]):
            pending["filled"] = True
            pending["entry_exec"] = self._entry_exec(direction, float(sig["entry"]))
            pending["fill_ts"] = int(bar["time"])
            pending["n_bars"] += 1
            return
        # 3) TTL: se acaban los bares de vigencia -> expira.
        pending["n_bars"] += 1
        if pending["ttl_left"] <= 1:
            pending["done"], pending["result"] = True, "TTL_EXPIRY"
        else:
            pending["ttl_left"] -= 1

    # -- posición abierta -----------------------------------------------------

    def _open_position(self, pending: Dict[str, Any], bar: Dict[str, Any]) -> Dict[str, Any]:
        sig = pending["signal"]
        return {
            "signal": sig,
            "fill_ts": pending["fill_ts"],
            "entry_price": pending["entry_exec"],
            "bars_pending": int(pending["n_bars"]),
            "bars_held": 0,
            "closed": False,
        }

    def _check_position_exit(self, position: Dict[str, Any], bar: Dict[str, Any]) -> None:
        if position["closed"]:
            return
        sig = position["signal"]
        direction = sig["direction"]
        if direction == "BUY":
            bid_low = self._bid(float(bar["low"]))
            bid_high = self._bid(float(bar["high"]))
            # SL-first: dentro de una vela, si toca SL y TP gana el SL.
            if bid_low <= float(sig["sl"]):
                position["exit_path"], position["exit_price"] = "SL", self._exit_exec("BUY", float(sig["sl"]))
            elif bid_high >= float(sig["tp"]):
                position["exit_path"], position["exit_price"] = "TP", self._exit_exec("BUY", float(sig["tp"]))
            else:
                position["bars_held"] += 1
                return
        else:
            ask_high = self._ask(float(bar["high"]))
            ask_low = self._ask(float(bar["low"]))
            if ask_high >= float(sig["sl"]):
                position["exit_path"], position["exit_price"] = "SL", self._exit_exec("SELL", float(sig["sl"]))
            elif ask_low <= float(sig["tp"]):
                position["exit_path"], position["exit_price"] = "TP", self._exit_exec("SELL", float(sig["tp"]))
            else:
                position["bars_held"] += 1
                return
        position["exit_ts"] = int(bar["time"])
        position["closed"] = True

    # -- ensamblado del trade ------------------------------------------------

    def _trade_dict(self, entity: Dict[str, Any], status: str, reason: str,
                    trade_id: int) -> Dict[str, Any]:
        sig = entity["signal"]
        direction = sig["direction"]
        entry = entity.get("entry_price") if entity.get("entry_price") is not None else None
        exit_ = entity.get("exit_price")
        pnl_pips = pnl_r = None
        if entry is not None and exit_ is not None:
            dist_sl = abs(float(entry) - float(sig["sl"]))
            pnl_pips = (float(exit_) - float(entry)) / self.pip * (1.0 if direction == "BUY" else -1.0)
            pnl_r = (float(exit_) - float(entry)) / dist_sl * (1.0 if direction == "BUY" else -1.0)
        return {
            "id": int(trade_id),
            "signal_ts": int(sig["signal_ts"]),
            "fill_ts": entity.get("fill_ts"),
            "exit_ts": entity.get("exit_ts"),
            "direction": direction,
            "score": sig["score"],
            "verdict": sig["verdict"],
            "killzone": sig["killzone"],
            "entry_kind": sig["entry_kind"],
            "plan": {"entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
                     "invalidate": sig.get("invalidate")},
            "entry_price": entry,
            "exit_price": exit_,
            "status": status,
            "exit_reason": reason,
            "bars_pending": int((entity.get("bars_pending")
                                 if entity.get("bars_pending") is not None
                                 else entity.get("n_bars")) or 0),
            "bars_held": int(entity.get("bars_held") or 0) if entry is not None else None,
            "pnl_pips": round(pnl_pips, 2) if pnl_pips is not None else None,
            "pnl_r": round(pnl_r, 4) if pnl_r is not None else None,
            "reasons": list(sig.get("reasons") or []),
            "signal_components": dict(sig.get("components") or {}),
        }

    # -- ejecución --------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        candles = self.candles
        n = len(candles)
        lookback = max(1, int(self.cfg.get("lookback", LOOKBACK_DEFAULT)))
        # Arranque: con dataset completo usamos ventanas de `lookback` cerradas;
        # con dataset corto simulamos desde el primer prefijo usable (~5 velas,
        # mínimo que necesita regime/cvd del kernel).
        start = (lookback - 1) if n >= lookback else max(1, min(5, n - 1))
        ttl_bars = self._ttl_bars()
        trades: List[Dict[str, Any]] = []
        pending: Optional[Dict[str, Any]] = None
        position: Optional[Dict[str, Any]] = None

        for i in range(start, n):
            bar = candles[i]

            if position is not None:
                self._check_position_exit(position, bar)
                if position["closed"]:
                    trades.append(self._trade_dict(position, "WIN" if (
                        position["exit_path"] == "TP") else "LOSS",
                        position["exit_path"], len(trades) + 1))
                    position = None
                continue

            if pending is not None:
                self._advance_pending(pending, bar)
                if pending["filled"]:
                    position = self._open_position(pending, bar)
                    pending = None
                    # SL/TP en la MISMA vela del fill (convención SL-first).
                    self._check_position_exit(position, bar)
                    if position["closed"]:
                        trades.append(self._trade_dict(
                            position, "WIN" if position["exit_path"] == "TP" else "LOSS",
                            position["exit_path"], len(trades) + 1))
                        position = None
                    continue
                if pending["done"]:
                    pip_kind = pending["result"]
                    status = ("CANCELLED" if pip_kind == "INVALIDATED" else "EXPIRED")
                    trades.append(self._trade_dict(pending, status, pip_kind,
                                                   len(trades) + 1))
                    pending = None
                continue

            gate = evaluate_at(candles, i, self.cfg)
            if gate is None or not gate.get("approved"):
                continue
            pending = self._new_pending(gate, int(candles[i]["time"]), ttl_bars)

        # Fin del histórico: forzar cierre de lo que sigue abierto.
        if position is not None:
            trades.append(self._trade_dict(position, "OPEN", "END_OF_DATA",
                                           len(trades) + 1))
        elif pending is not None:
            trades.append(self._trade_dict(pending,
                                           "PENDING", "END_OF_DATA",
                                           len(trades) + 1))

        return {
            "trades": trades,
            "cfg": {k: v for k, v in self.cfg.items() if k not in ("cot", "smr")},
            "n_bars": n,
            "tf_sec": round(self.tf_sec, 1),
            "ttl_bars": ttl_bars,
            "pip": self.pip,
            "spread": self.spread,
            "slip": self.slip,
            "start_ts": int(candles[start]["time"]),
            "end_ts": int(candles[-1]["time"]),
        }