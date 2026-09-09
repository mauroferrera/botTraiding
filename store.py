import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

from strategy import (
    get_config,
    get_trading_config,
    get_data_sources as _strategy_data_sources,
    get_agent_topics as _strategy_agent_topics,
    get_watcher_config as _strategy_watcher_config,
    save as strategy_save,
)

DB_PATH = "trading.db"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


_SEED_CFG = get_config()


def _seed_system_prompt() -> str:
    """Prompt del rol 'general': system_prompt + risk_policy del YAML."""
    prompt = _SEED_CFG.get("agent_system_prompt") or ""
    risk = _SEED_CFG.get("agent_risk_policy") or ""
    data_sources = _SEED_CFG.get("agent_data_sources_policy") or ""
    parts = [p for p in (prompt, data_sources, risk) if p]
    return "\n\n".join(parts)


SEED_ROLES = [
    {
        "id": "general",
        "name": "Asistente Trading",
        "system_prompt": _seed_system_prompt(),
        "allowed_tools": _SEED_CFG.get("agent_allowed_tools") or [],
        "provider": "auto",
        "model": "",
    },
]

DEFAULT_SETTINGS = {
    "active_role_id": "general",
    "fallback_order": json.dumps(["gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash"]),
    "history_limit": "20",
    "max_tool_rounds": "6",
}

# La config de trading vive en strategy.yaml (fuente de verdad). get_config()
# devuelve el shape histórico (risk_weights/killzones como JSON string).
DEFAULT_TRADING_CONFIG = get_config()


