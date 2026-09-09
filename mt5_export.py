import os
import re
from pathlib import Path

# ============================================================
# Acceso a las exportaciones del indicador AI Chart Assistant
# (AR_AI_ADV) que escribe archivos .txt en MQL5\Files de MT5.
# Ruta por defecto detectada automáticamente; se puede
# sobreescribir con la variable de entorno MT5_FILES_DIR.
# ============================================================

_PREFIX = "AR_AI_ADV_"

# Modos de exportación según el nombre de archivo
_MODE_KEYWORDS = {
    "Full_Trade_Plan": "Full Trade Plan",
    "Analyze_Chart": "Analyze Chart",
    "Quick_Default_Analyze": "Quick Default Analyze",
    "Manual": "Manual",
}


def _default_files_dir():
    """Localiza el directorio MQL5\\Files del primer terminal MT5 instalado
    para el usuario actual (AppData\\Roaming\\MetaQuotes\\Terminal\\<HASH>).
    Devuelve None si no encuentra ningún terminal."""
    base = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    if not base.is_dir():
        return None
    for entry in sorted(base.iterdir()):
        candidate = entry / "MQL5" / "Files"
        if candidate.is_dir():
            return str(candidate)
    return None


def files_dir():
    return os.getenv("MT5_FILES_DIR") or _default_files_dir() or ""


def _parse_filename(name):
    """Extrae simbolo, timeframe y modo del nombre del archivo."""
    base = name[len(_PREFIX):] if name.startswith(_PREFIX) else name
    base = base[:-4] if base.endswith(".txt") else base
    mode = None
    for key, label in _MODE_KEYWORDS.items():
        if key in base:
            mode = label
            remaining = base.replace(key, "_")
            break
    else:
        remaining = base
    parts = [p for p in remaining.split("_") if p]
    symbol = None
    timeframe = None
    if len(parts) >= 2:
        col = 0
        # el primer token que parezca un par de divisas / simbolo
        if len(parts) > 0 and re.match(r"^[A-Z0-9]{2,12}$", parts[0]):
            symbol = parts[0]
            col = 1
        if len(parts) > col and re.match(r"^(M1|M5|M15|M30|H1|H4|H6|H12|D1|W1|MN)", parts[col].upper()):
            timeframe = parts[col].upper()
    return {"symbol": symbol, "timeframe": timeframe, "mode": mode}


def list_exports(symbol=None, mode=None, limit=10):
    d = files_dir()
    if not os.path.isdir(d):
        raise RuntimeError(f"Directorio de exportaciones no encontrado: {d}")
    entries = []
    for name in os.listdir(d):
        if not (name.startswith(_PREFIX) and name.endswith(".txt")):
            continue
        full = os.path.join(d, name)
        if not os.path.isfile(full):
            continue
        meta = _parse_filename(name)
        if symbol and meta["symbol"] and meta["symbol"].upper() != symbol.upper():
            continue
        if mode and meta["mode"] and meta["mode"].lower() != str(mode).lower():
            continue
        st = os.stat(full)
        entries.append({
            "filename": name,
            "symbol": meta["symbol"],
            "timeframe": meta["timeframe"],
            "mode": meta["mode"],
            "size": st.st_size,
            "modified": st.st_mtime,
        })
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return entries[:limit]


def resolve_path(filename):
    d = files_dir()
    full = os.path.abspath(os.path.join(d, filename))
    dabs = os.path.abspath(d)
    if not full.startswith(dabs + os.sep) or os.path.isdir(full):
        raise ValueError(f"Nombre de archivo inválido: {filename}")
    if not os.path.isfile(full):
        raise FileNotFoundError(f"No existe la exportación: {filename}")
    return full


def read_export(filename, max_bytes=20000):
    full = resolve_path(filename)
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(max_bytes)
    return {"filename": filename, "content": content}


def latest_export(symbol=None, mode=None):
    entries = list_exports(symbol=symbol, mode=mode, limit=1)
    if not entries:
        raise FileNotFoundError("No hay exportaciones recientes del AI Chart Assistant")
    return read_export(entries[0]["filename"])


_EXPORT_RE = re.compile(r"AR_AI_ADV_[A-Za-z0-9_]+\.txt")


def extract_export_path(text):
    """Busca en un texto la ruta/nombre de un archivo exportado (AR_AI_ADV_*.txt)
    y devuelve solo el nombre base del archivo. Acepta path completo o solo nombre.
    Devuelve None si no hay coincidencia."""
    if not text:
        return None
    m = _EXPORT_RE.search(text)
    if not m:
        return None
    return m.group(0)
