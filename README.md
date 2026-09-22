# botTraiding

Panel de control web para trading con **MetaTrader 5**, integrado con un **agente de IA** (multi-proveedor), **order flow del futuro 6E** (CME vía Databento) y **detección de patrones SMC** en tiempo real.

---

## Tabla de contenidos

- [Características](#características)
- [Stack de tecnologías](#stack-de-tecnologías)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Cómo ejecutarlo](#cómo-ejecutarlo)
- [Arquitectura](#arquitectura)
- [Base de datos](#base-de-datos)
- [Agente de IA](#agente-de-ia)
- [Endpoints API](#endpoints-api)
- [Integración con AI Chart Assistant](#integración-con-ai-chart-assistant)
- [Pipeline de research](#pipeline-de-research)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Seguridad](#seguridad)

---

## Características

- **Dashboard en tiempo real** con KPIs de cuenta MT5 (balance, equity, P&L, margen libre, nivel de margen, posiciones abiertas).
- **Gráfico en vivo** (Apache ECharts v6) con velas, CVD sincronizado y detección de patrones SMC:
  - Fair Value Gaps (FVG)
  - Order Blocks
  - Liquidity Sweeps de PDH/PDL
- **Modos de gráfico derivados** (vistas sintéticas unificadas): Classic, Footprint (delta por nivel), Heatmap de liquidez, Volume Profile (POC/VAH/VAL) y Event Bars (volbar/tickbar/renko).
- **Capas de chartismo** sobre el gráfico: canal/tendencia, triángulo, bandera/banderín, doble techo/suelo y cabeza y hombros.
- **Risk Engine / Setup Score** determinista (0–100): ponderación editable COT 25% · CVD/Order Flow 25% · SMC 30% · Killzone 20%, con killzones UTC (Londres/NY), R:R mínimo, TTL del setup y veredicto ALTA/MEDIA/SIN_OPERATIVA (bloqueo de ejecución).
- **SMR / Divergencia DXY** (Smart Money Reversal): detecta sweeps del EURUSD/6E sin confirmación del Índice del Dólar (Yahoo Finance, gratis — sin Databento).
- **Watcher (bot a la escucha)**: escaneo automático de setups, eventos por WebSocket y auto-ejecución opcional, con alertas y drawings de gráfico persistidos.
- **Order flow del futuro 6E (CME)** vía Databento:
  - CVD (Cumulative Volume Delta)
  - Delta por operación
  - Picos de volumen con **Z-score**
  - Detección de **absorción de liquidez**
  - **Feed sintético (mock)** para probar el panel sin licencia Databento (selector Live/Mock + escenarios en la UI)
- **Chatbot con agente de IA**:
  - Tool-calling con datos reales de cuenta, historial, order flow, patrones y bitácora.
  - Router multi-proveedor con fallback automático.
  - Lectura automática de exportaciones del indicador "AI Chart Assistant".
  - Respuestas en español.
- **Trading desde el dashboard** (espejo de EAs MQL5): órdenes de mercado con SL/TP, gestión de riesgo diario y configuración de Magic/Comment.
- **Bitácora de trading (journal)** estructurada con contexto SMC.
- **Visor de base de datos local** en la propia página (solo lectura).

---

## Stack de tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI · Uvicorn |
| Frontend | HTML5 · CSS · JavaScript (vanilla) · Apache ECharts v6 |
| Base de datos | SQLite (`trading.db`) |
| Tiempo real | WebSocket · Server-Sent Events (SSE) |
| Integración MT5 | `MetaTrader5` API (Python) |
| Order flow | `databento` (futuro 6E, dataset GLBX.MDP3) |
| IA | `litellm` (OpenAI · Gemini · Anthropic) |

---

## Requisitos

- **Python 3.10+** (probado en 3.12)
- **MetaTrader 5** instalado y con sesión iniciada
- API keys (al menos una de LLM) en el archivo `.env`

---

## Instalación

```bash
# Clona el repositorio y entra en la carpeta
git clone https://github.com/mauroferrera/botTraiding.git
cd botTraiding

# (Opcional) crea un entorno virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
.venv/bin/activate       # Linux / macOS

# Instala dependencias
pip install -r requirements.txt
```

**Dependencias (`requirements.txt`):**

```
fastapi==0.141.1
uvicorn==0.52.4
python-dotenv==1.2.3
databento==0.85.0
MetaTrader5==5.0.6147
pydantic==2.13.5
websockets==17.1
litellm==1.98.0
PyYAML==6.0.3
numpy==2.5.2
requests==2.34.2
mcp==1.29.1
yfinance==0.2.54
```

> **Nota para Linux/macOS y entornos sin MetaTrader 5**: el paquete `MetaTrader5` solo está disponible para Windows. La aplicación arranca igual sin él, pero las funciones de cuenta/trading histórico quedan deshabilitadas (el resto — order flow, chatbot, periodos SMC — sigue funcionando).
>
> `yfinance` se usa para el **SMR / divergencia DXY** (Índice del Dólar DX-Y.NYB, gratis, sin Databento) y requiere salida a internet.

---

## Configuración

Crea un archivo `.env` en la raíz:

```env
# Feed de order flow (6E del CME)
DATABENTO_API_KEY="tu-clave"

# Claves del agente IA (al menos una)
# OPENAI_API_KEY=""
GEMINI_API_KEY="tu-clave"
# ANTHROPIC_API_KEY=""
```

Puedes configurar varias claves Gemini (`GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`) para **rotación y backoff** ante límites de rate (429).

El detector **SMR / DXY** no requiere API key: obtiene el Índice del Dólar (DX-Y.NYB) de Yahoo Finance con caché TTL.

Variable de entorno opcional para el directorio de exportaciones del indicador. Si no se define, `mt5_export.py` lo detecta automáticamente en `AppData\Roaming\MetaQuotes\Terminal\<HASH>\MQL5\Files` del usuario actual:

```env
# Sobre escribe la ruta por defecto de MQL5\Files
MT5_FILES_DIR="C:\ruta\a\MetaQuotes\Terminal\<HASH>\MQL5\Files"
```

### Feed sintético (Mock) para el 6E

Sin licencia Databento puedes validar todo el pipeline (WebSocket, KPIs, alertas, CVD, latencia) con un **feed mock 100% offline**:

```env
# Habilita el feed sintético de order flow (default 1). Con 0 se oculta el
# selector "Mock (sintético)" en la UI y solo queda disponible el feed live.
ORDERFLOW_ALLOW_MOCK=1
```

Cómo funciona:

- En el panel **Order Flow · 6E** elige **Mock (sintético)** en el selector de fuente y un **escenario**: `noise` (normal, sin alertas), `spike` (ráfagas Z-score ≥ 2.5), `absorption` (rango estrecho con volumen alto y delta equilibrado) o `stress` (alta frecuencia, para probar latencia). Al arrancar (toggle) el feed se reinyecta en `OrderFlowEngine` igual que el live y emite los mismos payloads por el WebSocket.
- El engine se **resetea** en cada cambio de modo/escenario (replay determinista y limpieza Live↔Mock).
- Igualmente hay escenarios *fixture* que reproducen `.jsonl` reales (`tests/fixtures/orderflow_6e_*.jsonl`) para regresión.
- El feed **live de Databento** queda intacto: al obtener la licencia, basta seleccionar **Live (Databento)** — no hay cambios de configuración.
- Ver: `mock_feed.py` (módulo puro, determinista, sin dependencias de app).
- Con el feed mock activo, las vistas de gráfico (velas, footprint, volume profile, CVD del EURUSD/6E) también salen del **simulador unificado** (`simulator.py` + `market_view.py`): el mismo tick que consume el `OrderFlowEngine` alimenta todas las vistas, de forma determinista (misma semilla → misma secuencia → mismos outputs).

Pruebas del order flow:

```bash
python -m pytest tests/test_orderflow.py -v   # solo order flow / mock
python -m pytest tests/ -q                    # suite completa
```

---

## Cómo ejecutarlo

```bash
python app.py
```

El servidor arranca en `http://127.0.0.1:8000` (abre esa URL en el navegador).

La aplicación crea automáticamente la base de datos y siembra los roles por defecto la primera vez.

---

## Arquitectura

### Flujo general

```
Navegador (index.html / main.js)
        │  REST + WebSocket + SSE
        ▼
app.py (FastAPI)
  ├── /api/*  endpoints (cuenta, posiciones, historial, chat, trading)
  ├── OrderFlowEngine  (métricas 6E / Databento, thread-safe) ← mock_feed.py
  ├── patterns_service / pattern_engine  (SMC: FVG, Order Blocks, Sweeps)
  ├── chartism_engine  (patrones chartistas: canales, triángulos, H-C-H…)
  ├── smr_service      (SMR/divergencia DXY vía Yahoo Finance)
  ├── cvd_service      (cálculo de volumen delta)
  ├── risk_engine      (Setup Score, killzones, R:R, TTL, prop firm)
  ├── watcher          (bot a la escucha + auto-ejecución)
  ├── simulator + market_view  (vistas sintéticas unificadas 6E/EURUSD)
  └── agente IA  ──►  agent.py  ──►  litellm  ──►  proveedor LLM
                        │
                        ├── store.py  (SQLite)
                        └── mt5_export.py  (lectura exportaciones indicador)
```

### Hilos y concurrencia
- `ThreadPoolExecutor` dedicado (1 worker) para llamadas síncronas a **MT5**, con `sync` lock interno.
- El `OrderFlowEngine` es **thread-safe** (usa un `threading.Lock`).
- El agente ejecuta herramientas en un thread separado con timeout de 4 s.

---

## Base de datos

Tablas en `trading.db`:

| Tabla | Descripción |
|---|---|
| `roles` | Agentes IA (id, nombre, system_prompt, allowed_tools, provider, model). Roles por defecto: `general`, `analyst_6e`, `risk`, `journal`. |
| `conversations` | Conversaciones del chat (id, título, rol, fechas). |
| `messages` | Mensajes del chat (rol, contenido, timestamp). |
| `trades` | Historial de operaciones sincronizado desde MT5 (ticket, símbolo, acción, volumen, precios, P&L). |
| `journal` | Bitácora SMC de operaciones (POI type, liquidity_swept, cme_confirmation, setup_json, emociones, tags). |
| `agent_settings` | Configuración del agente (rol activo, orden de fallback de modelos, límites, trading_config). |

Aplicación `PRAGMA`: `journal_mode=WAL`, `busy_timeout`, `foreign_keys=ON`.

---

## Agente de IA

### Proveedores y fallback
Cada rol puede tener un proveedor/modelo fijo o usar **auto** (fallback automático). El orden por defecto:

```
gemini/gemini-3.8-flash  →  gemini/gemini-3.5-flash
```

Solo se usan los proveedores cuya API key esté configurada en `.env`.

### Herramientas (tool-calling)

| Herramienta | Descripción |
|---|---|
| `account_info` | Métricas de cuenta MT5 en tiempo real. |
| `positions_list` | Posiciones abiertas. |
| `history` | Historial de operaciones cerradas (días). |
| `price` | Cotización Bid/Ask en vivo de un símbolo. |
| `orderflow_snapshot` | Fotografía del order flow del 6E. |
| `orderflow_alerts` | Alertas de absorción/spikes del 6E. |
| `patterns` | Patrones SMC (FVG, Order Blocks, Sweeps) de un símbolo. |
| `trade_query` | Consulta de operaciones en la BD local. |
| `journal_append` / `journal_list` | Registrar / consultar bitácora SMC. |
| `mt5_export_read` | Leer exportaciones del indicador AI Chart Assistant. |
| `now` | Fecha/hora del servidor. |

### Streaming
El agente transmite la respuesta por **SSE** con eventos tipados (`role`, `status`, `model`, `delta`, `tool`, `error`, `done`), permitiendo a la UI mostrar el estado en tiempo real.

---

## Endpoints API

Rutas principales (todas bajo `http://127.0.0.1:8000`):

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Página principal. |
| `GET` | `/api/account` | Datos de cuenta. |
| `GET` | `/api/positions` | Posiciones abiertas. |
| `GET` | `/api/history?days=N` | Historial de operaciones. |
| `GET` | `/api/price/{symbol}` | Precio de un símbolo. |
| `GET` | `/api/candles/{symbol}` | Velas para el gráfico. |
| `GET` | `/api/candle/last/{symbol}` | Última vela. |
| `GET` | `/api/stream/{symbol}` | Streaming SSE del gráfico. |
| `GET` | `/api/analysis/patterns/{symbol}` | Patrones SMC. |
| `GET` | `/api/analysis/cvd/{symbol}` | Serie CVD. |
| `GET` | `/api/analysis/chartism/{symbol}` | Patrones chartistas (canal, triángulo, bandera, dobles, H-C-H). |
| `GET` | `/api/analysis/smr/{symbol}` | SMR / divergencia DXY. |
| `GET` | `/api/volume-profile/{symbol}` | Volume Profile (POC/VAH/VAL). |
| `GET` | `/api/analysis/footprint/{symbol}` | Footprint (delta por nivel, sintético). |
| `GET` | `/api/analysis/heatmap/{symbol}` | Heatmap de liquidez (sintético). |
| `GET` | `/api/analysis/eventbars/{symbol}` | Event bars (volbar/tickbar/renko). |
| `GET` | `/api/analysis/chart-assistant/{symbol}` | Snapshot para el AI Chart Assistant. |
| `GET` | `/api/orderflow` | Snapshot del order flow (CVD, delta, alertas). |
| `GET/POST` | `/api/orderflow/feed` | Estado/control del feed (`action`, `mode`, `fixture`). |
| `GET` | `/api/orderflow/fixtures` | Escenarios disponibles para el feed mock. |
| `POST` | `/api/orderflow/settings` | Ajustes de Z-score / ventana de absorción. |
| `GET` | `/api/orderflow/cvd?since=` | Serie CVD histórica del 6E. |
| `WS`  | `/ws/orderflow` | WebSocket del order flow. |
| `GET/POST` | `/api/cot/report` · `/api/cot/refresh` | Informe COT (CFTC) y refresco. |
| `GET` | `/api/risk/setup` | Setup Score + breakdown de componentes. |
| `GET` | `/api/risk/audit` | Auditoría win-rate por componente del score. |
| `GET/DELETE` | `/api/chart/alerts*` | Alertas de gráfico persistidas. |
| `GET/PUT/DELETE` | `/api/chart/drawings*` | Drawings del gráfico (líneas/niveles). |
| `GET` | `/api/chart/setup-eval` | Evaluación del setup actual. |
| `POST` | `/api/agent/message` | Envío de mensaje al agente (SSE). |
| `GET/POST/PUT/DELETE` | `/api/agent/roles*` | Gestión de roles. |
| `GET/POST/DELETE` | `/api/agent/conversations*` | Gestión de conversaciones. |
| `GET` | `/api/agent/config` | Config del agente. |
| `GET/POST/PUT/DELETE` | `/api/journal*` | Bitácora (más `/api/journal/overlay`). |
| `GET` | `/api/trades` | Operaciones locales. |
| `POST` | `/api/trades/sync` | Sincroniza historial MT5. |
| `GET` | `/api/db/tables*` | Visor de base de datos local. |
| `GET/POST` | `/api/trade/config` | Config de trading. |
| `GET` | `/api/trade/info/{symbol}` | Info del símbolo para operar. |
| `POST` | `/api/trade/market` | Enviar orden de mercado. |
| `POST` | `/api/positions/{ticket}/close` | Cerrar posición. |
| `GET` | `/api/watcher/status` | Config + estado del watcher. |
| `POST` | `/api/watcher/scan` | Dispara un escaneo manual. |
| `POST` | `/api/watcher/auto-execute` | Conmuta la auto-ejecución del watcher. |
| `GET/POST` | `/api/research/*` | Pipeline de research (runs, export, backtest, calibrate, validate, search, apply, audit). |

---

## Integración con AI Chart Assistant

El proyecto lee las **exportaciones** que escribe el indicador del Market MT5 **"AI Chart Assistant"** (AR_AI_ADV).

- El indicador exporta archivos `.txt` en `MQL5\Files` con los datos computados del gráfico (precios, ATR, RSI, EMAs, niveles D1, swings, velas) y un formato de salida de 13 secciones.
- El agente puede leer estos archivos de dos formas:
  1. **Automática**: pega el path en el chat (p.ej. `MQL5/Files/AR_AI_ADV_...txt`) → el sistema detecta, lee y adjunta el contenido al contexto del LLM.
  2. **Herramienta**: usa `mt5_export_read` con acciones `list` / `read` / `latest`.

El módulo `mt5_export.py` gestiona la ruta, parsea el nombre (símbolo, timeframe, modo) y valida el path.

---

## Pipeline de research

El proyecto incluye un **pipeline de research offline** (`research/`, separado del runtime): exporta histórico de MT5 a CSV, valida la invariante de no-look-ahead, hace **backtest** de la config vigente (`strategy.yaml` / `store`) y sugiere **calibración** (TTL, mínimo de score, riesgo y pesos de componentes) sin sobreescribir la configuración.

```bash
python research/run_research.py backtest --symbol EURUSD --timeframe M15 --days 90
python research/run_research.py calibrate --symbol EURUSD --timeframe M15 --days 90
```

Documentación completa (comandos, decisiones de simulación, pendientes): **`research/README.md`**. Los resultados se guardan en `research/results/` (gitignored).

---

## Estructura del proyecto

```
botTraiding/
├── .env.example          # Plantilla de variables de entorno (copiar a .env)
├── app.py                # Aplicación FastAPI, endpoints, order flow, trading
├── agent.py              # Agente IA: tools, streaming, router de proveedores
├── store.py              # Capa de acceso a SQLite
├── strategy.py           # Carga y valida strategy.yaml (fuente de verdad)
├── strategy.yaml         # Config de la estrategia (riesgo, símbolos, horarios)
├── risk_engine.py        # Setup Score, killzones, R:R, TTL, prop firm (puro)
├── watcher.py            # Bot "a la escucha" de opportunities
├── mt5_export.py         # Lectura de exportaciones AI Chart Assistant
├── mt5_mcp_local.py      # Servidor MCP local de herramientas MT5
├── cvd_service.py        # Cálculo de CVD / delta
├── patterns_service.py   # Servicio de patrones SMC
├── pattern_engine.py     # Motor de detección de patrones SMC
├── chartism_engine.py    # Patrones chartistas clásicos (canal, triángulo, bandera, dobles, H-C-H)
├── cot_service.py        # Informe COT (CFTC)
├── smr_service.py        # SMR / divergencia DXY (Yahoo Finance)
├── ff_calendar.py        # Calendario financiero
├── market_view.py        # Footprint / heatmap / event bars (sintéticos)
├── simulator.py          # Simulador de mercado sintético unificado (6E/EURUSD)
├── mock_feed.py          # Feed sintético determinista para order flow 6E
├── index.html            # Página principal
├── main.js               # Lógica del frontend
├── style.css             # Estilos
├── tools.js              # Utilidades del frontend (drawings)
├── echarts.min.js        # Librería vendada (Apache ECharts v6)
├── ILOF_Executor_Pro.mq5 # EA de ejecución (MetaEditor)
├── research/             # Pipeline offline (backtest + calibración; ver research/README.md)
├── requirements.txt      # Dependencias Python
└── tests/                # Suite de pruebas (pytest + escenarios + fixtures)
```

Notas sobre archivos locales **no versionados** (los crea la app en tiempo de ejecución): `trading.db` (SQLite generada al arrancar), `mt5_status.json` (snapshot de estado MT5) y `.env` (tus API keys).

---

## Seguridad

- **Solo lectura** en el visor de base de datos (no se edita/borra desde la web).
- Los paths de exportaciones se **validan** contra el directorio `MQL5\Files` (`resolve_path`) para evitar *path traversal*.
- Las herramientas del agente son mayormente de solo lectura; la escritura se limita a la bitácora local.
- Las API keys viven en `.env` (no se exponen al frontend).

---

## Notas

- El trading requiere que la terminal **MetaTrader 5** esté abierta y con sesión iniciada.
- Sin MT5 abierto puedes seguir usando: order flow mock (6E), chatbot, patrones/SMC/risk evaluación sobre el simulador sintético y el panel completo de research.
- Para ver cambios de backend recarga la página con **Ctrl+Shift+R** (evita caché).
- El **SMR / DXY** y el **calendario económico** necesitan salida a internet (Yahoo Finance / proxy Jina); si fallan, los guards degradan a aviso sin congelar el sistema.
- Verifica el log del servidor en `server_err.log` ante errores de arranque.
- Documentos de desarrollo incluidos: `ROADMAP.md` (mejoras M1–M4) y `ANALISIS_PROYECTO.md` (auditoría del código).