def init_db():
    with closing(get_db()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                allowed_tools TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'auto',
                model TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                role_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                volume REAL,
                price_open REAL,
                price_close REAL,
                profit REAL,
                time_close TEXT,
                synced_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                ticket TEXT,
                symbol TEXT NOT NULL DEFAULT 'EURUSD',
                action TEXT,
                poi_type TEXT,
                liquidity_swept TEXT,
                cme_confirmation TEXT,
                setup_json TEXT NOT NULL DEFAULT '{}',
                emotion TEXT,
                plan_compliance INTEGER,
                tags TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                timestamp TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                label TEXT,
                side TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                triggered_at TEXT
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cot_reports (
                report_date TEXT PRIMARY KEY,
                am_net INTEGER,
                lf_net INTEGER,
                nc_net INTEGER,
                cot_index_26w REAL,
                macro_bias TEXT,
                delta_am REAL,
                delta_lf REAL,
                created_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS setup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'M15',
                direction TEXT NOT NULL,
                verdict TEXT NOT NULL,
                score REAL NOT NULL,
                breakdown_json TEXT NOT NULL DEFAULT '{}',
                entry REAL,
                sl REAL,
                target REAL,
                invalidate_level REAL,
                validated INTEGER,
                reject_reasons TEXT NOT NULL DEFAULT '[]',
                risk_state_json TEXT NOT NULL DEFAULT '{}',
                trade_result_json TEXT NOT NULL DEFAULT '{}',
                timestamp TEXT NOT NULL
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_setup_log_time ON setup_log(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_setup_log_verdict ON setup_log(verdict);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(time_close);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_time ON journal(timestamp);")

        # Estado del watcher (bot a la escucha): dedup por symbol/timeframe.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS setup_state (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'M15',
                direction TEXT,
                score REAL,
                verdict TEXT,
                entry REAL,
                sl REAL,
                target REAL,
                invalidate_level REAL,
                status TEXT NOT NULL DEFAULT 'active',
                notified INTEGER NOT NULL DEFAULT 0,
                auto_executed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            );
            """
        )
        # Overrides del watcher persistidos (p.ej. auto_execute conmutado en la UI).
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS watcher_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # Estado del gate de prop-firm (baseline, picos de equity diario/total).
        # Se persiste como filas JSON clave->valor para no tocar el esquema por
        # cada métrica nueva (mismo patrón que watcher_settings).
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS prop_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # Dibujos manuales del gráfico (herramientas manuales del usuario y del agente),
        # persistidos por symbol/timeframe. Cada item lleva origin: "user"|"agent".
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_drawings (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'M15',
                drawings_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            );
            """
        )

        # Migración: añadir columna 'active' si la tabla roles ya existía sin ella
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(roles)").fetchall()]
        if "active" not in cols:
            cursor.execute("ALTER TABLE roles ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

        # Migración: columnas de herramientas en messages (multi-turno con tools)
        mcols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "tool_call_id" not in mcols:
            cursor.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")
        if "name" not in mcols:
            cursor.execute("ALTER TABLE messages ADD COLUMN name TEXT")

        # Migración: alertas multicondición en chart_alerts
        acols = [r["name"] for r in conn.execute("PRAGMA table_info(chart_alerts)").fetchall()]
        if "conditions" not in acols:
            cursor.execute("ALTER TABLE chart_alerts ADD COLUMN conditions TEXT NOT NULL DEFAULT '[]'")
        if "timeframe" not in acols:
            cursor.execute("ALTER TABLE chart_alerts ADD COLUMN timeframe TEXT")
        if "expires_at" not in acols:
            cursor.execute("ALTER TABLE chart_alerts ADD COLUMN expires_at TEXT")
        if "last_check" not in acols:
            cursor.execute("ALTER TABLE chart_alerts ADD COLUMN last_check TEXT")

        # Migración: precios y tiempos en journal (proyección gráfica de operaciones)
        jcols = [r["name"] for r in conn.execute("PRAGMA table_info(journal)").fetchall()]
        if "entry_price" not in jcols:
            cursor.execute("ALTER TABLE journal ADD COLUMN entry_price REAL")
        if "sl_price" not in jcols:
            cursor.execute("ALTER TABLE journal ADD COLUMN sl_price REAL")
        if "tp_price" not in jcols:
            cursor.execute("ALTER TABLE journal ADD COLUMN tp_price REAL")
        if "time_open" not in jcols:
            cursor.execute("ALTER TABLE journal ADD COLUMN time_open TEXT")
        if "time_close" not in jcols:
            cursor.execute("ALTER TABLE journal ADD COLUMN time_close TEXT")

        cursor.execute("SELECT COUNT(*) AS n FROM roles")
        if cursor.fetchone()["n"] == 0:
            for r in SEED_ROLES:
                cursor.execute(
                    "INSERT OR REPLACE INTO roles (id, name, system_prompt, allowed_tools, provider, model, active, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                    (r["id"], r["name"], r["system_prompt"], json.dumps(r["allowed_tools"]), r["provider"], r["model"], now_iso()),
                )
        else:
            # Roles legados se conservan pero inactivos; 'general' pasa a ser el único activo
            general = SEED_ROLES[0]
            cursor.execute(
                "UPDATE roles SET name=?, system_prompt=?, allowed_tools=?, provider=?, model=?, active=1, updated_at=? WHERE id=?",
                (general["name"], general["system_prompt"], json.dumps(general["allowed_tools"]), general["provider"], general["model"], now_iso(), "general"),
            )
            cursor.execute("UPDATE roles SET active=0 WHERE id != ?", ("general",))
        for k, v in DEFAULT_SETTINGS.items():
            cursor.execute("INSERT OR IGNORE INTO agent_settings (key, value) VALUES (?, ?)", (k, v))
        for k, v in DEFAULT_SETTINGS.items():
            if k in ("fallback_order", "max_tool_rounds"):
                cursor.execute(
                    "INSERT INTO agent_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, v),
                )
        conn.commit()


# ============================================================
# Settings
# ============================================================

def get_settings():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT key, value FROM agent_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_setting(key, value):
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO agent_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


# ============================================================
# Configuración de trading (espejo de los EAs MQL5)
# ============================================================

def get_trading_config():
    return get_config()


def set_trading_config(cfg):
    strategy_save(cfg or {})


def get_data_sources():
    return _strategy_data_sources()


def get_agent_topics():
    return _strategy_agent_topics()


def get_config_summary():
    """Resumen de reglas activas (visible en la UI) a partir del YAML."""
    cfg = get_config()
    risk_weights = cfg.get("risk_weights") or "{}"
    killzones = cfg.get("killzones") or "[]"
    try:
        weights = json.loads(risk_weights) if isinstance(risk_weights, str) else risk_weights
    except (json.JSONDecodeError, TypeError):
        weights = {}
    try:
        kz = json.loads(killzones) if isinstance(killzones, str) else killzones
    except (json.JSONDecodeError, TypeError):
        kz = []
    return {
        "risk_weights": weights,
        "killzones": [{"name": w.get("name"), "start": w.get("start"), "end": w.get("end")}
                      for w in kz if isinstance(w, dict)],
        "data_sources": cfg.get("data_sources") or {},
        "min_score": cfg.get("min_score"),
        "min_rr": cfg.get("min_rr"),
        "setup_ttl_minutes": cfg.get("setup_ttl_minutes"),
        "max_trades_day": cfg.get("max_trades_day"),
        "risk_pct": cfg.get("risk_pct"),
        "loss_limit_fixed": cfg.get("loss_limit_fixed"),
        "loss_limit_pct": cfg.get("loss_limit_pct"),
        "prop_enabled": bool(cfg.get("prop_enabled")),
        "prop_max_dd_daily_pct": cfg.get("prop_max_dd_daily_pct"),
        "prop_max_dd_total_pct": cfg.get("prop_max_dd_total_pct"),
        "prop_max_profit_day_pct": cfg.get("prop_max_profit_day_pct"),
        "prop_consistency_days": cfg.get("prop_consistency_days"),
        "news_buffer_min": cfg.get("news_buffer_min"),
        "agent_risk_policy": cfg.get("agent_risk_policy") or "",
    }


# ============================================================
# Setup log (post-mortem del risk engine, M3) — append-only
# ============================================================

def log_setup(entry: dict):
    """Registra de forma inmutable cada disparo del motor de riesgo.

    entry: symbol, timeframe, direction, verdict, score, breakdown(comps),
           entry/sl/target, invalidate_level, validated, reject_reasons,
           risk_state, trade_result.
    """
    with closing(get_db()) as conn:
        conn.execute(
            """
            INSERT INTO setup_log (
                symbol, timeframe, direction, verdict, score, breakdown_json,
                entry, sl, target, invalidate_level, validated, reject_reasons,
                risk_state_json, trade_result_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(entry.get("symbol") or "EURUSD").upper(),
                str(entry.get("timeframe") or "M15").upper(),
                str(entry.get("direction") or "BUY").upper(),
                str(entry.get("verdict") or ""),
                float(entry.get("score") or 0.0),
                json.dumps(entry.get("breakdown") or {}, ensure_ascii=False),
                entry.get("entry"),
                entry.get("sl"),
                entry.get("target"),
                entry.get("invalidate_level"),
                1 if entry.get("validated") else 0,
                json.dumps(entry.get("reject_reasons") or [], ensure_ascii=False),
                json.dumps(entry.get("risk_state") or {}, ensure_ascii=False),
                json.dumps(entry.get("trade_result") or {}, ensure_ascii=False),
                now_iso(),
            ),
        )
        conn.commit()


def list_setup_log(limit: int = 100, verdict: str = "", symbol: str = ""):
    """Consulta del post-mortem para /api/risk/audit."""
    q = "SELECT * FROM setup_log WHERE 1=1"
    args: list = []
    if verdict:
        q += " AND verdict = ?"
        args.append(verdict)
    if symbol:
        q += " AND symbol = ?"
        args.append(str(symbol).upper())
    q += " ORDER BY timestamp DESC LIMIT ?"
    args.append(int(limit))
    with closing(get_db()) as conn:
        rows = conn.execute(q, args).fetchall()
        return [
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "direction": r["direction"],
                "verdict": r["verdict"],
                "score": r["score"],
                "breakdown": json.loads(r["breakdown_json"] or "{}"),
                "entry": r["entry"],
                "sl": r["sl"],
                "target": r["target"],
                "invalidate_level": r["invalidate_level"],
                "validated": bool(r["validated"]),
                "reject_reasons": json.loads(r["reject_reasons"] or "[]"),
                "risk_state": json.loads(r["risk_state_json"] or "{}"),
                "trade_result": json.loads(r["trade_result_json"] or "{}"),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]


def link_last_setup(ticket, symbol="EURUSD", price_open=None, sl=None, tp=None):
    """Vincula el ticket de la orden ejecutada al último setup_log aprobado del símbolo
    (trade_result_json vacío), para poder medir win-rate por componente después."""
    sym = str(symbol).upper()
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT id FROM setup_log WHERE symbol = ? AND validated = 1 "
            "AND trade_result_json = '{}' ORDER BY timestamp DESC LIMIT 1",
            (sym,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE setup_log SET trade_result_json = ? WHERE id = ?",
            (
                json.dumps(
                    {"ticket": ticket, "price_open": price_open, "sl": sl, "tp": tp},
                    ensure_ascii=False,
                ),
                row["id"],
            ),
        )
        conn.commit()
        return True


# ============================================================
# Watcher (bot a la escucha) — config persistente + estado por símbolo
# ============================================================

def _watcher_row(r):
    return {
        "symbol": r["symbol"],
        "timeframe": r["timeframe"],
        "direction": r["direction"],
        "score": r["score"],
        "verdict": r["verdict"],
        "entry": r["entry"],
        "sl": r["sl"],
        "target": r["target"],
        "invalidate_level": r["invalidate_level"],
        "status": r["status"],
        "notified": bool(r["notified"]),
        "auto_executed": bool(r["auto_executed"]),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def get_watcher_config():
    """Config del watcher desde strategy.yaml (DEFAULT_TRADING_CONFIG aplanado)."""
    return _strategy_watcher_config() or {}


def get_watcher_auto_execute():
    """auto_execute efectivo: el override persistido (UI) si existe; si no, el YAML."""
    val = None
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT value FROM watcher_settings WHERE key = 'auto_execute'"
        ).fetchone()
        val = row["value"] if row else None
    if val is not None:
        return str(val).lower() in ("1", "true", "yes")
    return bool((get_watcher_config() or {}).get("auto_execute", False))


def set_watcher_auto_execute(enabled):
    """Persiste el toggle auto_execute (overrides el valor del YAML)."""
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO watcher_settings (key, value) VALUES ('auto_execute', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("1" if enabled else "0",),
        )
        conn.commit()


PROP_STATE_KEYS = ("baseline_equity", "baseline_day", "day_peak", "day_peak_day", "total_peak")


def get_prop_state():
    """Estado del gate prop-firm. Devuelve dict con los campos vigentes o None
    para los no persistidos aún (baseline sin crear, pico sin resetear)."""
    out = {k: None for k in PROP_STATE_KEYS}
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT key, value FROM prop_state WHERE key IN (%s)"
            % ",".join("?" * len(PROP_STATE_KEYS)),
            PROP_STATE_KEYS,
        ).fetchall()
    for r in rows:
        try:
            out[r["key"]] = float(r["value"])
        except (TypeError, ValueError):
            out[r["key"]] = r["value"]
    return out


def set_prop_state(**fields):
    """Persiste los campos prop_state dados (solo claves conocidas)."""
    payload = {k: v for k, v in fields.items() if k in PROP_STATE_KEYS}
    if not payload:
        return
    with closing(get_db()) as conn:
        for key, value in payload.items():
            conn.execute(
                "INSERT INTO prop_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
        conn.commit()


def get_setup_state(symbol, timeframe="M15"):
    """Estado vigente del watcher para un símbolo/timeframe (o None)."""
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT * FROM setup_state WHERE symbol = ? AND timeframe = ?",
            (str(symbol).upper(), str(timeframe).upper()),
        ).fetchone()
        return _watcher_row(row) if row else None


def list_setup_states():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM setup_state ORDER BY symbol, timeframe").fetchall()
        return [_watcher_row(r) for r in rows]


def new_setup_state(symbol, timeframe, gate=None, status="active", notified=True):
    """Crea (o reemplaza) el estado activo de un setup detectado. created_at se
    reinicia: es un nuevo ciclo de alerta."""
    g = gate or {}
    ts = now_iso()
    with closing(get_db()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO setup_state (
                symbol, timeframe, direction, score, verdict, entry, sl, target,
                invalidate_level, status, notified, auto_executed, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                str(symbol).upper(), str(timeframe).upper(),
                g.get("direction"), g.get("score"), g.get("verdict"),
                g.get("entry"), g.get("sl"), g.get("tp"),
                g.get("invalidate_level"), status,
                1 if notified else 0, ts, ts,
            ),
        )
        conn.commit()


def update_setup_state(symbol, timeframe, **fields):
    """Actualiza campos permitidos del estado (status/notified/auto_executed)."""
    allowed = ("status", "notified", "auto_executed")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    ts = now_iso()
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT 1 FROM setup_state WHERE symbol = ? AND timeframe = ?",
            (str(symbol).upper(), str(timeframe).upper()),
        ).fetchone()
        if row is None:
            # Estado mínimo para poder registrar la transición sin un gate nuevo.
            conn.execute(
                """
                INSERT INTO setup_state (
                    symbol, timeframe, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(symbol).upper(), str(timeframe).upper(),
                 sets.get("status", "active"), now_iso(), ts),
            )
        cols = ", ".join(f"{k} = ?" for k in sets)
        conn.execute(
            f"UPDATE setup_state SET {cols}, updated_at = ? "
            "WHERE symbol = ? AND timeframe = ?",
            (*sets.values(), ts, str(symbol).upper(), str(timeframe).upper()),
        )
        conn.commit()


# ============================================================
# Chart drawings (herramientas manuales del gráfico)
# ============================================================

def get_drawings(symbol, timeframe="M15"):
    """Lista de dibujos persistidos para un symbol/timeframe (default [])."""
    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT drawings_json FROM chart_drawings WHERE symbol = ? AND timeframe = ?",
            (str(symbol).upper(), str(timeframe).upper()),
        ).fetchone()
    if row is None:
        return []
    try:
        val = json.loads(row["drawings_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return val if isinstance(val, list) else []


def save_drawings(symbol, timeframe="M15", drawings=None):
    """Reemplaza (INSERT OR REPLACE) el set completo de dibujos del symbol/timeframe."""
    items = drawings if isinstance(drawings, list) else []
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chart_drawings (symbol, timeframe, drawings_json, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (str(symbol).upper(), str(timeframe).upper(),
             json.dumps(items, ensure_ascii=False), now_iso()),
        )
        conn.commit()
    return items


def delete_drawings(symbol, timeframe="M15"):
    """Borra todos los dibujos del symbol/timeframe."""
    with closing(get_db()) as conn:
        conn.execute(
            "DELETE FROM chart_drawings WHERE symbol = ? AND timeframe = ?",
            (str(symbol).upper(), str(timeframe).upper()),
        )
        conn.commit()


# ============================================================
# Roles
# ============================================================

def _role_row(r):
    return {
        "id": r["id"],
        "name": r["name"],
        "system_prompt": r["system_prompt"],
        "allowed_tools": json.loads(r["allowed_tools"]),
        "provider": r["provider"],
        "model": r["model"],
    }


def list_roles(active_only=True):
    with closing(get_db()) as conn:
        if active_only:
            return [_role_row(r) for r in conn.execute("SELECT * FROM roles WHERE active=1 ORDER BY name").fetchall()]
        return [_role_row(r) for r in conn.execute("SELECT * FROM roles ORDER BY name").fetchall()]


def get_role(role_id):
    with closing(get_db()) as conn:
        r = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        return _role_row(r) if r else None


def upsert_role(role_id, name, system_prompt, allowed_tools, provider="auto", model=""):
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO roles (id, name, system_prompt, allowed_tools, provider, model, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, system_prompt=excluded.system_prompt, "
            "allowed_tools=excluded.allowed_tools, provider=excluded.provider, model=excluded.model, "
            "updated_at=excluded.updated_at",
            (role_id, name, system_prompt, json.dumps(allowed_tools), provider, model, now_iso()),
        )
        conn.commit()
    return get_role(role_id)


def delete_role(role_id):
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
        conn.commit()


# ============================================================
# Conversations / Messages
# ============================================================

def create_conversation(title="Nueva conversación", role_id="general"):
    cid = uuid.uuid4().hex
    ts = now_iso()
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, role_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (cid, title, role_id, ts, ts),
        )
        conn.commit()
    return {"id": cid, "title": title, "role_id": role_id, "created_at": ts, "updated_at": ts}


def list_conversations():
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS nmsg "
            "FROM conversations c ORDER BY c.updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_conversation(cid):
    with closing(get_db()) as conn:
        r = conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        return dict(r) if r else None


def touch_conversation(cid):
    with closing(get_db()) as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), cid))
        conn.commit()


