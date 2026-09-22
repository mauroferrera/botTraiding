# Checklist de auditoría visual — UI en modo Mock (Order Flow 6E)

Auditoría **manual / visual** de la interfaz corriendo con feed **Mock (sintético)**.
Complementa a `tests/test_simulator.py` (assertions numéricas del engine) — aquí se
valida que **ECharts y el DOM pinten lo que el engine ya probó matemáticamente**.

Fecha de sesión que lo originó: 2026-09-05 (fin de M1–M3 + fixtures 6E). Revisado
contra `index.html` y `main.js` (los IDs coinciden con los chips/KPIs del panel).

> Regla de oro: **si un ID de abajo no existe o pinta `--` / "apagado" sin el feed
> Mock encendido, es un bug de la UI** (no del engine). Si el test
> `tests/test_simulator.py` pasa pero el overlay no se dibuja, el fallo es de
> `main.js`/`main.js vN`. El checklist separa **engine (tests)** de **pintado (UI)**.

---

## 0. Preparación

- [ ] `.env` con `ORDERFLOW_ALLOW_MOCK=1` (publica el selector "Mock (sintético)").
- [ ] Server arrancado: `python app.py` (o `python -m uvicorn app:app --port 8000`).
- [ ] Abrir `http://127.0.0.1:8000` y esperar a que la UI cargue (sin pantallazos
      de error en Consola DevTools → pestaña **Console** sin excepciones `Uncaught`).
- [ ] En el panel **Order Flow · 6E**:
      - Selector de fuente `ofSource` en **Mock (sintético)**.
      - Selector de escenario `ofFixture` **desplegado y con 8 opciones**
        (no oculto): `noise`, `spike`, `absorption`, `stress` + las **5 fijas**:
        `sweep_and_reverse`, `absorption_at_support`, `fvg_expansion_trend`,
        `range_consolidation_vp`, `latency_stress`.
- [ ] Validar que el select de escenario se **oculta automáticamente** al cambiar a
      **Live (Databento)** y vuelve al re-elegir Mock (toggle `feedToggle`).

---

## 1. LEDs y chips de conexión

| Verificación | Elemento | Esperado |
|---|---|---|
| Feed encendido | `feedToggle` + `feedToggleLabel` | Toggle ON/verde, label "Conectado" |
| Estado conexión | `ofConn` (dot) | Dot **verde online**, texto "en línea" |
| Chip fuente | `ofSourceChip` | `"fuente: SINTÉTICO 6E (MOCK)"` + clase `.mock` |
| Fuente del feed | `ofSource` | value `mock`, chip "fuente: mock" |
| KPI CVD | `ofCvd` + `ofCvdSub` | valor ≠ `--` tras unos segundos; sub "Delta acumulado" |
| KPI Delta | `ofDelta` | Último delta (puede ser 0 en `noise`) |
| KPI Volumen | `ofVol` + sub | Total acumulado creciendo con el feed |
| KPI Compra/Venta | `ofBuySell` + `ofBuySellSub` | Ratio o conteo B/S + sub |
| KPI Spikes | `ofSpikes` (sub "Z-score ≥ 2.5") | `0` en noise; ≥1 en spike/stress |
| Chip score | `scoreBadge` (header) | score setup al diseminar snapshot |

---

## 2. Pintado en el gráfico (ECharts) — por escenario

> El grafiquito de Order Flow (`ofChart`) y el gráfico principal repintan con cada
> barra del feed mock; la **tabla de footprint** se dibuja en el panel de footprint.

### 2.1 Escenario `noise` (regresión, sin patrones)

- [ ] `ofSpikes = 0`, sin `markPoint` de spike ni alerta de absorción.
- [ ] CVD ≈ 0 (delta acumulado plano): `ofCvd` estable, sin drift.
- [ ] **Sin** FVGs / Order Blocks pintados (análisis patterns vacío).
- [ ] KPI Buy/Sell balanceado ~50/50.

### 2.2 Escenario `spike` (picos Z-score)

- [ ] `ofSpikes ≥ 1` con **Z-score ≥ 2.5** (o el umbral `ofZscore` configurado).
- [ ] En `ofChart`: **puntos/marcadores de spike** encima de la(s) vela(s) del pico.
- [ ] En el grafo principal, el **FVG/OB del impulse** aparecen si el spike rompe
      estructura (validar con manual: al arrancar spike con replicación).
- [ ] El `output` del slider `ofZscoreOut` actualiza solo al mover (no toca el feed).

### 2.3 Escenario `absorption` (absorción en soporte)

- [ ] Alerta de **absorción en `ofAlerts`**: tipo `ABSORPTION_*` con dirección
      (compra en el soporte / venta en la resistencia) y volumen alto.
- [ ] `ofCvd` con valores estables dentro del rango (delta equilibrado, **no**
      ruptura de CVD — se valida con la regla de absorción).
- [ ] El **footprint** del fixture `absorption_at_support` pinta la **capa de
      agresor** (bid/ask) con las células altas mostrando el volumen del lado que
      absorbe.
- [ ] KPI **Buy/Sell** inclinado hacia el lado agresor sin romper nivel.

### 2.4 Escenario `sweep_and_reverse` (barrido + reversión) _[fixture]_

