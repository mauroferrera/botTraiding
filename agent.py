import asyncio
import json
import math
import os
from datetime import datetime

from litellm import acompletion

import store

import litellm
litellm.drop_params = True

# ============================================================
# Herramientas del agente (todas solo-lectura + journal)
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "account_info",
            "description": "Obtiene métricas en tiempo real de la cuenta MT5: balance, equity, ganancia/pérdida flotante, margen usado, margen libre y nivel de margen.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "positions_list",
            "description": "Lista las posiciones abiertas actualmente en MT5 (símbolo, dirección BUY/SELL, volumen, precio de apertura, SL/TP y ganancia flotante).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "history",
            "description": "Obtiene las operaciones cerradas desde el historial de MT5 de los últimos N días.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Número de días a mirar hacia atrás (por defecto 7).", "minimum": 1, "maximum": 365}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "price",
            "description": "Obtiene la cotización Bid/Ask en vivo de un símbolo (EURUSD, XAUUSD, 6E...).",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string", "description": "Símbolo, ej: EURUSD, XAUUSD."}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "orderflow_snapshot",
            "description": "Fotografía del order flow del futuro 6E (CME): CVD acumulado, delta del último trade, volumen total, volumen compra/venta, precio, conteo de picos Z-score y alertas recientes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "orderflow_alerts",
            "description": "Lista las últimas alertas de absorción y picos institucionales detectadas por el motor de order flow del 6E.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patterns",
            "description": "Detecta patrones SMC en tiempo real sobre un símbolo: Fair Value Gaps (FVG) activos o mitigados, Order Blocks de break of structure y Liquidity Sweeps de PDH/PDL. Útil para validar entradas y clasificar setups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD, XAUUSD."},
                    "timeframe": {"type": "string", "description": "M1, M5, M15, M30, H1, H4 (por defecto M15)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trade_query",
            "description": "Consulta la base de datos local de operaciones sincronizadas (historial MT5) con filtros por símbolo/dirección/días.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Filtro por símbolo (EURUSD, 6E...)."},
                    "action": {"type": "string", "description": "Filtro por dirección: BUY o SELL."},
                    "days": {"type": "integer", "description": "Filtrar por últimos N días.", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "description": "Máximo de filas (por defecto 50).", "minimum": 1, "maximum": 500},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "journal_append",
            "description": "Registra una entrada en la bitácora de trading. Campos SMC: poi_type (FVG, OrderBlock, Breaker), liquidity_swept (PDH, PDL, SessionHigh...), cme_confirmation (DivergenciaCVD, SpikeVolume...), emotion, plan_compliance, tags y notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, por defecto EURUSD."},
                    "action": {"type": "string", "description": "BUY o SELL."},
                    "poi_type": {"type": "string", "description": "Tipo de setup: FVG, Order Block, Breaker, etc."},
                    "liquidity_swept": {"type": "string", "description": "Liquidez barrida: PDH, PDL, Session High/Low, etc."},
                    "cme_confirmation": {"type": "string", "description": "Confirmación CME: Divergencia CVD, Spike Volume, Absorcion, etc."},
                    "emotion": {"type": "string", "description": "Estado emocional durante la operación."},
                    "plan_compliance": {"type": "boolean", "description": "¿Se cumplió el plan?"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Etiquetas libres."},
                    "notes": {"type": "string", "description": "Notas detalladas de la operación."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "journal_list",
            "description": "Lista entradas de la bitácora (opcional: filtro por símbolo y días).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mt5_export_read",
            "description": "Lee las exportaciones del indicador 'AI Chart Assistant' (AR_AI_ADV), archivos .txt que escribe en MQL5\\Files de MT5 con los datos computados del gráfico (precios, ATR, RSI, EMAs, niveles D1, swings, velas). Acciones: 'list' para listar las exportaciones recientes, 'read' pasando filename para leer su contenido, o 'latest' para leer el contenido de la más reciente (filtrable por symbol/mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "read", "latest"], "description": "list, read (con filename) o latest (con symbol/mode opcional)."},
                    "filename": {"type": "string", "description": "Nombre del archivo .txt a leer (solo con action='read')."},
                    "symbol": {"type": "string", "description": "Filtrar por símbolo, ej: EURUSD (déjalo vacío para todos)."},
                    "mode": {"type": "string", "description": "Filtrar por modo: 'Analyze Chart', 'Full Trade Plan', 'Quick Default Analyze', 'Manual'."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart_snapshot",
            "description": "Genera el snapshot técnico de la AI Chart Assistant para un símbolo: precio en vivo, PDH/PDL, velas recientes, análisis SMC (FVG, Order Blocks, Sweeps) y la exportación más reciente del indicador. Devuelve el contexto estructurado para redactar un diagnóstico educativo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD (por defecto EURUSD)."},
                    "timeframe": {"type": "string", "description": "M1, M5, M15, M30, H1, H4 (por defecto M15)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "setup_score",
            "description": "Setup Score determinista (0-100) del risk engine para una dirección concreta: breakdown de los 4 componentes (COT, CVD/Order Flow, SMC, Killzone en UTC), veredicto (ALTA/MEDIA/SIN_OPERATIVA), régimen de mercado, nivel de invalidez estructural y precio actual. Úsala ANTES de recomendar una entrada y recálcala siempre (no reutilices una score vieja: expira).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD (por defecto EURUSD)."},
                    "timeframe": {"type": "string", "description": "M1, M5, M15, M30, H1, H4 (por defecto M15)."},
                    "direction": {"type": "string", "enum": ["BUY", "SELL"], "description": "Dirección del setup (por defecto BUY)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "now",
            "description": "Devuelve la fecha y hora actual del servidor.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "economic_news",
            "description": "Obtiene del calendario económico de Forex Factory la última y la próxima noticia del día relevantes para EUR/USD (monedas EUR y USD), con su hora, nivel de impacto y título. Útil para saber qué dato acaba de salir y cuál viene.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_chart_alert",
            "description": "Coloca un nivel de alarma VISUAL persistente sobre el gráfico (línea horizontal amarilla) y lo guarda en la base de datos; cuando el precio en vivo alcance el nivel y se cumplan TODAS las condiciones extra (si se dan), el dashboard avisa automáticamente. Úsala cuando el usuario pida cosas como 'avísame si el EURUSD toca 1.1650 dentro de la killzone de Nueva York' o 'pon una alerta en X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD, XAUUSD."},
                    "price": {"type": "number", "description": "Precio del nivel de alerta."},
                    "label": {"type": "string", "description": "Etiqueta corta, ej: 'Resistencia' o 'Soporte diario'."},
                    "side": {"type": "string", "enum": ["above", "below", "touch"], "description": "above: avisa cuando el precio suba a ese nivel; below: cuando baje; touch: al pasar por él (default)."},
                    "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"], "description": "Timeframe de referencia para las condiciones SMC (patrones); por defecto M15. No afecta al precio en vivo."},
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["killzone", "smc", "ttl"], "description": "killzone: solo dispara dentro de la ventana de sesión; smc: requiere un patrón (FVG/OB/sweep) cuya zona contenga el precio; ttl: autoexpiración."},
                                "name": {"type": "string", "description": "Para killzone: 'Londres' o 'Nueva York' (UTC)."},
                                "pattern": {"type": "string", "enum": ["fvg", "order_blocks", "sweep"], "description": "Para smc: qué tipo de patrón exige (por defecto fvg)."},
                                "side": {"type": "string", "description": "Para smc: 'bullish' o 'bearish' para filtrar por dirección; para sweep: 'PDH_SWEEP' o 'PDL_SWEEP'."},
                                "minutes": {"type": "integer", "description": "Para ttl: minutos de vigencia desde la creación."},
                            },
                        },
                    },
                    "expires_in_minutes": {"type": "integer", "description": "Autoexpiración de la alerta (TTL) en minutos desde su creación; al vencer se cancela y el dashboard avisa. Ej: 30 para 'que expire en media hora'."},
                },
                "required": ["symbol", "price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart_drawings",
            "description": "Lee los dibujos manuales que el usuario guardó en el gráfico (líneas de tendencia, niveles horizontales, rectángulos, texto, mediciones). Devuelve coordenadas reales: tiempo en epoch segundos y precios. Úsalo antes de opinar sobre lo que el usuario marcó en pantalla.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD."},
                    "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"], "description": "Timeframe del gráfico (por defecto M15)."},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart_annotate",
            "description": "Dibuja en el gráfico anotaciones del análisis. Dos modos: (1) marcar PATRONES reales (FVG / Order Block / Liquidity Sweep): las refs son los valores start_time/time (epoch segundos) EXACTOS que devuelve la tool 'patterns' del mismo símbolo/timeframe, cópialos tal cual, NUNCA los inventes; el server valida cada ref y descarta las que no existen. (2) dibujar FIGURAS LIBRES: kind 'line' / 'horizontal' / 'rect' / 'text' con coordenadas propias (start_time/end_time en epoch segundos, price_from/price_to en precio); el server valida que estén dentro de la ventana de velas real del símbolo y las recorta si hace falta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Símbolo, ej: EURUSD."},
                    "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"], "description": "Mismo timeframe con el que se consultó 'patterns' (por defecto M15)."},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["markArea", "markPoint", "line", "horizontal", "rect", "text"], "description": "markArea dibuja una zona (FVG/Order Block), markPoint una flecha (Sweep). line/horizontal/rect/text dibujan figuras libres con sus propias coordenadas."},
                                "pattern": {"type": "string", "enum": ["fvgs", "order_blocks", "sweeps"], "description": "Grupo de patrones donde buscar la ref (solo para markArea/markPoint)."},
                                "ref": {"type": ["integer", "string"], "description": "start_time (para fvgs/order_blocks) o time (para sweeps) exacto devuelto por 'patterns'."},
                                "start_time": {"type": ["integer", "string"], "description": "Inicio en epoch segundos (para figuras libres o si el agente marca un rango)."},
                                "end_time": {"type": ["integer", "string"], "description": "Fin en epoch segundos (solo line/rect)."},
                                "price_from": {"type": "number", "description": "Precio inicial de la figura (solo line/horizontal/rect/text)."},
                                "price_to": {"type": "number", "description": "Precio final (solo line/rect)."},
                                "name": {"type": "string", "description": "Etiqueta opcional (texto de la figura 'text' o leyenda)."},
                            },
                            "required": ["kind"],
                        },
                    },
                },
                "required": ["symbol", "actions"],
            },
        },
    },
]