def delete_conversation(cid):
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        conn.commit()


def add_message(conversation_id, role, content, tool_call_id=None, name=None):
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_call_id, name, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, tool_call_id, name, now_iso()),
        )
        conn.commit()
    touch_conversation(conversation_id)


def get_messages(conversation_id, limit=20):
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT role, content, tool_call_id, name FROM messages "
            "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        out = []
        for r in reversed(rows):
            # Las filas role='tool' se persisten solo como traza (debug); sin el
            # assistant tool_calls pareado serían huérfanas y romperían la API.
            if r["role"] == "tool":
                continue
            out.append({"role": r["role"], "content": r["content"]})
        return out


# ============================================================
# Chart Alerts (niveles visuales colocados por el agente)
# ============================================================

def _alert_row(r):
    return {
        "id": r["id"],
        "symbol": r["symbol"],
        "price": r["price"],
        "label": r["label"],
        "side": r["side"],
        "status": r["status"],
        "created_at": r["created_at"],
        "triggered_at": r["triggered_at"],
        "conditions": json.loads(r["conditions"] or "[]"),
        "timeframe": r["timeframe"],
        "expires_at": r["expires_at"],
        "last_check": r["last_check"],
    }


def add_chart_alert(symbol, price, label=None, side=None, conditions=None, timeframe=None, expires_at=None):
    with closing(get_db()) as conn:
        cur = conn.execute(
            "INSERT INTO chart_alerts (symbol, price, label, side, status, conditions, timeframe, "
            "expires_at, created_at, triggered_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, NULL)",
            (
                symbol.upper(),
                float(price),
                label,
                side,
                json.dumps(conditions or []),
                timeframe,
                expires_at,
                now_iso(),
            ),
        )
        conn.commit()
        aid = cur.lastrowid
    return get_chart_alert(aid)


