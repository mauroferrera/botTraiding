import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional

import store

LOG = logging.getLogger("cot")

# Fuentes oficiales CFTC (Socrata, sin API key). Verificadas en vivo:
#  - TFF "Traders in Financial Futures" (gpe5-46if): categoría financiera con
#    Asset Managers (asset_mgr_*) y Leveraged Money (lev_money_*). Es la
#    evolución del antiguo "suplementario financiero" donde se desglosa el
#    Managed Money del reporte disaggregated para futuros financieros.
#  - Legacy "Futures Only" (6dca-aqww): posiciones Non-Commercial (especulador)
#    del mismo contrato. Con él se calcula el índice COT 26 semanas clásico.
TFF_DATASET = "gpe5-46if"
LEGACY_DATASET = "6dca-aqww"
MARKET = "EURO FX - CHICAGO MERCANTILE EXCHANGE"
SYMBOL = "EURUSD"
BASE_URL = "https://publicreporting.cftc.gov/resource"
FETCH_LIMIT = 60
TIMEOUT = 30

INDEX_WINDOW = 26
MIN_INDEX_WEEKS = 2
IDX_BULL_LOW = 25.0
IDX_BEAR_HIGH = 75.0
SCORE_BULL = 0.5
SCORE_BEAR = -0.5


def _socrata(dataset: str, cols: str) -> List[dict]:
    """Consulta SoQL al dataset Socrata de la CFTC para el contrato EURO FX."""
    sql = (
        f"select {cols} where market_and_exchange_names = '{MARKET}' "
        f"order by report_date_as_yyyy_mm_dd desc limit {FETCH_LIMIT}"
    )
    url = f"{BASE_URL}/{dataset}.json?$query={urllib.parse.quote(sql)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        LOG.warning("COT fetch falló (%s): %s", dataset, exc)
        return []
    return rows or []


def fetch_reports(limit: int = FETCH_LIMIT) -> List[dict]:
    """Fusiona TFF + Legacy por fecha de reporte; series asc por fecha."""
    tff = _socrata(
        TFF_DATASET,
        "report_date_as_yyyy_mm_dd, asset_mgr_positions_long, asset_mgr_positions_short, "
        "lev_money_positions_long, lev_money_positions_short",
    )
    leg = _socrata(
        LEGACY_DATASET,
        "report_date_as_yyyy_mm_dd, noncomm_positions_long_all, noncomm_positions_short_all",
    )
    tff = {r["report_date_as_yyyy_mm_dd"][:10]: r for r in tff}
    leg = {r["report_date_as_yyyy_mm_dd"][:10]: r for r in leg}

    merged = []
    for d in sorted(set(tff) & set(leg), reverse=True)[:limit]:
        a, b = tff[d], leg[d]
        merged.append(
            {
                "report_date": d,
                "am_net": int(a["asset_mgr_positions_long"]) - int(a["asset_mgr_positions_short"]),
                "lf_net": int(a["lev_money_positions_long"]) - int(a["lev_money_positions_short"]),
                "nc_net": int(b["noncomm_positions_long_all"]) - int(b["noncomm_positions_short_all"]),
            }
        )
    merged.reverse()
    return merged


def _norm(xs: List[float]) -> List[float]:
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    if hi - lo == 0:
        return [0.0] * len(xs)
    return [2.0 * (x - lo) / (hi - lo) - 1.0 for x in xs]


def _make_report(stored: List[dict]) -> Optional[dict]:
    """macro_bias DETERMINISTA con la precedencia aprobada:
        1) si el índice 26w es válido (>= 2 semanas): <25 => BULLISH, >75 => BEARISH.
        2) si no, o si el índice queda neutro: score = 0.6·norm(ΔAM) + 0.4·norm(−ΔLF)
           con umbrales ±0.5.
    Devuelve None si no hay reportes almacenados. Nunca inventa cifras."""
    if not stored:
        return None
    rep = sorted(stored, key=lambda r: r["report_date"])
    latest = rep[-1]

    am_vals = [r["am_net"] for r in rep]
    lf_vals = [r["lf_net"] for r in rep]
    d_am = [rep[i]["am_net"] - rep[i - 1]["am_net"] for i in range(1, len(rep))] if len(rep) > 1 else []
    d_lf = [rep[i]["lf_net"] - rep[i - 1]["lf_net"] for i in range(1, len(rep))] if len(rep) > 1 else []
    n_am = _norm(d_am)
    n_lf = _norm([-x for x in d_lf])
    score = round(0.6 * n_am[-1] + 0.4 * n_lf[-1], 3) if n_am else None

    window = rep[-INDEX_WINDOW:]
    nc = [r["nc_net"] for r in window]
    lo_i, hi_i = min(nc), max(nc)
    cot_index = round((latest["nc_net"] - lo_i) / (hi_i - lo_i) * 100.0, 1) if hi_i != lo_i else 50.0
    index_valid = len(window) >= MIN_INDEX_WEEKS

    bias = "NEUTRAL"
    if index_valid and cot_index < IDX_BULL_LOW:
        bias = "BULLISH"
    elif index_valid and cot_index > IDX_BEAR_HIGH:
        bias = "BEARISH"
    elif score is not None and score >= SCORE_BULL:
        bias = "BULLISH"
    elif score is not None and score <= SCORE_BEAR:
        bias = "BEARISH"

    return {
        "report_date": latest["report_date"],
        "asset_managers_net": latest["am_net"],
        "leveraged_funds_net": latest["lf_net"],
        "non_commercial_net": latest["nc_net"],
        "delta_asset_managers": round(d_am[-1], 0) if d_am else None,
        "delta_leveraged_funds": round(d_lf[-1], 0) if d_lf else None,
        "score": score,
        "cot_index_26w": cot_index,
        "index_valid": index_valid,
        "macro_bias": bias,
        "symbol": SYMBOL,
    }


def build_report(stored: List[dict]) -> Optional[dict]:
    return _make_report(stored)


def sync() -> Optional[dict]:
    """Descarga el COT CFTC, lo persiste en cot_reports y devuelve el reporte último.

    Persiste la serie cruda y, tras calcular el reporte derivado, actualiza la
    fecha más reciente con cot_index_26w / macro_bias / deltas para que el
    visor muestre el sesgo vigente en la BD (no solo en vivo)."""
    rows = fetch_reports()
    if not rows:
        return None
    for r in rows:
        store.upsert_cot_report(
            r["report_date"], r["am_net"], r["lf_net"], r["nc_net"],
            cot_index=None, macro_bias=None, delta_am=None, delta_lf=None,
        )
    rep = _make_report(store.list_cot_reports())
    if rep:
        store.upsert_cot_report(
            rep["report_date"],
            rep["asset_managers_net"],
            rep["leveraged_funds_net"],
            rep["non_commercial_net"],
            cot_index=rep["cot_index_26w"],
            macro_bias=rep["macro_bias"],
            delta_am=rep["delta_asset_managers"],
            delta_lf=rep["delta_leveraged_funds"],
        )
    return rep