# ROADMAP — Próximas mejoras del proyecto

Fecha: 2026-09-05. Documento que consolida las mejoras M1–M4, las refinaciones de
riesgo y las decisiones de diseño ya tomadas.

> **Estado (fin de sesión 2026-09-05):** M1 completo salvo 1 gap detectado
> (§7.1), M2 integrado dentro del motor, M3 completo, **M4 pendiente** (§7.3).

---

## 1. Contexto y objetivo

El plan A+B (snapshot híbrido con CVD etiquetado + análisis COT CFTC) está
**completado y verificado en vivo**. El siguiente salto de calidad es convertir el
riesgo en un **sistema determinista en backend**, de modo que el agente IA *narr e*
(jamás *calcule*), y las decisiones de aprobación de un trade sean:

- **repetibles** (misma entrada → misma decisión),
- **auditables** (cada disparo deja un post-mortem en SQLite),
- **configurables** (pesos, ventanas de killzone, prop firm) sin tocar código.

Principio rector: cada componente conduce a un **gate determinista** en
`send_market_order` (bloqueo duro) o a un **peso/aviso** (degradación de score),
nunca a una opinión del LLM. El LLM solo interpreta los resultados.

---

## 2. Qué ya existe (no duplicar)

| Capacidad | Dónde está | Nota |
|---|---|---|
| Lote por riesgo % con specs reales del contrato | `app.lot_suggestion()` (`app.py:1756`) | Usa `mt5.order_calc_profit()` → **intocable y superior** a una fórmula manual de pips. |
| Drawdown Guardian diario (bloqueo duro) | `app.daily_risk_state()` (`app.py:1797`) | Equity vs. balance inicio de día; bloquea con `loss_limit_fixed` 1250 / `loss_limit_pct` 2% / `max_trades_day` 10. |
| Ejecución de mercado con SL/TP | `app.send_market_order` (`app.py:1860`) | Punto de inserción de los gates M1/M3. |
| Calendario económico | tool `economic_news` (`agent.py:183/339`) + `ff_calendar.py` | Vía proxy Jina (`r.jina.ai`), sin API key. Puede fallar → el guard degrada a aviso. |
| R:R configurable | `tp_ratio_r: 2.0` en `DEFAULT_TRADING_CONFIG` (`store.py:63`) | Solo fija TP; **no exige** el R:R mínimo. |
| Indicador de riesgo en UI | `riskChip` (`main.js:1789–1805`) + clase `.blocked` | Muestra estado diario; se extiende con score/killzone. |
| Ruta simple del agente | `agent._fetch_live_data` (`agent.py:697`) | Punto de inyección de la `risk_policy` para el contexto del agente. |
| Order Flow / CVD | `OrderFlowEngine` (`app.py:82`), snapshot (`235`), `cvd_series` (`251`), `cvd_service.get_cvd` (`91`) | Input del componente CVD/OF del Setup Score. |
| Regla COT en contexto | regla COT en `system_prompt` de `general` (`store.py`) + `cot_service` | Input del componente COT del Setup Score. |

---

## 3. Mejoras M1–M4

### M1 — Risk Engine + Setup Score determinista (núcleo)

**Qué:** módulo puro `risk_engine.py` (sin imports de MT5 ni de la app) que calcula:

1. **Setup Score 0–100** con 4 componentes ponderados (pesos **editables** en config,
   defaults decididos: **COT 25% · CVD/OF 25% · SMC 30% · Killzone 20%**):

   ```
   Score = cot×0.25 + cvd_of×0.25 + smc×0.30 + killzone×0.20
   ```

   - **COT**: coincidencia entre `macro_bias` (BULLISH/BEARISH/NEUTRAL) y la
     dirección del setup. Datos ausentes → componente 0 (baja el máximo honesto).
   - **CVD/OF**: pendiente del CVD (o delta/z-score si hay datos Databento) a favor
     de la dirección; sin datos → 0.
   - **SMC**: confluencia estructural real (FVG activo + sweep previo + OB) a favor
     o en contra de la dirección; extracto de `patterns_service`, jamás del LLM.
   - **Killzone**: 1.0 dentro de ventana, 0.25 fuera.

   Verdictos por umbral (config): `≥80 → ALTA_PROBABILIDAD` (riesgo normal),
   `60–79 → MEDIA_PROBABILIDAD` (riesgo reducido 0.25% o config),
   `<60 → SIN_OPERATIVA` (mantenerse al margen).