def get_chart_alert(aid):
    with closing(get_db()) as conn:
        r = conn.execute("SELECT * FROM chart_alerts WHERE id = ?", (aid,)).fetchone()
        return _alert_row(r) if r else None


def list_chart_alerts(active_only=False, limit=100):
    q = "SELECT * FROM chart_alerts WHERE 1=1"
    if active_only:
        q += " AND status = 'active'"
    q += " ORDER BY id DESC LIMIT ?"
    with closing(get_db()) as conn:
        return [_alert_row(r) for r in conn.execute(q, (limit,)).fetchall()]


def touch_chart_alert(aid):
    with closing(get_db()) as conn:
        conn.execute("UPDATE chart_alerts SET last_check = ? WHERE id = ?", (now_iso(), aid))
        conn.commit()


def set_chart_alert_status(aid, status):
    ts = now_iso() if status == "triggered" else None
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE chart_alerts SET status = ?, triggered_at = COALESCE(?, triggered_at) WHERE id = ?",
            (status, ts, aid),
        )
        conn.commit()
    return get_chart_alert(aid)


# ============================================================
# COT (Commitments of Traders, CFTC)
# ============================================================

def upsert_cot_report(report_date, am_net, lf_net, nc_net,
                      cot_index=None, macro_bias=None, delta_am=None, delta_lf=None):
    with closing(get_db()) as conn:
        conn.execute(
            "INSERT INTO cot_reports (report_date, am_net, lf_net, nc_net, cot_index_26w, "
            "macro_bias, delta_am, delta_lf, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(report_date) DO UPDATE SET "
            "am_net=excluded.am_net, lf_net=excluded.lf_net, nc_net=excluded.nc_net, "
            "cot_index_26w=COALESCE(excluded.cot_index_26w, cot_reports.cot_index_26w), "
            "macro_bias=COALESCE(excluded.macro_bias, cot_reports.macro_bias)",
            (report_date, am_net, lf_net, nc_net, cot_index, macro_bias, delta_am, delta_lf, now_iso()),
        )
        conn.commit()


