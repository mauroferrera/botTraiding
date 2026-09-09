"""Selector de fuente CVD (cvd_service.pick_cvd_source): puro y sin MT5.

Verifica que el snapshot etiquete la fuente REAL: la serie live de Databento
solo gana si hay suficientes puntos recientes; si no, cae a la sintética (con
warning cuando la feed está conectada pero no aporta) y nunca miente en el label.

Run:  python -m pytest tests/test_cvd_selector.py -v
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("MetaTrader5")

from cvd_service import pick_cvd_source  # noqa: E402


def _pts(n):
    return [{"time": 1_000_000 + i * 900, "value": round(float(i), 2)} for i in range(n)]


class TestPickCvdSource:
    def test_uses_live_when_sufficient(self):
        live, syn = _pts(8), _pts(4)
        points, source, warning = pick_cvd_source(live, syn)
        assert points == live
        assert source == "live (Databento 6E)"
        assert warning is None

    def test_falls_back_when_live_insufficient(self):
        live, syn = _pts(2), _pts(6)
        points, source, warning = pick_cvd_source(live, syn)
        assert points == syn
        assert source == "synthetic (tick volume MT5)"
        assert warning is not None and "live" in warning

    def test_synthetic_without_feed_has_no_warning(self):
        syn = _pts(6)
        points, source, warning = pick_cvd_source(None, syn)
        assert source == "synthetic (tick volume MT5)"
        assert warning is None

    def test_no_data_at_all(self):
        points, source, warning = pick_cvd_source(None, None)
        assert points is None
        assert source is None
        assert "sin datos" in warning

    def test_custom_min_points(self):
        """Con min_live_points=3, 3 puntos live ya alcanzan."""
        live, syn = _pts(3), _pts(5)
        points, source, _ = pick_cvd_source(live, syn, min_live_points=3)
        assert source == "live (Databento 6E)"
        assert points == live

    def test_synthetic_data_is_not_mutated(self):
        live = None
        syn = _pts(4)
        _, _, _ = pick_cvd_source(live, syn)
        assert syn == _pts(4)