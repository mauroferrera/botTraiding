"""Tests del motor de chartismo clásico (chartism_engine.py).

Series sintéticas de velas OHLC para canales, triángulos, banderas,
doble techo/suelo y cabeza y hombros. La API de salida es la misma que
consume tools.js en el frontend (line/hline/text con t0/p0/t1/p1).
"""

from __future__ import annotations

import math

import chartism_engine as ce


def _candles(opens, highs, lows, closes, base=1700000000, step=60):
    return [
        {"time": base + i * step, "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(zip(opens, highs, lows, closes))
    ]


def _trend_series(n, per, amp=0.0003, body=0.0005, base=1.0, phase=0.0):
    """Serie con tendencia `per` (precio/vela) y onda senoidal para formar pivotes."""
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        w = math.sin(2 * math.pi * i / 10 + phase)
        low = base + i * per + amp * w
        high = low + 0.002 + amp * 0.5 * w
        opens.append(low + body)
        highs.append(high)
        lows.append(low)
        closes.append(high - body)
    return opens, highs, lows, closes


def test_regress_devuelve_none_con_pocos_puntos():
    assert ce._regress([(0, 1.0)]) is None
    assert ce._regress([]) is None


def test_regress_devuelve_none_con_datos_degenerados():
    # precios constantes / x constante → el ajuste es inválido (evita polyfit roto)
    assert ce._regress([(0, 1.0), (1, 1.0), (2, 1.0)]) is None
    assert ce._regress([(5, 1.0), (5, 1.1)]) is None


def test_regress_lineal_ok():
    pts = [(i, 1.0 + 0.001 * i) for i in range(10)]
    reg = ce._regress(pts)
    assert reg is not None
    slope, intercept, r2 = reg
    assert abs(slope - 0.001) < 1e-9
    assert r2 > 0.99


def test_pivot_k_timeframe():
    assert ce.PIVOT_K["M1"] == 3
    assert ce.PIVOT_K["H1"] == 5
    assert ce.PIVOT_K["D1"] == 7
    # timeframe desconocido cae al default
    o, h, l, c = _trend_series(60, 0.0004, 0.0)
    cs = _candles(o, h, l, c)
    assert ce.detect_all(cs, ["trend"], "XX9")["timeframe"] == "XX9"


# --------------------------------------------------------------------------- #
# Canal alcista
# --------------------------------------------------------------------------- #

def test_detect_trend_canal_alcista():
    o, h, l, c = _trend_series(90, per=0.00015, amp=0.0015, phase=0.0)
    candles = _candles(o, h, l, c)
    res = ce.detect_all(candles, ["trend"], "M15")
    assert res["patterns"] == ["trend"]
    assert res["summary"]["trend"] == 1
    lines = [d for d in res["drawings"] if d["tool"] == "line"]
    assert len(lines) == 2
    labels = [d["text"] for d in res["drawings"] if d["tool"] == "text"]
    assert any("Canal" in t for t in labels)


def test_detect_trend_sin_datos_no_rompe():
    res = ce.detect_all([], ["trend"], "M15")
    assert res["drawings"] == []
    assert res["summary"] == {"trend": 0}


# --------------------------------------------------------------------------- #
# Triángulo ascendente
# --------------------------------------------------------------------------- #

def test_detect_triangle_ascendente():
    n = 70
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        w = math.sin(2 * math.pi * i / 10)
        low = 1.0000 + i * 0.00014 + 0.0006 * w
        high = 1.0098 + 0.0006 * w
        opens.append(low + 0.0004)
        highs.append(high)
        lows.append(low)
        closes.append(min(high - 0.0004, low + 0.001))
    candles = _candles(opens, highs, lows, closes)

    res = ce.detect_all(candles, ["triangle"], "M15")
    assert res["summary"]["triangle"] == 1
    texts = [d["text"] for d in res["drawings"] if d["tool"] == "text"]
    assert any("ascendente" in t for t in texts)
    lines = [d for d in res["drawings"] if d["tool"] == "line"]
    assert len(lines) == 2


# --------------------------------------------------------------------------- #
# Bandera (asta alcista + consolidación en paralelo)
# --------------------------------------------------------------------------- #

def test_detect_flag_bull():
    n = 80
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        if i < 50:  # asta hacia arriba con oscilación (deja pivotes bajistas)
            low = 1.0000 + i * 0.00025 + 0.0004 * math.sin(2 * math.pi * i / 8)
            high = low + 0.0015
        else:  # consolidación lateral corta (grosor constante)
            low = 1.0110 + 0.0005 * math.sin(2 * math.pi * i / 6)
            high = low + 0.0026
        opens.append((low + high) / 2)
        highs.append(high)
        lows.append(low)
        closes.append((low + high) / 2)
    candles = _candles(opens, highs, lows, closes)

    res = ce.detect_all(candles, ["flag"], "M15")
    assert res["summary"]["flag"] == 1
    texts = [d["text"] for d in res["drawings"] if d["tool"] == "text"]
    assert any("Bandera" in t for t in texts)
    assert sum(1 for d in res["drawings"] if d["tool"] == "line") >= 3


# --------------------------------------------------------------------------- #
# Doble techo
# --------------------------------------------------------------------------- #

def test_detect_double_techo():
    n = 90
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        w = math.sin(2 * math.pi * i / 9)
        if i < 25:
            low = 1.0000 + i * 0.0004
        elif i < 45:
            low = 1.0100 - (i - 25) * 0.0004
        elif i < 65:
            low = 1.0040 + (i - 45) * 0.0004
        else:
            low = 1.0100 - (i - 65) * 0.0003
        high = low + 0.006 + 0.0003 * w
        opens.append(low + 0.0004)
        highs.append(high if not (i in (25, 65)) else 1.0100 + 0.0003 * w)
        lows.append(low)
        closes.append(high - 0.0004)
    candles = _candles(opens, highs, lows, closes)

    res = ce.detect_all(candles, ["double"], "M15")
    assert res["summary"]["double"] == 1
    texts = [d["text"] for d in res["drawings"] if d["tool"] == "text"]
    assert any("Doble techo" in t for t in texts)
    assert any(d["tool"] == "hline" for d in res["drawings"])


# --------------------------------------------------------------------------- #
# Cabeza y hombros
# --------------------------------------------------------------------------- #

def test_detect_hns():
    n = 95
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        w = math.sin(2 * math.pi * i / 9)
        if i < 20:
            low = 1.0000 + i * 0.0004
        elif i < 35:
            low = 1.0080 - (i - 20) * 0.0004
        elif i < 50:
            low = 1.0040 + (i - 35) * 0.0007
        elif i < 65:
            low = 1.0145 - (i - 50) * 0.0007
        elif i < 80:
            low = 1.0045 + (i - 65) * 0.0006
        else:
            low = 1.0130 - (i - 80) * 0.0005
        high = low + 0.006 + 0.0003 * w
        opens.append(low + 0.0004)
        highs.append(high)
        lows.append(low)
        closes.append(high - 0.0004)
    # Ajuste fino de los hombros y la cabeza (más altos que las líneas de base)
    peaks = {20: 1.0100, 50: 1.0180, 80: 1.0090}
    for idx, p in peaks.items():
        lows[idx] = p - 0.006
        highs[idx] = p
        opens[idx] = p - 0.0004
        closes[idx] = p - 0.0004
    candles = _candles(opens, highs, lows, closes)

    res = ce.detect_all(candles, ["hns"], "M15")
    assert res["summary"]["hns"] == 1
    texts = [d["text"] for d in res["drawings"] if d["tool"] == "text"]
    assert any("Hombro" in t for t in texts)
    assert any(d["tool"] == "line" for d in res["drawings"])


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #

def test_detect_all_all_groups_y_filtros():
    o, h, l, c = _trend_series(90, per=0.00015, amp=0.0015, phase=0.0)
    candles = _candles(o, h, l, c)
    res = ce.detect_all(candles, ["all"], "M15")
    assert res["patterns"] == ce.GROUPS
    assert set(res["summary"].keys()) == set(ce.GROUPS)
    for d in res["drawings"]:
        assert d.get("group") in ce.GROUPS
        assert d.get("tool") in ("line", "hline", "text")


def test_detect_all_patterns_none():
    o, h, l, c = _trend_series(90, per=0.00015, amp=0.0015, phase=0.0)
    candles = _candles(o, h, l, c)
    res = ce.detect_all(candles, None, "M15")
    assert res["drawings"] == []