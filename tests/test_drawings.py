"""Tests for manual chart drawings: store round-trip (unified user/agent), the
FastAPI endpoints and the agent-side resolution of free-drawing coordinates
(line / horizontal / rect / text) in chart_annotate."""

from __future__ import annotations

import sqlite3

import pytest

import agent
import store


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "drawings_test.db"))
    store.init_db()
    return store


def test_get_drawings_default_vacio(tmp_store):
    assert tmp_store.get_drawings("EURUSD", "M15") == []


def test_save_get_roundtrip_con_origin(tmp_store):
    drawings = [
        {"id": "u1", "origin": "user", "tool": "line", "t0": 1000000, "p0": 1.10, "t1": 1000200, "p1": 1.11},
        {"id": "a1", "origin": "agent", "tool": "hline", "p0": 1.1050},
        {"id": "u2", "origin": "user", "tool": "text", "t0": 1000000, "p0": 1.1055, "text": "resistencia"},
    ]
    tmp_store.save_drawings("EURUSD", "M15", drawings)
    got = tmp_store.get_drawings("EURUSD", "M15")
    assert got == drawings
    assert got[1]["origin"] == "agent"


def test_save_drawings_reescribe_completo(tmp_store):
    tmp_store.save_drawings("EURUSD", "M15", [{"tool": "line", "t0": 1, "p0": 1.1, "t1": 2, "p1": 1.2}])
    tmp_store.save_drawings("EURUSD", "M15", [{"tool": "hline", "p0": 1.3}])
    got = tmp_store.get_drawings("EURUSD", "M15")
    assert len(got) == 1
    assert got[0]["tool"] == "hline"


def test_drawings_aisladas_por_symbol_y_timeframe(tmp_store):
    tmp_store.save_drawings("EURUSD", "M15", [{"tool": "hline", "p0": 1.1}])
    tmp_store.save_drawings("EURUSD", "H1", [{"tool": "line", "t0": 1, "p0": 1.1, "t1": 2, "p1": 1.2}])
    tmp_store.save_drawings("XAUUSD", "M15", [{"tool": "rect", "t0": 1, "p0": 1.1, "t1": 2, "p1": 1.2}])
    assert len(tmp_store.get_drawings("EURUSD", "M15")) == 1
    assert len(tmp_store.get_drawings("EURUSD", "H1")) == 1
    assert len(tmp_store.get_drawings("XAUUSD", "M15")) == 1


def test_delete_drawings(tmp_store):
    tmp_store.save_drawings("EURUSD", "M15", [{"tool": "hline", "p0": 1.1}])
    tmp_store.delete_drawings("EURUSD", "M15")
    assert tmp_store.get_drawings("EURUSD", "M15") == []


def test_get_drawings_ignora_json_corrupto(tmp_store):
    tmp_store.save_drawings("EURUSD", "M15", [{"tool": "hline", "p0": 1.1}])
    db = sqlite3.connect(tmp_store.DB_PATH)
    db.execute("UPDATE chart_drawings SET drawings_json = 'no-es-json' WHERE symbol='EURUSD' AND timeframe='M15'")
    db.commit()
    db.close()
    assert tmp_store.get_drawings("EURUSD", "M15") == []


def _seed_last_analysis(monkeypatch):
    """Sembra la caché _LAST_ANALYSIS con una ventana de velas real."""
    agent._LAST_ANALYSIS["EURUSD|M15"] = {
        "analysis": {"patterns": {"fvgs": [], "order_blocks": [], "sweeps": []}},
        "last_time": 1000200,
        "candle_start": 1000000,
        "candle_lo": 1.1000,
        "candle_hi": 1.1100,
    }


def test_resolve_line_horizontal_rect_text(monkeypatch):
    _seed_last_analysis(monkeypatch)
    out = agent._resolve_annotations({
        "symbol": "EURUSD",
        "timeframe": "M15",
        "actions": [
            {"kind": "line", "start_time": 1000100, "price_from": 1.1020, "end_time": 1000200, "price_to": 1.1050},
            {"kind": "horizontal", "price_from": 1.1080},
            {"kind": "rect", "start_time": 1000000, "price_from": 1.1010, "end_time": 1000150, "price_to": 1.1040},
            {"kind": "text", "start_time": 1000200, "price_from": 1.1055, "name": "zona clave"},
        ],
    })
    draws = out["echarts"]["draw"]
    assert len(draws) == 4
    assert [d["tool"] for d in draws] == ["line", "hline", "rect", "text"]

    line = draws[0]
    assert line["origin"] == "agent"
    assert line["t0"] == 1000100 and line["t1"] == 1000200
    assert line["p0"] == 1.1020 and line["p1"] == 1.1050

    hline = draws[1]
    assert hline["tool"] == "hline" and hline["p0"] == 1.1080

    text = draws[3]
    assert text["text"] == "zona clave"
    assert text["t0"] == 1000200

    assert out["applied"] == 4
    assert out["skipped"] == 0
    assert out["view"]["price_min"] <= 1.1010
    assert out["view"]["price_max"] >= 1.1055


def test_resolve_descarta_coords_invalidas_y_recorta(monkeypatch):
    _seed_last_analysis(monkeypatch)
    out = agent._resolve_annotations({
        "symbol": "EURUSD",
        "timeframe": "M15",
        "actions": [
            {"kind": "line", "start_time": 1000000, "price_from": 5.0, "end_time": 1000050, "price_to": 1.1050},
            {"kind": "horizontal", "price_to": 1.11},
            {"kind": "rect", "start_time": 1, "price_from": 1.1020, "end_time": 1000050, "price_to": 1.1040},
        ],
    })
    draws = out["echarts"]["draw"]
    assert len(draws) == 2
    assert draws[0]["p0"] == pytest.approx(1.1125)  # recortado a hi + 25% del span
    assert draws[1]["t0"] == 1000000
    assert out["skipped"] == 1


def test_resolve_figuras_requieren_caché(monkeypatch):
    monkeypatch.setattr(agent, "_LAST_ANALYSIS", {})
    with pytest.raises(RuntimeError):
        agent._resolve_annotations({"symbol": "EURUSD", "timeframe": "M15", "actions": [{"kind": "line", "price_from": 1.1, "price_to": 1.2}]})


def test_summarize_drawings_formato(monkeypatch):
    monkeypatch.setattr(store, "get_drawings", lambda s, tf="M15": [
        {"tool": "hline", "p0": 1.1080, "origin": "user"},
        {"tool": "line", "t0": 1, "p0": 1.10, "t1": 2, "p1": 1.11, "origin": "agent"},
        {"tool": "text", "t0": 1, "p0": 1.1055, "text": "zona", "origin": "user"},
    ])
    out = agent._summarize_drawings({"symbol": "EURUSD", "timeframe": "M15"})
    assert out["count"] == 3
    assert "línea de tendencia" in out["lectura"]
    assert "nivel horizontal" in out["lectura"]
    assert "'zona'" in out["lectura"]
    assert out["drawings"][1]["origin"] == "agent"


def test_summarize_drawings_vacio(monkeypatch):
    monkeypatch.setattr(store, "get_drawings", lambda s, tf="M15": [])
    out = agent._summarize_drawings({"symbol": "EURUSD", "timeframe": "M15"})
    assert out["count"] == 0
    assert "No hay dibujos" in out["lectura"]