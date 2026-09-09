"""Cargador de la estrategia de trading desde strategy.yaml (fuente única de verdad).

Este módulo es el ÚNICO punto donde la estrategia se materializa para el resto del
proyecto. Lee strategy.yaml, valida tipos y rangos, aplica los valores por defecto y
devuelve la config que antes vivía en store.DEFAULT_TRADING_CONFIG, con el MISMO shape
de siempre (por lo que store.get_trading_config() / app.py / risk_engine / agent siguen
funcionando sin cambios).

Normas de validación:
  - Un valor desconocido se ignora (para no petar el arranque por claves nuevas).
  - Un valor con el tipo incorrecto o fuera de rango LANZA error (para que el plan nunca
    se ejecute con reglas rotas en silencio).
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML no está instalado. Ejecuta: pip install pyyaml"
    ) from exc

STRATEGY_PATH = os.environ.get(
    "STRATEGY_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy.yaml")
)

_cache: Dict[str, Any] = {}
_cache_ts: float = 0.0
_cache_lock = threading.Lock()


# ============================================================
# Valores por defecto (mantienen el comportamiento histórico).
# ============================================================

_DEFAULTS: Dict[str, Any] = {
    # Perfil de riesgo
    "risk_pct": 0.5,
    "reduced_risk_pct": 0.25,
    "loss_limit_fixed": 1250.0,
    "loss_limit_pct": 2.0,
    "max_trades_day": 10,
    # Ejecución
    "magic": 8882026,
    "comment": "Web Exec",
    "sl_default_pips": 15,
    "tp_ratio_r": 2.0,
    "deviation_points": 20,
    "news_buffer_min": 15,
    "symbols_allow": [],
    # Score
    "min_score": 80.0,
    "min_rr": 2.0,
    "setup_ttl_minutes": 45,
    "risk_weights": {"cot": 25.0, "cvd_of": 25.0, "smc": 30.0, "killzone": 20.0},
    "grade_thresholds": {"alta": 80.0, "media": 60.0},
    # Killzones
    "killzones": [
        {"name": "Londres", "start": "08:00", "end": "11:00"},
        {"name": "Nueva York", "start": "13:00", "end": "16:00"},
    ],
    # Prop firm
    "prop_enabled": False,
    "prop_max_dd_daily_pct": 2.0,
    "prop_max_dd_total_pct": 6.0,
    "prop_max_profit_day_pct": 1.5,
    "prop_consistency_days": 4,
    # Fuentes de datos
    "data_sources": {
        "cot": True,
        "cvd_of": True,
        "smc": True,
        "killzone": True,
        "news": True,
        "orderflow": False,
    },
    # Watcher (bot a la escucha)
    "watcher_config": {
        "enabled": True,
        "scan_interval_sec": 60,
        "auto_execute": False,
        "dedup_ttl_sec": 2700,
        "symbols": [{"symbol": "EURUSD", "timeframe": "M15"}],
    },
    "agent_topics": {
        "account": ["saldo", "equity", "margen", "balance", "capital", "cuenta", "account"],
        "positions": ["posicion", "abierta", "abierto", "trades"],
        "history": ["historial", "historia", "cerrada", "historico", "gan"],
        "news": ["noticia", "noticias", "economi", "calendario", "dato", "pip", "fed", "nipc", "inflacion"],
        "trade": ["oper", "entrar", "entrada", "setup", "compr", "vend", "buy", "sell",
                  "stoploss", "sl", "tp", "take", "riesgo", "score", "ganar", "perder"],
    },
    "agent_system_prompt": "",
    "agent_risk_policy": "",
    "agent_data_sources_policy": "",
    "agent_allowed_tools": [
        "account_info", "positions_list", "history", "price", "now",
        "orderflow_snapshot", "orderflow_alerts", "patterns",
        "trade_query", "journal_append", "journal_list",
        "mt5_export_read", "chart_snapshot", "economic_news",
        "set_chart_alert", "chart_annotate",
    ],
}

# ============================================================
# Especificación de tipos y rangos por clave, para la validación.
# ============================================================
# (nombre, tipo, opcional, rango o validador)
_BOOLEAN = "bool"
_NUMBER = "number"
_STRING = "string"
_LIST_STR = "list_str"


def _spec_for(key: str):
    table: Dict[str, tuple] = {
        "risk_pct": (_NUMBER, 0.0, 100.0),
        "reduced_risk_pct": (_NUMBER, 0.0, 100.0),
        "loss_limit_fixed": (_NUMBER, 0.0, None),
        "loss_limit_pct": (_NUMBER, 0.0, 100.0),
        "max_trades_day": (_NUMBER, 0, None),
        "magic": (_NUMBER, 0, None),
        "comment": (_STRING, None, None),
        "sl_default_pips": (_NUMBER, 0.0, None),
        "tp_ratio_r": (_NUMBER, 0.0, None),
        "deviation_points": (_NUMBER, 0, None),
        "news_buffer_min": (_NUMBER, 0, None),
        "symbols_allow": (_LIST_STR, None, None),
        "min_score": (_NUMBER, 0.0, 100.0),
        "min_rr": (_NUMBER, 0.0, None),
        "setup_ttl_minutes": (_NUMBER, 0, None),
        "prop_max_dd_daily_pct": (_NUMBER, 0.0, 100.0),
        "prop_max_dd_total_pct": (_NUMBER, 0.0, 100.0),
        "prop_max_profit_day_pct": (_NUMBER, 0.0, 100.0),
        "prop_consistency_days": (_NUMBER, 0, None),
    }
    return table.get(key)


def _check(value: Any, spec: tuple, key: str) -> None:
    kind, lo, hi = spec
    if kind == _BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError(f"strategy.yaml: '{key}' debe ser true/false (booleano).")
        return
    if kind == _STRING:
        if not isinstance(value, str):
            raise ValueError(f"strategy.yaml: '{key}' debe ser un texto.")
        return
    if kind == _LIST_STR:
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"strategy.yaml: '{key}' debe ser una lista de símbolos/textos.")
        return
    if kind == _NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"strategy.yaml: '{key}' debe ser un número.")
        if lo is not None and value < lo:
            raise ValueError(f"strategy.yaml: '{key}' no puede ser menor que {lo} (es {value}).")
        if hi is not None and value > hi:
            raise ValueError(f"strategy.yaml: '{key}' no puede ser mayor que {hi} (es {value}).")


# ============================================================
# Construcción de la config aplanada (shape histórico de get_trading_config)
# ============================================================

def _parse_killzones(raw: Any) -> List[Dict[str, str]]:
    """Acepta el formato plano (lista de ventanas) y el jerárquico
    `{timezone, windows: [...]}`. La zona horaria informativa no se aplana:
    los consumidores trabajan siempre en UTC (killzone_score)."""
    if raw is None:
        return list(_DEFAULTS["killzones"])
    if isinstance(raw, dict):
        raw = raw.get("windows") if isinstance(raw.get("windows"), list) else raw.get("windows")
        if not isinstance(raw, list):
            raise ValueError(
                "strategy.yaml: 'killzones' debe ser una lista (formato plano) o "
                "{timezone, windows: [...]} (formato jerárquico)."
            )
    if not isinstance(raw, list):
        raise ValueError("strategy.yaml: 'killzones' debe ser una lista de ventanas.")
    out: List[Dict[str, str]] = []
    for w in raw:
        if not isinstance(w, dict) or "start" not in w or "end" not in w:
            raise ValueError(
                "strategy.yaml: cada killzone debe tener 'name', 'start' y 'end' HH:MM."
            )
        for k in ("start", "end"):
            if not isinstance(w.get(k), str) or ":" not in w[k]:
                raise ValueError(
                    f"strategy.yaml: killzone '{w.get('name', '?')}' requiere '{k}' en formato HH:MM."
                )
        out.append({
            "name": str(w.get("name") or "?"),
            "start": str(w["start"]),
            "end": str(w["end"]),
        })
    return out if out else list(_DEFAULTS["killzones"])


def _parse_weights(raw: Any, key: str = "score.weights") -> Dict[str, float]:
    if raw is None:
        return dict(_DEFAULTS["risk_weights"])
    if not isinstance(raw, dict):
        raise ValueError(f"strategy.yaml: '{key}' debe ser un objeto de pesos.")
    base = dict(_DEFAULTS["risk_weights"])
    for k in ("cot", "cvd_of", "smc", "killzone"):
        if k in raw:
            v = raw[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ValueError(f"strategy.yaml: 'weights.{k}' debe ser un número >= 0.")
            base[k] = float(v)
    return base


def _parse_data_sources(raw: Any) -> Dict[str, bool]:
    if raw is None:
        return dict(_DEFAULTS["data_sources"])
    if not isinstance(raw, dict):
        raise ValueError("strategy.yaml: 'data_sources' debe ser un objeto de flags true/false.")
    out = dict(_DEFAULTS["data_sources"])
    for k in out:
        if k in raw:
            if not isinstance(raw[k], bool):
                raise ValueError(f"strategy.yaml: 'data_sources.{k}' debe ser true/false.")
            out[k] = raw[k]
    return out


def _parse_topics(raw: Any) -> Dict[str, List[str]]:
    if raw is None:
        return {k: list(v) for k, v in _DEFAULTS["agent_topics"].items()}
    if not isinstance(raw, dict):
        raise ValueError("strategy.yaml: 'agent.topics' debe ser un objeto de palabras clave.")
    out: Dict[str, List[str]] = {}
    base = _DEFAULTS["agent_topics"]
    for key, default in base.items():
        val = raw.get(key, default)
        if not isinstance(val, list) or not all(isinstance(x, str) and x for x in val):
            raise ValueError(f"strategy.yaml: 'agent.topics.{key}' debe ser una lista de palabras.")
        out[key] = list(val)
    return out


def _parse_watcher(raw: Any) -> Dict[str, Any]:
    """Valida la sección 'watcher' del YAML. Acepta sección ausente (defaults)."""
    if raw is None:
        return {
            "enabled": True,
            "scan_interval_sec": 60,
            "auto_execute": False,
            "dedup_ttl_sec": 2700,
            "symbols": [{"symbol": "EURUSD", "timeframe": "M15"}],
        }
    if not isinstance(raw, dict):
        raise ValueError("strategy.yaml: 'watcher' debe ser un objeto.")

    def _bool(val: Any, key: str) -> bool:
        if not isinstance(val, bool):
            raise ValueError(f"strategy.yaml: 'watcher.{key}' debe ser true/false.")
        return val

    def _num(val: Any, key: str) -> float:
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
            raise ValueError(f"strategy.yaml: 'watcher.{key}' debe ser un número >= 0.")
        return float(val)

    out: Dict[str, Any] = {
        "enabled": _bool(raw.get("enabled", True), "enabled"),
        "scan_interval_sec": _num(raw.get("scan_interval_sec", 60), "scan_interval_sec"),
        "auto_execute": _bool(raw.get("auto_execute", False), "auto_execute"),
        "dedup_ttl_sec": _num(raw.get("dedup_ttl_sec", 2700), "dedup_ttl_sec"),
    }
    syms_raw = raw.get("symbols")
    if syms_raw is None:
        out["symbols"] = [{"symbol": "EURUSD", "timeframe": "M15"}]
    else:
        if not isinstance(syms_raw, list) or not syms_raw:
            raise ValueError("strategy.yaml: 'watcher.symbols' debe ser una lista no vacía.")
        syms = []
        for s in syms_raw:
            if not isinstance(s, dict):
                raise ValueError("strategy.yaml: cada 'watcher.symbols' debe tener symbol y timeframe.")
            symbol = str(s.get("symbol") or "EURUSD").upper()
            timeframe = str(s.get("timeframe") or "M15").upper()
            if not symbol:
                raise ValueError("strategy.yaml: 'watcher.symbols[].symbol' no puede estar vacío.")
            syms.append({"symbol": symbol, "timeframe": timeframe})
        out["symbols"] = syms
    return out


def _build_flat(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte el YAML jerárquico en la config plana del shape histórico."""
    d = doc.get("risk") or {}
    e = doc.get("execution") or {}
    s = doc.get("score") or {}
    prop = doc.get("prop") or {}
    agent = doc.get("agent") or {}

    flat: Dict[str, Any] = dict(_DEFAULTS)

    scalar = {
        "risk_pct": ("risk", "risk_pct"),
        "reduced_risk_pct": ("risk", "reduced_risk_pct"),
        "loss_limit_fixed": ("risk", "loss_limit_fixed"),
        "loss_limit_pct": ("risk", "loss_limit_pct"),
        "max_trades_day": ("risk", "max_trades_day"),
        "magic": ("execution", "magic"),
        "comment": ("execution", "comment"),
        "sl_default_pips": ("execution", "sl_default_pips"),
        "tp_ratio_r": ("execution", "tp_ratio_r"),
        "deviation_points": ("execution", "deviation_points"),
        "news_buffer_min": ("execution", "news_buffer_min"),
        "symbols_allow": ("execution", "symbols_allow"),
        "min_score": ("score", "min_score"),
        "min_rr": ("score", "min_rr"),
        "setup_ttl_minutes": ("score", "setup_ttl_minutes"),
        "prop_enabled": ("prop", "enabled"),
        "prop_max_dd_daily_pct": ("prop", "max_dd_daily_pct"),
        "prop_max_dd_total_pct": ("prop", "max_dd_total_pct"),
        "prop_max_profit_day_pct": ("prop", "max_profit_day_pct"),
        "prop_consistency_days": ("prop", "consistency_days"),
    }
    secs = {
        "risk": d, "execution": e, "score": s, "prop": prop,
    }
    for key, (sec, k) in scalar.items():
        src = secs[sec]
        if k in src:
            flat[key] = src[k]

    # grade thresholds
    gth = s.get("grade_thresholds") or _DEFAULTS["grade_thresholds"]
    if isinstance(gth, dict):
        flat["grade_thresholds"] = gth

    # risk_weights y killzones se exponen como JSON string (shape histórico:
    # los consumidores hacen json.loads(...)).
    flat["risk_weights"] = json.dumps(
        _parse_weights(s.get("weights"), "score.weights"), ensure_ascii=False
    )
    flat["killzones"] = json.dumps(
        _parse_killzones(doc.get("killzones")), ensure_ascii=False
    )
    flat["data_sources"] = _parse_data_sources(doc.get("data_sources"))
    flat["watcher_config"] = _parse_watcher(doc.get("watcher"))
    flat["agent_topics"] = _parse_topics(agent.get("topics"))
    # Agent textos (prompt / policy)
    flat["agent_system_prompt"] = str(agent.get("system_prompt") or "").strip()
    flat["agent_risk_policy"] = str(agent.get("risk_policy") or "").strip()
    flat["agent_data_sources_policy"] = str(agent.get("data_sources_policy") or "").strip()
    flat["agent_allowed_tools"] = (
        agent.get("allowed_tools") or list(_DEFAULTS.get("agent_allowed_tools", []))
    )

    # Validar escalares (prop_enabled es booleano, no numérico).
    for key in scalar:
        spec = _spec_for(key)
        if spec:
            _check(flat[key], spec, key)
    if not isinstance(flat.get("prop_enabled"), bool):
        raise ValueError("strategy.yaml: 'prop.enabled' debe ser true/false (booleano).")

    return flat


