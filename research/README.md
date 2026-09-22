# Pipeline de research (offline: backtest + calibración)

Pipeline **separado del runtime** (app/agent/watcher): para ejecutar las
herramientas de research NO hace falta el dashboard, y el runtime NUNCA importa
nada de `research/`. La calibración produce un **diff sugerido** contra
`strategy.yaml` y jamás sobreescribe la config vigente.

## Comandos (desde la raíz del repo)

```powershell
# 0) Exporta histórico (única vez que necesita la terminal MT5 abierta)
python research/run_research.py export --symbol EURUSD --timeframe M15 --days 90

# 1) Valida el dataset: integridad + NO-LOOK-AHEAD (200 bares muestreados)
python research/run_research.py validate --symbol EURUSD --timeframe M15 --days 90

# 2) Backtest sobre la config vigente (store/strategy.yaml)
python research/run_research.py backtest --symbol EURUSD --timeframe M15 --days 90

# 3) Backtest + sugerencias de calibración vs strategy.yaml (no escribe nada)
python research/run_research.py calibrate --symbol EURUSD --timeframe M15 --days 90

# 4) Renderiza un JSON guardado en texto plano (consola o --out archivo)
python research/run_research.py report --run research/results/EURUSD_M15_<fecha>_cal.json
```

Salidas: `research/data/*.csv` (caché exportada), `research/results/*_bt.json,
*_cal.json, *_val.json` (resultados). Todo gitignored.

Flags de backtest/calibrate: `--lookback --weights --killzones --spread-pips
--slippage-pips --ttl-min --min-score --sl-pips --tp-r`. `--weights` y
`--killzones` esperan **JSON literal**; en PowerShell rompe el escape, pásalo
con comillas simples del shell o desde un script runner.

## Módulos

- `data.py` — export paginado por MT5 + caché CSV + PDH/PDL por vela (solo de
  días **cerrados**) y carga offline. `load_dataset()` normaliza times y adjunta
  niveles.
- `sim.py` — `BarBacktest`, réplica exacta del gate live: mismo
  `pattern_engine.analyze`, mismo `risk_engine.setup_score` (pesos/killzones de
  la config) y mismo `watcher.evaluate_gate`. CVD sintético acumulado desde el
  inicio de la ventana (espejo de `cvd_service`).
- `metrics.py` — win rate, esperanza R/pips, profit factor, max DD (curva de
  sizing 1%), barras pendiente/abierta, desglose por dirección/killzone/tipo de
  entrada.
- `calibrator.py` — `suggest()`: reglas deterministas sobre TTL, min_score,
  risk_pct y pesos de componentes (media wins−losses), con ruta en el YAML y
  confianza por muestra.
- `report.py` — render legible del payload JSON (tabla de trades + bloques).
- `validate.py` — checks de monotonicidad de tiempos, PDH/PDL, consistencia de
  TF y la invariante de no-look-ahead sobre bares muestreados.

## Decisiones de simulación (fijadas)

- Fill de **orden límite** activa durante `ttl_bars = ceil(setup_ttl_minutes*60
  / tf_seconds)` velas; si no la toca, `EXPIRED`. Si la invalidez estructural se
  cruza antes, `CANCELLED`. Una sola orden pendiente a la vez.
- Ejecución con **bid/ask** (spread) y slippage adverso en entrada y salida;
  opción `spread_model: "mid"` prevista para cuantificar el inflado 3–5%.
- Convención **SL-first** dentro de una vela (si tocan SL y TP, gana el SL).
- **Invariante look-ahead**: la evaluación en el bar i usa solo velas ≤ ts_i
  (ventana cerrada, PDH/PDL de días cerrados, CVD acumulado desde el inicio).
  `validate` la verifica empíricamente sobre el dataset.
- Cada trade guarda `signal_components` (valores de los componentes en el lado
  elegido al señalar) → insumo del calibrador de pesos.

## Pendientes / a considerar

- `entry_kind` sin llenar: hoy la orden límite contempla `current_price`
  (close del bar) aunque el gate de mercado quiera entrar; documentar/decidir si
  el fill final debe usar el plan de entrada en vez de `current_price` cuando
  `entry_kind == "market"`.
- Cross-validación por ventanas (walk-forward) para no sobreajustar los pesos
  que sugiera `calibrate`.