def _ok(data):
    return {"status": "ok", "data": data}


def _fail(error):
    return {"status": "failed", "data": None, "error": str(error)}


# Último análisis de patrones por (symbol|timeframe) para anclar las anotaciones
# del agente a datos reales (refs exactas de start_time/time) y no a coordenadas
# inventadas por el LLM.
_LAST_ANALYSIS = {}


def _safe(fn, *args, **kwargs):
    try:
        return _ok(fn(*args, **kwargs))
    except Exception as exc:
        return _fail(exc)


def _handler(name, args):
    if name == "now":
        return _ok({"datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    import app  # import tardío para evitar ciclos

    if name == "account_info":
        return _safe(app.get_account)
    if name == "positions_list":
        return _safe(app.get_positions)
    if name == "history":
        return _safe(app.get_history, int(args.get("days", 7)))
    if name == "price":
        return _ok(app.get_price(str(args.get("symbol", "EURUSD")).upper()) or {"status": "offline", "data": None, "error": "símbolo no disponible"})
    if name == "orderflow_snapshot":
        return _ok(app.engine.snapshot())
    if name == "orderflow_alerts":
        return _ok(list(app.engine.alerts)[-20:])
    if name == "patterns":
        symbol = str(args.get("symbol", "EURUSD")).upper()
        timeframe = str(args.get("timeframe", "M15")).upper()

        def _patterns():
            data = app.patterns_service.get_pattern_data(symbol, timeframe)
            if data is None:
                raise RuntimeError(f"Sin datos de '{symbol}' (¿símbolo en Market Watch?).")
            candles = data.get("candles") or []
            _LAST_ANALYSIS[f"{symbol}|{timeframe}"] = {
                "analysis": data["analysis"],
                "last_time": candles[-1]["time"] if candles else None,
                "candle_start": candles[0]["time"] if candles else None,
                "candle_lo": min((c.get("low") for c in candles), default=None),
                "candle_hi": max((c.get("high") for c in candles), default=None),
            }
            return data["analysis"]

        return _safe(_patterns)
    if name == "trade_query":
        return _ok(store.list_trades(
            symbol=args.get("symbol"),
            action=(args.get("action") or "").upper() or None,
            days=args.get("days"),
            limit=int(args.get("limit", 50)),
        ))
    if name == "journal_append":
        entry = {
            "conversation_id": args.get("conversation_id"),
            "ticket": args.get("ticket"),
            "symbol": args.get("symbol", "EURUSD"),
            "action": (args.get("action") or "").upper() or None,
            "poi_type": args.get("poi_type"),
            "liquidity_swept": args.get("liquidity_swept"),
            "cme_confirmation": args.get("cme_confirmation"),
            "emotion": args.get("emotion"),
            "plan_compliance": args.get("plan_compliance"),
            "tags": args.get("tags") or [],
            "notes": args.get("notes"),
        }
        try:
            entry = app.enrich_journal_entry(entry)
        except Exception:
            pass  # si MT5 no responde, se guarda tal cual
        return _ok(store.add_journal_entry(entry))
    if name == "journal_list":
        return _ok(store.list_journal(symbol=args.get("symbol"), days=args.get("days"), limit=int(args.get("limit", 50))))
    if name == "mt5_export_read":
        import mt5_export as me
        action = str(args.get("action", "list")).lower()
        try:
            if action == "list":
                return _ok(me.list_exports(symbol=args.get("symbol"), mode=args.get("mode"), limit=int(args.get("limit", 10))))
            if action == "read":
                filename = args.get("filename")
                if not filename:
                    return _fail("Falta 'filename' para action='read'")
                return _ok(me.read_export(str(filename)))
            if action == "latest":
                return _ok(me.latest_export(symbol=args.get("symbol"), mode=args.get("mode")))
            return _fail("action debe ser list, read o latest")
        except Exception as exc:
            return _fail(exc)
    if name == "chart_snapshot":
        return _safe(lambda: app.build_chart_snapshot(
            symbol=str(args.get("symbol", "EURUSD")),
            timeframe=str(args.get("timeframe", "M15")),
        ))
    if name == "get_chart_drawings":
        return _safe(lambda: _summarize_drawings(args))
    if name == "setup_score":
        symbol = str(args.get("symbol", "EURUSD")).upper()
        timeframe = str(args.get("timeframe", "M15")).upper()
        direction = str(args.get("direction", "BUY")).upper()

        def _setup_score():
            snap = app.build_chart_snapshot(symbol, timeframe)
            risk = snap.get("risk_engine")
            if not risk:
                raise RuntimeError("risk_engine no disponible para este snapshot.")
            prefix = "bull" if direction == "BUY" else "bear"
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": direction,
                "current_price": snap.get("current_price"),
                "score": risk[prefix]["score"],
                "verdict": risk[prefix]["verdict"],
                "components": risk[prefix]["components"],
                "regime": risk["regime"],
                "killzone": risk["killzone"],
                "invalidation": risk["invalidation"],
            }

        return _safe(_setup_score)
    if name == "economic_news":
        def _news():
            import ff_calendar as ff
            return ff.eurusd_news()
        return _safe(_news)
    if name == "set_chart_alert":
        symbol = str(args.get("symbol", "")).upper()
        try:
            price = float(args.get("price"))
        except (TypeError, ValueError):
            return _fail("price debe ser un número")
        if not symbol or not (0 < price < 1e7):
            return _fail("symbol inválido o precio fuera de rango")
        side = str(args.get("side") or "touch").lower()
        if side not in ("above", "below", "touch"):
            side = "touch"
        conditions = args.get("conditions") or []
        tf = str(args.get("timeframe") or "M15").upper()
        expires_in_minutes = args.get("expires_in_minutes")
        expires_at = None
        try:
            if expires_in_minutes is not None and int(expires_in_minutes) > 0:
                from datetime import datetime, timedelta
                expires_at = (datetime.now() + timedelta(minutes=int(expires_in_minutes))).strftime("%Y-%m-%dT%H:%M:%S")
        except (TypeError, ValueError):
            expires_at = None
        return _safe(lambda: store.add_chart_alert(
            symbol, price, args.get("label"), side,
            conditions=conditions, timeframe=tf if conditions else None,
            expires_at=expires_at,
        ))
    if name == "chart_annotate":
        return _safe(lambda: _resolve_annotations(args))

    return _fail("Herramienta no encontrada")


def _resolve_annotations(args):
    """Convierte referencias de patrones (start_time/time reales) en datos ECharts
    listos para dibujar, y figuras libres (line/horizontal/rect/text) coords propias.
    Valida cada ref contra el último análisis en caché / la ventana real de velas; las
    refs inexistentes o coordenadas fuera de rango se descartan o recortan (nunca se
    inventan completamente)."""
    symbol = str(args.get("symbol", "EURUSD")).upper()
    tf = str(args.get("timeframe", "M15")).upper()
    entry = _LAST_ANALYSIS.get(f"{symbol}|{tf}")
    if not entry:
        raise RuntimeError(
            f"Sin análisis de patrones en caché para {symbol} {tf}. "
            "Consulta primero 'patterns' del MISMO símbolo/timeframe." 
        )
    analysis = entry["analysis"]
    last_time = entry["last_time"]
    patterns = analysis.get("patterns", {})
    actions = (args.get("actions") or [])[:8]

    win_cache = {}

    def _window():
        if "win" in win_cache:
            return win_cache["win"]
        w = None
        if entry.get("candle_start") is not None and entry.get("last_time") is not None:
            w = {
                "start": entry["candle_start"],
                "last": entry["last_time"],
                "lo": entry.get("candle_lo"),
                "hi": entry.get("candle_hi"),
            }
        if w is None or w["lo"] is None or w["hi"] is None:
            import app as _app
            data = _app.patterns_service.get_pattern_data(symbol, tf)
            candles = (data or {}).get("candles") or []
            if not candles:
                raise RuntimeError(f"Sin velas reales para {symbol} {tf}: no puedo validar coordenadas.")
            w = {
                "start": candles[0]["time"],
                "last": candles[-1]["time"],
                "lo": min((c.get("low") for c in candles), default=None),
                "hi": max((c.get("high") for c in candles), default=None),
            }
        win_cache["win"] = w
        return w

    def _num(v):
        if v is None or v == "":
            return None
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return x if math.isfinite(x) else None

    def _clamp_price(p, win):
        span = (win["hi"] - win["lo"]) or p
        lo = win["lo"] - span * 0.25
        hi = win["hi"] + span * 0.25
        return max(lo, min(hi, p))

    def _clamp_t(t, win):
        return max(win["start"], min(win["last"], t))

    mark_area, mark_point, draw = [], [], []
    applied = skipped = 0
    for act in actions:
        if not isinstance(act, dict):
            skipped += 1
            continue
        kind = act.get("kind")
        pat = act.get("pattern")
        try:
            ref = int(act.get("ref"))
        except (TypeError, ValueError):
            ref = None
        label = act.get("name")

        if kind == "markArea" and pat in ("fvgs", "order_blocks"):
            obj = next(
                (z for z in patterns.get(pat, []) if int(z.get("start_time", -1)) == ref),
                None,
            )
            if not obj:
                skipped += 1
                continue
            if pat == "fvgs":
                bull = obj.get("type") == "BULLISH_FVG"
                color = "rgba(38,166,154,0.30)" if bull else "rgba(239,83,80,0.30)"
                border = "#26a69a" if bull else "#ef5350"
                name = label or f"{'Bullish' if bull else 'Bearish'} FVG {tf}"
            else:
                color = "rgba(41,98,255,0.35)"
                border = "#2962ff"
                name = label or f"Order Block {tf}"
            mark_area.append([
                {
                    "xAxis": ref,
                    "yAxis": obj["bottom"],
                    "itemStyle": {"color": color, "borderColor": border, "borderType": "dashed"},
                    "label": {"show": True, "color": border, "fontSize": 10, "position": "insideTop"},
                    "name": name,
                },
                {"xAxis": last_time, "yAxis": obj["top"]},
            ])
            applied += 1
        elif kind == "markPoint" and pat == "sweeps":
            obj = next(
                (s for s in patterns.get("sweeps", []) if int(s.get("time", -1)) == ref),
                None,
            )
            if not obj:
                skipped += 1
                continue
            is_pdh = obj.get("type") == "PDH_SWEEP"
            mark_point.append({
                "coord": [ref, obj["wick_extreme"]],
                "value": label or ("PDH" if is_pdh else "PDL"),
                "symbol": "arrowDown" if is_pdh else "arrowUp",
                "symbolSize": 14,
                "symbolOffset": [0, -6] if is_pdh else [0, 6],
                "itemStyle": {"color": "#ff5d6c" if is_pdh else "#2ee6a8", "borderColor": "transparent"},
                "label": {"show": False},
            })
            applied += 1
        elif kind in ("line", "horizontal", "rect", "text"):
            win = _window()
            p0 = _num(act.get("price_from"))
            p1 = _num(act.get("price_to"))
            t0 = _num(act.get("start_time"))
            t1 = _num(act.get("end_time"))
            it = {"origin": "agent"}
            if kind in ("line", "rect"):
                if p0 is None or p1 is None:
                    skipped += 1
                    continue
                it["tool"] = "line" if kind == "line" else "rect"
                it["p0"] = _clamp_price(p0, win)
                it["p1"] = _clamp_price(p1, win)
                a = _clamp_t(t0 if t0 is not None else win["start"], win)
                b = _clamp_t(t1 if t1 is not None else win["last"], win)
                if b < a:
                    a, b = b, a
                it["t0"], it["t1"] = a, b
            elif kind == "horizontal":
                if p0 is None:
                    skipped += 1
                    continue
                it["tool"] = "hline"
                it["p0"] = _clamp_price(p0, win)
            else:  # text
                if p0 is None:
                    skipped += 1
                    continue
                it["tool"] = "text"
                it["t0"] = _clamp_t(t0 if t0 is not None else win["last"], win)
                it["p0"] = _clamp_price(p0, win)
                it["text"] = (act.get("name") or "").strip()[:60]
            draw.append(it)
            applied += 1
        else:
            skipped += 1

    if not mark_area and not mark_point and not draw:
        raise RuntimeError("Ninguna ref de patrón ni coordenada de dibujo válida.")

    # Límites de cámara para que el front pueda enfocar la zona dibujada (solo con
    # coordenadas reales aplicadas; nunca inventadas).
    view = None
    if mark_area or mark_point or draw:
        refs, lo, hi = [], None, None
        for pair in mark_area:
            refs.append(pair[0]["xAxis"])
            y1, y2 = pair[0]["yAxis"], pair[1]["yAxis"]
            lo = y1 if lo is None else min(lo, y1)
            hi = y2 if hi is None else max(hi, y2)
        for pt in mark_point:
            refs.append(pt["coord"][0])
            y = pt["coord"][1]
            lo = y if lo is None else min(lo, y)
            hi = y if hi is None else max(hi, y)
        for d in draw:
            t_val = d.get("t0") if d.get("t0") is not None else d.get("t1")
            if t_val is not None:
                refs.append(t_val)
            for pk in ("p0", "p1"):
                y = d.get(pk)
                if y is None:
                    continue
                lo = y if lo is None else min(lo, y)
                hi = y if hi is None else max(hi, y)
        end_time = None
        if refs:
            tmin = min(refs)
            span = max((max(refs) - tmin) * 4, 3600 * 2)
            end_time = min(last_time, tmin + span)
            view = {
                "start_time": tmin,
                "end_time": end_time,
                "price_min": lo,
                "price_max": hi,
            }
    return {
        "symbol": symbol,
        "timeframe": tf,
        "applied": applied,
        "skipped": skipped,
        "echarts": {"markArea": mark_area, "markPoint": mark_point, "draw": draw},
        "view": view,
    }


def _summarize_drawings(args):
    """Devuelve los dibujos manuales del usuario en formato legible para el LLM."""
    symbol = str(args.get("symbol", "EURUSD")).upper()
    tf = str(args.get("timeframe", "M15")).upper()
    drawings = store.get_drawings(symbol, tf) or []
    tool_names = {
        "line": "línea de tendencia",
        "hline": "nivel horizontal",
        "rect": "rectángulo",
        "measure": "medición",
        "text": "texto",
    }
    lines = []
    for i, d in enumerate(drawings[:50], 1):
        if not isinstance(d, dict):
            continue
        tool = tool_names.get(d.get("tool"), str(d.get("tool") or "dibujo"))
        origin = "agente" if d.get("origin") == "agent" else "usuario"
        tk = d.get("tool")
        try:
            if tk == "hline":
                detail = f"nivel {float(d.get('p0')):.5f}"
            elif tk == "text":
                detail = f"'{d.get('text', '')}' en t={d.get('t0')} p={float(d.get('p0') or 0):.5f}"
            elif tk in ("line", "rect", "measure"):
                detail = (
                    f"de (t={d.get('t0')}, p={float(d.get('p0') or 0):.5f}) "
                    f"a (t={d.get('t1')}, p={float(d.get('p1') or 0):.5f})"
                )
            else:
                detail = json.dumps(d)
        except (TypeError, ValueError):
            detail = json.dumps(d)
        lines.append(f"{i}. [{origin}] {tool}: {detail}")
    return {
        "symbol": symbol,
        "timeframe": tf,
        "count": len(drawings),
        "drawings": drawings,
        "lectura": "; ".join(lines) if lines else "No hay dibujos guardados para este símbolo/timeframe.",
        "nota": "Los tiempos están en epoch segundos; coordina con 'patterns'/'chart_snapshot' del mismo símbolo y timeframe.",
    }


# ============================================================
# Router de proveedores (fallback GPT -> Gemini -> Claude)
# ============================================================

PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
}

