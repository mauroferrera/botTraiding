"""Tests del simulador de mercado sintético unificado (6E).

Cubre Fase 1 (MarketSimulator), Fase 3 (escenarios integrados .jsonl) y la
auditoría del checklist por fixture:

  - determinismo: misma semilla -> mismas velas/footprint/VP.
  - consistencia: el delta acumulado del footprint == CVD del engine por ventana
    (incluida la barra en formación).
  - triggers por régimen: spike/absorción disparan según el escenario.
  - sweep del fixture: detect_sweeps dispara con el PDH sintético del simulador.
  - auditoría slash_check-list de los 5 escenarios maestros:
      1. sweep_and_reverse        (barrido + reversión)
      2. absorption_at_support    (absorción institucional)
      3. fvg_expansion_trend      (tendencia + FVG + Order Block)
      4. range_consolidation_vp   (rango, VP en campana, sin alertas falsas)
      5. latency_stress           (estrés de alta frecuencia)

100% offline: inyecta los MISMOS ticks por add_tick (MarketSimulator) y
add_trade (OrderFlowEngine), el contrato que app.py consume en modo mock.

Run:  python -m pytest tests/test_simulator.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import mock_feed  # noqa: E402
import risk_engine as re_mod  # noqa: E402
import simulator  # noqa: E402
from app import OrderFlowEngine  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
NY_KILLZONE = [{"name": "Nueva York", "start": "13:00", "end": "16:00"}]
NOW_KZ = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)


def _load(name: str) -> list:
    return mock_feed.load_fixture(str(FIXTURES / name))


def _feed_sim(s, trades):
    for t in trades:
        s.add_tick(t["price"], t["size"], t["side"], t["ts"])


def _feed_engine(eng, trades):
    for t in trades:
        eng.add_trade(price=t["price"], size=t["size"], side=t["side"], ts=t["ts"])


def _new_sim() -> simulator.MarketSimulator:
    return simulator.MarketSimulator()


def _setup_sell_score(candles, cvd, patterns, cot=None):
    inputs = {"direction": "SELL", "cot": cot, "cvd": cvd,
              "patterns": patterns, "candles": candles}
    return re_mod.setup_score(inputs, killzones=NY_KILLZONE, now=NOW_KZ)


class TestDeterminism:
    """Misma semilla -> mismas velas/footprint/VP en instancias separadas."""

    def test_same_stream_same_candles(self):
        trades = _load("sweep_and_reverse.jsonl")
        a, b = _new_sim(), _new_sim()
        _feed_sim(a, trades)
        _feed_sim(b, trades)
        assert a.candles("M15", 300) == b.candles("M15", 300)
        assert a.footprint() == b.footprint()
        assert a.vp() == b.vp()
        assert a.state() == b.state()

    def test_gen_stream_same_regime_same_candles(self):
        a, b = _new_sim(), _new_sim()
        _feed_sim(a, list(mock_feed.gen_stream("noise", count=200, seed=7)))
        _feed_sim(b, list(mock_feed.gen_stream("noise", count=200, seed=7)))
        assert a.candles() == b.candles()

    def test_different_seed_differs(self):
        a, b = _new_sim(), _new_sim()
        _feed_sim(a, list(mock_feed.gen_stream("noise", count=200, seed=7)))
        _feed_sim(b, list(mock_feed.gen_stream("noise", count=200, seed=8)))
        assert a.candles() != b.candles()

    def test_reset_replays_same(self):
        trades = list(mock_feed.gen_stream("spike", count=150, seed=3))
        s = _new_sim()
        _feed_sim(s, trades)
        first = s.candles()
        s.reset()
        assert s.candles() == []
        _feed_sim(s, trades)
        assert s.candles() == first

    def test_scenario_builders_are_deterministic(self):
        assert mock_feed.build_sweep_reverse_trades() == mock_feed.build_sweep_reverse_trades()
        assert mock_feed.build_absorption_trades() == mock_feed.build_absorption_trades()

    def test_committed_fixtures_match_generators(self):
        assert _load("sweep_and_reverse.jsonl") == mock_feed.build_sweep_reverse_trades()
        assert _load("absorption_at_support.jsonl") == mock_feed.build_absorption_trades()
        assert _load("fvg_expansion_trend.jsonl") == mock_feed.build_fvg_expansion_trades()
        assert _load("range_consolidation_vp.jsonl") == mock_feed.build_range_consolidation_trades()
        assert _load("latency_stress.jsonl") == mock_feed.build_latency_stress_trades()

    def test_all_registered_fixture_files_exist_and_load(self):
        """Todo fixture registrado en SCENARIOS existe y valida su shape."""
        found = 0
        for key, sc in mock_feed.SCENARIOS.items():
            if sc["kind"] != "fixture":
                continue
            found += 1
            trades = mock_feed.load_fixture(sc["path"])
            assert trades, f"{key}: fixture vacío"
        assert found >= 8  # 3 base + 2 integrados + 3 nuevos escenarios maestros


class TestConsistency:
    """El footprint y el engine comparten el MISMO stream: el delta acumulado del
    footprint coincide con el CVD del engine, incluida la barra en formación."""

    def _delta_from_footprint(self, fp):
        if fp is None:
            return 0.0
        return sum(float(b["delta"]) for b in fp["bars"])

    def test_closed_candle_delta_equals_engine_cvd(self):
        trades = _load("sweep_and_reverse.jsonl")  # 975 ticks -> 39 velas cerradas
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)
        fp = s.footprint()
        assert len(fp["bars"]) == 39
        assert self._delta_from_footprint(fp) == pytest.approx(eng.snapshot()["cvd"], abs=1e-3)
        assert sum(float(b["vol"]) for b in fp["bars"]) == pytest.approx(eng.snapshot()["total_vol"])

    def test_live_bar_delta_included(self):
        trades = list(mock_feed.gen_stream("noise", count=373, seed=5))  # 373 no es múltiplo de 25
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)
        assert s.state()["candles"] == 15  # 14 cerradas + 1 en formación
        fp = s.footprint()
        assert len(fp["bars"]) == 15
        assert self._delta_from_footprint(fp) == pytest.approx(eng.snapshot()["cvd"], abs=1e-3)
        assert self._delta_from_footprint(fp) == pytest.approx(eng.cvd, abs=1e-3)

    def test_per_bar_delta_equals_engine_window(self):
        trades = _load("sweep_and_reverse.jsonl")  # 975 ticks -> 39 velas cerradas
        eng, s = OrderFlowEngine(), _new_sim()
        boundaries = []
        for i, t in enumerate(trades):
            eng.add_trade(t["price"], t["size"], t["side"], t["ts"])
            s.add_tick(t["price"], t["size"], t["side"], t["ts"])
            if (i + 1) % s.ticks_per_candle == 0:
                boundaries.append(float(eng.cvd))
        fp = s.footprint()
        assert len(fp["bars"]) == len(boundaries) == 39
        for k, b in enumerate(fp["bars"]):
            seg = boundaries[k] - (boundaries[k - 1] if k > 0 else 0.0)
            assert b["delta"] == pytest.approx(seg, abs=1e-3)

    def test_cvd_series_matches_engine_buckets(self):
        trades = _load("absorption_at_support.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)
        assert s.cvd_series() == eng.cvd_series()


class TestRegimeTriggers:
    """Los triggers del engine se mantienen a través del pipeline simulado."""

    def test_spike_regime_triggers(self):
        eng = OrderFlowEngine()
        _feed_engine(eng, list(mock_feed.gen_stream("spike", count=300, seed=7)))
        assert eng.snapshot()["spike_count"] >= 1

    def test_noise_regime_quiet(self):
        eng = OrderFlowEngine()
        _feed_engine(eng, list(mock_feed.gen_stream("noise", count=300, seed=7)))
        assert eng.snapshot()["spike_count"] == 0

    def test_signals_surface_through_simulator(self):
        for regime in ("noise", "spike", "stress"):
            trades = list(mock_feed.gen_stream(regime, count=260, seed=7))
            s = _new_sim()
            _feed_sim(s, trades)
            assert s.state()["candles"] >= 10
            assert s.state()["last_price"] is not None


class TestSyntheticSweep:
    """El escenario sweep_and_reverse dispara el sweep SMC contra el PDH
    sintético del simulador."""

    def test_pdh_is_derived(self):
        s = _new_sim()
        _feed_sim(s, _load("sweep_and_reverse.jsonl"))
        pdh, pdl = s.session_levels()
        assert pdh is not None and pdl is not None
        assert pdl < pdh

    def test_detect_sweeps_fires_with_synthetic_pdh(self):
        s = _new_sim()
        _feed_sim(s, _load("sweep_and_reverse.jsonl"))
        pat = s.patterns("6E", "M15", 300)
        sweeps = pat["analysis"]["patterns"]["sweeps"]
        assert [w["type"] for w in sweeps], "no se detectó ningún sweep"
        assert any(w["type"] == "PDH_SWEEP" for w in sweeps)
        assert pat["analysis"]["patterns"].get("fvgs") is not None

    def test_impulse_has_spikes_with_rising_cvd(self):
        # Checklist: Z>=2.5 + CVD↑ durante el impulso comprador que rompe el PDH.
        eng = OrderFlowEngine()
        peak_cvd, spikes_while_up = -1e18, 0
        for t in _load("sweep_and_reverse.jsonl"):
            payload = eng.add_trade(t["price"], t["size"], t["side"], t["ts"])
            if payload and payload.get("is_spike") and eng.cvd > 0:
                spikes_while_up += 1
            if eng.cvd > peak_cvd:
                peak_cvd = eng.cvd
        assert spikes_while_up >= 1
        assert peak_cvd > 100


class TestScenarioAudit:
    """Check-list de auditoría de los escenarios integrados (validable en
    pantalla y en tests)."""

    def test_sweep_and_reverse_audit(self):
        trades = _load("sweep_and_reverse.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)

        # (1) Z>=2.5 presente.
        assert eng.snapshot()["spike_count"] >= 10
        # (2) celda footprint ask>bid en los niveles altos (impulso comprador).
        fp = s.footprint()
        assert fp is not None
        askgt = 0
        for b in fp["bars"][-14:]:
            top = max(lv["price"] for lv in b["levels"])
            top_levels = [lv for lv in b["levels"] if lv["price"] >= top - fp["step"]]
            if any(lv["ask"] > lv["bid"] for lv in top_levels):
                askgt += 1
        assert askgt >= 1, "falta footprint comprador en los niveles altos"
        # (3) flecha Sweep SMC (PDH sintético).
        sweeps = s.patterns("6E", "M15", 300)["analysis"]["patterns"]["sweeps"]
        assert any(w["type"] == "PDH_SWEEP" for w in sweeps)
        # (4) VP expandido (amplio frente al rango típico de 6E).
        vp = s.vp(bins=48)
        assert vp is not None and (vp["vah"] - vp["val"]) >= 0.004

    def test_sweep_and_reverse_favors_sell(self):
        # (5) El risk engine da score alto a la venta después de la reversión.
        s = _new_sim()
        _feed_sim(s, _load("sweep_and_reverse.jsonl"))
        candles = s.candles("M15", 300)
        cvd = s.cvd_series()
        pat = s.patterns("6E", "M15", 300)["analysis"]["patterns"]

        bear = _setup_sell_score(candles, cvd, pat)
        assert bear["components"]["cvd_of"]["value"] >= 0.8
        assert bear["components"]["smc"]["value"] >= 0.7
        bull = re_mod.setup_score(
            {"direction": "BUY", "cot": None, "cvd": cvd, "patterns": pat,
             "candles": candles},
            killzones=NY_KILLZONE, now=NOW_KZ,
        )
        assert bear["score"] > bull["score"]

        # Con COT bajista (macros reales a favor) el veredicto alcanza ALTA.
        bear_cot = _setup_sell_score(candles, cvd, pat,
                                     cot={"macro_bias": "BEARISH", "cot_index_26w": -8.0})
        assert bear_cot["score"] >= 80
        assert bear_cot["verdict"] == re_mod.VERDICT_ALTA

    def test_absorption_at_support_audit(self):
        trades = _load("absorption_at_support.jsonl")
        s = _new_sim()
        _feed_sim(s, trades)

        # (1) absorción dispara en el soporte (volumen masivo sin mover precio).
        eng = OrderFlowEngine()
        flags = []
        for t in trades:
            p = eng.add_trade(t["price"], t["size"], t["side"], t["ts"])
            if p and p.get("absorption"):
                flags.append(p["absorption"])
        assert flags, "la alerta de absorción no disparó"
        assert {f["direction"] for f in flags} == {"venta"}

        # (2) estancamiento: rango de la última ventana muy compacto.
        win = trades[-100:]
        prices = [t["price"] for t in win]
        assert (max(prices) - min(prices)) / (max(prices) + min(prices)) * 2 <= 0.0004

        # (3) CVD cae con el precio plano (divergencia visible).
        cvd = s.cvd_series()
        assert len(cvd) >= 30
        assert re_mod._trend_coef([p["value"] for p in cvd]) < 0
        assert eng.cvd < 0


class TestFvgExpansionAudit:
    """Escenario tendencia alcista + ineficiencia FVG (check-list del panel)."""

    def test_impulse_creates_fvg_and_order_block(self):
        trades = _load("fvg_expansion_trend.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)

        pat = s.patterns("6E", "M15", 300)["analysis"]["patterns"]

        # (1) FVGs bullish vivos (c3.low > c1.high), sin mitigación posterior.
        fvgs = pat["fvgs"]
        assert len(fvgs) >= 3, f"solo {len(fvgs)} FVGs detectados"
        assert all(f["type"] == "BULLISH_FVG" for f in fvgs)
        assert all(f["bottom"] < f["top"] for f in fvgs)

        # (2) Order Block comprador en la base del impulso (sin duplicados).
        obs = pat["order_blocks"]
        assert all(o["type"] == "BULLISH_OB" for o in obs)
        assert len(obs) == 1, f"OB duplicado ({len(obs)}): el BOS multi-vela repite la zona"
        ob = obs[0]
        # El OB es la vela bajista previa al impulso: queda bajo la base del
        # trozo alcista (que arranca en 1.0986), sin ser barrido por las velas.
        assert ob["bottom"] < ob["top"] < 1.0986

        # (3) Sin sweeps: solo hay impulso/consolidación (sin barridos falsos).
        assert pat["sweeps"] == []

    def test_impulse_drives_cvd_and_vp_up(self):
        trades = _load("fvg_expansion_trend.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)

        # (4) CVD fuertemente positivo y ascendente durante el impulso.
        assert eng.cvd > 4000
        assert re_mod._trend_coef([p["value"] for p in s.cvd_series()]) > 0

        # (5) VP: el POC se desplaza a niveles superiores al centro del ruido.
        vp = s.vp(bins=48)
        assert vp is not None
        assert vp["poc"] > 1.0985, f"POC {vp['poc']} no se desplazó al alza"
        assert vp["vah"] > 1.0995

    def test_impulse_fires_institutional_spikes(self):
        trades = _load("fvg_expansion_trend.jsonl")
        eng = OrderFlowEngine()
        _feed_engine(eng, trades)
        assert eng.snapshot()["spike_count"] >= 1

    def test_footprint_consistent_and_bullish_on_impulse(self):
        trades = _load("fvg_expansion_trend.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)

        fp = s.footprint()
        assert abs(sum(float(b["delta"]) for b in fp["bars"]) - eng.snapshot()["cvd"]) < 1e-3
        # Las velas del impulso (últimas 4 cerradas antes de la consolidación)
        # muestran delta positivo (agresión compradora en el footprint).
        impulse = fp["bars"][-6:-2]
        assert all(b["delta"] > 0 for b in impulse)


class TestRangeConsolidationAudit:
    """Escenario rango/consolidación: VP en campana SIN alertas falsas."""

    def test_no_false_signals(self):
        trades = _load("range_consolidation_vp.jsonl")
        eng = OrderFlowEngine()
        absorbs = []
        for t in trades:
            p = eng.add_trade(t["price"], t["size"], t["side"], t["ts"])
            if p and p.get("absorption"):
                absorbs.append(p["absorption"])
        # (1) Z bajo: 0 spikes (los filtros del Order Flow no disparan).
        assert eng.snapshot()["spike_count"] == 0
        # (2) Sin absorción: el rango de ventana queda FUERA del umbral.
        assert absorbs == []

    def test_no_smc_patterns_in_noise(self):
        s = _new_sim()
        _feed_sim(s, _load("range_consolidation_vp.jsonl"))
        pat = s.patterns("6E", "M15", 300)["analysis"]["patterns"]
        assert pat["fvgs"] == []
        assert pat["order_blocks"] == []

    def test_vp_bell_centered_on_base(self):
        s = _new_sim()
        _feed_sim(s, _load("range_consolidation_vp.jsonl"))
        vp = s.vp(bins=48)
        assert vp is not None
        # Campana centrada en el precio base y rango estrecho.
        center = (vp["vah"] + vp["val"]) / 2.0
        assert abs(center - 1.0985) <= 0.0001, f"centro del VP {center}"
        assert vp["val"] <= vp["poc"] <= vp["vah"]
        assert (vp["vah"] - vp["val"]) <= 0.0015

    def test_cvd_flat_and_event_bars_build(self):
        trades = _load("range_consolidation_vp.jsonl")
        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)
        # CVD sin dirección (paseo plano), dentro de un rango acotado.
        assert abs(eng.cvd) < 1000
        cvd = [p["value"] for p in s.cvd_series()]
        assert abs(re_mod._trend_coef(cvd)) < 0.001
        # Event bars por volumen se construyen a partir de los ticks sintéticos.
        eb = s.event_bars(bar_type="volbar", param=500)
        assert eb is not None and len(eb["bars"]) >= 1


class TestLatencyStressAudit:
    """Escenario de estrés: la agregación no se rompe y todo se mantiene
    consistente (proxy de que la UI aguantará el replay a 50 ticks/s)."""

    def test_stress_is_deterministic_and_consistent(self):
        trades = _load("latency_stress.jsonl")
        a, b = _new_sim(), _new_sim()
        _feed_sim(a, trades)
        _feed_sim(b, trades)
        assert a.candles("M15", 300) == b.candles("M15", 300)

        eng, s = OrderFlowEngine(), _new_sim()
        _feed_engine(eng, trades)
        _feed_sim(s, trades)
        assert s.state()["candles"] >= 50
        fp = s.footprint()
        assert abs(sum(float(x["delta"]) for x in fp["bars"]) - eng.snapshot()["cvd"]) < 1e-3

    def test_stress_volume_and_alerts(self):
        trades = _load("latency_stress.jsonl")
        eng = OrderFlowEngine()
        _feed_engine(eng, trades)
        snap = eng.snapshot()
        # Ráfagas de 80-300 lotes: volumen alto y spikes institucionales.
        assert snap["total_vol"] > 20000
        assert snap["spike_count"] >= 20

    def test_stress_event_bars_and_cvd_series(self):
        trades = _load("latency_stress.jsonl")
        s = _new_sim()
        _feed_sim(s, trades)
        assert s.cvd_series() != []
        assert s.event_bars(bar_type="volbar", param=500) is not None
        assert s.event_bars(bar_type="tickbar", param=100) is not None
        assert s.event_bars(bar_type="renko", param=5) is not None