"""Layer 1 — research/data: partes puras del export/caché offline.

No toca MT5 ni la terminal: se testean las funciones puras (_iter_history,
with_daily_levels, to_candle, csv/load) con datos sintéticos inyectados.
Ejecutar:  python -m pytest tests/test_research_data.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from research import data as rdata  # noqa: E402


SPACING = 900  # M15
BPD = 96  # velas por día M15


def _rows(days=3, dup_at=None):
    """Filas válidas de MT5 (listas) ascendentes, terminando en `now`."""
    now = 2_000_000_000
    n = days * BPD
    times = [now - (n - 1 - i) * SPACING for i in range(n)]
    rows = [[t, 1.10 + 1e-4 * (i % 7), 1.10 + 1e-4 * (i % 7) + 5e-5,
             1.10 + 1e-4 * (i % 7) - 5e-5, 1.10 + 1e-4 * (i % 7), 10 + i % 5, 2]
            for i, t in enumerate(times)]
    if dup_at is not None:
        rows.insert(dup_at, list(rows[dup_at]))
    return rows, now, times


class TestIterHistory:
    def _fetch_factory(self, rows, now):
        total = len(rows)

        def _fetch(pos, count):
            desc = list(reversed(rows))
            return desc[pos:pos + count]

        return _fetch

    def test_full_window(self):
        rows, now, times = _rows(days=3)
        out = list(rdata._iter_history(self._fetch_factory(rows, now), now, days=3))
        assert len(out) == 3 * BPD
        tss = [int(r[0]) for r in out]
        assert tss == sorted(tss, reverse=True)  # descendente (nueva → vieja)
        assert len(set(tss)) == len(tss)
        assert tss[0] == now
        assert tss[-1] == now - (3 * BPD - 1) * SPACING

    def test_cutoff_respects_days(self):
        rows, now, _ = _rows(days=3)
        out = list(rdata._iter_history(self._fetch_factory(rows, now), now, days=2))
        assert len(out) == 2 * BPD
        cutoff = now - 2 * 86400
        assert all(int(r[0]) > cutoff for r in out)
        assert int(out[-1][0]) == now - (2 * BPD - 1) * SPACING

    def test_stops_at_end_of_history(self):
        rows, now, _ = _rows(days=3)
        out = list(rdata._iter_history(self._fetch_factory(rows, now), now, days=30))
        assert len(out) == 3 * BPD  # solo lo disponible; fetch vacío corta el loop

    def test_dedup_within_chunk(self):
        rows, now, times = _rows(days=3, dup_at=15)
        out = list(rdata._iter_history(self._fetch_factory(rows, now), now, days=3))
        tss = [int(r[0]) for r in out]
        assert len(out) == 3 * BPD  # fila duplicada (n=15 y n=16) sellada
        assert len(set(tss)) == len(tss)


class TestDailyLevels:
    def _candles(self):
        def dt(y, m, d, hh, mm=0):
            return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp())

        # día0: highs 1040/1042/1041 · lows 1032/1030/1031 → pdh 1042 pdl 1030
        # día1: highs 1050/1055/1052 · lows 1044/1042/1045 → pdh 1055 pdl 1042
        # día2: highs 1060/1062/1061 · lows 1055/1053/1056
        base = 1.0
        d0 = [dt(2026, 9, 7, 8), dt(2026, 9, 7, 8, 15), dt(2026, 9, 7, 8, 30)]
        d1 = [dt(2026, 9, 8, 8), dt(2026, 9, 8, 8, 15), dt(2026, 9, 8, 8, 30)]
        d2 = [dt(2026, 9, 9, 8), dt(2026, 9, 9, 8, 15), dt(2026, 9, 9, 8, 30)]
        lows = {d0[0]: 0.1032, d0[1]: 0.1030, d0[2]: 0.1031,
                d1[0]: 0.1044, d1[1]: 0.1042, d1[2]: 0.1045,
                d2[0]: 0.1055, d2[1]: 0.1053, d2[2]: 0.1056}
        highs = {d0[0]: 0.1040, d0[1]: 0.1042, d0[2]: 0.1041,
                 d1[0]: 0.1050, d1[1]: 0.1055, d1[2]: 0.1052,
                 d2[0]: 0.1060, d2[1]: 0.1062, d2[2]: 0.1061}
        cs = []
        for t in d0 + d1 + d2:
            cs.append({"time": t, "open": 1.0 + lows[t],
                       "high": base + highs[t], "low": base + lows[t],
                       "close": base + highs[t], "volume": 10.0, "spread": 2.0})
        return cs

    def test_first_day_no_levels(self):
        cs = self._candles()
        out = rdata.with_daily_levels(cs)
        outs = {c["time"]: c for c in out}
        assert all(outs[t]["pdh"] is None and outs[t]["pdl"] is None
                   for t in (out[0]["time"], out[1]["time"], out[2]["time"]))

    def test_day1_uses_day0_range(self):
        out = rdata.with_daily_levels(self._candles())
        d1bar = out[4]["time"]
        assert out[4]["pdh"] == pytest.approx(1.1042)
        assert out[4]["pdl"] == pytest.approx(1.1030)

    def test_day2_uses_last_2_completed_days(self):
        out = rdata.with_daily_levels(self._candles())
        for c in out[6:]:
            assert c["pdh"] == pytest.approx(1.1055)  # max(day0, day1) high
            assert c["pdl"] == pytest.approx(1.1030)  # min(day0, day1) low

    def test_own_day_never_filters_its_levels(self):
        out = rdata.with_daily_levels(self._candles())
        last = out[-1]
        # high de la última vela del día2 (1.1062) NO sube el PDH (día sin cerrar)
        assert last["pdh"] == pytest.approx(1.1055)
        assert last["pdl"] == pytest.approx(1.1030)

    def test_prior_days_single(self):
        out = rdata.with_daily_levels(self._candles(), prior_days=1)
        for c in out[6:]:
            assert c["pdh"] == pytest.approx(1.1055)
            assert c["pdl"] == pytest.approx(1.1042)  # solo el día1 cerrado

    def test_input_order_is_sorted(self):
        cs = self._candles()
        shuffled = list(reversed(cs))
        out = rdata.with_daily_levels(shuffled)
        tss = [c["time"] for c in out]
        assert tss == sorted(tss)


class TestToCandle:
    def test_normalizes_types(self):
        c = rdata.to_candle({"time": "2000000000", "open": "1.10", "high": "1.12",
                             "low": "1.09", "close": "1.11",
                             "tick_volume": "10", "spread": "2"})
        assert c["time"] == 2_000_000_000
        assert isinstance(c["open"], float) and c["open"] == 1.10
        assert isinstance(c["volume"], float)
        assert isinstance(c["spread"], float)


class TestCsvRoundtrip:
    def test_write_read_load_and_fusion_dedup(self, tmp_path):
        base = 1_100_000_000
        c1 = [{"time": base + i * SPACING, "open": 1.10, "high": 1.11,
               "low": 1.09, "close": 1.105, "volume": 5.0, "spread": 2.0}
              for i in range(10)]
        p1 = tmp_path / f"EURUSD_M15_30d_20260901.csv"
        rdata.write_csv(str(p1), c1)
        # segundo archivo solapa 3 velas (dedup por time en load)
        c2 = [dict(c1[7]), dict(c1[8]), dict(c1[9])]
        c2 += [{"time": base + (10 + i) * SPACING, "open": 1.10, "high": 1.11,
                "low": 1.09, "close": 1.105, "volume": 5.0, "spread": 2.0}
               for i in range(5)]
        p2 = tmp_path / f"EURUSD_M15_30d_20260902.csv"
        rdata.write_csv(str(p2), c2)

        loaded = rdata.load_data(symbol="EURUSD", timeframe="M15", datadir=str(tmp_path))
        assert loaded is not None
        candles = loaded["candles"]
        assert len(candles) == 15  # 10 + 5 nuevos, los 3 solapados sellados
        tss = [c["time"] for c in candles]
        assert tss == sorted(tss) and len(set(tss)) == len(tss)

        ds = rdata.load_dataset(symbol="EURUSD", timeframe="M15",
                                days=1, datadir=str(tmp_path))
        assert ds is not None
        assert all("pdh" in c and "pdl" in c for c in ds["candles"])

    def test_load_returns_none_without_files(self, tmp_path):
        assert rdata.load_data(symbol="EURUSD", timeframe="M15",
                               datadir=str(tmp_path)) is None


class TestExport:
    def test_export_writes_csv_and_meta(self, tmp_path):
        rows, now, _ = _rows(days=3)

        def _fetch(pos, count):
            desc = list(reversed(rows))
            return desc[pos:pos + count]

        res = rdata.export(symbol="EURUSD", timeframe="M15", days=3,
                           outdir=str(tmp_path), now_ts=now, fetch=_fetch)
        assert res["bars"] == 3 * BPD
        assert Path(res["path"]).exists()
        assert Path(res["meta_path"]).exists()

        reloaded = rdata.load_data(symbol="EURUSD", timeframe="M15",
                                   datadir=str(tmp_path))
        assert reloaded is not None
        assert len(reloaded["candles"]) == 3 * BPD

    def test_export_invalid_tf(self, tmp_path):
        with pytest.raises(ValueError):
            rdata.export(symbol="EURUSD", timeframe="XYZ", days=3,
                         outdir=str(tmp_path), now_ts=2_000_000_000,
                         fetch=lambda pos, count: [])