2. **`validate_entry()`** — re-chaza la entrada antes de pasar a `send_market_order`:
   - **R:R mínimo**: `(target − entry)/(entry − sl) ≥ min_rr` (default **2.0**);
     cumple lo que la propuesta original llama "Risk Engine" sin duplicar
     `order_calc_profit`.
   - **Riesgo en dinero**: `balance × risk_pct/100 ≥ loss_per_lot × lot +
     tolerancia` (matemática de auditoría sobre los valores reales del contrato).
   - **Invalidez por ruptura estructural** (`P2`): si el tick actual **cruza el
     nivel de invalidez** (para BUY = mínimo del OB/FVG que dio origen; para SELL =
     máximo) antes de la ejecución → `score = 0` y rechazo determinista con motivo.
     Como no existen órdenes pendientes, "cancelar pendiente" se adapta a *refusar
     la ejecución de mercado* (mismo efecto sin nueva superficie).
   - **TTL del setup** (`P2`): `setup_ttl_minutes` (default **45**). Al vencer, el
     setup expira y se re-chaza hasta un snapshot fresco.

3. **Régimen de mercado** (`regime()`, base de M2): clasifica cada snapshot en
   `expansión` (rango ancho, spreads amplios, momento direccional) o
   `rango/compresión` (cuerpos con tendencia, poco recorrido nocional) a partir del
   ATR/rango vs. día previo.

**Porqué:** el `lot_suggestion()` y el `daily_risk_state()` existen pero no hay un
único punto que **sume señales y decida**. Sin score + validate_entry, el agente
aprueba setups con `tp_ratio_r` sin garantía de que el R:R se cumpla, y no hay
expiración de setups viejos. El score con pesos editables permite calibrar con
datos (vía `setup_log`, M3), no con intuición.

**P1 (lotaje) — matiz registrado:** la propuesta de recalcular el lote con
`Balance×R%/(pips×pip_value)` **se rechaza como sustitución**: `order_calc_profit`
resuelve tick value/size y convenciones por símbolo (Euro FX, XAUUSD, JPY) con
mayor precisión. Se adopta la mejora accesoria: `get_specs()` exponerá además
`tick_value`, `tick_size` y `contract_size` para que `risk_engine` calcule el
R:R **en dinero** y el riesgo efectivo de forma explícita y auditable. El motor
sigue siendo puro: recibe esas specs como **inputs**, no consulta MT5.

**Entregables:** `risk_engine.py`; claves `risk_weights`, `min_rr`,
`setup_ttl_minutes`, `reduced_risk_pct` en config; tabla `setup_log` (M3, se crea
ya en M1); `get_specs` ampliado; `build_chart_snapshot` expone
`setup_score`/`regime`/`killzone`; tool `setup_score` en el agente.

---

### M2 — Killzones y régimen de mercado

**Qué (decisiones tomadas):**

- **Killzones EURUSD** (ventanas configurables, UTC):
  - Londres: **08:00–11:00 UTC**
  - Nueva York: **13:00–16:00 UTC**
- `killzone_score(now_utc)`: 1.0 dentro de ventana, 0.25 fuera; el peso Killzone
  (20%) fluye dentro del Setup Score.
- `regime(candles)`: `expansión`/`rango` para que score y avisos distingan día de
  tendencia vs. día de consolidación.
- Clave `killzones` en config (lista de ventanas con nombre/inicio/fin).

**Porqué:** la mayoría de los movimientos EURUSD de alta probabilidad ocurren en
esas ventanas; el score lo refleja como **peso + aviso**. Se descarta (decisión
tomada) convertirlo en bloqueo duro: dejaría el sistema inoperable gran parte del
día sin aportar gestión de riesgo real.

---

### M3 — Guards del agente + auditoría post-mortem

**Qué (decisiones tomadas):**

1. **Enforcement por niveles**:
   - **DD diario → bloqueo duro en backend** (ya existe; se mantiene).
   - **Noticias ±15min (`news_buffer_min`)** y **killzone → aviso + degradación
     de score**, nunca bloqueo duro.
2. **Inyección de `risk_policy`** al agente vía `_fetch_live_data` (`agent.py:657`):
   estado de `daily_risk_state`, régimen, killzone, noticias próximas y resumen del
   último validado/rechazado. Ruta simple, sin tool nueva (el agente ya recibe el
   contexto del chat).
3. **`setup_log` (post-mortem, `P3`)** — tabla SQLite **append-only**; cada disparo
   del motor registra:
   - timestamp, símbolo, timeframe, dirección,
   - **breakdown de los 4 componentes** del score (valores y motivos),
   - veredicto y R:R, nivel de invalidez y TTL restante,
   - estado del `daily_risk_state`, régimen y `in_killzone` en el momento del disparo,
   - resultado final vinculado (ticket → profit) para medir.
