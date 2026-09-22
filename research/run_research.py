#!/usr/bin/env python3
"""CLI del pipeline de research (offline/backtesting/calibración).

Pipeline SEPARADO del runtime: no toca app/agent/watcher ni strategy.yaml.
Ejecuta desde la raíz del repo (abrir terminal MT5 solo en `export`):

  python research/run_research.py export --symbol EURUSD --timeframe M15 --days 90

Subcomandos (Steps 2-4): backtest | calibrate | report | validate.
Ejemplos:

  python research/run_research.py export --symbol EURUSD --timeframe M15 --days 90
  python research/run_research.py validate --symbol EURUSD --timeframe M15 --days 90
  python research/run_research.py backtest --symbol EURUSD --timeframe M15 --days 90
  python research/run_research.py calibrate --symbol EURUSD --timeframe M15 --days 90
  python research/run_research.py report --run research/results/EURUSD_M15_foo_bt.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from research import data as rdata  # noqa: E402


def _human_ts(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _cmd_export(args: argparse.Namespace) -> int:
    print(
        f"Exportando {args.symbol} {args.timeframe} (últimos {args.days} días) "
        "con la terminal MT5 abierta…"
    )
    try:
        res = rdata.export(
            symbol=args.symbol,
            timeframe=args.timeframe,
            days=args.days,
            outdir=args.datadir,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    eff_days = (res["last_time"] - res["first_time"]) / 86400.0
    print(f"  OK  {res['bars']} velas")
    print(f"      rango : {_human_ts(res['first_time'])} → {_human_ts(res['last_time'])} "
          f"(~{eff_days:.1f} días de historial)")
    print(f"      csv   : {res['path']}")
    print(f"      meta  : {res['meta_path']}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415

    from research import metrics as rm  # noqa: PLC0415
    from research import sim  # noqa: PLC0415
    from research import report as rreport  # noqa: PLC0415

    ds = _load_dataset(args)
    if ds is None:
        return 1
    try:
        cfg = _build_cfg(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    bt = sim.BarBacktest(ds["candles"], cfg=cfg)
    res = bt.run()
    trades = res["trades"]
    m = rm.compute_metrics(trades, symbol=args.symbol, timeframe=args.timeframe)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = _results_dir(args) / f"{args.symbol}_{args.timeframe}_{day}_bt.json"
    payload = _payload(res, m)
    with open(out_path, "w", encoding="utf-8") as fh:
        _json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(rreport.render_report(res, m, payload["breakdowns"], max_rows=40))
    print(f"  JSON  : {out_path}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415

    from research import calibrator  # noqa: PLC0415
    from research import metrics as rm  # noqa: PLC0415
    from research import report as rreport  # noqa: PLC0415
    from research import sim  # noqa: PLC0415

    ds = _load_dataset(args)
    if ds is None:
        return 1
    try:
        cfg = _build_cfg(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    bt = sim.BarBacktest(ds["candles"], cfg=cfg)
    res = bt.run()
    trades = res["trades"]
    m = rm.compute_metrics(trades, symbol=args.symbol, timeframe=args.timeframe)

    baseline = sim.load_trading_cfg()  # strategy.yaml/store VIGENTE (nunca se escribe)
    cal = calibrator.suggest(cfg=cfg, trades=trades, metrics=m, baseline=baseline)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = _results_dir(args) / f"{args.symbol}_{args.timeframe}_{day}_cal.json"
    payload = {
        **_payload(res, m),
        "suggestions": cal["suggestions"],
        "warnings": cal["warnings"],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        _json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(rreport.render_report(res, m, payload["breakdowns"],
                                suggestions=cal["suggestions"],
                                warnings=cal["warnings"], max_rows=40))
    print(f"  JSON  : {out_path}  (sugerencias NUNCA sobreescriben strategy.yaml)")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415

    from research import report as rreport  # noqa: PLC0415

    try:
        with open(args.run, "r", encoding="utf-8") as fh:
            payload = _json.load(fh)
    except OSError as exc:
        print(f"ERROR: no leo {args.run}: {exc}", file=sys.stderr)
        return 1
    text = rreport.render_payload(payload, max_rows=args.rows)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"  guardado en {args.out}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415

    from research import validate as rval  # noqa: PLC0415

    ds = _load_dataset(args)
    if ds is None:
        return 1
    try:
        cfg = _build_cfg(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = rval.validate_dataset(ds["candles"], cfg, sample=args.sample)
    print(f"Validación {args.symbol} {args.timeframe}:")
    print(rval.summarize(result) or "  (sin datos)")

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = _results_dir(args) / f"{args.symbol}_{args.timeframe}_{day}_val.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        _json.dump({"dataset": {"symbol": args.symbol, "timeframe": args.timeframe,
                                "candles": result["n_bars"]},
                    "checks": result["checks"],
                    "lookahead_checked": result["lookahead_checked"],
                    "lookahead_mismatches": result["lookahead_mismatches"],
                    "warnings": result["warnings"],
                    "tf_sec": result["tf_sec"]},
                   fh, indent=2, ensure_ascii=False)
    print(f"  JSON  : {out_path}")

    ok = all(result["checks"].values())
    if not ok:
        print("  VALIDACIÓN CON FALLOS: no confíes en un backtest sobre estos datos.",
              file=sys.stderr)
        return 1
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415

    from research import search as rsearch  # noqa: PLC0415

    ds = _load_dataset(args)
    if ds is None:
        return 1
    try:
        cfg = _build_cfg(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    grid = rsearch.DEFAULT_GRID
    if args.grid:
        try:
            grid = _json.loads(args.grid)
        except _json.JSONDecodeError:
            print(f"ERROR: --grid debe ser JSON (p. ej. "
                  f"'{{\"min_score\":[65,75]}}').", file=sys.stderr)
            return 1
    if not isinstance(grid, dict) or not grid:
        print("ERROR: --grid debe ser un dict con listas de valores.", file=sys.stderr)
        return 1

    print(f"Buscando {args.symbol} {args.timeframe} sobre "
          f"{len(ds['candles'])} velas…")
    result = rsearch.search_grid(ds["candles"], base_cfg=cfg, grid=grid,
                                 top_n=args.top, min_filled=args.min_filled,
                                 symbol=args.symbol, timeframe=args.timeframe)

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = _results_dir(args) / f"{args.symbol}_{args.timeframe}_{day}_search.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        _json.dump({"dataset": {"symbol": args.symbol, "timeframe": args.timeframe,
                                "n_bars": len(ds["candles"])},
                    **{k: v for k, v in result.items() if k != "results"},
                    "top_n": args.top,
                    "results": result["results"]},
                   fh, indent=2, ensure_ascii=False)

    _print_search(result)
    print(f"  JSON  : {out_path}")
    return 0


def _print_search(result: dict) -> None:
    print(f"\nGrid search · {result['combos']} combinaciones "
          f"(mín. {result['min_filled']} fills para rankear) · "
          f"mejores {len(result.get('results') or [])} de {result['total']}:")
    for r in (result.get("results") or []):
        if r.get("error"):
            print(f"  {r['params']}  -> ERROR {r['error']}")
            continue
        m = r["metrics"] or {}
        params = " ".join(f"{k}={v}" for k, v in r["params"].items()) or "base"
        flag = "  ⚠ muestra insuficiente" if r.get("underpowered") else ""
        print(f"  {params:<32} fills={m.get('n_filled')}  "
              f"WR={_fmt(m.get('win_rate'))}%  E={_fmt(m.get('expectancy_r'))}R  "
              f"PF={_fmt(m.get('profit_factor'))}  DD={_fmt(m.get('max_dd_equity_pct'))}%"
              f"{flag}")


def _fmt(v) -> str:
    if v is None:
        return "--"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:.2f}"


# ============================================================
# Helpers compartidos
# ============================================================

def _load_dataset(args: argparse.Namespace):
    ds = rdata.load_dataset(symbol=args.symbol, timeframe=args.timeframe,
                            days=args.days, datadir=args.datadir)
    if ds is None or not ds["candles"]:
        print(
            f"ERROR: sin datos de {args.symbol} {args.timeframe} en "
            f"{args.datadir or rdata.DATA_DIR}. Exporta primero: "
            "python research/run_research.py export --symbol "
            f"{args.symbol} --timeframe {args.timeframe} --days {args.days}",
            file=sys.stderr,
        )
        return None
    return ds


def _build_cfg(args: argparse.Namespace) -> dict:
    import json as _json  # noqa: PLC0415

    from research import sim  # noqa: PLC0415

    cfg = sim.default_cfg()
    overrides: dict = {}
    if args.weights:
        try:
            overrides["risk_weights"] = _json.loads(args.weights)
        except _json.JSONDecodeError:
            raise ValueError("--weights debe ser JSON (p. ej. '{\"smc\":50}')")
    if args.killzones:
        try:
            overrides["killzones"] = _json.loads(args.killzones)
        except _json.JSONDecodeError:
            raise ValueError("--killzones debe ser JSON de ventanas.")
    for src, dst in ((args.lookback, "lookback"),
                     (args.spread_pips, "spread_pips"),
                     (args.slippage_pips, "slippage_pips"),
                     (args.ttl_min, "setup_ttl_minutes"),
                     (args.min_score, "min_score"),
                     (args.sl_pips, "sl_default_pips"),
                     (args.tp_r, "tp_ratio_r")):
        if src is not None:
            overrides[dst] = float(src)
    cfg.update(overrides)
    return cfg


_build_cfg_err = ValueError  # alias para los except de los comandos


def _results_dir(args: argparse.Namespace) -> Path:
    outdir = Path(args.outdir) if args.outdir else Path(rdata.RESEARCH_DIR) / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def _payload(res: dict, m: dict) -> dict:
    return {
        "run": res,
        "metrics": {k: v for k, v in m.items() if k not in (
            "by_direction", "by_killzone", "by_entry_kind")},
        "breakdowns": {
            "by_direction": m["by_direction"],
            "by_killzone": m["by_killzone"],
            "by_entry_kind": m["by_entry_kind"],
        },
    }


def _add_sim_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--symbol", default="EURUSD", help="Símbolo (default EURUSD).")
    p.add_argument("--timeframe", default="M15", help="Timeframe (default M15).")
    p.add_argument("--days", type=int, default=90, help="Ventana a usar (default 90).")
    p.add_argument("--datadir", default=None,
                   help="Directorio de caché (default research/data).")
    p.add_argument("--outdir", default=None,
                   help="Directorio de resultados (default research/results).")
    p.add_argument("--lookback", type=float, default=None,
                   help="Velas de la ventana deslizante (default 300).")
    p.add_argument("--weights", default=None,
                   help="JSON de riesgo (p. ej. '{\"smc\":60}').")
    p.add_argument("--killzones", default=None,
                   help="JSON de ventanas de killzone.")
    p.add_argument("--spread-pips", dest="spread_pips", type=float, default=None,
                   help="Coste mitad del spread en pips (default 1).")
    p.add_argument("--slippage-pips", dest="slippage_pips", type=float, default=None,
                   help="Slippage adverso en pips (default 0).")
    p.add_argument("--ttl-min", dest="ttl_min", type=float, default=None,
                   help="Vigencia de la orden en minutos (overrride TTL).")
    p.add_argument("--min-score", dest="min_score", type=float, default=None)
    p.add_argument("--sl-pips", dest="sl_pips", type=float, default=None)
    p.add_argument("--tp-r", dest="tp_r", type=float, default=None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_research",
        description="Pipeline offline de backtesting/calibración.",
    )
    sub = p.add_subparsers(dest="subcommand", required=True)

    ex = sub.add_parser("export", help="Exporta histórico MT5 a research/data/.")
    ex.add_argument("--symbol", default="EURUSD", help="Símbolo (default EURUSD).")
    ex.add_argument("--timeframe", default="M15",
                    help="M1..M30, H1, H4, D1, W1 (default M15).")
    ex.add_argument("--days", type=int, default=90,
                    help="Días de historial a exportar (default 90).")
    ex.add_argument("--datadir", default=None,
                    help="Directorio de caché (default research/data).")
    ex.set_defaults(func=_cmd_export)

    bt = sub.add_parser("backtest", help="Simula sobre research/data y guarda métricas.")
    _add_sim_args(bt)
    bt.set_defaults(func=_cmd_backtest)

    ca = sub.add_parser("calibrate",
                        help="Backtest + diff sugerido contra strategy.yaml (no escribe).")
    _add_sim_args(ca)
    ca.set_defaults(func=_cmd_calibrate)

    rp = sub.add_parser("report",
                        help="Renderiza un JSON de backtest/calibrate en texto plano.")
    rp.add_argument("--run", required=True, help="Ruta al JSON de backtest/calibrate.")
    rp.add_argument("--rows", type=int, default=40, help="Máx trades en la tabla.")
    rp.add_argument("--out", default=None, help="Archivo de salida (.txt).")
    rp.set_defaults(func=_cmd_report)

    va = sub.add_parser("validate",
                        help="Integridad + no-look-ahead del dataset (antes de un backtest).")
    _add_sim_args(va)
    va.add_argument("--sample", type=int, default=200,
                    help="Bares muestreados para el check de look-ahead (default 200).")
    va.set_defaults(func=_cmd_validate)

    se = sub.add_parser("search",
                        help="Grid search: barre combinaciones y rankea las Top-N. No escribe.")
    _add_sim_args(se)
    se.add_argument("--grid", default=None,
                    help="JSON del grid (p. ej. '{\"min_score\":[65,75],\"setup_ttl_minutes\":[20,30]}').")
    se.add_argument("--top", type=int, default=5, help="Mejores configuraciones (default 5).")
    se.add_argument("--min-filled", dest="min_filled", type=int, default=10,
                    help="Fills mínimos para rankear (default 10).")
    se.set_defaults(func=_cmd_search)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())