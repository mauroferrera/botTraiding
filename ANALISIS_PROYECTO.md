# Análisis del proyecto — MT5 Dashboard & Chatbot

Fecha: 2026-09-05. Documento generado a partir de una revisión de código del repositorio.

---

## Resumen ejecutivo

Panel de control web de trading en tiempo real para **MetaTrader 5**, con:

- Dashboard con KPIs de cuenta (balance, equity, P&L, márgenes, posiciones).
- Gráfico en vivo (velas, CVD, patrones SMC: FVG / Order Blocks / Liquidity Sweeps PDH-PDL).
- Order flow del futuro **6E (CME vía Databento)** con CVD, delta, Z-score y absorción de liquidez.
- **Agente de IA** con tool-calling, router multi-proveedor y fallback automático (litellm).
- Trading desde la web ("espejo" de EAs MQL5): órdenes de mercado, SL/TP, riesgo diario.
- Bitácora de trading (journal) con contexto SMC y visor de base de datos local (solo lectura).

**Stack:** Python 3.12 · FastAPI · Uvicorn · SQLite (`trading.db`) · Vanilla JS · Lightweight Charts → Apache ECharts (migración) · WebSocket/SSE · `MetaTrader5` · `databento` · `litellm`.

---

## Arquitectura

```
index.html + main.js (frontend vanilla)
   │  REST + SSE + WebSocket
   ▼
app.py (FastAPI, ~1900 líneas)
  ├── OrderFlowEngine   (CVD, delta, z-score, absorción 6E / Databento, thread-safe)
  ├── patterns_service  → pattern_engine (FVG, OB, Sweeps, PDH/PDL)
  ├── cvd_service       (CVD sintético desde tick volume de MT5)
  ├── chat por intents  (regex, coexiste con el agente IA)
  ├── agent.py          (tool-calling, router multi-proveedor, streaming SSE)
  │     ├── store.py            (SQLite: roles, conversaciones, journal, trades)
  │     ├── mt5_export.py       (exportaciones del indicador AI Chart Assistant)
  │     └── ff_calendar.py      (calendario económico vía proxy Jina)
  └── mt5_mcp_local.py  (servidor MCP independiente, NO conectado con app.py)
```

**Concurrencia:** todo acceso a MT5 pasa por un `ThreadPoolExecutor` de 1 hilo + `threading.Lock`; cada llamada reabre la conexión (`initialize()/shutdown()`), sin conexión persistente.

### Estructura del proyecto

| Archivo | Rol |
|---|---|
| `app.py` | FastAPI: endpoints, OrderFlowEngine, trading, streaming, chat intents |
| `agent.py` | Agente IA: herramientas, router/fallback, streaming SSE |
| `store.py` | Capa SQLite (roles, conversaciones, journal, trades, config) |
| `patterns_service.py` + `pattern_engine.py` | Patrones SMC (fetch MT5 + algoritmos puros) |
| `cvd_service.py` | CVD sintético del símbolo del gráfico |
| `mt5_export.py` | Lectura de exportaciones del indicador AI Chart Assistant |
| `mt5_mcp_local.py` | Servidor MCP local independiente (MT5) |
| `ff_calendar.py` | Calendario Forex Factory vía proxy Jina |
| `index.html` / `main.js` / `style.css` | Frontend vanilla |
| `lightweight-charts.*.js` | Librería de gráficos (reemplazada por `echarts.min.js`) |

### Flow del agente IA

```
/api/agent/message (SSE)
  → agent.stream_agent
     → rol + settings + tools permitidos (store)
     → detecta anexo AR_AI_ADV_*.txt pegado en el chat (mt5_export)
     → _route_model / resolve_model_chain (fallback + rotación de claves Gemini)
     → loop de rondas: acompletion (litellm) → ejecuta tools (timeout 4 s) → repite
     → eventos SSE: status / tool / delta / error / done
```

---

## Puntos fuertes

- Serialización correcta de MT5 (lock + executor de 1 hilo) y `OrderFlowEngine` thread-safe con un solo lock.
- Envoltorios uniformes `_ok/_fail/_safe` en las tools del agente.
- `pattern_engine.py` es puro (OHLC → patrones), sin dependencia de MT5, fácilmente testeable.
- `enrich_journal_entry` defensiva (nunca lanza).
- Path-traversal mitigado en `mt5_export.resolve_path`; chat del agente escapado contra XSS.
- Mensajes de error MT5 en español; compatibilidad mitigada con `getattr`/`_sfield` para versiones del paquete MetaTrader5.