4. **Endpoint de auditoría** (`GET /api/risk/audit`): win-rate por componente,
   aprobados vs. rechazados, por qué se rechazó.

**Porqué:** hoy el journal guarda la orden y el contexto SMC, pero **no el porqué**
de la decisión de riesgo. Sin un snapshot completo no hay forma de saber qué
componente del score *realmente acierta*, y no se pueden calibrar los pesos
25/25/30/20 con evidencia. El guard de noticias protege de los spikes pero degrada
a aviso si el calendario (proxy Jina) falla: **nunca congela el sistema**.

---

### M4 — Prop firm configurable

**Qué (decisiones tomadas):** sistema configurable **por defecto desactivado
(`prop_enabled: false`)**, con claves `prop_*` en `trading_config`:
`prop_max_dd_daily_pct`, `prop_max_dd_total_pct`, `prop_max_profit_day_pct`,
`prop_consistency_days`. Al activarse, `daily_risk_state` y `validate_entry`
incorporan esos límites como gates/avisos según corresponda.

**Porqué:** las reglas de FTMO/Topstep varían; **no se hardcodean**. El sistema
solo debe saber un conjunto de límites configurados.

---

## 4. Decisiones tomadas (resumen ejecutivo)

| Tema | Decisión | Default |
|---|---|---|
| Enforcement | DD diario bloquea duro (existente); noticias/killzone degradan y avisan | `news_buffer_min: 15` |
| Prop firm | Configurable, no hardcoded | `prop_enabled: false` |
| Killzones EURUSD (UTC) | Londres 08:00–11:00 + NY 13:00–16:00 | ventanas editables |
| Pesos score | 25/25/30/20 editables en config | `COT/CVD_OF/SMC/KILLZONE` |
| R:R mínimo | Exigido en `validate_entry` | `min_rr: 2.0` |
| TTL del setup | Expiración de setups viejos | `setup_ttl_minutes: 45` |

---

## 5. Arquitectura e implementación (por fases)

```
M1  risk_engine.py (puro) ──┬──> build_chart_snapshot (setup_score, regime, killzone)
    store: trading_config + setup_log (CRUD append) ──┬──> /api/risk/audit (M3)
    get_specs +tick_value/size/contract ──────────────┘
M2  killzone en config + regime() listos (peso, no bloqueo)
M3  risk_policy → _fetch_live_data · gates → send_market_order · setup_log → auditoría
M4  claves prop_* → daily_risk_state / validate_entry
```

Orden de trabajo:
1. `risk_engine.py` (settling score, killzone_score, regime, validate_entry).
2. Extender `DEFAULT_TRADING_CONFIG` + crear tabla `setup_log`.
3. Ampliar `get_specs` (tick_value/tick_size/contract_size) y pasar specs al motor.
4. Integrar en `build_chart_snapshot` + endpoints (`/api/risk/setup`,
   `/api/risk/audit`) + dump en `setup_log`.
5. Tool `setup_score` en `agent.py` + inyección `risk_policy` (M3).
6. Gates reales en `send_market_order` (M1/M3) + registro del veredicto.
7. UI: `riskChip` + sección score/killzone (bump `main.js?v=14`).

Verificación por fase: `py_compile` de los módulos y `node --check main.js`; cada
endpoint probado vía curl/SSE; la lógica pura de `risk_engine` con ejecución en
shell (sin MT5). Componentes que dependan de MT5 (gates de ejecución, CVD real)
requieren la terminal abierta durante las pruebas — documentado como limitación
conocida.

---

## 6. Pushback documentado a propuestas externas

- **P1 lotaje**: `order_calc_profit` es superior a `Balance×R%/(pips×pip_value)`
  (convenciones de pips por activo, J3/Gold); se adopta solo la exposición de
  specs + auditoría en dinero.
- **Cancelar órdenes pendientes por invalidez**: no existen órdenes pendientes;
  se refusa la ejecución de mercado si el tick violó el nivel de invalidez.
- **Score ≠ win-rate**: el score se etiqueta honestamente como *calidad de
  confluencia*, no probabilidad; el win-rate real se mide después (setup_log).
- **Calendario puede fallar**: el guard de noticias degrada a aviso; el DD diario
  es el único candado duro garantizado.

---

## 7. Estado real y pendientes (fin de sesión 2026-09-05)

### 7.1 Implementado y verificado (M1 + M2 + M3)

- `risk_engine.py` (puro, sin MT5): `setup_score` (pesos 25/25/30/20 editables),
  `killzone_score`, `regime`, `cot_component`, `cvd_component`, `smc_component`,
  `grade_score` (≥80 ALTA / ≥60 MEDIA / SIN_OPERATIVA), `invalidation_level`,
  `validate_entry` (R:R≥2.0, TTL 45min, invalidez estructural, cabeza de riesgo en
  dinero).