def _cot_row(r):
    return {
        "report_date": r["report_date"],
        "am_net": r["am_net"],
        "lf_net": r["lf_net"],
        "nc_net": r["nc_net"],
        "cot_index_26w": r["cot_index_26w"],
        "macro_bias": r["macro_bias"],
        "delta_am": r["delta_am"],
        "delta_lf": r["delta_lf"],
    }


def list_cot_reports(limit=60):
    with closing(get_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM cot_reports ORDER BY report_date DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_cot_row(r) for r in rows]


def latest_cot_report():
    with closing(get_db()) as conn:
        r = conn.execute(
            "SELECT * FROM cot_reports ORDER BY report_date DESC LIMIT 1"
        ).fetchone()
    return _cot_row(r) if r else None


# ============================================================
# Trades (snapshot del historial MT5)
# ============================================================

def clear_trades():
    """Vacía la tabla espejo de operaciones (se re-llena en cada sync)."""
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM trades")
        conn.commit()


def upsert_trades(trades):
    with closing(get_db()) as conn:
        for t in trades:
            conn.execute(
                "INSERT INTO trades (ticket, symbol, action, volume, price_open, price_close, profit, time_close, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ticket) DO UPDATE SET profit=excluded.profit, price_close=excluded.price_close, synced_at=excluded.synced_at",
                (t.get("ticket"), t.get("symbol", "EURUSD"), t.get("action", ""), t.get("volume"),
                 t.get("price_open"), t.get("price_close"), t.get("profit"), t.get("time_close"), now_iso()),
            )
        conn.commit()


