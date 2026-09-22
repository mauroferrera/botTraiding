"""Watcher de setups (bot a la escucha).

Escanea los símbolos/timeframes configurados en strategy.yaml (sección
`watcher:`) cada `scan_interval_sec` y evalúa el MISMO gate determinista de
risk_engine que `/api/chart/setup-eval` (sin LLM). Cuando detecta un setup
válido lo propaga por WebSocket/UI; con auto_execute activado, ejecuta además
la orden de mercado usando el executor que le inyecta app.py.

Este módulo NO importa app.py (evita ciclos): las dependencias de efecto
lateral (snapshot_builder, executor, broadcast y el acceso a store) se inyectan.
`evaluate_gate`, `decide_transition` y `scan_once` son puras y testeables con
fakes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import risk_engine
import store

log = logging.getLogger("watcher")

DEFAULT_TIMEFRAME = "M15"


# ============================================================
# Gate determinista (mismo criterio que api_chart_setup_eval)
# ============================================================

def _nearest_entry_zone(patterns, price, direction, max_span=0.01):
    """Elige la zona (FVG/OB) más cercana donde entrar.

    - BUY  -> la zona que queda POR DEBAJO del precio (rebote alcista).
    - SELL -> la zona que queda POR ENCIMA (rechazo bajista).

    Devuelve {"price", "kind", "top", "bottom"} o None. El 'entry' se toma del
    borde que mira al precio (BUY: bottom, SELL: top)."""
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


def evaluate_gate(snapshot: Dict[str, Any], cfg: Dict[str, Any],
                  pip_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Calcula dirección, score, killzone, plan entry/SL/TP y el gate de aprobación.

    Devuelve None si el snapshot no trae risk_engine (p. ej. sin datos MT5).
    """
    re_ = snapshot.get("risk_engine") or {}
    sides = []
    for direction, score_obj in (("BUY", re_.get("bull")), ("SELL", re_.get("bear"))):
        if score_obj:
            sides.append((direction, score_obj))
    if not sides:
        return None

    direction, best = max(sides, key=lambda s: s[1].get("score") or 0)
    score = best.get("score") or 0
    verdict = best.get("verdict") or ""
    killzone = best.get("components", {}).get("killzone", {})
    in_killzone = bool(killzone.get("in_killzone"))
    kz_name = killzone.get("name") or ""

    invalidation = (re_.get("invalidation") or {}).get(direction)
    current = snapshot.get("current_price")
    patterns = ((snapshot.get("analysis") or {}).get("patterns")) or {}
    min_score = float(cfg.get("min_score") or 80.0)

    zone = _nearest_entry_zone(patterns, current, direction) if current is not None else None
    entry = zone["price"] if zone else current
    entry_kind = zone["kind"] if zone else "market"

    sl_pips = float(cfg.get("sl_default_pips") or 15.0)
    tp_r = float(cfg.get("tp_ratio_r") or 2.0)
    if pip_price is None:
        pip_price = 0.0001  # forex 5 dígitos (EURUSD); app inyecta el real si aplica
    sl_dist = sl_pips * float(pip_price)
    if entry is None:
        sl = tp = None
    else:
        if direction == "BUY":
            sl = round(entry - sl_dist, 6)
            tp = round(entry + sl_dist * tp_r, 6)
        else:
            sl = round(entry + sl_dist, 6)
            tp = round(entry - sl_dist * tp_r, 6)

    val = None
    try:
        val = risk_engine.validate_entry(
            entry=entry, sl=sl, target=tp, direction=direction,
            current_price=current, invalidate_level=invalidation, cfg=cfg,
        )
    except Exception as exc:  # pragma: no cover - defensivo
        val = {"approved": False, "rejected": True, "reasons": [f"risk_engine error: {exc}"]}

    reasons: List[str] = []
    approved = bool(score >= min_score and in_killzone and val and val.get("approved"))
    if score < min_score:
        reasons.append(f"Score {score:.1f} < umbral {min_score:.0f}.")
    if not in_killzone:
        reasons.append("Fuera de killzone.")
    if val and val.get("reasons"):
        reasons.extend(val["reasons"])

    return {
        "direction": direction,
        "score": score,
        "verdict": verdict,
        "killzone_active": in_killzone,
        "killzone_name": kz_name,
        "current_price": current,
        "entry": entry,
        "entry_kind": entry_kind,
        "sl": sl,
        "tp": tp,
        "invalidate_level": invalidation,
        "approved": approved,
        "reasons": reasons,
    }


# ============================================================
# Máquina de estados del setup (dedup + ciclo de alerta)
# ============================================================