- `store.py`: `DEFAULT_TRADING_CONFIG` extendido + tablas `setup_log` (append-only)
  e índice; `log_setup`, `list_setup_log`, `link_last_setup` (vincula ticket→setup).
- `app.py`: `get_specs` +tick_value/tick_size/contract_size; `build_chart_snapshot`
  expone `risk_engine`; endpoints `GET /api/risk/setup` y `GET /api/risk/audit`
  (con win-rate real por componente vía `link_last_setup`); gate en
  `send_market_order`; call a `link_last_setup` tras orden exitosa (app.py:2178).
- `agent.py`: tool `setup_score`; `_fetch_live_data` + `_risk_policy_lines`
  (DD, killzone UTC, prop firm, enforcement, setup score si intención operativa),
  guard de `economic_news` con degración a aviso.
- UI: `main.js?v=14` con `scoreBadge`/`loadRiskScore` + `analizarGrafico`.
- Server en ejecución al cierre: **PID 21972** (puerto 8000, carga M3 sin M4).

### 7.2 GAP detectado en M1 (arreglar antes de M4)

`api_trade_market` (app.py:2172) llama a `send_market_order(...)` **sin pasar
`invalidate_level`** → `validate_entry` recibe `None` y el gate de invalidez
estructural **nunca aplica en la ejecución real** (solo en el snapshot).

**Fix:** en el endpoint, antes de `send_market_order`, computar patrones con
`patterns_service.get_pattern_data(symbol, patterns_service.DEFAULT_TIMEFRAME)` →
`risk_engine.invalidation_level(patterns, action)` y pasarlo como parámetro. Es
seguro: `patterns_service` usa su propio thread MT5 (fuera de la región `run_mt5`).

### 7.3 M4 — Prop firm configurable (pendiente, plan exacto)

1. **`risk_engine.py`**: añadir función pura
   `prop_firm_state(balance, equity, day_start_balance, dd_daily, realized_today,
   trades_today, baseline_balance, trading_days, cfg) → dict`.
   - Si `prop_enabled: false` → `{"enabled": False, "blocked": False, ...}`.
   - Límites desde `cfg`: `prop_max_dd_daily_pct` (default 2.0),
     `prop_max_dd_total_pct` (6.0), `prop_max_profit_day_pct` (1.5),
     `prop_consistency_days` (4).
   - Reglas: DD diario `dd_daily/day_start` ≥ límite → **bloquea**; DD total
     `(baseline − equity)/baseline` ≥ límite → **bloquea**; profit día
     `realized_today/baseline` ≥ límite → **bloquea nuevas entradas**;
     `trading_days < consistency_days` → **flag de aviso, no bloquea**.
   - Retorno con `reasons` (bloqueo) y `flags` (aviso) + usados/límites.
2. **`store.py`** (~línea 86): añadir `"prop_initial_balance": 0.0` a
   `DEFAULT_TRADING_CONFIG` (baseline para DD total).
3. **`app.py` `daily_risk_state` (1797)**: si `prop_enabled`, obtener baseline
   (si 0 → `account.balance` y persistir con `set_trading_config({**cfg, ...})`),
   `trading_days` = días con `d.profit != 0` en `history_deals_get` (últimas ~30d,
   dentro de `_get`), llamar `prop_firm_state`, hacer
   `blocked |= prop["blocked"]`, `reasons.extend(...)`, `flags.extend(...)`, y
   añadir claves `"flags"` y `"prop"` al dict de retorno. Mantener límites genéricos.
4. **`agent.py` `_risk_policy_lines` (736)**: cuando `prop_enabled`, la línea de
   política debe reportar límites prop reales (DD total usada/límite, profit día,
   consistencia) e imprimir `flags` como "Aviso: …".
5. **Tests** `test_risk_engine.py` (nuevo, `unittest` stdlib): `prop_firm_state`
   (desactivado / >límite diario / >límite total / tope profit / flag consistencia),
   `setup_score` (~100 ALTA con todo a favor; killzone fuera baja), `validate_entry`
   (R:R, TTL, invalidez, dinero, aprobado), `invalidation_level`, `grade_score`.
6. **Verificación**: `py_compile` app/agent/store/risk_engine; `python -m unittest
   test_risk_engine.py`; reiniciar server (matar PID puerto 8000 → `Start-Process
   python -m uvicorn app:app --host 127.0.0.1 --port 8000`); probar
   `/api/risk/setup` y `/api/risk/audit`.