"""Layer 4: Watcher (bot a la escucha).

Prueba el módulo watcher.py con dependencias inyectadas (sin MT5 ni HTTP):

  - evaluate_gate: gate determinista sobre el snapshot (mismo criterio que
    /api/chart/setup-eval, pero sin LLM ni servidor).
  - decide_transition: máquina de estados (dedup + ciclo de alerta).
  - scan_once: orquestación con fakes (snapshot_builder, executor, broadcast,
    y acceso a store en memoria). Verifica dedup (1 alerta por ciclo), cierre
    por señal muerta, auto_execute on/off y fallo de ejecución.
  - store: persistencia del toggle auto_execute y del estado por símbolo
    (setup_state / watcher_settings) contra una DB temporal.

Run:  python -m pytest tests/test_watcher.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import store
import watcher
from conftest import make_snapshot_from_scenario, load_scenario

SNAP_CFG = {"sl_default_pips": 15, "tp_ratio_r": 2.0, "min_rr": 2.0,
            "setup_ttl_minutes": 45, "min_score": 80.0}

NOW = datetime(2026, 9, 7, 14, 15, 0, tzinfo=timezone.utc)


def approved_snapshot():
    return make_snapshot_from_scenario(
        load_scenario("sweep_valid_confluence"), current_price=1.1040
    )


def rejected_snapshot():
    return make_snapshot_from_scenario(
        load_scenario("trap_liquidity"), current_price=1.1040
    )


# ---------------------------------------------------------------------------
# In-memory store fake (mismo contrato que store.* usado por scan_once)
# ---------------------------------------------------------------------------

class FakeStoreIO:
    def __init__(self, auto_execute=False, wcfg=None):
        self.state = {}
        self.auto_execute = auto_execute
        self.wcfg = wcfg or {
            "enabled": True, "scan_interval_sec": 60.0, "auto_execute": False,
            "dedup_ttl_sec": 2700.0,
            "symbols": [{"symbol": "EURUSD", "timeframe": "M15"}],
        }
        self.tcfg = dict(SNAP_CFG)

    def io(self):
        return {
            "get_watcher_config": lambda: self.wcfg,
            "get_trading_config": lambda: dict(self.tcfg),
            "get_setup_state": lambda sym, tf="M15": self._row(sym, tf),
            "new_setup_state": self._new,
            "update_setup_state": self._update,
            "get_auto_execute": lambda: self.auto_execute,
        }

    def _key(self, sym, tf):
        return (str(sym).upper(), str(tf or "M15").upper())

    def _row(self, sym, tf="M15"):
        row = self.state.get(self._key(sym, tf))
        return dict(row) if row else None

    def _new(self, sym, tf, gate=None, status="active", notified=True):
        g = gate or {}
        self.state[self._key(sym, tf)] = {
            "symbol": str(sym).upper(), "timeframe": str(tf).upper(),
            "status": status, "direction": g.get("direction"),
            "score": g.get("score"), "verdict": g.get("verdict"),
            "entry": g.get("entry"), "sl": g.get("sl"), "target": g.get("tp"),
            "invalidate_level": g.get("invalidate_level"),
            "created_at": "2026-09-07T14:15:00+00:00",
            "updated_at": "2026-09-07T14:15:00+00:00",
        }

    def _update(self, sym, tf, **fields):
        key = self._key(sym, tf)
        if key not in self.state:
            self.state[key] = {
                "symbol": str(sym).upper(), "timeframe": str(tf).upper(),
                "status": fields.get("status", "active"),
                "created_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
            }
        for k, v in fields.items():
            self.state[key][k] = v
        self.state[key]["updated_at"] = "2026-09-07T14:16:00+00:00"


def make_broadcaster():
    msgs = []

    def broadcast(payload):
        msgs.append(payload)

    return msgs, broadcast


# ---------------------------------------------------------------------------
# evaluate_gate
# ---------------------------------------------------------------------------

def test_evaluate_gate_none_without_risk_engine():
    assert watcher.evaluate_gate({"current_price": 1.0, "analysis": {}}, SNAP_CFG) is None


def test_evaluate_gate_approved_confluence():
    gate = watcher.evaluate_gate(approved_snapshot(), SNAP_CFG)
    assert gate is not None
    assert gate["approved"] is True
    assert gate["direction"] == "BUY"
    assert gate["killzone_active"] is True
    assert gate["killzone_name"] == "Nueva York"
    assert None not in (gate["entry"], gate["sl"], gate["tp"])


def test_evaluate_gate_reject_low_score():
    gate = watcher.evaluate_gate(rejected_snapshot(), SNAP_CFG)
    assert gate is not None
    assert gate["approved"] is False
    assert any("score" in r.lower() for r in gate["reasons"])


def test_evaluate_gate_reject_outside_killzone_despite_high_score():
    snap = approved_snapshot()
    snap["risk_engine"]["bull"]["components"]["killzone"]["in_killzone"] = False
    snap["risk_engine"]["bear"]["components"]["killzone"]["in_killzone"] = False
    gate = watcher.evaluate_gate(snap, SNAP_CFG)
    assert gate["approved"] is False
    assert any("killzone" in r.lower() for r in gate["reasons"])


# ---------------------------------------------------------------------------
# decide_transition (máquina de estados)
# ---------------------------------------------------------------------------

def active_row(created_at=NOW):
    return {"symbol": "EURUSD", "timeframe": "M15", "status": "active",
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat()}


def test_decide_transition_matrix():
    # Sin ciclo previo
    assert watcher.decide_transition(None, True, now=NOW) == "active"
    assert watcher.decide_transition(None, False, now=NOW) is None
    # Activo
    assert watcher.decide_transition(active_row(), True, now=NOW) is None      # silent/dedup
    assert watcher.decide_transition(active_row(), False, now=NOW) == "closed"  # señal muerta
    # Activo expirado por TTL aunque el gate siga aprobado
    old = active_row(created_at=NOW - timedelta(seconds=3600))
    assert watcher.decide_transition(old, True, now=NOW, ttl_sec=2700) == "closed"
    # Ejecutado: no re-ejecuta mientras la señal siga viva; cierra al morir
    exec_row = {**active_row(), "status": "executed"}
    assert watcher.decide_transition(exec_row, True, now=NOW) is None
    assert watcher.decide_transition(exec_row, False, now=NOW) == "closed"
    # Cerrado: recuperación -> nuevo ciclo
    closed_row = {**active_row(), "status": "closed"}
    assert watcher.decide_transition(closed_row, True, now=NOW) == "active"
    assert watcher.decide_transition(closed_row, False, now=NOW) is None
    # Ignorado por noticia: dedup silencioso mientras vive, cierre al morir
    news_row = {**active_row(), "status": "news_ignored"}
    assert watcher.decide_transition(news_row, True, now=NOW) is None
    assert watcher.decide_transition(news_row, False, now=NOW) == "closed"


def blocked_news_gate(reason="Nonfarm Payrolls en curso"):
    return {"ok": False, "reason": reason,
            "event": {"title": "Nonfarm Payrolls", "impact": "red"}}


def test_scan_once_news_blackout_ignora_y_hace_dedup():
    fake = FakeStoreIO()
    logs = []
    io = fake.io()
    io["news_gate"] = lambda: blocked_news_gate()
    io["log_setup"] = lambda entry: logs.append(entry)
    msgs, broadcast = make_broadcaster()
    calls = []

    def executor(*args, **kwargs):
        calls.append(1)

    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: approved_snapshot(),
        executor=executor, broadcast=broadcast, now=NOW, io=io,
    )
    ig = [e for e in events if e["event"] == "ignored_news"]
    assert len(ig) == 1
    assert ig[0]["direction"] == "BUY"
    assert "Nonfarm" in ig[0]["reason"]
    # Sin ejecución ni alerta de setup normal
    assert calls == []
    assert not [e for e in events if e["event"] == "new"]
    assert not [e for e in events if e["event"] == "executed"]
    # Registro inmutable en setup_log
    assert len(logs) == 1
    assert logs[0]["verdict"] == "IGNORED_NEWS"
    assert logs[0]["validated"] is False
    assert logs[0]["reject_reasons"][0].startswith("BLOCKED_BY_NEWS_GATE:")
    # Estado del watcher marcado para dedup
    assert fake._row("EURUSD", "M15")["status"] == "news_ignored"

    # Segundo ciclo durante la misma ventana: sin re-log ni re-evento
    events2 = watcher.scan_once(
        snapshot_builder=lambda s, tf: approved_snapshot(),
        executor=executor, broadcast=broadcast, now=NOW, io=io,
    )
    assert not [e for e in events2 if e["event"] == "ignored_news"]
    assert len(logs) == 1
    assert calls == []


def test_scan_once_news_blackout_se_cierra_al_morir_la_senal():
    fake = FakeStoreIO()
    io = fake.io()
    io["news_gate"] = lambda: blocked_news_gate()
    fake._new("EURUSD", "M15", gate={"direction": "BUY", "score": 90.0,
               "entry": 1.1020, "sl": 1.1005, "tp": 1.1050}, status="news_ignored")
    msgs, broadcast = make_broadcaster()
    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: rejected_snapshot(),
        broadcast=broadcast, now=NOW, io=io,
    )
    closed = [e for e in events if e["event"] == "closed"]
    assert len(closed) == 1
    assert fake._row("EURUSD", "M15")["status"] == "closed"
    assert len([m for m in msgs if m["type"] == "closed"]) == 1


# ---------------------------------------------------------------------------
# scan_once
# ---------------------------------------------------------------------------

def test_scan_once_dedup_1_alerta_por_ciclo():
    fake = FakeStoreIO()
    msgs, broadcast = make_broadcaster()
    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: approved_snapshot(),
        broadcast=broadcast, now=NOW, io=fake.io(),
    )
    news = [e for e in events if e["event"] == "new"]
    assert len(news) == 1
    assert news[0]["direction"] == "BUY"
    assert fake._row("EURUSD", "M15")["status"] == "active"
    assert len([m for m in msgs if m["type"] == "new"]) == 1

    # Segundo ciclo: mismo setup activo y válido -> sin nueva alerta (dedup)
    events2 = watcher.scan_once(
        snapshot_builder=lambda s, tf: approved_snapshot(),
        broadcast=broadcast, now=NOW, io=fake.io(),
    )
    assert not [e for e in events2 if e["event"] == "new"]
    assert len([m for m in msgs if m["type"] == "new"]) == 1


def test_scan_once_reject_sin_alerta():
    fake = FakeStoreIO()
    msgs, broadcast = make_broadcaster()
    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: rejected_snapshot(),
        broadcast=broadcast, now=NOW, io=fake.io(),
    )
    assert events == []
    assert msgs == []
    assert fake.state == {}


def test_scan_once_active_a_closed():
    fake = FakeStoreIO()
    fake._new("EURUSD", "M15", gate={"direction": "BUY", "score": 90.0, "entry": 1.1020,
                "sl": 1.1005, "tp": 1.1050, "invalidate_level": 1.1005})
    msgs, broadcast = make_broadcaster()
    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: rejected_snapshot(),
        broadcast=broadcast, now=NOW, io=fake.io(),
    )
    closed = [e for e in events if e["event"] == "closed"]
    assert len(closed) == 1
    assert fake._row("EURUSD", "M15")["status"] == "closed"
    assert len([m for m in msgs if m["type"] == "closed"]) == 1


def test_scan_once_auto_execute_off_no_ordene():
    fake = FakeStoreIO(auto_execute=False)
    called = []

    def executor(*args, **kwargs):
        called.append((args, kwargs))

    events = watcher.scan_once(
        snapshot_builder=lambda s, tf: approved_snapshot(),
        executor=executor, now=NOW, io=fake.io(),
    )
    assert not [e for e in events if e["event"] == "executed"]
    assert called == []


def test_scan_once_auto_execute_on_ejecuta_una_vez():
    fake = FakeStoreIO(auto_execute=True)
    calls = []

    def executor(symbol, action, sl_pips=15.0, tp_pips=30.0):
        calls.append((symbol, action))
        return {"ok": True, "ticket": 777, "price": 1.1040, "volume": 0.05}

    msgs, broadcast = make_broadcaster()
    watcher.scan_once(snapshot_builder=lambda s, tf: approved_snapshot(),
                      executor=executor, broadcast=broadcast, now=NOW, io=fake.io())
    assert len(calls) == 1
    assert calls == [("EURUSD", "BUY")]
    row = fake._row("EURUSD", "M15")
    assert row["status"] == "executed"
    assert row["auto_executed"] is True
    assert len([m for m in msgs if m["type"] == "executed"]) == 1

    # Segundo ciclo con la misma señal viva: no re-ejecuta
    watcher.scan_once(snapshot_builder=lambda s, tf: approved_snapshot(),
                      executor=executor, broadcast=broadcast, now=NOW, io=fake.io())
    assert len(calls) == 1
    assert not [m for m in msgs if m["type"] == "executed"][1:]


def test_scan_once_auto_execute_fallo_no_ejecuta_y_avisa():
    fake = FakeStoreIO(auto_execute=True)
    calls = []

    def executor(*args, **kwargs):
        calls.append(1)
        return {"ok": False, "error": "Margen libre insuficiente."}

    msgs, broadcast = make_broadcaster()
    events = watcher.scan_once(snapshot_builder=lambda s, tf: approved_snapshot(),
                               executor=executor, broadcast=broadcast, now=NOW, io=fake.io())
    assert len(calls) == 1
    errs = [e for e in events if e["event"] == "executed_error"]
    assert len(errs) == 1
    assert "margen" in errs[0]["error"].lower()
    # Sin marcar como ejecutado: el setup sigue activo (sin reintentar por dedup)
    assert fake._row("EURUSD", "M15")["status"] == "active"
    assert [m for m in msgs if m["type"] == "executed_error"]


def test_scan_once_error_por_snapshot_no_tumba_el_ciclo():
    fake = FakeStoreIO()
    msgs, broadcast = make_broadcaster()

    def builder(symbol, tf):
        raise RuntimeError("Sin datos de market watch.")

    events = watcher.scan_once(snapshot_builder=builder,
                               broadcast=broadcast, now=NOW, io=fake.io())
    assert len(events) == 1 and events[0]["event"] == "error"
    assert "Sin datos" in events[0]["error"]
    assert msgs == []


# ---------------------------------------------------------------------------
# store: persistencia del toggle y del estado (DB temporal)
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "watcher_test.db"))
    store.init_db()
    return store


def test_store_watcher_settings_toggle(tmp_store):
    assert tmp_store.get_watcher_auto_execute() is False
    tmp_store.set_watcher_auto_execute(True)
    assert tmp_store.get_watcher_auto_execute() is True
    tmp_store.set_watcher_auto_execute(False)
    assert tmp_store.get_watcher_auto_execute() is False


def test_store_setup_state_cycle(tmp_store):
    gate = {"direction": "BUY", "score": 95.0, "verdict": "ALTA_PROBABILIDAD",
            "entry": 1.1020, "sl": 1.1005, "tp": 1.1050, "invalidate_level": 1.1005}
    tmp_store.new_setup_state("EURUSD", "M15", gate=gate)
    row = tmp_store.get_setup_state("EURUSD", "M15")
    assert row["status"] == "active"
    assert row["direction"] == "BUY"
    assert row["entry"] == 1.1020
    assert row["notified"] is True

    tmp_store.update_setup_state("EURUSD", "M15", status="closed")
    assert tmp_store.get_setup_state("eurusd", "m15")["status"] == "closed"

    tmp_store.update_setup_state("EURUSD", "M15", status="executed", auto_executed=True)
    row = tmp_store.get_setup_state("EURUSD", "M15")
    assert row["status"] == "executed"
    assert row["auto_executed"] is True

    # Un nuevo ciclo reemplaza la fila (created_at nuevo)
    tmp_store.new_setup_state("EURUSD", "M15", gate=gate, status="active")
    row = tmp_store.get_setup_state("EURUSD", "M15")
    assert row["status"] == "active"
    assert row["auto_executed"] is False
    assert len(tmp_store.list_setup_states()) == 1


def test_store_update_sin_fila_crea_estado_minimo(tmp_store):
    tmp_store.update_setup_state("EURUSD", "M1", status="executed", auto_executed=True)
    row = tmp_store.get_setup_state("EURUSD", "M1")
    assert row["status"] == "executed"
    assert row["auto_executed"] is True


def test_store_prop_state_roundtrip(tmp_store):
    st = tmp_store.get_prop_state()
    assert st["baseline_equity"] is None
    assert st["day_peak"] is None

    tmp_store.set_prop_state(
        baseline_equity=10000.0, baseline_day="2026-09-01",
        day_peak=10100.0, day_peak_day="2026-09-07", total_peak=10100.0,
    )
    st = tmp_store.get_prop_state()
    assert st["baseline_equity"] == 10000.0
    assert st["baseline_day"] == "2026-09-01"
    assert st["day_peak_day"] == "2026-09-07"
    assert st["total_peak"] == 10100.0

    # upsert parcial no pisa las demás claves
    tmp_store.set_prop_state(total_peak=10500.0)
    st = tmp_store.get_prop_state()
    assert st["total_peak"] == 10500.0
    assert st["baseline_equity"] == 10000.0

    # claves desconocidas se ignoran sin romper
    tmp_store.set_prop_state(nonexistent_key=1)
    assert tmp_store.get_prop_state()["total_peak"] == 10500.0