---

## Deudas técnicas priorizadas

### 1 · Seguridad (critica)

- **[XSS real] `dbValue`** (main.js:232-242): los valores objeto se insertan vía `JSON.stringify` dentro de `<code>` SIN escapar.
  *(Estado: corregido durante la migración a ECharts)*
- **Endpoints de trading sin autenticación** (`/api/trade/market`, `/api/positions/{ticket}/close`, `/api/journal`). Cualquiera que alcance el dashboard en la red puede mandar órdenes. Riesgo serio si el servidor sale de localhost.
- **`innerHTML` sin escapar**: alertas de order flow (`ofAddAlert`) y filas de posiciones/historial (`positionRow`/`historyRow`). Riesgo bajo-medio (datos MT5/Databento), pero patrón inseguro. *(ofAddAlert corregido)*
- **Sin CSRF ni rate-limit** en endpoints de escritura.

### 2 · Duplicación / redundancia (mayor deuda estructural)

- **Inicialización MT5 duplicada en 3 módulos** con 3 locks y 3 executors sobre la misma DLL: `app.py:47` (`_mt5_call_sync`), `patterns_service.py:52` (`_mt5_call_lock`), `cvd_service.py:39` (`_mt5_call_lock`). Nombres de thread "mt5", "mt5p", "mt5c".
- **`TIMEFRAMES` duplicado**: `app.py:779-788` y `patterns_service.py:24-33`.
- **Cachés TTL duplicadas**: `patterns_service` (10 s) y `cvd_service` (5 s), sin invalidación cruzada.
- **Conversión de velas duplicada**: `to_candle` (app.py:793) vs `_candle` (patterns_service.py:70).
- **Bucle de fillings FOK→IOC + retry** duplicado literalmente en `send_market_order` (app.py:1636-1684) y `close_position` (app.py:1710-1752); retcodes `10030/10004/10020` hardcodeados pese a existir `_RETCODE_LABELS`.
- **Patrón de manejo de errores** `except ValueError→400 / RuntimeError→503 / None→404` repetido en ~7 endpoints.
- **Doble sistema de chat**: intents regex (`chat_answer`) + agente IA (`/api/agent/message`).

### 3 · Agente IA

- **`resolve_model_chain` inerte**: en `stream_agent` (agent.py:524) `or` nunca se ejecuta porque `_route_model` siempre devuelve lista no vacía → el proveedor/modelo por rol y el `fallback_order` persistido quedan ignorados de facto.
- **Historial multi-turno incompleto**: solo se persisten mensajes `user`/`assistant`; los resultados de tools (`role:"tool"`) solo viven en el turno actual → en turnos siguientes el modelo puede recibir tool-calls huérfanos sin respuesta.
- **Pérdida del texto bufferizado** en la ruta local con tool-calls (agent.py:620-629).
- **Hilos huérfanos**: `asyncio.wait_for` sobre `to_thread` con timeout de 4 s cancela la coroutina pero el hilo MT5 sigue corriendo.
- **`TOOL_HANDLERS` muerto** (agent.py:190) y `price` con formato inconsistente (`status:"ok"` con error embebido).
- **`gemini-3.6-flash`** como modelo por defecto en seed/settings (nombre atípico, riesgo de no existir).
- `_fetch_live_data` coincide por substrings en español → sobre-dispara o falla.
- Sin backoff ante 429/rate-limit (`max_retries=0`).

### 4 · Frontend / dashboard

- **Modal "Editar rol del agente" muerto**: HTML completo sin handlers en main.js; `ROLES`/`TOOL_LABELS` (desactualizados) semi-utilizados.
- **Conversaciones limitadas a "nueva"**: la UI no lista/carga/borra conversaciones aunque los endpoints existen.
- **Sincronización del sub-chart CVD por rango lógico** frágil (eliminada con la migración a ECharts: ahora un solo chart con 2 grids).
- **Sin `AbortController`/timeout** en `sendChat` ni en varios fetch → la UI puede colgarse.
- **BUY/SELL no se deshabilitan** cuando el riesgo diario está bloqueado (solo se bloquea server-side).
- **`console.log` de debug** en producción en patrones.
- **Doble fuente de verdad del símbolo**: `els.chartSymbol` (input) vs `chartState.symbol`.
- Reconstrucción completa del DOM de tablas cada 8 s (pierde foco/estado; escala mal).