DEFAULT_CHAIN = ["gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash"]

LOCAL_MODEL = "ollama/llama3.2:3b"

# Señales de peticiones complejas (análisis de mercado, SMC, order flow, noticias)
COMPLEX_HINTS = (
    "analiza", "análisis", "analisis", "analizar", "order flow", "patrones", "patrón",
    "smc", "gráfico", "grafico", "graficar", "evaluar", "recomendación", "recomendacion",
    "setup", "tendencia", "cvd", "delta", "volumen", "absorb", "absorción", "barrido",
    "pdh", "pdl", "fvg", "order block", "liquidez", "liquidity", "chart", "economic_news",
    "noticias", "escenario", "entrada", "operar", "signals", "señal",
    "alarma", "alerta", "alert", "avisa", "avisame", "notific",
)


def env_for_model(model):
    prefix = model.split("/")[0].lower()
    return PROVIDER_ENV.get(prefix)


def _is_complex(user_message):
    msg = (user_message or "").lower()
    return any(h in msg for h in COMPLEX_HINTS)


# Modelos legados que ya no existen en litellm -> se reasignan al default actual.
LEGACY_MODEL_MAP = {
    "gemini/gemini-3.6-flash": "gemini/gemini-3.8-flash",
    "gemini/gemini-3.7-flash": "gemini/gemini-3.8-flash",
    "google/gemini-3.6-flash": "gemini/gemini-3.8-flash",
    "google/gemini-3.7-flash": "gemini/gemini-3.8-flash",
}