def _load_yaml() -> Dict[str, Any]:
    if not os.path.exists(STRATEGY_PATH):
        # Falla en claro: sin archivo no hay plan que ejecutar.
        raise FileNotFoundError(
            f"No se encontró {STRATEGY_PATH}. El archivo de estrategia es obligatorio."
        )
    with open(STRATEGY_PATH, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc if isinstance(doc, dict) else {}


def load(force: bool = False, validate_only: bool = False) -> Dict[str, Any]:
    """Carga y valida strategy.yaml, devolviendo la config aplanada.

    - force=True: ignora la caché.
    - validate_only=True: valida y devuelve el dict jerárquico (sin aplanar), útil
      para un endpoint de chequeo.
    """
    with _cache_lock:
        if not force and _cache:
            return _cache["flat"] if not validate_only else _cache["doc"]

    doc = _load_yaml()
    flat = _build_flat(doc)
    if not validate_only:
        with _cache_lock:
            _cache["flat"] = flat
            _cache["doc"] = doc
        return flat
    return doc


def get_trading_config() -> Dict[str, Any]:
    """Devuelve la config aplanada (shape histórico) leyendo strategy.yaml."""
    return load()


def get_data_sources() -> Dict[str, bool]:
    return load().get("data_sources", {})


def get_watcher_config() -> Dict[str, Any]:
    """Config del watcher (bot a la escucha) desde strategy.yaml."""
    return load().get("watcher_config", {})


def get_agent_topics() -> Dict[str, List[str]]:
    return load().get("agent_topics", {})


# Exposición de la config para app/risk/agent con nombre estable.
def get_config() -> Dict[str, Any]:
    return get_trading_config()


# ============================================================
# Ruta de escritura: set_trading_config() escribe al YAML.
# ============================================================

# Mapa: flat key -> (sección YAML, sub-clave)
_FLAT_TO_YAML: Dict[str, tuple] = {
    "risk_pct": ("risk", "risk_pct"),
    "reduced_risk_pct": ("risk", "reduced_risk_pct"),
    "loss_limit_fixed": ("risk", "loss_limit_fixed"),
    "loss_limit_pct": ("risk", "loss_limit_pct"),
    "max_trades_day": ("risk", "max_trades_day"),
    "magic": ("execution", "magic"),
    "comment": ("execution", "comment"),
    "sl_default_pips": ("execution", "sl_default_pips"),
    "tp_ratio_r": ("execution", "tp_ratio_r"),
    "deviation_points": ("execution", "deviation_points"),
    "news_buffer_min": ("execution", "news_buffer_min"),
    "symbols_allow": ("execution", "symbols_allow"),
    "min_score": ("score", "min_score"),
    "min_rr": ("score", "min_rr"),
    "setup_ttl_minutes": ("score", "setup_ttl_minutes"),
    "prop_enabled": ("prop", "enabled"),
    "prop_max_dd_daily_pct": ("prop", "max_dd_daily_pct"),
    "prop_max_dd_total_pct": ("prop", "max_dd_total_pct"),
    "prop_max_profit_day_pct": ("prop", "max_profit_day_pct"),
    "prop_consistency_days": ("prop", "consistency_days"),
    "risk_weights": ("score", "weights"),
    "killzones": (None, None),  # tratamiento especial
}


def _apply_updates(doc: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica un dict de actualizaciones planas al dict jerárquico del YAML."""
    for key, value in updates.items():
        if key in ("risk_weights", "killzones"):
            # Tratamiento especial: serializar como JSON string
            if key == "risk_weights" and isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif key == "killzones" and isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    continue
            if key == "risk_weights":
                if doc.get("score") is None:
                    doc["score"] = {}
                doc["score"]["weights"] = value
            elif key == "killzones":
                doc["killzones"] = value
            continue

        mapping = _FLAT_TO_YAML.get(key)
        if not mapping:
            continue
        section, subkey = mapping
        if section is None:
            continue
        if doc.get(section) is None:
            doc[section] = {}
        doc[section][subkey] = value
    return doc


def _yaml_scalar(value: Any) -> str:
    """Serializa un escalar/lista plana en YAML compacto (sin marcador '...' de PyYAML)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = ", ".join(_yaml_scalar(x) for x in value)
        return f"[{items}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = ", ".join(f"{_yaml_plain_key(k)}: {_yaml_scalar(v)}" for k, v in value.items())
        return "{" + (items[:80] + ",\n  ..." if len(items) > 80 else items) + "}"
    s = str(value)
    if s == "":
        return '""'
    # Plain (bare) si es seguro: solo alfanum + separadores, sin espacios.
    bare_ok = re.fullmatch(r"[A-Za-z0-9_./+\-]+", s)
    if bare_ok and "@" not in s:
        return s
    # Doble comilla (JSON-ish) con escapes mínimos; el YAML doble-comillado admite
    # unicode y se ve bien.
    quoted = s.replace("\\", "\\\\").replace('"', '\\"')
    if "\n" in quoted:
        return '"' + quoted.replace("\n", "\\n") + '"'
    return '"' + quoted + '"'


def _yaml_plain_key(k: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_\-]+", str(k)):
        return str(k)
    return _yaml_scalar(str(k))


def _patch_scalar(text: str, section: str, subkey: str, value: Any) -> str:
    """Reemplaza 'subkey:' dentro de la sección toplevel 'section:' sin tocar
    comentarios ni el resto del archivo. Devuelve el texto actualizado."""
    lines = text.splitlines()
    sec_idx = None
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("#") and ln.strip() == f"{section}:":
            sec_idx = i
            break
    if sec_idx is None:
        lines.append(f"{section}:\n  {subkey}: {_yaml_scalar(value)}")
        return "\n".join(lines)

    key_pat = re.compile(r"^(\s*)" + re.escape(subkey) + r":(?=\s|$)")
    repl = f"{_yaml_scalar(value)}"
    for j in range(sec_idx + 1, len(lines)):
        ln = lines[j]
        if not ln.strip().startswith("#") and _is_toplevel(ln):
            break
        m = key_pat.match(ln)
        if m and not ln.strip().startswith("#"):
            # Conserva el comentario inline de la línea original (si lo hay).
            inline = ""
            cm = re.search(r"(?<![\w])#", ln[m.end():])
            if cm:
                inline = ln[m.end() + cm.start():].rstrip()
            new_line = f"{m.group(1)}{subkey}: {repl}"
            if inline:
                # Alinear tras el valor para legibilidad.
                pad = max(1, 22 - len(f"{subkey}: {repl}"))
                new_line += " " * pad + inline.lstrip()
            lines[j] = new_line
            return "\n".join(lines)

    # El subkey no existe aún: lo insertamos tras la cabecera de la sección.
    indent = "  "
    lines[sec_idx:sec_idx + 1] = [
        lines[sec_idx],
        f"{indent}{subkey}: {repl}",
    ]
    return "\n".join(lines)


def _is_toplevel(ln: str) -> bool:
    return bool(ln) and not ln[0].isspace() and not ln.strip().startswith("#") and ":" in ln


def save(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza strategy.yaml con las claves del dict plana y limpia la caché.

    Preserva comentarios y formato: solo se reescriben las líneas cuyo valor cambia.
    risk_weights / killzones se omiten salvo que cambien de verdad (entonces se
    regenera el archivo entero con yaml.dump y se pierden comentarios).

    Devuelve la config aplanada actualizada.
    """
    doc = _load_yaml()
    with open(STRATEGY_PATH, "r", encoding="utf-8") as fh:
        text = fh.read()

    changed = False
    needs_full_dump = False
    for key, value in updates.items():
        mapping = _FLAT_TO_YAML.get(key)
        if not mapping:
            continue
        if key in ("risk_weights", "killzones"):
            # JSON string -> dict para comparar contra el doc
            cmp_val = value
            if isinstance(cmp_val, str):
                try:
                    cmp_val = json.loads(cmp_val)
                except (json.JSONDecodeError, TypeError):
                    cmp_val = None
            if cmp_val is None:
                continue
            if key == "risk_weights":
                cur = (doc.get("score") or {}).get("weights")
            else:
                cur = doc.get("killzones")
            if cur != cmp_val:
                needs_full_dump = True
            continue

        section, subkey = mapping
        if section is None:
            continue
        new_text = _patch_scalar(text, section, subkey, value)
        if new_text != text:
            text = new_text
            changed = True

    if needs_full_dump:
        doc = _apply_updates(doc, updates)
        text = yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)
        changed = True

    if changed:
        with open(STRATEGY_PATH, "w", encoding="utf-8") as fh:
            fh.write(text)

    # Limpiar caché para que la próxima lectura recargue el YAML.
    with _cache_lock:
        _cache.clear()

    return get_trading_config()