def list_trades(symbol=None, action=None, days=None, limit=200):
    q = "SELECT * FROM trades WHERE 1=1"
    params = []
    if symbol:
        q += " AND symbol = ?"
        params.append(symbol.upper())
    if action:
        q += " AND action = ?"
        params.append(action.upper())
    if days:
        q += " AND time_close >= ?"
        params.append((datetime.now().replace(microsecond=0) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"))
    q += " ORDER BY time_close DESC LIMIT ?"
    params.append(limit)
    with closing(get_db()) as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ============================================================
# Journal / Bitácora (SMC)
# ============================================================

def _journal_row(r):
    return {
        "id": r["id"],
        "conversation_id": r["conversation_id"],
        "ticket": r["ticket"],
        "symbol": r["symbol"],
        "action": r["action"],
        "poi_type": r["poi_type"],
        "liquidity_swept": r["liquidity_swept"],
        "cme_confirmation": r["cme_confirmation"],
        "setup_json": json.loads(r["setup_json"] or "{}"),
        "emotion": r["emotion"],
        "plan_compliance": r["plan_compliance"],
        "tags": json.loads(r["tags"] or "[]"),
        "notes": r["notes"],
        "timestamp": r["timestamp"],
        "entry_price": r["entry_price"],
        "sl_price": r["sl_price"],
        "tp_price": r["tp_price"],
        "time_open": r["time_open"],
        "time_close": r["time_close"],
    }


def add_journal_entry(entry):
    with closing(get_db()) as conn:
        cur = conn.execute(
            "INSERT INTO journal (conversation_id, ticket, symbol, action, poi_type, liquidity_swept, "
            "cme_confirmation, setup_json, emotion, plan_compliance, tags, notes, timestamp, "
            "entry_price, sl_price, tp_price, time_open, time_close) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.get("conversation_id"),
                entry.get("ticket"),
                entry.get("symbol", "EURUSD"),
                entry.get("action"),
                entry.get("poi_type"),
                entry.get("liquidity_swept"),
                entry.get("cme_confirmation"),
                json.dumps(entry.get("setup_json") or {}),
                entry.get("emotion"),
                entry.get("plan_compliance"),
                json.dumps(entry.get("tags") or []),
                entry.get("notes"),
                now_iso(),
                entry.get("entry_price"),
                entry.get("sl_price"),
                entry.get("tp_price"),
                entry.get("time_open"),
                entry.get("time_close"),
            ),
        )
        conn.commit()
        eid = cur.lastrowid
    return get_journal_entry(eid)


def get_journal_entry(eid):
    with closing(get_db()) as conn:
        r = conn.execute("SELECT * FROM journal WHERE id = ?", (eid,)).fetchone()
        return _journal_row(r) if r else None


def list_journal(symbol=None, days=None, limit=50):
    q = "SELECT * FROM journal WHERE 1=1"
    params = []
    if symbol:
        q += " AND symbol = ?"
        params.append(symbol.upper())
    if days:
        q += " AND timestamp >= ?"
        params.append((datetime.now() - timedelta(days=days)).isoformat(timespec="seconds"))
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    with closing(get_db()) as conn:
        return [_journal_row(r) for r in conn.execute(q, params).fetchall()]


def update_journal_entry(eid, entry):
    with closing(get_db()) as conn:
        conn.execute(
            "UPDATE journal SET conversation_id=?, ticket=?, symbol=?, action=?, poi_type=?, liquidity_swept=?, "
            "cme_confirmation=?, setup_json=?, emotion=?, plan_compliance=?, tags=?, notes=?, "
            "entry_price=?, sl_price=?, tp_price=?, time_open=?, time_close=? WHERE id=?",
            (
                entry.get("conversation_id"),
                entry.get("ticket"),
                entry.get("symbol", "EURUSD"),
                entry.get("action"),
                entry.get("poi_type"),
                entry.get("liquidity_swept"),
                entry.get("cme_confirmation"),
                json.dumps(entry.get("setup_json") or {}),
                entry.get("emotion"),
                entry.get("plan_compliance"),
                json.dumps(entry.get("tags") or []),
                entry.get("notes"),
                entry.get("entry_price"),
                entry.get("sl_price"),
                entry.get("tp_price"),
                entry.get("time_open"),
                entry.get("time_close"),
                eid,
            ),
        )
        conn.commit()
    return get_journal_entry(eid)


def delete_journal_entry(eid):
    with closing(get_db()) as conn:
        conn.execute("DELETE FROM journal WHERE id = ?", (eid,))
        conn.commit()


# ============================================================
# Explorador de tablas (solo lectura)
# ============================================================

def list_db_tables():
    with closing(get_db()) as conn:
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        out = []
        for t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')").fetchall()]
            n = conn.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
            out.append({"name": t, "columns": cols, "rows": n})
        return out


def _extract_setup_score(setup_json):
    """Extrae el score de confluencia de setup_json (raíz, breakdown o risk)."""
    if not setup_json:
        return None
    if isinstance(setup_json, str):
        try:
            setup_json = json.loads(setup_json)
        except Exception:
            return None
    if not isinstance(setup_json, dict):
        return None
    for cand in ("score", "setup_score", "score_total"):
        v = setup_json.get(cand)
        if isinstance(v, (int, float)):
            return round(float(v), 1)
    for grp in ("breakdown", "risk", "summary"):
        g = setup_json.get(grp)
        if isinstance(g, dict):
            for cand in ("score", "total", "score_total"):
                v = g.get(cand)
                if isinstance(v, (int, float)):
                    return round(float(v), 1)
    return None


def query_db_table(table, limit=100):
    with closing(get_db()) as conn:
        valid = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if table not in valid:
            return None
        if table == "trades":
            # Vista combinada: trades + contexto de journal por ticket
            cols = [
                "id", "ticket", "symbol", "action", "volume", "price_open",
                "price_close", "profit", "time_close", "synced_at",
                "poi_type", "setup_score", "cme_confirmation",
            ]
            sql = (
                "SELECT t.id, t.ticket, t.symbol, t.action, t.volume, t.price_open, "
                "t.price_close, t.profit, t.time_close, t.synced_at, "
                "j.poi_type, j.setup_json, j.cme_confirmation "
                "FROM trades t "
                "LEFT JOIN journal j ON j.ticket = t.ticket "
                "LIMIT ?"
            )
            raw = conn.execute(sql, (limit,)).fetchall()
            rows = []
            for r in raw:
                setup = _extract_setup_score(r[11])
                rows.append(list(r[:10]) + [r[10], setup, r[12]])
            return {"table": table, "columns": cols, "rows": rows}
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
        sql = f"SELECT * FROM '{table}' LIMIT ?"
        rows = [list(r) for r in conn.execute(sql, (limit,)).fetchall()]
        return {"table": table, "columns": cols, "rows": rows}