def _normalize_model(model):
    model = (model or "").strip()
    if not model:
        return None
    return LEGACY_MODEL_MAP.get(model, model)


def _gemini_keys():
    """Devuelve la lista de claves Gemini disponibles (para rotación)."""
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5"):
        v = os.getenv(name)
        if v and v.strip():
            keys.append(v.strip())
    return keys


def _provider_tasks(model_chain):
    """Expande la cadena de modelos en (model, api_key_override). Para gemini rota
    entre las claves disponibles; para ollama (local) no requiere clave; para el
    resto usa la env var por defecto."""
    tasks = []
    for model in model_chain:
        prefix = model.split("/")[0].lower()
        if prefix == "ollama":
            tasks.append((model, None))
            continue
        env = env_for_model(model) or "OPENAI_API_KEY"
        if env == "GEMINI_API_KEY":
            for key in _gemini_keys():
                tasks.append((model, key))
        else:
            if os.getenv(env):
                tasks.append((model, None))
    return tasks


def resolve_model_chain(role):
    """Cadena de modelos definitiva. El rol manda: si declara provider/model
    explícitos se usa solo ese modelo; si provider='auto' se usa el fallback_order
    persistido (validando claves/Ollama); como último recurso, DEFAULT_CHAIN.
    Los modelos legados rotos se reasignan al default vigente."""
    if role and role["provider"] != "auto":
        model = _normalize_model(role["model"])
        if not model:
            return resolve_model_chain(None)
        if "/" not in model:
            model = f"{role['provider']}/{model}".replace("claude/", "anthropic/")
        model = _normalize_model(model)
        return [model]

    settings = store.get_settings()
    raw = settings.get("fallback_order")
    try:
        chain = json.loads(raw) if raw else []
    except Exception:
        chain = []
    chain = [m for m in (_normalize_model(x) for x in chain) if m]
    if not chain:
        chain = DEFAULT_CHAIN
    available = []
    for model in chain:
        if model.split("/")[0].lower() == "ollama":
            available.append(model)
            continue
        env = env_for_model(model) or "OPENAI_API_KEY"
        if os.getenv(env):
            available.append(model)
    return available or chain


