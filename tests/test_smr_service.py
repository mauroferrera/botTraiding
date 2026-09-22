"""Layer 1b: Módulo SMR / Divergencia DXY (smr_service + componente de score).

Verifica con datos deterministas (sin red):

  - detect_smr: divergencia alcista (BUY) y bajista (SELL) confirmada solo
    cuando el EURUSD quiebra su extremo previo y el DXY NO confirma la ruptura.
  - degradación: sin velas / sin DXY / velas insuficientes -> nunca lanza,
    confirmed=False (neutro).
  - smr_component: aporta 1.0 solo si la divergencia confirmada coincide con la
    dirección; nunca resta por falta de dato.
  - setup_score: el peso smr_dxy suma al score cuando confirma.

Run:  python -m pytest tests/test_smr_service.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import risk_engine
import smr_service


def candles(rows):
    """Convierte [[o, h, l, c], ...] en velas {time, open, high, low, close}."""
    return [
        {"time": 1_000_000 + i * 900, "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(rows)
    ]


def test_detect_smr_buy_confirmado():
    # EURUSD rompe su mínimo previo (LL) en la última vela
    eu_rows = [[1.1090, 1.1095, 1.1088, 1.1092]] * 9
    eu_rows.append([1.1090, 1.1092, 1.1081, 1.1083])
    eu = candles(eu_rows)
    # DXY con techos al alza salvo la última vela: NO hace nuevo máximo (no HH)
    dxy_rows = [[99.30, 99.35, 99.29, 99.34],
                [99.34, 99.40, 99.33, 99.39],
                [99.39, 99.47, 99.38, 99.46],
                [99.46, 99.55, 99.45, 99.54],
                [99.54, 99.62, 99.53, 99.61],
                [99.61, 99.68, 99.60, 99.67]] * 1
    dxy_rows.append([99.67, 99.64, 99.56, 99.58])  # alto 99.64 < 99.68 previo
    dxy = candles(dxy_rows)

    res = smr_service.detect_smr(eu, dxy, "BUY", lookback=5)
    assert res["confirmed"] is True
    assert res["data"]["eurusd"]["broke"] is True
    assert res["data"]["dxy"]["broke"] is False


def test_detect_smr_sell_confirmado():
    # EURUSD quiebra su máximo previo (LH) en la última vela
    eu_rows = [[1.0960, 1.0965, 1.0958, 1.0962]] * 9
    eu_rows.append([1.0960, 1.0980, 1.0959, 1.0978])
    eu = candles(eu_rows)
    # DXY en descenso salvo la última vela: NO hace nuevo mínimo (no LL)
    dxy_rows = [[100.10, 100.14, 100.09, 100.13],
                [100.13, 100.17, 100.08, 100.16],
                [100.16, 100.20, 100.11, 100.19],
                [100.19, 100.23, 100.14, 100.22],
                [100.22, 100.26, 100.17, 100.25],
                [100.25, 100.29, 100.20, 100.28]] * 1
    dxy_rows.append([100.28, 100.32, 100.24, 100.30])  # mínimo 100.24 > 100.17 previo
    dxy = candles(dxy_rows)

    res = smr_service.detect_smr(eu, dxy, "SELL", lookback=5)
    assert res["confirmed"] is True
    assert res["data"]["eurusd"]["broke"] is True
    assert res["data"]["dxy"]["broke"] is False


def test_detect_smr_no_confirmado_cuando_dxy_confirma():
    # Mismo quiebre de EURUSD (LL) pero el DXY SÍ hace nuevo máximo: no SMR
    eu = candles([[1.1080, 1.1084, 1.1077, 1.1081]] * 9 +
                 [[1.1079, 1.1081, 1.1070, 1.1072]])
    dxy = candles([[99.40, 99.44, 99.39, 99.43]] * 9 +
                  [[99.43, 99.55, 99.42, 99.54]])  # HH
    res = smr_service.detect_smr(eu, dxy, "BUY")
    assert res["confirmed"] is False
    assert res["data"]["eurusd"]["broke"] is True
    assert res["data"]["dxy"]["broke"] is True


def test_detect_smr_eurusd_no_quiebra():
    eu = candles([[1.1080, 1.1084, 1.1077, 1.1081]] * 10)  # plano, sin LL
    dxy = candles([[99.40, 99.44, 99.39, 99.43]] * 9 +
                  [[99.43, 99.55, 99.42, 99.54]])
    res = smr_service.detect_smr(eu, dxy, "BUY")
    assert res["confirmed"] is False
    assert res["data"]["eurusd"]["broke"] is False


def test_detect_smr_degradaciones_nunca_lanza():
    assert smr_service.detect_smr(None, [{}], "BUY")["confirmed"] is False
    assert smr_service.detect_smr([{}], None, "BUY")["confirmed"] is False
    assert smr_service.detect_smr([{}], [{}], "BUY", lookback=8)["confirmed"] is False
    try:
        smr_service.detect_smr([{}], [{}], "HOLD")
        assert False, "direction inválida debe fallar"
    except ValueError:
        pass


def test_smr_component_solo_cuando_confirmada():
    smr_payload = {
        "bull": {"confirmed": True, "detail": "Divergencia SMR alcista"},
        "bear": {"confirmed": False, "detail": "sin divergencia"},
    }
    assert risk_engine.smr_component(smr_payload, "BUY")["value"] == 1.0
    assert risk_engine.smr_component(smr_payload, "SELL")["value"] == 0.0  # lado equivocado
    neutral = {"bull": {"confirmed": False}, "bear": {"confirmed": False}}
    assert risk_engine.smr_component(neutral, "BUY")["value"] == 0.0
    assert risk_engine.smr_component(None, "BUY")["value"] == 0.0  # sin feed


def test_setup_score_integra_peso_smr_dxy():
    now = datetime(2026, 9, 7, 9, 30, 0, tzinfo=timezone.utc)
    weights = {"cot": 0.0, "cvd_of": 0.0, "smc": 0.0, "killzone": 0.0,
               "smr_dxy": 50.0}  # solo el SMR aporta al score
    base = {"direction": "BUY", "cot": None, "cvd": None,
            "patterns": None, "candles": None, "killzone": []}

    sin_smr = risk_engine.setup_score({**base, "smr": None}, weights=weights, now=now)
    assert sin_smr["score"] == 0.0
    assert sin_smr["components"]["smr_dxy"]["confirmed"] is False

    smr_payload = {
        "bull": {"confirmed": True, "detail": "Divergencia SMR alcista"},
        "bear": {"confirmed": False},
    }
    con_smr = risk_engine.setup_score({**base, "smr": smr_payload},
                                      weights=weights, now=now)
    assert con_smr["score"] == 100.0
    assert con_smr["components"]["smr_dxy"]["confirmed"] is True
    assert con_smr["components"]["smr_dxy"]["weight"] == 50.0