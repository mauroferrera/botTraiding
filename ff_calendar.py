"""Calendario económico de Forex Factory vía proxy Jina (sin API key).

Fuente elegida por el usuario. El scraping directo está protegido por
Cloudflare (403), por eso se usa el proxy gratuito r.jina.ai que devuelve
el calendario como texto plano y nos permite parsear los eventos sin clave.
"""

import re
import threading
import time
from datetime import datetime, timezone

import requests

CALENDAR_URL = "https://r.jina.ai/http://www.forexfactory.com/calendar?day=today"

IMPACT_LEVEL = {"red": 3, "ora": 2, "yel": 1}
IMPACT_LABEL = {"red": "Alto", "ora": "Medio", "yel": "Bajo"}

# Caché TTL del gate de noticias: el fetch de FF es caro y el gate se consulta
# en el camino de ejecución de órdenes. Nunca debe golpear la red por trade.
_CACHE_TTL = 600.0
_cache: dict = {}
_cache_lock = threading.Lock()


def _fetch_markdown(timeout=45):
    r = requests.get(
        CALENDAR_URL,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    return r.text


def _to_minutes(hm):
    """Convierte '1:30pm' a minutos transcurridos desde medianoche."""
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", hm.strip().lower())
    if not m:
        return None
    h, mn, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "pm" and h != 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return h * 60 + mn


def _impact(icon_url):
    for key, val in IMPACT_LEVEL.items():
        if f"ff-impact-{key}.png" in icon_url:
            return key
    return "yel"


TIME_RE = re.compile(r"(\d{1,2}:\d{2}[ap]m)")
CURRENCY_RE = re.compile(r"\|\s*([A-Z]{3})\s*\|")
IMPACT_RE = re.compile(r"ff-impact-(red|ora|yel)\.png\s*\)\s*\|\s*([^|]+?)(?:\s*\|)")
BRANCH_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def parse_calendar(md):
    """Devuelve (reloj_minutos, eventos)."""
    clock_min = None
    mclock = re.search(r"\| \[(\d{1,2}:\d{2}[ap]m)\]\([^)]*?timezone", md)
    if mclock:
        clock_min = _to_minutes(mclock.group(1))

    events = []
    prev_time = None
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue

        tm = TIME_RE.search(line)
        minutes = None
        time_str = ""
        if tm:
            minutes = _to_minutes(tm.group(1))
            time_str = tm.group(1)
            prev_time = minutes
        elif prev_time is not None:
            # fila que hereda la hora de la anterior
            minutes = prev_time

        cur = CURRENCY_RE.search(line)
        currency = cur.group(1) if cur else ""

        im = IMPACT_RE.search(line)
        title = ""
        impact = "yel"
        if im:
            impact = im.group(1)
            title = BRANCH_RE.sub("", im.group(2)).strip()
            title = title.strip(" |")

        if not currency or not title:
            continue

        events.append({
            "time": time_str,
            "minutes": minutes,
            "currency": currency,
            "impact": impact,
            "title": title,
        })
    return clock_min, events


def eurusd_news():
    """Última y próxima noticia del día relevantes para EUR/USD."""
    md = _fetch_markdown()
    clock_min, events = parse_calendar(md)

    # solo monedas EUR o USD, con hora conocida
    relevant = [
        e for e in events
        if e["currency"] in ("EUR", "USD") and e["minutes"] is not None
    ]

    # orden cronológico
    relevant.sort(key=lambda e: e["minutes"])

    passed, upcoming = [], []
    for e in relevant:
        if clock_min is not None and e["minutes"] <= clock_min:
            passed.append(e)
        else:
            upcoming.append(e)

    def pick(seq, reverse):
        if not seq:
            return None
        return max(seq, key=lambda e: (IMPACT_LEVEL[e["impact"]], e["minutes"]))

    return {
        "asof_minutes": clock_min,
        "source": "Forex Factory (vía Jina)",
        "last": pick(passed, True),
        "next": pick(upcoming, False),
        "relevant_count": len(relevant),
    }


# ---------------------------------------------------------------------------
# Gate de noticias (hard gate)
# ---------------------------------------------------------------------------

FULL_DAY = 24 * 60


def _minutes_of_day(dt) -> int:
    return dt.hour * 60 + dt.minute


def event_utc_minutes(event, clock_min, now_utc):
    """Convierte los `minutes` del calendario (hora del reloj FF) a minutos
    UTC de hoy.

    Si el reloj no se pudo leer (`clock_min` es None) se asume que los eventos
    ya vienen en UTC (referencia degradada y documentada).
    """
    if event.get("minutes") is None:
        return None
    offset = 0 if clock_min is None else (_minutes_of_day(now_utc) - clock_min)
    return (event["minutes"] + offset) % FULL_DAY


def high_impact_in_window(
    events,
    clock_min=None,
    now_utc=None,
    buffer_min=15,
    currencies=("EUR", "USD"),
    min_impact="red",
):
    """¿Hay un evento de impacto alto/medio en la ventana [now-buffer, now+buffer]?

    Pura y testeable: no toca la red. Los minutos de los eventos están en la
    zona del reloj FF; `now_utc` es un datetime con TZ. Devuelve
    {"blocked": bool, "event": evento|None, "detail": str}.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    ref = _minutes_of_day(now_utc)
    level = IMPACT_LEVEL.get(min_impact, IMPACT_LEVEL["red"])

    candidates = []
    for e in events:
        if e["currency"] not in currencies:
            continue
        if IMPACT_LEVEL.get(e["impact"], IMPACT_LEVEL["yel"]) < level:
            continue
        ev = event_utc_minutes(e, clock_min, now_utc)
        if ev is None:
            continue
        delta = (ev - ref) % FULL_DAY
        if delta > FULL_DAY / 2:
            delta -= FULL_DAY
        if abs(delta) <= buffer_min:
            candidates.append((e, delta))

    if not candidates:
        return {"blocked": False, "event": None, "detail": "sin eventos en ventana"}

    # prioriza el de mayor impacto y el más cercano
    candidates.sort(key=lambda it: (-IMPACT_LEVEL[it[0]["impact"]], abs(it[1])))
    ev, delta = candidates[0]
    rel = "ahora" if delta == 0 else ("hace %d min" % -delta if delta < 0 else "en %d min" % delta)
    return {
        "blocked": True,
        "event": ev,
        "detail": "%s (%s impacto) %s: %s"
        % (ev["title"], IMPACT_LABEL.get(ev["impact"], ev["impact"]), rel, ev["currency"]),
    }


def cached_calendar(ttl=_CACHE_TTL, timeout=20):
    """Calendario del día con caché TTL. Devuelve (clock_min, events).

    Si el fetch falla y existe caché (aunque esté vencida) la sirve en vez de
    romper el gate: un calendario viejo es mejor que ningún calendario.
    Solo lanza cuando no hay caché alguna (primera llamada sin red).
    """
    now = time.time()
    with _cache_lock:
        hit = _cache.get("calendar")
        if hit and now - hit["ts"] < ttl:
            return hit["clock_min"], hit["events"]
        stale = hit

    try:
        md = _fetch_markdown(timeout=timeout)
        clock_min, events = parse_calendar(md)
        with _cache_lock:
            _cache["calendar"] = {"ts": now, "clock_min": clock_min, "events": events}
        return clock_min, events
    except Exception:
        if stale is not None:
            return stale["clock_min"], stale["events"]
        raise


def news_gate(
    min_impact="red",
    buffer_min=15,
    now_utc=None,
    currencies=("EUR", "USD"),
    ttl=_CACHE_TTL,
):
    """Gate de noticias listo para producción.

    - TTL cacheado (no golpea la red por cada trade).
    - Devuelve {"ok": True, ...} si no hay evento en ventana o el gateway se
      degrada a fail-open cuando el fetch falla (NUNCA bloquea por red caída).
    - Devuelve {"ok": False, "reason": ..., "event": ...} para bloquear.
    """
    try:
        clock_min, events = cached_calendar(ttl=ttl)
    except Exception as exc:
        return {
            "ok": True,
            "fail_open": True,
            "reason": "calendario no disponible (%s): fail-open, no se bloquea" % exc,
            "event": None,
        }
    res = high_impact_in_window(
        events,
        clock_min=clock_min,
        now_utc=now_utc,
        buffer_min=buffer_min,
        currencies=currencies,
        min_impact=min_impact,
    )
    if res["blocked"]:
        return {
            "ok": False,
            "fail_open": False,
            "reason": "ventana de noticia: %s" % res["detail"],
            "event": res["event"],
        }
    return {"ok": True, "fail_open": False, "reason": res["detail"], "event": None}