- [ ] En el gráfico principal, **sweep marcado** (flecha/tag SMC "PDH/PDL sweep") en
      el `markPoint` del gráfico (zona de barrido) — el test exige `PDH_SWEEP` con
      `wick_extreme`.
- [ ] **FVG/Order Block** pintados tras el sweep (reversión): flecha compradora si
      fue sweep del PDL, vendedora si fue PDH.
- [ ] `ofAlerts` con la alerta de sweep + setup, **no** falsa absorción.
- [ ] CVD muestra **reversión** (cambio de signo del CVD tras el sweep) — validar
      que la curva CVD cruza 0 / cambia pendiente en la vela de reversión.

### 2.5 Escenario `fvg_expansion_trend` (tendencia + FVG) _[fixture]_

- [ ] **FVG bullish** dibujado como área coloreada (zona verde, `bottom<top`).
- [ ] **Order Block** (OB) resaltado en la base del impulso (rectángulo OB).
- [ ] **Sin sweeps** (el test `assert pat["sweeps"] == []`): la zona FVG/OB no debe
      tener marcador de barrido.
- [ ] Price Action: el POC del VP se desplaza al alza (validar `vp()`).

### 2.6 Escenario `range_consolidation_vp` (rango/consolidación) _[fixture]_

- [ ] **CVD plano** (`ofCvd` estable, |CVD| < 1000) — sin drift direccional.
- [ ] La alerta de absorción **NO** dispara (el test `test_no_false_signals` exige
      `absorbs == []`): `ofAlerts` sin absorción/ spkie.
- [ ] Footprint VP en **forma de campana** centrada en el precio base (POC dentro
      del rango, VAH-VAL estrecho).
- [ ] Los KPIs Buy/Sell ~ balanceados, sin spike.

### 2.7 Escenario `latency_stress` (latencia) _[fixture]_

- [ ] El feed NO se "congela": sigue emitiendo (puede bajar de frecuencia pero no
      colapsar el WebSocket ni el gráfico).
- [ ] `ofSpikes` alto (≥20, estrés): el panel de alertas puede inundarse — validar
      que la lista de alertas **no se desborda** (scroll / límite de items).
- [ ] El récord del footprint y del gráfico se mantienen consistentes (candles M15
      `≥ 50`), sin saltos de precios imposibles.
- [ ] WebSocket: el `ofChart` sigue actualizándose (timestamps aumentando), sin
      reconexiones repetidas (`ofConn` no parpadea).

---

## 3. Consistencia engine ↔ sim (pantalla vs tests)

> Estas ya las garantiza el pytest; en la UI se audita que los **número que dibuja
> el footprint (CVD/delta del ticking)** coincidan con los KPI del engine.

- [ ] `sum(delta de footprint) == CVD del engine` — visible al comparar la tabla de
      footprint (columna `delta`) con `ofCvd` acoplado con CVD.
- [ ] **Barra en formación**: el delta del footprint incluye la vela sin cerrar
      (CVD del engine == delta acumulado footprint, incluida la en-formación).
- [ ] `cvd_series()` del sim == `cvd_series()` del engine por ventana (idéntico
      cuando se reinyecta el MISMO fixture .jsonl vía toggle/escenario).

---

## 4. Modos = determinismo (audit al volver a Live)

- [ ] Al apagar/encender el toggle (Live↔Mock) o cambiar de escenario, el engine
      **se resetea**: KPI vuelven a `--` y el CVD parte de 0 (limpieza de estado).
- [ ] Con el MISMO escenario y MISMA semilla al **re-arrancar** (apagar → encender):
      las velas/footprint/CVD se reproducen **idénticos** (determinismo visible en
      pantalla: misma forma de velas, mismo CVD final).
- [ ] Publicador que emite los **mismos payloads por WebSocket** en Mock que en Live
      (estructura idéntica; solo cambia el regumen/fixture).

---

## 5. Checklist rápida (para `Ctrl+F` corto, una línea cada una)

- [ ] `ofSource == mock` y `ofFixture` visible con las 5 fijas.
- [ ] `ofConn` dot verde · `ofSourceChip` "SINTÉTICO 6E (MOCK)".
- [ ] `ofCvd` ≠ `--` y estable en noise.
- [ ] `ofSpikes = 0` en noise; ≥1 en spike; alto en stress.
- [ ] `ofAlerts` pinta absorción solo en `absorption` (no en `range_consolidation_vp`).
- [ ] FVG/OB dibujados en `fvg_expansion_trend` (zona verde + rect OB).
- [ ] Sweep marcado en `sweep_and_reverse`; ninguno en `fvg_expansion_trend`.
- [ ] POC dentro del rango (campana centrada) en `range_consolidation_vp`.
- [ ] CVD plano en `range_consolidation_vp` (< 1000), sin drift.
- [ ] Feed determinista: re-arrancar Mock ≡ mismos candles/CVD/CVD.
- [ ] Nada de `--` persistente ni eror en Console con Mock encendido.
- [ ] Cambiar a Live oculta el escenario (clean UI) y al volver Mock reaparece.

---

## Nota de alcance

Este checklist es la **contraparte visual** de `test_simulator.py`; el QA numérico se
hace con `python -m pytest tests/test_simulator.py -v` (engine puro, sin MT5). El
único rejilla que no puede auditarse sin terminal: el **gate de ejecución real** con
Databento (`send_market_order`), que queda documentado como limitación conocida de
M3/M4.