async def execute_tool(name, args_json, conversation_id=None):
    try:
        args = json.loads(args_json) if args_json else {}
    except Exception:
        args = {}
    if conversation_id:
        args.setdefault("conversation_id", conversation_id)
    try:
        return await asyncio.wait_for(asyncio.to_thread(_handler, name, args), timeout=4.0)
    except asyncio.TimeoutError:
        return {"status": "offline", "data": None, "error": f"tiempo agotado (tool {name})"}
    except Exception as exc:
        return {"status": "failed", "data": None, "error": str(exc)}


# ============================================================
# Loop del agente (SSE)
# ============================================================

def _sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _is_local_model(model):
    return model.split("/")[0].lower() == "ollama"


def _try_parse_text_tool_call(text, allowed):
    """Modelos locales (p.ej. llama3.2) a veces emiten el tool call como texto
    (`{"name": ..., "arguments": ...}`) en lugar de tool_calls estructurados.
    Detecta ese caso y lo devuelve con el mismo formato que un tool_call."""
    if not text or not allowed:
        return None
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        parsed = json.loads(stripped)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name")
    if not isinstance(name, str) or not name.strip() or name.strip() not in allowed:
        return None
    args = parsed.get("arguments", {})
    if isinstance(args, dict):
        args_json = json.dumps(args, ensure_ascii=False)
    elif isinstance(args, str):
        args_json = args
    else:
        args_json = "{}"
    return {
        "id": f"call_local_{int(datetime.now().timestamp() * 1000)}",
        "function": {"name": name.strip(), "arguments": args_json},
    }