def _row_value(row, key, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def decide_transition(prev_row, gate_ok: bool, now: Optional[datetime] = None,
                      ttl_sec: float = 2700.0) -> Optional[str]:
    """Transición de estado para {symbol, timeframe}.

    Estados: None (sin ciclo) -> "active" -> "closed" o "executed".
    Devuelve "new" | "active" (silent) | "closed" | None.
    """
    now = now or datetime.now(timezone.utc)
    status = (_row_value(prev_row, "status") or "").lower()

    # Sin ciclo previo: solo importa si el gate está aprobado ahora.
    if status in ("", "none", "closed", "expired", "invalidated"):
        return "active" if gate_ok else None

    # Ciclo activo: mientras siga válido, no re-avisar (dedup). Si muere o
    # expira el TTL (created_at), se cierra.
    if status == "active":
        created = _parse_ts(_row_value(prev_row, "created_at"))
        expired = created is not None and ttl_sec > 0 and (
            now - created).total_seconds() > ttl_sec
        if not gate_ok or expired:
            return "closed"
        return None  # silencioso: mismo setup, ya avisado

    # Setup bloqueado por noticia: dedup como "active" pero sin re-notificar.
    # Se cierra cuando la señal muere o expira (nunca revive en mitad de la
    # ventana de blackout ya registrada).
    if status == "news_ignored":
        created = _parse_ts(_row_value(prev_row, "created_at"))
        expired = created is not None and ttl_sec > 0 and (
            now - created).total_seconds() > ttl_sec
        return "closed" if not gate_ok or expired else None

    # Ya ejecutado: espera a que la señal muera para cerrar el ciclo y permitir
    # un ciclo nuevo (nunca re-ejecuta mientras el setup siga vivo).
    if status == "executed":
        return "closed" if not gate_ok else None

    return None


# ============================================================
# Scan (orquestación pura con dependencias inyectadas)
# ============================================================

def _default_io() -> Dict[str, Callable]:
    return {
        "get_watcher_config": store.get_watcher_config,
        "get_trading_config": store.get_trading_config,
        "get_setup_state": store.get_setup_state,
        "new_setup_state": store.new_setup_state,
        "update_setup_state": store.update_setup_state,
        "get_auto_execute": store.get_watcher_auto_execute,
        "log_setup": store.log_setup,
    }


def _emit(broadcast, event_name: str, payload: Dict[str, Any]) -> None:
    if broadcast is None:
        return
    try:
        res = broadcast({"event": event_name, **payload})
    except Exception:
        return
    # Si el wiring devuelve un coroutine sin programar (p. ej. alguien pasa
    # manager.broadcast directo), lo programamos en el loop en curso.
    if asyncio.iscoroutine(res):
        try:
            asyncio.get_event_loop().create_task(res)
        except RuntimeError:  # pragma: no cover - sin loop en curso en tests
            pass


def scan_once(snapshot_builder: Callable,
              executor: Optional[Callable] = None,
              broadcast: Optional[Callable] = None,
              now: Optional[datetime] = None,
              auto_execute: Optional[bool] = None,
              io: Optional[Dict[str, Callable]] = None) -> List[Dict[str, Any]]:
    """Un ciclo de escaneo: construye snapshots, evalúa el gate, decide la
    transición y propaga/ejecuta. Devuelve la lista de eventos emitidos."""
    io = {**_default_io(), **(io or {})}
    wcfg = io["get_watcher_config"]() or {}
    tcfg = io["get_trading_config"]() or {}
    ttl_sec = float(wcfg.get("dedup_ttl_sec") or 2700.0)
    auto_exec = (auto_execute if auto_execute is not None
                 else bool(io["get_auto_execute"]()))
    sl_default = float(tcfg.get("sl_default_pips") or 15.0)
    tp_ratio = float(tcfg.get("tp_ratio_r") or 2.0)

    events: List[Dict[str, Any]] = []
    for sc in wcfg.get("symbols") or []:
        symbol = str(sc.get("symbol") or "EURUSD").upper()
        timeframe = str(sc.get("timeframe") or DEFAULT_TIMEFRAME).upper()

        try:
            snapshot = snapshot_builder(symbol, timeframe)
        except Exception as exc:
            ev = {"event": "error", "symbol": symbol, "timeframe": timeframe,
                  "error": str(exc)}
            events.append(ev)
            continue

        gate = evaluate_gate(snapshot, tcfg)
        if gate is None:
            continue

        prev = io["get_setup_state"](symbol, timeframe)

        base = {"symbol": symbol, "timeframe": timeframe,
                "direction": gate["direction"], "score": gate["score"]}

        # Gate de noticias (News Blackout): con un setup aprobado pero en ventana
        # de noticia, se registra "Ignorado por Noticia" y NO se notifica ni se
        # ejecuta. Dedup por estado para no re-log cada ciclo de escaneo.
        news = None
        news_gate = io.get("news_gate")
        if gate["approved"] and news_gate is not None:
            try:
                news = news_gate()
            except Exception as exc:  # pragma: no cover - defensivo
                news = {"ok": True, "fail_open": True, "reason": str(exc), "event": None}
        prev_status = (_row_value(prev, "status") or "").lower()

        if gate["approved"] and news is not None and not news.get("ok"):
            if prev_status != "news_ignored":
                try:
                    io["log_setup"]({
                        "symbol": symbol, "timeframe": timeframe,
                        "direction": gate["direction"],
                        "verdict": "IGNORED_NEWS",
                        "score": gate["score"],
                        "breakdown": {"gate": gate, "news": news},
                        "entry": gate["entry"], "sl": gate["sl"], "target": gate["tp"],
                        "invalidate_level": gate.get("invalidate_level"),
                        "validated": False,
                        "reject_reasons": [
                            "BLOCKED_BY_NEWS_GATE: " + str(news.get("reason"))
                        ],
                        "risk_state": {}, "trade_result": {},
                    })
                except Exception:  # pragma: no cover - nunca romper el scan
                    pass
                io["new_setup_state"](symbol, timeframe, gate=gate,
                                      status="news_ignored", notified=False)
                payload = {**base, "killzone": gate["killzone_name"],
                           "reason": str(news.get("reason")),
                           "news": news.get("event")}
                events.append({"event": "ignored_news", **payload})
                _emit(broadcast, "strategy_setup", {**payload, "type": "ignored_news"})
            continue

        transition = decide_transition(prev, gate["approved"], now=now, ttl_sec=ttl_sec)

        base = {"symbol": symbol, "timeframe": timeframe,
                "direction": gate["direction"], "score": gate["score"],
                "verdict": gate["verdict"], "entry": gate["entry"],
                "sl": gate["sl"], "tp": gate["tp"]}

        if transition == "active":
            io["new_setup_state"](symbol, timeframe, gate=gate,
                                  status="active", notified=True)
            payload = {**base, "killzone": gate["killzone_name"],
                       "reason": "; ".join(gate["reasons"])}
            events.append({"event": "new", **payload})
            _emit(broadcast, "strategy_setup", {**payload, "type": "new"})

            if auto_exec and executor is not None:
                try:
                    res = executor(symbol, gate["direction"],
                                   sl_pips=sl_default, tp_pips=sl_default * tp_ratio)
                except Exception as exc:  # pragma: no cover - defensivo
                    res = {"ok": False, "error": str(exc)}
                if res and res.get("ok"):
                    io["update_setup_state"](symbol, timeframe,
                                             status="executed", auto_executed=True)
                    ex_ev = {"event": "executed", "symbol": symbol,
                             "timeframe": timeframe, "direction": gate["direction"],
                             "ticket": res.get("ticket"), "price": res.get("price"),
                             "volume": res.get("volume"), "filling": res.get("filling")}
                    events.append(ex_ev)
                    _emit(broadcast, "strategy_setup", {**ex_ev, "type": "executed"})
                else:
                    ex_ev = {"event": "executed_error", "symbol": symbol,
                             "timeframe": timeframe, "direction": gate["direction"],
                             "error": (res or {}).get("error") or "Error desconocido al ejecutar."}
                    events.append(ex_ev)
                    _emit(broadcast, "strategy_setup", {**ex_ev, "type": "executed_error"})

        elif transition == "closed":
            io["update_setup_state"](symbol, timeframe, status="closed")
            payload = {**base, "reason": "Setup ya no es válido o expiró (TTL)."}
            events.append({"event": "closed", **payload})
            _emit(broadcast, "strategy_setup", {**payload, "type": "closed"})

    return events


# ============================================================
# Bucle asíncrono + estado para la UI
# ============================================================

async def strategy_watcher(snapshot_builder: Optional[Callable] = None,
                           executor: Optional[Callable] = None,
                           broadcast: Optional[Callable] = None,
                           io: Optional[Dict[str, Callable]] = None):
    """Bucle del bot a la escucha. Relee la config cada ciclo (la caché de
    strategy.yaml se invalida con save()) y respeta 'watcher.enabled'."""
    while True:
        try:
            wcfg = store.get_watcher_config()
            if wcfg.get("enabled") and snapshot_builder is not None:
                scan_once(snapshot_builder, executor=executor, broadcast=broadcast, io=io)
        except Exception:
            log.exception("error en el ciclo del watcher")
        interval = float((store.get_watcher_config() or {}).get("scan_interval_sec") or 60.0)
        await asyncio.sleep(max(5.0, interval))


def watcher_status() -> Dict[str, Any]:
    """Estado del watcher para /api/watcher/status (config + estados vigentes)."""
    wcfg = store.get_watcher_config() or {}
    symbols = wcfg.get("symbols") or []
    return {
        "enabled": bool(wcfg.get("enabled")),
        "scan_interval_sec": wcfg.get("scan_interval_sec"),
        "auto_execute_conf": bool(wcfg.get("auto_execute")),
        "auto_execute": store.get_watcher_auto_execute(),
        "dedup_ttl_sec": wcfg.get("dedup_ttl_sec"),
        "symbols": symbols,
        "states": [store.get_setup_state(s.get("symbol"), s.get("timeframe"))
                   for s in symbols],
        "min_score": store.get_trading_config().get("min_score"),
    }