"""Mock feed generativo para Order Flow 6E (offline, sin Databento).

Genera trades con la MISMA forma que consume `add_trade` de app.py:
    {"ts": <epoch float>, "price": <float>, "size": <int>, "side": "A"|"B"}
Semántica: A = Ask (agresor que compra a mercado), B = Bid (agresor que vende a
mercado).

Módulo puro: NO importa app.py (evita circularidad), no toca red y es
determinista (cada stream usa un random.Random(seed) local). Sirve para validar
el cableado WS/UI, el ciclo completo de alertas y la latencia sin licencia
Databento. Umbrales espejo del engine (app.py) — mantener sincronizados:
    ZSCORE_THRESHOLD     = OF_ZSCORE_THRESHOLD
    ABSORB_VOL_MIN       = OF_ABSORB_VOL_MIN
    ABSORB_RANGE_RATIO   = OF_ABSORB_RANGE_RATIO
    ABSORB_DELTA_RATIO   = OF_ABSORB_DELTA_RATIO
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, Iterator, List

ZSCORE_THRESHOLD = 2.5
ABSORB_VOL_MIN = 40
ABSORB_RANGE_RATIO = 0.0004
ABSORB_DELTA_RATIO = 0.25

DEFAULT_BASE_PRICE = 1.0985
DEFAULT_PRICE_STEP = 0.00005  # 0.5 pips para 6E
_START_TS = 1_700_000_000.0

SCENARIOS: Dict[str, dict] = {
    "noise": {"kind": "generated", "regime": "noise"},
    "spike": {"kind": "generated", "regime": "spike"},
    "absorption": {"kind": "generated", "regime": "absorption"},
    "stress": {"kind": "generated", "regime": "stress"},
    "fixture_noise": {"kind": "fixture", "path": "tests/fixtures/orderflow_6e_noise.jsonl"},
    "fixture_spike": {"kind": "fixture", "path": "tests/fixtures/orderflow_6e_spike.jsonl"},
    "fixture_absorption": {"kind": "fixture", "path": "tests/fixtures/orderflow_6e_absorption.jsonl"},
    "sweep_and_reverse": {"kind": "fixture", "path": "tests/fixtures/sweep_and_reverse.jsonl"},
    "absorption_at_support": {"kind": "fixture", "path": "tests/fixtures/absorption_at_support.jsonl"},
    "fvg_expansion_trend": {"kind": "fixture", "path": "tests/fixtures/fvg_expansion_trend.jsonl"},
    "range_consolidation_vp": {"kind": "fixture", "path": "tests/fixtures/range_consolidation_vp.jsonl"},
    # regime=stress -> el listener lo reinyecta a 50 ticks/s en batch de 5.
    "latency_stress": {"kind": "fixture", "path": "tests/fixtures/latency_stress.jsonl",
                       "regime": "stress"},
}


# ---------------------------------------------------------------------------
# Load / replay de fixtures .jsonl
# ---------------------------------------------------------------------------

def _resolved(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parent / p


def load_fixture(path: str) -> List[dict]:
    """Carga un .jsonl de trades (una línea por trade) validando el shape."""
    trades: List[dict] = []
    with open(_resolved(path), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if not {"ts", "price", "size", "side"} <= set(t):
                raise ValueError(f"trade sin shape completo en {path}: {t}")
            if t["side"] not in ("A", "B"):
                raise ValueError(f"side inválido en {path}: {t['side']!r}")
            trades.append(t)
    return trades


def replay(path: str) -> Iterator[dict]:
    """Reproduce un fixture .jsonl trade a trade (streaming sin cargar todo)."""
    with open(_resolved(path), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


# ---------------------------------------------------------------------------
# Generadores por régimen
# ---------------------------------------------------------------------------

def _emit(price: float, size: int, side: str) -> dict:
    return {"price": round(float(price), 5), "size": int(size), "side": side}


def _gen_noise(rng: random.Random, count, base_price, step):
    """Régimen normal: deltas ~N(0), tamaños moderados, sin alertas.

    El paseo de precio, ancho suficiente (~1.6 pasos/trade), mantiene la ventana
    de absorción fuera de umbral (rango > 4.4 pips en 6E) y los tamaños
    estables no cruzan la Z del engine.
    """
    price = base_price
    for _ in range(count):
        side = "A" if rng.random() < 0.5 else "B"
        size = max(1, int(round(rng.gauss(12, 2.5))))
        price += rng.gauss(0, step * 1.6)
        yield _emit(price, size, side)


def _gen_spike(rng: random.Random, count, base_price, step):
    """Régimen con ráfagas atípicas que cruzan Z >= umbral."""
    price = base_price
    for i in range(count):
        if i > 0 and i % 40 == 0:
            side = "A" if rng.random() < 0.6 else "B"
            size = int(round(rng.uniform(150, 250)))
            price += rng.gauss(0, step)
        else:
            side = "A" if rng.random() < 0.5 else "B"
            size = max(1, int(round(rng.gauss(12, 2.5))))
            price += rng.gauss(0, step * 1.6)
        yield _emit(price, size, side)


def _gen_absorption(rng: random.Random, count, base_price, step):
    """Régimen de absorción: rango estrecho, volumen alto, |delta_ratio| bajo."""
    level = base_price
    half = 1.5 * step
    for i in range(count):
        price = level + rng.uniform(-half, half)
        side = "A" if i % 2 == 0 else "B"
        size = int(round(rng.uniform(4, 7)))
        yield _emit(price, size, side)


def _gen_stress(rng: random.Random, count, base_price, step):
    """Régimen de alta frecuencia: se reinyecta rápido, sin exigir alertas."""
    price = base_price
    for _ in range(count):
        side = "A" if rng.random() < 0.5 else "B"
        size = max(1, int(round(rng.gauss(8, 2))))
        price += rng.gauss(0, step * 0.8)
        yield _emit(price, size, side)


_GENERATORS = {
    "noise": _gen_noise,
    "spike": _gen_spike,
    "absorption": _gen_absorption,
    "stress": _gen_stress,
}


def gen_stream(regime: str = "noise", count: int = 300, seed: int = 7,
               base_price: float = DEFAULT_BASE_PRICE,
               price_step: float = DEFAULT_PRICE_STEP) -> Iterator[dict]:
    """Stream determinista de trades para el régimen pedido.

    Misma semilla + mismos args -> misma secuencia exacta (los `size`/`side`/
    `price` sólo dependen del random.Random local). Los `ts` son incrementales
    para que el stream sea reproducible; el listener puede remapearlos a
    time.time() al reinyectarlos en vivo.
    """
    gen = _GENERATORS.get(regime)
    if gen is None:
        raise ValueError(f"régimen desconocido: {regime!r}")
    rng = random.Random(seed)
    for i, t in enumerate(gen(rng, count, float(base_price), float(price_step))):
        t["ts"] = _START_TS + i * 1.0
        yield t


# ---------------------------------------------------------------------------
# Generadores de escenarios integrados (.jsonl deterministas)
# ---------------------------------------------------------------------------
#
# Su objetivo es que TODAS las herramientas respondan a un mismo mercado: el
# script gen_fixtures escribe estos .jsonl y el MarketSimulator (simulator.py)
# los convierte en velas/footprint/VP para que la auditoría visual en pantalla
# pueda verificar el escenario completo (sweep SMC + CVD + footprint + risk).

def _stamp(trades_lst: List[dict], start_ts: float = _START_TS) -> List[dict]:
    """Asigna ts incrementales (1s por tick) a una lista de trades."""
    for i, t in enumerate(trades_lst):
        t["ts"] = start_ts + i * 1.0
    return trades_lst


def build_sweep_reverse_trades(seed: int = 11, total: int = 975) -> List[dict]:
    """Escenario Sweep & Reverse (determinista): impulso comprador que rompe el
    PDH sintético de la sesión pasada con volumen alto (wick), cierre de vuelta
    dentro del rango (sweep) y reversión agresiva vendedora (spikes Z >= 2.5).

    El número total de ticks es múltiplo fijo de 25 (ticks/velas del simulador)
    y la primera sesión (40% de las velas) define el PDH que se rompe.

    Devuelve ticks [{ts, price, size, side}] listos para escibir a .jsonl.
    """
    rng = random.Random(seed)
    step = DEFAULT_PRICE_STEP
    base = DEFAULT_BASE_PRICE
    warmup_n = 400      # primera sesión simulada → se deriva PDH/PDL
    breakout_n = 150
    sweep_n = 25        # vela con mecha sobre PDH + cierre bajo PDH
    reversal_n = 400

    out: List[dict] = []
    prices: List[float] = []

    # 1) Ruido normal (define el rango de la sesión pasada).
    price = base
    for _ in range(warmup_n):
        price += rng.gauss(0, step * 1.6)
        side = "A" if rng.random() < 0.5 else "B"
        size = max(1, int(round(rng.gauss(12, 2.5))))
        prices.append(price)
        out.append(_emit(price, size, side))

    # PDH sintético = máximo de la primera sesión simulada (la que ve el sim).
    pdh = max(prices[: int(warmup_n * 0.9375)])  # primeras 375/400 ticks
    pdl = min(prices[: int(warmup_n * 0.9375)])

    # 2) Impulso: rompe el PDH con agresión compradora creciente (FVG al alza).
    start = price
    for i in range(1, breakout_n + 1):
        progress = i / breakout_n
        target = pdh + (pdh - pdl) * 0.6
        price = start + (target - start) * progress + rng.gauss(0, step * 0.9)
        side = "A"
        size = int(round(rng.uniform(15, 60) * (0.5 + progress)))
        out.append(_emit(price, size, side))

    # 3) Vela sweep: mecha cierra fuera, cierre dentro (sweep de PDH).
    peak = price
    for _ in range(8):
        price += step * (2 + rng.uniform(0, 1.5))
        out.append(_emit(price, int(round(rng.uniform(20, 60))), "A"))
    for i in range(sweep_n - 8):
        price -= step * (2.5 + rng.uniform(0, 2.5))
        side = "B"
        size = int(round(rng.uniform(150, 500)))  # spike vendedor
        out.append(_emit(price, size, side))

    # 4) Reversión: retrazo a través del rango de la sesión cerrando
    #    ligeramente por debajo del PDL, con sesgo vendedor y ráfagas atípicas
    #    (spikes vendedores Z >= 2.5). Acotada al rango para no destruir la
    #    escala del mercado (uniendo sweep SMC + CVD bajista + VP amplio).
    start = price
    rev_target = pdl - (pdh - pdl) * 0.35
    for i in range(reversal_n):
        progress = (i + 1) / reversal_n
        price = start + (rev_target - start) * progress + rng.gauss(0, step * 1.4)
        price = max(price, rev_target - step * 6)
        side = "B" if rng.random() < 0.68 else "A"
        if i % 30 == 0:
            size = int(round(rng.uniform(200, 380)))
        else:
            size = max(1, int(round(rng.gauss(15, 3))))
        out.append(_emit(price, size, side))

    return _stamp(out[:total], _START_TS)


def build_absorption_trades(seed: int = 13, total: int = 900) -> List[dict]:
    """Escenario Absorción en soporte (determinista): caída a una zona de soporte,
    estancamiento con volumen masivo alternado de poco rango (dispara la alerta de
    absorción del engine) y leve exceso vendedor → CVD cae mientras el precio se
    queda plano (divergencia visible en la UI).

    Devuelve ticks [{ts, price, size, side}] listos para escibir a .jsonl.
    """
    rng = random.Random(seed)
    step = DEFAULT_PRICE_STEP
    base = DEFAULT_BASE_PRICE

    out: List[dict] = []
    warmup_n = 300
    drift_n = 150
    absorb_n = 450
    total = max(int(total), warmup_n + drift_n + absorb_n)

    # 1) Ruido con leve sesgo vendedor (bajada inicial).
    price = base
    for _ in range(warmup_n):
        price += rng.gauss(0, step * 1.4)
        side = "A" if rng.random() < 0.47 else "B"
        out.append(_emit(price, max(1, int(round(rng.gauss(10, 2.5)))), side))

    # 2) Impulso bajista hacia el soporte.
    start = price
    for i in range(1, drift_n + 1):
        progress = i / drift_n
        price = start - progress * (start - (base - 0.0012)) + rng.gauss(0, step * 0.8)
        price = max(price, base - 0.0012 - step * 3)
        out.append(_emit(price, int(round(rng.uniform(10, 30))), "B"))

    # Nivel de soporte (zona de estancamiento).
    support = round(price, 5)
    half = 0.6 * step

    # 3) Absorción: rango estrecho, volumen alto, |delta_ratio| dentro del
    #    umbral del engine (<= 0.25) con leve exceso vendedor periódico:
    #    la alerta de absorción dispara (dirección "venta") mientras el precio
    #    se queda plano y el CVD cae (divergencia visible en la UI).
    for i in range(absorb_n):
        px = support + rng.uniform(-half, half)
        if i % 8 == 0:
            side = "B"
            size = int(round(rng.uniform(10, 16)))
        else:
            side = "A" if i % 2 == 0 else "B"
            size = int(round(rng.uniform(5, 12)))
        out.append(_emit(px, size, side))

    return _stamp(out[:total], _START_TS)


def build_fvg_expansion_trades(seed: int = 17, total: int = 425) -> List[dict]:
    """Escenario Tendencia Alcista + Ineficiencia FVG (determinista).

    Estructura (17 velas de 25 ticks):
      - 250 ticks de ruido mean-reverting con un PICO de liquidez en la vela 5
        (ticks 125-149): ese pico es el swing high (ventana 5 de pattern_engine)
        Y el PDH de la sesión (session_frac lo incluye) -> el BOS posterior lo
        rompe y nace el Order Block comprador en el pullback.
      - 25 ticks: vela bajista de pullback -> Order Block comprador.
      - 100 ticks: 4 velas alcistas con bandas DISJUNTAS (gap 2 pasos, span 6
        pasos, por encima del centro del warmup) -> FVG bullish vivos
        (c3.low > c1.high) sin mitigación y POC del VP desplazado al alza.
      - 50 ticks: consolidación en el techo (no entra en las zonas).

    Tamaños en {9,10,11} (tras descenso inicial): Z-score estacionario ~1.2,
    sin spikes de arranque frío; el impulso (40-100) sí dispara spikes
    institucionales legítimos.

    Devuelve ticks [{ts, price, size, side}] listos para escibir a .jsonl.
    """
    rng = random.Random(seed)
    step = DEFAULT_PRICE_STEP
    base = DEFAULT_BASE_PRICE
    warmup_n = 250
    pullback_n = 25
    impulse_n = 100
    total = max(int(total), warmup_n + pullback_n + impulse_n)

    out: List[dict] = []

    # 1) Ruido mean-reverting + pico de liquidez en la vela 5 (ticks 125-149).
    peak = base + 20 * step
    price = base
    for i in range(warmup_n):
        if i < 125:
            price += (base - price) * 0.05 + rng.gauss(0, step * 1.5)
            side = "A" if rng.random() < 0.5 else "B"
        elif i < 137:
            price = base + (peak - base) * (i - 124) / 12.0
            side = "A" if rng.random() < 0.75 else "B"
        elif i < 149:
            price = peak - (peak - base) * (i - 136) / 12.0
            side = "B" if rng.random() < 0.75 else "A"
        else:
            price += (base - price) * 0.05 + rng.gauss(0, step * 1.5)
            side = "A" if rng.random() < 0.5 else "B"
        if i < 5:
            size = (16, 14, 12, 10, 9)[i]  # descenso: evita spike de arranque
        else:
            size = rng.choice((9, 10, 11))
        out.append(_emit(price, size, side))

    # 2) Pullback: vela claramente bajista (close < open) -> OB candidato.
    pb_start = price
    for i in range(pullback_n):
        price = pb_start - (8 * step) * (i + 1) / pullback_n + rng.gauss(0, step * 0.2)
        side = "B" if rng.random() < 0.7 else "A"
        out.append(_emit(price, rng.choice((9, 10, 11)), side))

    # 3) Impulso: 4 velas de 25 ticks, bandas disjuntas y crecientes, por
    #    ENCIMA del centro del warmup (el POC del VP se desplaza hacia arriba:
    #    ~417 volumen/nivel de impulso vs ~270 del centro del ruido).
    gap, span = 2 * step, 6 * step
    lo = base + 2 * step
    for _ in range(4):
        for i in range(25):
            px = lo + span * i / 24 + rng.gauss(0, step * 0.15)
            out.append(_emit(px, int(round(rng.uniform(70, 130))), "A"))
        lo = lo + span + gap
    roof = lo - gap  # high de la 4ta vela del impulso

    # 4) Consolidación en el techo: balanceada, sin entrar en las zonas.
    for _ in range(total - (warmup_n + pullback_n + impulse_n)):
        px = roof + 5 * step + rng.gauss(0, step * 0.6)
        side = "A" if rng.random() < 0.5 else "B"
        out.append(_emit(px, rng.choice((9, 10, 11)), side))

    return _stamp(out[:total], _START_TS)


def build_range_consolidation_trades(seed: int = 19, total: int = 750) -> List[dict]:
    """Escenario Rango / Consolidación (determinista).

    Paseo mean-reverting (OU) alrededor de base durante 30 velas: el volumen se
    concentra en el centro (VP en campana con POC central) y el rango de la
    ventana mantiene la absorción FUERA de umbral. Los tamaños {9,10,11} (tras
    un descenso inicial que evita el spike de arranque frío del Z-score, que
    dispara z=+4.95 en el tick 2 si s2>s1) mantienen |z| ~ 1.2 < 1.5 -> 0
    spikes y sin alertas falsas.

    Devuelve ticks [{ts, price, size, side}] listos para escibir a .jsonl.
    """
    rng = random.Random(seed)
    step = DEFAULT_PRICE_STEP
    base = DEFAULT_BASE_PRICE

    out: List[dict] = []
    price = base
    for i in range(total):
        price += (base - price) * 0.05 + rng.gauss(0, step * 2.2)
        side = "A" if rng.random() < 0.5 else "B"
        if i < 5:
            size = (16, 14, 12, 10, 9)[i]  # descenso: evita spike de arranque
        else:
            size = rng.choice((9, 10, 11))
        out.append(_emit(price, size, side))

    return _stamp(out[:total], _START_TS)


def build_latency_stress_trades(seed: int = 23, total: int = 1500) -> List[dict]:
    """Escenario Test de Estrés a Alta Frecuencia (determinista).

    1500 ticks (60 velas) con saltos abruptos de precio (2-12 pasos por tick,
    lado del salto = lado agresor) y ráfagas de tamaño cada 10 ticks. Pensado
    para verificar que la UI aguante el replay a 50 ticks/s en batch (regimen
    "stress" del listener) sin congelar ECharts ni desincronizar el WS.

    Devuelve ticks [{ts, price, size, side}] listos para escibir a .jsonl.
    """
    rng = random.Random(seed)
    step = DEFAULT_PRICE_STEP
    price = DEFAULT_BASE_PRICE

    out: List[dict] = []
    for i in range(total):
        jump = (1 if rng.random() < 0.5 else -1) * step * rng.uniform(2, 12)
        price += jump
        if i % 10 == 0:
            size = int(round(rng.uniform(80, 300)))
        else:
            size = max(1, int(round(rng.gauss(10, 4))))
        out.append(_emit(price, size, "A" if jump > 0 else "B"))

    return _stamp(out[:total], _START_TS)


def write_fixtures(target_dir: str = "tests/fixtures") -> List[str]:
    """Escribe los .jsonl de escenarios integrados (deterministas)."""
    import os
    from pathlib import Path

    dst = Path(_resolved(target_dir))
    dst.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "sweep_and_reverse.jsonl": build_sweep_reverse_trades(),
        "absorption_at_support.jsonl": build_absorption_trades(),
        "fvg_expansion_trend.jsonl": build_fvg_expansion_trades(),
        "range_consolidation_vp.jsonl": build_range_consolidation_trades(),
        "latency_stress.jsonl": build_latency_stress_trades(),
    }
    written = []
    for name, trades in fixtures.items():
        path = dst / name
        with open(path, "w", encoding="utf-8") as f:
            for t in trades:
                f.write(json.dumps(t) + "\n")
        written.append(str(path))
    return written


if __name__ == "__main__":
    import os

    for p in write_fixtures():
        print(f"generado: {os.path.abspath(p)}")