### 5 · Rendimiento y robustez

- **SSE reabre MT5 2×/segundo**: el `stream_generator` hace 2 llamadas `initialize()/shutdown()` por segundo.
- **`sync_trades()` reingesta 365 días** de historial tras cada operación.
- **Encoder SSE inconsistente**: `ensure_ascii=False` en agent.py pero no en el stream de velas (app.py:898). *(corregido)*
- **`@app.on_event("startup")` deprecado** → migrar a lifespan de FastAPI.
- **Parche [TEMPORAL] Databento**: feed live desactivado por falta de licencia; `enabled` se autodesactiva tras error (lógica temporal en el flujo principal).
- Estado global mutable sin tipos (`DB_STATE`, `_main_loop`).
- SSE del agente no emite `event:`/`id:` y el front reconecta sin resincronización; parseo manual `slice(6)` frágil.

---

## Estado actual

- Cuenta demo conectada en `mt5_status.json` (login, balance y estado de cuenta locales).
- El `server_err.log` muestra que MT5 estaba cerrado en el último arranque ("No hay conexión con MetaTrader 5").
- `store.py` conserva roles legacy (inactivos) y deja solo `general` activo; migración de la columna `active` automática.
- **Migración de gráficos completada**: Lightweight Charts reemplazado por Apache ECharts v5 vendado (`/static/echarts.min.js`, sin CDN). Una sola instancia ECharts con 2 grids (velas 56% + CVD 20%) en `main.js`, zoom sincronizado vía `xAxisIndex: [0,1]`, y el sub-chart CVD eliminado (`cvdSubChart`/`timeScale` sync borrados). `#ofChart` es una instancia ECharts independiente. Incluye fixes XSS (`dbValue`, `ofAddAlert` → `textContent`), eliminación de `console.log` de debug y `ensure_ascii=False` en el SSE (app.py:898).
- **Router de modelos rediseñado** (agent.py): `resolve_model_chain(role)` es la única fuente (rol con provider/model explícitos manda; si `auto` usa `fallback_order` persistido; last resort `DEFAULT_CHAIN`). Eliminado `_route_model` y `TOOL_HANDLERS` muerto. `DEFAULT_CHAIN = gemini/gemini-3.8-flash → gemini-3.5-flash`; modelos legacy (`3.6/3.7-flash`) se reasignan automáticamente. Heurística `_is_complex` solo elige el modo de respuesta (no el modelo).
- **3 modos de respuesta** en `stream_agent`: `tools` (mensaje complejo), `simple auto` (sin tools + live data inyectado via `_fetch_live_data`, matcher por palabras), `simple forzado` (botón "Analizar Gráfico con IA" = `skipTools`: sin tools y sin live data extra, el snapshot ya va en el mensaje). Primario local con tools → degradación controlada a modo simple.
- **Backoff 429**: rate-limit con la misma clave/modelo (0.5→1→2 s, máx 3) antes de rotar a la siguiente de las 3 claves Gemini (`_provider_tasks`).
- **Multi-turno con tools**: migración SQLite (`messages.tool_call_id`, `messages.name`), `add_message`/`get_messages` actualizados; los `role:"tool"` se persisten como traza de debug y se sanean fuera del historial que ve la API (evita conversaciones inválidas en turnos siguientes).

---

## Próximos pasos recomendados

1. **Autenticación para endpoints de escritura** (mínimo: token en cabecera para `/api/trade/*` y `/api/journal`).
1. **Autenticación para endpoints de escritura** (mínimo: token en cabecera para `/api/trade/*` y `/api/journal`).
2. **Refactor de la capa MT5**: un módulo único `mt5_client.py` con conexión persistente o un pool bien gestionado; eliminar la triplicación (los hilos huérfanos de `asyncio.wait_for` sobre `to_thread` quedan serializados por el executor de 1 hilo: inofensivos, solo lentos).
3. **Terminar la UI de roles y conversaciones** (el código backend ya existe).