def _get_agent_topics():
    """Keywords de topics del YAML (strategy.agent.topics) o defaults si falla."""
    try:
        import app
        return app.store.get_agent_topics()
    except Exception:
        return {}


async def _fetch_live_data(user_message, allowed):
    """Ruta simple: consulta en vivo los datos típicos de la cuenta y los devuelve
    como contexto inyectable en el prompt. Así el modelo local NO necesita llamar
    tools (su function-calling es poco fiable); solo redacta usando estos datos."""
    topics = _get_agent_topics()
    msg = (user_message or "").lower()
    tokens = [w.strip(".,;:!?()\"'«»") for w in msg.split()]
    lines = []
    now = datetime.now()
    lines.append(f"- Fecha y hora actual del sistema: {now.strftime('%d/%m/%Y %H:%M:%S')}")

    def mentions(*keys):
        return any(any(t.startswith(k) for k in keys) for t in tokens)

    async def grab(key, name, args):
        if name not in allowed:
            return
        res = await execute_tool(name, json.dumps(args, ensure_ascii=False))
        if isinstance(res, dict) and res.get("status") == "ok":
            lines.append(f"- {key}: {json.dumps(res.get('data'), ensure_ascii=False)[:2500]}")
        else:
            lines.append(f"- {key}: NO DISPONIBLE (MT5 no responde)")

    jobs = []
    if mentions(*topics.get("account", [])):
        jobs.append(grab("Saldo, equity, margen y nivel de margen de la cuenta", "account_info", {}))
    if mentions(*topics.get("positions", [])):
        jobs.append(grab("Posiciones abiertas en MT5", "positions_list", {}))
    if mentions(*topics.get("history", [])):
        jobs.append(grab("Historial de operaciones de los últimos 7 días", "history", {"days": 7}))
    if mentions(*topics.get("news", [])):
        jobs.append(grab("Última y próxima noticia económica relevante (Forex Factory)", "economic_news", {}))
    if jobs:
        await asyncio.gather(*jobs)
    policy = _risk_policy_lines(msg, mentions)
    if policy:
        lines.append(policy)
    return "\n".join(lines)


