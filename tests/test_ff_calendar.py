"""News gate (ff_calendar): lógica pura de ventana + fetch cacheado + fail-open.

Sin red: la lógica de ventanas se prueba con eventos fabricados y `now_utc`
fijos; la capa de red se mockea con monkeypatch (fetch que devuelve o lanza).

Run:  python -m pytest tests/test_ff_calendar.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import ff_calendar as ff

NOW = datetime(2026, 9, 7, 14, 0, 0, tzinfo=timezone.utc)  # 14:00 UTC


def _event(minutes: int, currency: str = "USD", impact: str = "red", title: str = "Nonfarm Payrolls"):
    return {"time": "xx:xx", "minutes": minutes, "currency": currency,
            "impact": impact, "title": title}


def _md_block(clock="10:00am", rows=()):
    lines = [
        "| date | [%s](https://www.forexfactory.com/timezone) | currency | "
        "impact | actual | forecast | previous |" % clock,
    ]
    for (hm, cur, impact, title) in rows:
        lines.append(
            "| 1/1/26 | %s | 06:00 | ![img](https://n4s-fx.com/img/ff-impact-%s.png) |"
            " %s | %s | | | | | | |" % (hm, impact, title, cur)
        )
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def _clean_cache():
    ff._cache.clear()
    yield
    ff._cache.clear()


# ---------------------------------------------------------------------------
# high_impact_in_window (lógica pura)
# ---------------------------------------------------------------------------

class TestHighImpactWindow:
    def test_red_near_now_blocks(self):
        """Reloj FF 10:00 con UTC 14:00 -> offset +240 min. Evento 09:45 -> 13:45 UTC,
        a 15 min del now -> dentro de la ventana (borde incluido)."""
        res = ff.high_impact_in_window(
            [_event(9 * 60 + 45)], clock_min=10 * 60, now_utc=NOW, buffer_min=15
        )
        assert res["blocked"] is True
        assert res["event"]["title"] == "Nonfarm Payrolls"
        assert res["event"]["currency"] == "USD"

    def test_just_outside_buffer_free(self):
        """Evento a 16 min del now (borde +1) -> fuera de la ventana."""
        res = ff.high_impact_in_window(
            [_event(9 * 60 + 44)], clock_min=10 * 60, now_utc=NOW, buffer_min=15
        )
        assert res["blocked"] is False

    def test_min_impact_filter(self):
        """Naranja cerca del now NO bloquea con min_impact=red; sí con 'ora'."""
        near = _event(9 * 60 + 50, impact="ora", title="CPI")
        assert ff.high_impact_in_window([near], clock_min=10 * 60,
                                        now_utc=NOW, buffer_min=15)["blocked"] is False
        assert ff.high_impact_in_window([near], clock_min=10 * 60,
                                        now_utc=NOW, buffer_min=15,
                                        min_impact="ora")["blocked"] is True

    def test_currency_filter(self):
        """Evento GBP rojo no aplica (solo EUR/USD)."""
        res = ff.high_impact_in_window(
            [_event(9 * 60 + 50, currency="GBP")], clock_min=10 * 60,
            now_utc=NOW, buffer_min=15
        )
        assert res["blocked"] is False

    def test_no_clock_assumes_utc(self):
        """Sin reloj (None) los eventos se toman como UTC directamente."""
        now_utc = datetime(2026, 9, 7, 13, 50, 0, tzinfo=timezone.utc)
        res = ff.high_impact_in_window(
            [_event(13 * 60 + 40)], clock_min=None, now_utc=now_utc, buffer_min=15
        )
        assert res["blocked"] is True

    def test_midnight_wrap(self):
        """Evento cerca de medianoche en el reloj que mapea a 03:55 UTC con now 04:00
        (offset +245): debe bloquear (diferencia -5 min, cruce de día)."""
        now_utc = datetime(2026, 9, 7, 4, 0, 0, tzinfo=timezone.utc)
        res = ff.high_impact_in_window(
            [_event(23 * 60 + 50)], clock_min=23 * 60 + 55,
            now_utc=now_utc, buffer_min=15
        )
        assert res["blocked"] is True

    def test_prioritizes_higher_impact_closer(self):
        """Con dos candidatos (red lejos, ora cerca) gana el de mayor impacto."""
        far_red = _event(10 * 60 + 30, impact="red", title="A")
        near_ora = _event(9 * 60 + 50, impact="ora", title="B")
        res = ff.high_impact_in_window(
            [far_red, near_ora], clock_min=10 * 60, now_utc=NOW, buffer_min=60
        )
        assert res["event"]["title"] == "A"


# ---------------------------------------------------------------------------
# parse de markdown real (sanity del formato fabricado)
# ---------------------------------------------------------------------------

class TestParseAndGate:
    def test_md_roundtrip(self):
        md = _md_block("10:00am", [( "09:45am", "USD", "red", "Nonfarm Payrolls")])
        clock_min, events = ff.parse_calendar(md)
        assert clock_min == 600
        assert len(events) == 1
        ev = events[0]
        assert ev["currency"] == "USD"
        assert ev["impact"] == "red"
        assert ev["minutes"] == 9 * 60 + 45


# ---------------------------------------------------------------------------
# cached_calendar y news_gate (fetch mockeado)
# ---------------------------------------------------------------------------

class TestCacheAndGate:
    def test_cache_hits_within_ttl(self, monkeypatch):
        md = _md_block("10:00am", [])
        calls = {"n": 0}
        def fake_fetch(timeout=45):
            calls["n"] += 1
            return md
        monkeypatch.setattr(ff, "_fetch_markdown", fake_fetch)
        ff.cached_calendar(ttl=5)
        ff.cached_calendar(ttl=5)
        assert calls["n"] == 1

    def test_gate_blocks_with_red_event(self, monkeypatch):
        md = _md_block("10:00am", [("09:45am", "USD", "red", "Nonfarm Payrolls")])
        monkeypatch.setattr(ff, "_fetch_markdown", lambda timeout=45: md)
        res = ff.news_gate(buffer_min=15, now_utc=NOW)
        assert res["ok"] is False
        assert res["fail_open"] is False
        assert "ventana de noticia" in res["reason"]

    def test_gate_allows_quiet_calendar(self, monkeypatch):
        md = _md_block("10:00am", [("06:00am", "JPY", "yel", "CPI")])
        monkeypatch.setattr(ff, "_fetch_markdown", lambda timeout=45: md)
        res = ff.news_gate(buffer_min=15, now_utc=NOW)
        assert res["ok"] is True

    def test_fail_open_when_no_cache_and_network_down(self, monkeypatch):
        monkeypatch.setattr(ff, "_fetch_markdown", lambda timeout=45: (_ for _ in ()).throw(RuntimeError("red")))
        res = ff.news_gate(buffer_min=15, now_utc=NOW)
        assert res["ok"] is True
        assert res["fail_open"] is True

    def test_stale_cache_used_when_fetch_fails(self, monkeypatch):
        md = _md_block("10:00am", [("09:45am", "USD", "red", "Nonfarm Payrolls")])
        monkeypatch.setattr(ff, "_fetch_markdown", lambda timeout=45: md)
        ff.cached_calendar(ttl=5)  # puebla la caché

        def boom(timeout=45):
            raise RuntimeError("red caída")
        monkeypatch.setattr(ff, "_fetch_markdown", boom)
        # caché vencida pero presente: se usa el evento stale -> bloquea igual
        res = ff.news_gate(buffer_min=15, now_utc=NOW, ttl=-1)
        assert res["ok"] is False
        assert res["fail_open"] is False