def _risk_policy_lines(msg, mentions):
    """Política de riesgo para la ruta simple (M3): estado diario, killzone en UTC,
    prop firm y reglas de enforcement. La parte de score/régimen solo se calcula si
    el usuario habla de operar/entrar (build_chart_snapshot es más pesado)."""
    try:
        import app
        import risk_engine
    except Exception:
        return ""

    out = []
    risk = {}
    try:
        cfg = app.store.get_trading_config()
    except Exception:
        return ""

    try:
        risk = app.daily_risk_state()
        if risk.get("error"):
            out.append(f"- Política de riesgo: MT5 offline ({risk['error']}).")
        elif risk["blocked"]:
            out.append("- Política de riesgo: OPERAR BLOQUEADO (drawdown diario): " + "; ".join(risk["reasons"]))
        else:
            out.append(
                f"- Política de riesgo diaria: DD ${risk.get('dd_daily', 0):,.2f} "
                f"({risk.get('dd_pct', 0):.2f}%) · {risk.get('trades_today', 0)}/"
                f"{risk.get('max_trades_day', 0)} operaciones · tope "
                f"${risk.get('max_loss_fixed', 0):,.0f} / {risk.get('max_loss_pct', 0)}%."
            )
    except Exception:
        pass

    try:
        kz = risk_engine.killzone_score(json.loads(cfg.get("killzones") or "[]"))
        where = "DENTRO de " + kz["name"] if kz["in_killzone"] else "FUERA"
        out.append(f"- Killzone (UTC): {where} (peso 20% del score).")
    except Exception:
        pass

    if cfg.get("prop_enabled") and risk.get("prop_enabled"):
        out.append(
            f"- Modo prop firm activo (ENFORCED): DD diario {risk.get('prop_dd_daily_pct')}%/"
            f"{cfg.get('prop_max_dd_daily_pct')}% usada · DD total {risk.get('prop_dd_total_pct')}%/"
            f"{cfg.get('prop_max_dd_total_pct')}% · ganancia día {risk.get('prop_day_profit_pct')}%/"
            f"{cfg.get('prop_max_profit_day_pct')}% · consistencia {cfg.get('prop_consistency_days')}d."
        )
    elif cfg.get("prop_enabled"):
        out.append(
            f"- Modo prop firm activo (ENFORCED): límites {cfg.get('prop_max_dd_daily_pct')}% DD diario / "
            f"{cfg.get('prop_max_dd_total_pct')}% DD total / tope ganancia "
            f"{cfg.get('prop_max_profit_day_pct')}% (métricas en vivo no disponibles)."
        )
    else:
        out.append("- Modo prop firm desactivado (configurable).")

    news_on = (cfg.get("data_sources") or {}).get("news", True)
    out.append(
        f"- Enforcement: el drawdown diario y el modo prop BLOQUEAN duro. Las noticias "
        f"{'BLOQUEAN duro' if news_on else 'NO bloquean'} ±{cfg.get('news_buffer_min', 15)} min "
        "(impacto alto; fail-open si el calendario no responde). "
        "La killzone solo AVISA y baja el score (nunca congela)."
    )

    topics = _get_agent_topics()
    t = (topics or {}).get("trade") or []
    if mentions(*t):
        try:
            symbol = "EURUSD"
            snap = app.build_chart_snapshot(symbol, "M15")
            re_ = snap.get("risk_engine")
            if re_:
                frm = lambda s: f"{s['score']} ({s['verdict'].replace('_', ' ')})"
                out.append(
                    f"- Setup Score (risk engine, {symbol} M15): BUY {frm(re_['bull'])} · "
                    f"SELL {frm(re_['bear'])} · régimen {re_['regime']['regime']} · "
                    f"killzone {re_['killzone']['in_killzone'] and 'dentro' or 'fuera'} · "
                    f"invalidez BUY {re_['invalidation']['BUY']} / SELL {re_['invalidation']['SELL']}."
                )
        except Exception:
            pass

    return "\n".join(out) if out else ""


def _is_rate_limit(exc):
    status = getattr(exc, "status_code", None)
    msg = str(exc).lower()
    return status in (429, 503) or any(
        k in msg
        for k in (
            "rate limit",
            "ratelimit",
            "429",
            "503",
            "quota",
            "high demand",
            "serviceunavailable",
            "unavailable",
            "overloaded",
            "try again later",
        )
    )


async def stream_agent(conversation_id, role_id, user_message, skip_tools=False, chart_image=None):
    role = store.get_role(role_id) or store.get_role("general")
    settings = store.get_settings()
    history_limit = int(settings.get("history_limit", "20"))
    max_rounds = int(settings.get("max_tool_rounds", "6"))

    # Modo de la petición (el rol manda en el router; aquí se decide CÓMO responder):
    #   tools           -> mensaje complejo y no forzado: herramientas del rol habilitadas.
    #   simple auto     -> mensaje no complejo: sin tools, datos en vivo inyectados.
    #   simple forzado  -> skip_tools (botón "Analizar Gráfico con IA"): sin tools y SIN
    #                      auto-inyección de live data (el snapshot ya viaja en el mensaje).
    force_simple = skip_tools
    wants_tools = (not skip_tools) and _is_complex(user_message)
    role_allowed = set(role["allowed_tools"])

    allowed = role_allowed if wants_tools else set()
    tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in allowed] if allowed else []

    store.add_message(conversation_id, "user", user_message)
    history = store.get_messages(conversation_id, limit=history_limit)

    # Detección automática de exportación del AI Chart Assistant pegada en el chat
    anexo = None
    try:
        import mt5_export as me
        fname = me.extract_export_path(user_message)
        if fname:
            yield _sse({"type": "tool", "content": f"Leyendo archivo anexo {fname}…"})
            anexo = me.read_export(fname)
    except ImportError:
        pass
    except Exception as exc:
        yield _sse({"type": "error", "content": f"Error al leer el archivo anexo: {exc}"})
        yield _sse({"type": "done"})
        return

    messages = [{"role": "system", "content": role["system_prompt"]}]
    messages.extend(history)
    user_content = user_message + "\n\nResponde siempre en español."
    if anexo:
        user_content += (
            f"\n\nArchivo Anexo del AI Chart Assistant ({anexo['filename']}):\n"
            f"{anexo['content']}"
        )
    # Multimodal: si llega una captura del gráfico (PNG base64), se envía junto
    # al texto en formato OpenAI (image_url). litellm traduce a inline_data en
    # Gemini si hace falta.
    if chart_image:
        img_url = chart_image if str(chart_image).startswith("data:") else f"data:image/png;base64,{chart_image}"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_content},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        })
    else:
        messages.append({"role": "user", "content": user_content})

    yield _sse({"type": "role", "content": role["name"]})
    yield _sse({"type": "status", "content": f"Iniciando agente «{role['name']}»…"})

    model_chain = resolve_model_chain(role)
    if not model_chain:
        yield _sse({"type": "error", "content": "No hay claves de API configuradas (OPENAI_API_KEY, GEMINI_API_KEY o ANTHROPIC_API_KEY) en el archivo .env."})
        yield _sse({"type": "done"})
        return

    # Degradación controlada: primario local con function-calling poco fiable ->
    # se baja a modo simple con datos en vivo inyectados (sin tools).
    if wants_tools and _is_local_model(model_chain[0]):
        yield _sse({"type": "status", "content": "Modelo local: degradando a modo simple (sin tools) con datos en vivo…"})
        wants_tools = False
        allowed = set()
        tools = []

    # Modo simple (auto o degradado): el modelo redacta sin tools con datos ya inyectados.
    if not force_simple and not wants_tools:
        yield _sse({"type": "status", "content": "Consultando datos en vivo de la cuenta…"})
        live_data = await _fetch_live_data(user_message, role_allowed)
        if live_data:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Datos consultados en vivo (usa SOLO estos valores, NUNCA inventes cifras):\n"
                        + live_data
                    ),
                }
            )

    for round_no in range(1, max_rounds + 1):
        assistant = {"role": "assistant", "content": "", "tool_calls": {}}
        is_local = None
        buffered_chunks = None
        last_error = None
        round_stream_ok = False
        for model, api_key in _provider_tasks(model_chain):
            attempts = 0
            while True:
                attempts += 1
                stream = None
                try:
                    yield _sse({"type": "model", "content": model})
                    kwargs = {}
                    if api_key:
                        kwargs["api_key"] = api_key
                    stream = await acompletion(
                        model=model,
                        messages=messages,
                        tools=tools or None,
                        stream=True,
                        timeout=180 if _is_local_model(model) else 45,
                        max_retries=0,
                        **kwargs,
                    )
                except Exception as exc:
                    last_error = exc
                    # 429/503 de alta demanda (transitorios): backoff corto con la MISMA
                    # clave/modelo antes de probar la siguiente clave/proveedor.
                    if _is_rate_limit(exc) and attempts < 3:
                        wait = 0.5 * (2 ** (attempts - 1))
                        yield _sse({"type": "status", "content": f"Límite de peticiones en {model}: reintento en {wait:.1f}s…"})
                        await asyncio.sleep(wait)
                        continue
                    yield _sse({"type": "status", "content": f"Fallo {model}: {exc}. Probando siguiente clave/proveedor…"})
                    break
                # Consumir el stream; si se interrumpe a medias, se descarta y se prueba
                # la siguiente clave/modelo en lugar de repetir la misma ronda.
                try:
                    is_local = _is_local_model(model)
                    buffered_chunks = [] if is_local else None
                    async for chunk in stream:
                        if not getattr(chunk, "choices", None):
                            continue
                        ch = chunk.choices[0]
                        delta = getattr(ch, "delta", None)
                        if delta is None and getattr(ch, "message", None) is not None:
                            delta = ch.message
                        if delta is None:
                            continue
                        if getattr(delta, "content", None):
                            assistant["content"] += delta.content
                            if is_local:
                                buffered_chunks.append(delta.content)
                            else:
                                yield _sse({"type": "delta", "content": delta.content})
                        if getattr(delta, "tool_calls", None):
                            for tc in delta.tool_calls:
                                idx = tc.index if tc.index is not None else 0
                                slot = assistant["tool_calls"].setdefault(idx, {"id": None, "name": "", "arguments": ""})
                                if tc.id:
                                    slot["id"] = tc.id
                                if tc.function:
                                    if tc.function.name:
                                        slot["name"] += tc.function.name
                                    if tc.function.arguments:
                                        slot["arguments"] += tc.function.arguments
                    round_stream_ok = True
                    break
                except Exception as exc:
                    last_error = exc
                    yield _sse({"type": "status", "content": f"Conexión interrumpida con {model}: {exc}. Probando siguiente clave/proveedor…"})
                    break
            if round_stream_ok:
                break

        if not round_stream_ok:
            detail = str(last_error) if last_error else "sin proveedores con clave configurada"
            yield _sse({"type": "error", "content": f"Todos los proveedores fallaron ({detail})."})
            yield _sse({"type": "done"})
            return

        tool_calls = [
            {
                "id": slot["id"] or f"call_{idx}",
                "function": {"name": slot["name"].strip(), "arguments": slot["arguments"]},
            }
            for idx, slot in sorted(assistant["tool_calls"].items())
            if slot["name"].strip()
        ]

        if not tool_calls and buffered_chunks:
            tool_call = _try_parse_text_tool_call(assistant["content"], allowed)
            if tool_call:
                tool_calls = [tool_call]
                assistant["content"] = ""

        if not tool_calls:
            if buffered_chunks:
                for piece in buffered_chunks:
                    yield _sse({"type": "delta", "content": piece})
            text = assistant["content"].strip()
            if text:
                store.add_message(conversation_id, "assistant", text)
            else:
                store.add_message(conversation_id, "assistant", "Sin respuesta textual del modelo.")
            yield _sse({"type": "done"})
            return

        assistant["role"] = "assistant"
        assistant["content"] = assistant["content"] or None
        assistant["tool_calls"] = tool_calls
        messages.append(assistant)

        for tc in tool_calls:
            name = tc["function"]["name"]
            yield _sse({"type": "tool", "content": f"Consultando {name}…"})
            if name not in allowed:
                result = {"status": "failed", "data": None, "error": "tool no permitido para este rol"}
            else:
                result = await execute_tool(name, tc["function"]["arguments"], conversation_id=conversation_id)
            if name == "set_chart_alert" and isinstance(result, dict) and result.get("status") == "ok":
                yield _sse({"type": "chart_alert", "content": result["data"]})
            if name == "chart_annotate" and isinstance(result, dict) and result.get("status") == "ok":
                yield _sse({"type": "chart_actions", "content": result["data"]})
            store.add_message(
                conversation_id,
                "tool",
                json.dumps(result, ensure_ascii=False),
                tool_call_id=tc["id"],
                name=name,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    store.add_message(conversation_id, "assistant", "El agente alcanzó el máximo de rondas de herramientas.")
    yield _sse({"type": "error", "content": "Demasiadas rondas de herramientas. Respuesta interrumpida."})
    yield _sse({"type": "done"})