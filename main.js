const REFRESH_MS = 8000;

const els = {
  accountLabel: document.getElementById("accountLabel"),
  connDot: document.getElementById("connDot"),
  connText: document.getElementById("connText"),
  kpiBalance: document.getElementById("kpiBalance"),
  kpiBalanceSub: document.getElementById("kpiBalanceSub"),
  kpiEquity: document.getElementById("kpiEquity"),
  kpiProfit: document.getElementById("kpiProfit"),
  kpiProfitSub: document.getElementById("kpiProfitSub"),
  kpiFreeMargin: document.getElementById("kpiFreeMargin"),
  kpiMarginLevel: document.getElementById("kpiMarginLevel"),
  kpiMarginLevelSub: document.getElementById("kpiMarginLevelSub"),
  kpiPositions: document.getElementById("kpiPositions"),
  kpiPositionsSub: document.getElementById("kpiPositionsSub"),
  posTable: document.querySelector("#posTable tbody"),
  posUpdated: document.getElementById("posUpdated"),
  histTable: document.querySelector("#histTable tbody"),
  histUpdated: document.getElementById("histUpdated"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatText: document.getElementById("chatText"),
  chatSend: document.getElementById("chatSend"),
  suggestions: document.getElementById("suggestions"),
  newConvBtn: document.getElementById("newConvBtn"),
  chartSymbol: document.getElementById("chartSymbol"),
  btnChartAssistant: document.getElementById("btnChartAssistant"),
  btnSetupEval: document.getElementById("btnSetupEval"),
  tfGroup: document.getElementById("tfGroup"),
  chartMode: document.getElementById("chartMode"),
  sourceChip: document.getElementById("sourceChip"),
  evControls: document.getElementById("evControls"),
  evMode: document.getElementById("evMode"),
  evParam: document.getElementById("evParam"),
  chartMsg: document.getElementById("chartMsg"),
  chartQuote: document.getElementById("chartQuote"),
  btnCvd: document.getElementById("btnCvd"),
  btnVp: document.getElementById("btnVp"),
  btnJournal: document.getElementById("btnJournal"),
  cotBadge: document.getElementById("cotBadge"),
  scoreBadge: document.getElementById("scoreBadge"),
  chartEl: document.getElementById("chart"),
  tradeBuyBtn: document.getElementById("tradeBuyBtn"),
  tradeSellBtn: document.getElementById("tradeSellBtn"),
  riskChip: document.getElementById("riskChip"),
  tradeCfgBtn: document.getElementById("tradeCfgBtn"),
  tradeModal: document.getElementById("tradeModal"),
  tradeClose: document.getElementById("tradeClose"),
  tradeConfirm: document.getElementById("tradeConfirm"),
  tradeModalTitle: document.getElementById("tradeModalTitle"),
  tmType: document.getElementById("tmType"),
  tmSymbol: document.getElementById("tmSymbol"),
  tmAction: document.getElementById("tmAction"),
  tmEntry: document.getElementById("tmEntry"),
  tmVolume: document.getElementById("tmVolume"),
  tmSl: document.getElementById("tmSl"),
  tmTp: document.getElementById("tmTp"),
  tmRisk: document.getElementById("tmRisk"),
  tmMargin: document.getElementById("tmMargin"),
  tmMeta: document.getElementById("tmMeta"),
  tmFill: document.getElementById("tmFill"),
  tmNote: document.getElementById("tmNote"),
  tradeConfigModal: document.getElementById("tradeConfigModal"),
  tradeCfgClose: document.getElementById("tradeCfgClose"),
  tradeCfgSave: document.getElementById("tradeCfgSave"),
  tcMagic: document.getElementById("tcMagic"),
  tcComment: document.getElementById("tcComment"),
  tcRisk: document.getElementById("tcRisk"),
  tcLossFixed: document.getElementById("tcLossFixed"),
  tcLossPct: document.getElementById("tcLossPct"),
  tcMaxTrades: document.getElementById("tcMaxTrades"),
  tcSlPips: document.getElementById("tcSlPips"),
  tcTpR: document.getElementById("tcTpR"),
  tcDeviation: document.getElementById("tcDeviation"),
  tcAllow: document.getElementById("tcAllow"),
  tcAutoExec: document.getElementById("tcAutoExec"),
  watcherAgent: document.getElementById("watcherAgent"),
  watcherStatusDot: document.getElementById("watcherStatusDot"),
  watcherScan: document.getElementById("watcherScan"),
  closeModal: document.getElementById("closeModal"),
  closeCancel: document.getElementById("closeCancel"),
  closeConfirm: document.getElementById("closeConfirm"),
  closeInfo: document.getElementById("closeInfo"),
  toast: document.getElementById("toast"),
  resSymbol: document.getElementById("resSymbol"),
  resTf: document.getElementById("resTf"),
  resDays: document.getElementById("resDays"),
  resExportBtn: document.getElementById("resExportBtn"),
  resValidateBtn: document.getElementById("resValidateBtn"),
  resBacktestBtn: document.getElementById("resBacktestBtn"),
  resCalibrateBtn: document.getElementById("resCalibrateBtn"),
  resSearchBtn: document.getElementById("resSearchBtn"),
  resExplainBtn: document.getElementById("resExplainBtn"),
  resSearch: document.getElementById("resSearch"),
  resStatus: document.getElementById("resStatus"),
  resResults: document.getElementById("resResults"),
  resKpis: document.getElementById("resKpis"),
  resChart: document.getElementById("resChart"),
  resSuggestions: document.getElementById("resSuggestions"),
  resBreakdown: document.getElementById("resBreakdown"),
  resTradesBody: document.getElementById("resTradesBody"),
  resPlotTitle: document.getElementById("resPlotTitle"),
  auditBanner: document.getElementById("auditBanner"),
  auditTitle: document.getElementById("auditTitle"),
  auditPlan: document.getElementById("auditPlan"),
  auditExitBtn: document.getElementById("auditExit"),
  applyModal: document.getElementById("applyModal"),
  applyClose: document.getElementById("applyClose"),
  applyCancel: document.getElementById("applyCancel"),
  applyConfirm: document.getElementById("applyConfirm"),
  applyList: document.getElementById("applyList"),
  applyResult: document.getElementById("applyResult"),
  applyBackupNote: document.getElementById("applyBackupNote"),
};

const money = (value, currency = "$") => {
  if (value === null || value === undefined) return "--";
  return `${currency} ${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}`;
};

const num = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
};

const setConn = (ok, text) => {
  els.connDot.classList.toggle("online", ok);
  els.connText.textContent = text || (ok ? "en línea" : "offline");
};

function flash(el) {
  el.style.transition = "transform 0.3s ease";
  el.style.transform = "scale(1.06)";
  setTimeout(() => {
    el.style.transform = "scale(1)";
  }, 300);
}

async function loadAccount() {
  try {
    const res = await fetch("/api/account");
    if (!res.ok) throw new Error("bad status " + res.status);
    const a = await res.json();

    els.accountLabel.textContent = `Cuenta ${a.login} · ${a.name} · ${a.server} · ${a.currency}`;
    setConn(true, "en línea");

    els.kpiBalance.textContent = money(a.balance, a.currency);
    els.kpiBalanceSub.textContent = `Cuenta #${a.login}`;
    els.kpiEquity.textContent = money(a.equity, a.currency);
    els.kpiEquitySub.textContent = `${money(a.profit, a.currency)} flotante`;
    els.kpiProfit.textContent = money(a.profit, a.currency);
    els.kpiProfit.classList.toggle(
      "profit-pos",
      a.profit > 0
    );
    els.kpiProfit.classList.toggle(
      "profit-neg",
      a.profit < 0
    );
    els.kpiFreeMargin.textContent = money(a.margin_free, a.currency);
    els.kpiMarginLevel.textContent =
      a.margin_level && a.margin_level > 0
        ? `${num(a.margin_level, 0)} %`
        : "--";
    els.kpiMarginLevelSub.textContent = `Margen usado: ${money(a.margin, a.currency)}`;
    els.kpiPositionsSub.textContent = `Apalancamiento: 1:${a.leverage}`;

    flash(els.kpiBalance);
  } catch (err) {
    setConn(false, "sin conexión MT5");
    els.accountLabel.textContent = "No se pudo conectar con el servidor";
  }
}

function positionRow(p) {
  const row = document.createElement("tr");
  const profitCls = p.profit > 0 ? "profit-pos" : p.profit < 0 ? "profit-neg" : "";
  row.innerHTML = `
    <td class="symbol">${p.symbol}</td>
    <td><span class="tradetype ${p.type === "BUY" ? "buy" : "sell"}">${p.type}</span></td>
    <td>${num(p.volume)}</td>
    <td>${num(p.price_open, 5)}</td>
    <td>${p.sl && p.sl !== 0 ? num(p.sl, 5) : '<span class="muted">—</span>'}</td>
    <td>${p.tp && p.tp !== 0 ? num(p.tp, 5) : '<span class="muted">—</span>'}</td>
    <td>${num(p.price_current, 5)}</td>
    <td class="${profitCls}">${money(p.profit)}</td>
    <td><button type="button" class="btn-mini close-pos" data-ticket="${p.ticket}" title="Cerrar posición">Cerrar</button></td>
  `;
  return row;
}

async function loadPositions() {
  try {
    const res = await fetch("/api/positions");
    if (!res.ok) throw new Error("bad status " + res.status);
    const pos = await res.json();
    els.posTable.innerHTML = "";
    if (!pos.length) {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      tr.innerHTML = `<td colspan="9">No hay posiciones abiertas</td>`;
      els.posTable.appendChild(tr);
    } else {
      pos.forEach((p) => els.posTable.appendChild(positionRow(p)));
    }
    els.kpiPositions.textContent = pos.length;
    els.posUpdated.textContent = `Actualizado ${new Date().toLocaleTimeString("es-ES")}`;
  } catch (_) {
    els.posTable.innerHTML = `<tr class="empty-row"><td colspan="9">Error al cargar posiciones</td></tr>`;
  }
}

function historyRow(d) {
  const tr = document.createElement("tr");
  const profit = d.profit + d.commission + d.swap;
  const cls = profit > 0 ? "profit-pos" : profit < 0 ? "profit-neg" : "";
  const priceCell = (v) =>
    v === null || v === undefined || Number.isNaN(v) ? '<span class="muted">—</span>' : num(v, 5);
  tr.innerHTML = `
    <td>${d.time}</td>
    <td class="symbol">${d.symbol}</td>
    <td><span class="tradetype ${d.type === "BUY" ? "buy" : "sell"}">${d.type}</span></td>
    <td>${num(d.volume)}</td>
    <td>${priceCell(d.price_open)}</td>
    <td>${priceCell(d.price_close)}</td>
    <td>${money(d.commission)}</td>
    <td>${money(d.swap)}</td>
    <td class="${cls}">${money(profit)}</td>
  `;
  return tr;
}

async function loadHistory() {
  try {
    const res = await fetch("/api/history?days=7");
    if (!res.ok) throw new Error("bad status " + res.status);
    const hist = await res.json();
    els.histTable.innerHTML = "";
    if (!hist.length) {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      tr.innerHTML = `<td colspan="9">Sin operaciones en los últimos 7 días</td>`;
      els.histTable.appendChild(tr);
    } else {
      hist.forEach((d) => els.histTable.appendChild(historyRow(d)));
    }
    els.histUpdated.textContent = `${hist.length} operaciones · ${new Date().toLocaleTimeString("es-ES")}`;
  } catch (_) {
    els.histTable.innerHTML = `<tr class="empty-row"><td colspan="9">Error al cargar el historial</td></tr>`;
  }
}

/* ---- Explorador de tablas de la base local ---- */

const dbEls = {
  tabs: document.getElementById("dbTabs"),
  search: document.getElementById("dbSearch"),
  limit: document.getElementById("dbLimitSelect"),
  refresh: document.getElementById("dbRefreshBtn"),
  updated: document.getElementById("dbUpdated"),
  head: document.getElementById("dbTableHead"),
  body: document.getElementById("dbTableBody"),
};

const jsonModal = {
  overlay: document.getElementById("jsonModal"),
  title: document.getElementById("jsonModalTitle"),
  pretty: document.getElementById("jsonPretty"),
  copy: document.getElementById("jsonCopy"),
  close: document.getElementById("jsonClose"),
  value: null,
};

let DB_TABLES = [];
let DB_CURRENT = null;
let DB_FULL_ROWS = null;

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* ---- Visor JSON expandible (modal) ---- */

function openJsonModal(title, value) {
  if (value === undefined || value === null) return;
  jsonModal.value = value;
  jsonModal.title.textContent = title || "Valor JSON";
  jsonModal.pretty.textContent =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  jsonModal.pretty.className = "json-pretty" + (typeof value === "string" ? " json-plain" : "");
  jsonModal.overlay.hidden = false;
}

function closeJsonModal() {
  jsonModal.overlay.hidden = true;
  jsonModal.value = null;
}

jsonModal.close.addEventListener("click", closeJsonModal);
jsonModal.overlay.addEventListener("click", (e) => {
  if (e.target === jsonModal.overlay) closeJsonModal();
});
jsonModal.copy.addEventListener("click", () => {
  if (jsonModal.value === null) return;
  const text =
    typeof jsonModal.value === "string"
      ? jsonModal.value
      : JSON.stringify(jsonModal.value, null, 2);
  if (navigator.clipboard) {
    navigator.clipboard
      .writeText(text)
      .then(() => toast("JSON copiado"))
      .catch(() => {});
  }
});

/* ---- Renderizado de celdas ---- */

function dbValue(v, key) {
  if (v === null || v === undefined) return '<span class="muted">—</span>';
  if (typeof v === "object") {
    try {
      const label = `${esc(JSON.stringify(v))}`;
      const short = label.length > 60 ? label.slice(0, 60) + "…" : label;
      return `<button type="button" class="json-btn" data-json>${esc(short)} ⧉</button>`;
    } catch (_) {
      return "";
    }
  }
  if (typeof v === "number") {
    if (key && (key === "profit" || key === "pnl")) {
      const cls = v >= 0 ? "profit-pos" : "profit-neg";
      return `<span class="${cls}">${esc(v)}</span>`;
    }
    if (key === "score" || key === "setup_score") return scoreChip(v);
    return esc(v);
  }
  if (key === "macro_bias") return cotChip(v);
  if (key === "action" && (v === "BUY" || v === "SELL")) return actionChip(v);
  if (key === "status" && v === "active") return statusBadge(v);
  if (key === "cme_confirmation") return boolsConfirmed(v);
  if (key === "name" && v) return `<span class="tool-gear" data-gear>⚙️ ${esc(v)}</span>`;
  return esc(v);
}

function scoreChip(v) {
  const cls = v >= 70 ? "high" : v >= 40 ? "mid" : "low";
  return `<span class="score-chip ${cls}">${esc(v)}</span>`;
}

function cotChip(v) {
  if (v === null || v === undefined) return '<span class="cot-chip neutral">sin sesgo</span>';
  const s = String(v).toLowerCase();
  const cls = s.includes("bull") ? "bullish" : s.includes("bear") ? "bearish" : "neutral";
  return `<span class="cot-chip ${cls}">${esc(v)}</span>`;
}

function actionChip(v) {
  const cls = v === "BUY" ? "chip-buy" : "chip-sell";
  return `<span class="chip ${cls}">${esc(v)}</span>`;
}

function statusBadge(v) {
  return `<span class="status-badge">${esc(v)}</span>`;
}

function boolsConfirmed(v) {
  const s = String(v).toLowerCase();
  if (s === "1" || s === "yes" || s === "true" || s === "si") {
    return `<span class="chip chip-muted chip-confirmed">Confirmado</span>`;
  }
  const neg = s === "0" || s === "no" || s === "false";
  if (neg) return `<span class="chip chip-muted">Rechazado</span>`;
  return esc(v);
}

/* ---- Views inteligentes por tabla (config de columnas) ----
   Cada tabla con vista define reorden/ocultación y celdas;
   las tablas sin vista usan el fallback genérico completo. */

const TABLE_VIEWS = {
  trades: {
    title: "Operaciones + Bitácora",
    columns: [
      "ticket", "symbol", "action", "volume", "price_open", "price_close",
      "profit", "poi_type", "setup_score", "cme_confirmation", "time_close",
    ],
  },
  cot_reports: {
    title: "Reportes COT (CME)",
    columns: [
      "report_date", "macro_bias", "am_net", "lf_net", "nc_net",
      "cot_index_26w", "delta_am", "delta_lf",
    ],
  },
  messages: {
    title: "Mensajes del chat",
    columns: ["conversation_id", "role", "name", "content", "timestamp", "tool_call_id"],
  },
  agent_settings: {
    title: "Config del agente",
    columns: ["key", "value"],
  },
};

/* ---- Tabs superiores con badge de conteo ---- */

function renderDbTabs() {
  dbEls.tabs.innerHTML = "";
  for (const t of DB_TABLES) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "db-tab" + (t.name === DB_CURRENT ? " active" : "");
    btn.dataset.table = t.name;
    btn.innerHTML = `${esc(t.name)} <span class="db-tab-count">${t.rows}</span>`;
    btn.addEventListener("click", () => selectDbTable(t.name));
    dbEls.tabs.appendChild(btn);
  }
}

function selectDbTable(name) {
  DB_CURRENT = name;
  dbEls.search.value = "";
  renderDbTabs();
  loadDbTable();
}

function dbEmpty(colspan, text) {
  dbEls.head.innerHTML = "";
  dbEls.body.innerHTML = `<tr class="empty-row"><td colspan="${colspan || 1}">${text}</td></tr>`;
}

async function loadDbTables() {
  try {
    const res = await fetch("/api/db/tables");
    if (!res.ok) throw new Error("bad status " + res.status);
    DB_TABLES = await res.json();
    if (!DB_CURRENT && DB_TABLES.length) DB_CURRENT = DB_TABLES[0].name;
    renderDbTabs();
    if (DB_TABLES.length) loadDbTable();
    else dbEmpty(1, "No hay tablas");
  } catch (_) {
    dbEmpty(1, "No se pudieron cargar las tablas");
  }
}

async function loadDbTable() {
  if (!DB_CURRENT) return;
  const limit = parseInt(dbEls.limit.value, 10) || 100;
  try {
    const res = await fetch(`/api/db/tables/${encodeURIComponent(DB_CURRENT)}?limit=${limit}`);
    if (!res.ok) throw new Error("bad status " + res.status);
    const data = await res.json();
    if (!data.columns.length) {
      dbEmpty(1, "Tabla sin columnas");
      return;
    }
    DB_FULL_ROWS = { columns: data.columns, rows: data.rows };
    renderDbRows(data.columns, data.rows);
    dbEls.updated.textContent = `${data.rows.length} filas · ${new Date().toLocaleTimeString("es-ES")}`;
    dbEls.refresh.disabled = false;
  } catch (_) {
    dbEmpty(1, "Error al cargar la tabla");
  }
}

function renderDbRows(columns, rows) {
  const view = TABLE_VIEWS[DB_CURRENT];
  const colName2idx = new Map(columns.map((c, i) => [c, i]));
  const cols = view ? view.columns.filter((c) => colName2idx.has(c)) : columns;
  dbEls.head.innerHTML = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const f = dbEls.search.value.trim().toLowerCase();
  let filtered = rows;
  if (f) {
    filtered = rows.filter((row) =>
      row.some((v) => v !== null && v !== undefined && String(v).toLowerCase().includes(f))
    );
  }
  const renderRow = (row, idx) =>
    `<tr>${cols
      .map((c) => {
        const cidx = colName2idx.get(c);
        return `<td data-key="${esc(c)}" data-idx="${idx}" data-cidx="${cidx}">${dbValue(row[cidx], c)}</td>`;
      })
      .join("")}</tr>`;
  dbEls.body.innerHTML = filtered.length
    ? filtered.map((row, idx) => renderRow(row, idx)).join("")
    : `<tr class="empty-row"><td colspan="${cols.length}">${f ? "Sin resultados para el filtro" : "Sin registros"}</td></tr>`;
}

/* Delegación de eventos: clics en botones JSON y engranajes y filtro */
dbEls.body.addEventListener("click", (e) => {
  const jsonBtn = e.target.closest("[data-json]");
  if (jsonBtn) {
    const td = jsonBtn.closest("td");
    const idx = parseInt(td.dataset.idx, 10);
    const cidx = parseInt(td.dataset.cidx, 10);
    const row = DB_FULL_ROWS.rows[idx];
    if (row) openJsonModal(`${DB_FULL_ROWS.columns[cidx]}`, row[cidx]);
    return;
  }
  const gear = e.target.closest("[data-gear]");
  if (gear) {
    const td = gear.closest("td");
    const idx = parseInt(td.dataset.idx, 10);
    const row = DB_FULL_ROWS.rows[idx];
    if (row) {
      const nameIdx = DB_FULL_ROWS.columns.indexOf("name");
      const callIdx = DB_FULL_ROWS.columns.indexOf("tool_call_id");
      const contentIdx = DB_FULL_ROWS.columns.indexOf("content");
      const info = {
        name: nameIdx >= 0 ? row[nameIdx] : null,
        tool_call_id: callIdx >= 0 ? row[callIdx] : null,
        contenido: contentIdx >= 0 ? row[contentIdx] : null,
      };
      openJsonModal("Llamada a herramienta", info);
    }
    return;
  }
});

dbEls.limit.addEventListener("change", loadDbTable);
dbEls.refresh.addEventListener("click", loadDbTable);
dbEls.search.addEventListener("input", () => {
  if (DB_FULL_ROWS) renderDbRows(DB_FULL_ROWS.columns, DB_FULL_ROWS.rows);
});
loadDbTables();

async function refreshAll() {
  await Promise.all([loadAccount(), loadPositions(), loadHistory(), loadCotBadge(), loadRiskScore()]);
}

let chart = null; // instancia ECharts del gráfico principal
let lastCandles = []; // velas espejo { time, open, high, low, close, volume }
let vpData = null; // {profile, poc, vah, val, source}
let vpSortedRows = []; // profile ordenado por precio, para lookup de color
let vpVisible = false;
const chartState = { tf: "M15", symbol: "EURUSD", lastBid: null };
chartState.mode = "classic"; // classic | footprint | heatmap | vp | event
chartState.fpData = null; // footprint payload (sintético)
chartState.hmData = null; // heatmap payload (sintético)
chartState.hmMaxV = 1; // valor máximo de intensidad → escala de color del heatmap
chartState.hmPriceStep = 0; // paso de precio del ladder → alto de celda vertical
chartState.eventBars = null; // velas por evento (sintéticas)

// Fixtures de test (mode=test del backend) para footprint/heatmap: sirven datos
// de control SIN depender de MT5. Se activan con la URL `?mode=test` o con el
// botón del mensaje de error cuando Market Watch no tiene el símbolo.
let fixtureMode = new URLSearchParams(window.location.search).get("mode") === "test";

// Marca si el chart tiene la opción de un modo derivado (un solo grid). Cuando
// se vuelve a classic/vp hay que restaurar baseChartOption() o los ejes quedan
// desalineados (timestamps y volumen crudos sobre el eje de precio).
let chartOptionIsDerived = false;

const MODE_SOURCE = {
  classic: "fuente: MT5",
  footprint: "fuente: SINTÉTICO MT5",
  heatmap: "fuente: SINTÉTICO MT5",
  vp: "fuente: MT5",
  event: "fuente: SINTÉTICO MT5",
};

// Refresco debounced de los modos derivados cuando llega una vela nueva.
let derivedRefreshTimer = null;
let eventRefreshTimer = null;
function scheduleDerivedRefresh() {
  if (chartState.mode === "event") {
    scheduleEventRefresh();
    return;
  }
  if (derivedRefreshTimer) clearTimeout(derivedRefreshTimer);
  derivedRefreshTimer = setTimeout(() => {
    derivedRefreshTimer = null;
    if (chartState.mode === "footprint") loadFootprint();
    else if (chartState.mode === "heatmap") loadHeatmap();
  }, 4000);
}
function scheduleEventRefresh() {
  if (eventRefreshTimer) clearTimeout(eventRefreshTimer);
  eventRefreshTimer = setTimeout(() => {
    eventRefreshTimer = null;
    loadEventBars();
  }, 3000);
}
const chartIndexMap = new Map(); // time -> índice en lastCandles

const PATTERN_TFS = ["M1", "M5", "M15", "M30", "H1", "H4"];
let patternBusy = false;
let cvdOverlayOn = false;
let journalOverlay = []; // líneas de SL/TP del journal para el símbolo activo
let journalOverlayOn = false;

// Capas de chartismo activas por botón (toggle). Los botones mapean a los
// grupos que detecta chartism_engine.py (trend/triangle/flag/double/hns).
const CHARTISM_GROUPS = {
  trend: "Canal/Tendencia",
  triangle: "Triángulo",
  flag: "Bandera",
  double: "Doble techo/suelo",
  hns: "Cabeza y hombros",
};
const chartismLayers = new Set();

const CVD_AXIS_KEY = "cvd_overlay_axis";

const CHART_COLORS = {
  up: "#2ee6a8",
  down: "#ff5d6c",
  text: "#9aa3bf",
  grid: "rgba(255,255,255,0.05)",
  border: "rgba(255,255,255,0.08)",
  cvdTop: "#8a6cff",
  cvdBottom: "#ff5d6c",
};

function chartMsg(text, action) {
  if (!els.chartMsg) return;
  els.chartMsg.classList.toggle("hidden", !text);
  els.chartMsg.textContent = text || "";
  if (text && action && els.chartMsg.querySelector(".chart-msg-btn") === null) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chart-msg-btn";
    btn.textContent = action.label;
    btn.addEventListener("click", action.handler);
    els.chartMsg.appendChild(btn);
  }
}

// Activa los fixtures de test (mode=test) y recarga el modo derivado actual.
function enableFixtureMode() {
  fixtureMode = true;
  setChartMode(chartState.mode);
}

const pad2 = (x) => String(x).padStart(2, "0");

function chartTimeLabel(value) {
  if (value === null || value === undefined || value === "") return value ?? "";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  const d = new Date(n * 1000);
  if (chartState.tf === "D1") return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  if (chartState.tf === "W1") {
    return `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`;
  }
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

function chartNiceTime(t) {
  if (t === null || t === undefined) return "";
  const n = Number(t);
  if (!Number.isFinite(n)) return String(t);
  const d = new Date(n * 1000);
  if (Number.isNaN(d.getTime())) return String(t);
  return `${d.toISOString().slice(0, 10)} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;
}

function eventBarLabel(value, index) {
  // Event Bars (volbar/tickbar/renko): el eje X es de CATEGORÍA indexado por
  // barra de evento, no por reloj. La etiqueta muestra el número de orden de la
  // barra (distancia equidistante) en lugar de horas fijas (00:00, 05:00...).
  // El timestamp real queda disponible en el tooltip vía chartTooltip.
  if (chartState.mode !== "event") return chartTimeLabel(value);
  return String(index);
}

function chartTooltip(params) {
  const arr = Array.isArray(params) ? params : [params];
  const candle = arr.find((p) => p.seriesType === "candlestick");
  if (candle) {
    const barData =
      chartState.mode === "event" && chartState.eventBars && chartState.eventBars.length
        ? chartState.eventBars
        : lastCandles;
    const c = barData[candle.dataIndex];
    const datum = candle.data;
    const digits = datum[1] < 100 ? 5 : 2;
    const fmt = (v) => (v === undefined || v === null ? "—" : Number(v).toFixed(digits));
    const up = datum[1] >= datum[0];
    return [
      c ? `<div style="font-weight:600">${chartNiceTime(c.time)}</div>` : "",
      `Apertura: <b>${fmt(datum[0])}</b>`,
      `Máximo: <b>${fmt(datum[3])}</b>`,
      `Mínimo: <b>${fmt(datum[2])}</b>`,
      `Cierre: <b style="color:${up ? CHART_COLORS.up : CHART_COLORS.down}">${fmt(datum[1])}</b>`,
      c && c.volume != null ? `Volumen: <b>${Math.round(c.volume)}</b>` : "",
    ]
      .filter(Boolean)
      .join("<br>");
  }
  const cvd = arr.find((p) => p.seriesName === "CVD");
  if (cvd) {
    const v = cvd.data;
    return `CVD: <b>${v === null || v === undefined ? "—" : Number(v).toFixed(2)}</b>`;
  }
  return "";
}

function baseChartOption() {
  return {
    animation: false,
    backgroundColor: "transparent",
    textStyle: { color: CHART_COLORS.text, fontFamily: "'DM Sans', sans-serif", fontSize: 12 },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "cross",
        lineStyle: { color: "rgba(255,255,255,0.2)" },
        label: { backgroundColor: "#1d2333", color: "#e6e9f2" },
      },
      backgroundColor: "rgba(13,17,28,0.92)",
      borderColor: CHART_COLORS.border,
      textStyle: { color: "#e6e9f2", fontSize: 12 },
      formatter: chartTooltip,
    },
    grid: [
      { left: 64, right: 14, top: 6, height: "56%" },
      { left: 64, right: 14, top: "70%", height: "20%" },
      { left: 66, right: "84%", top: 6, height: "56%", show: false },
    ],
    xAxis: [
      {
        type: "category",
        gridIndex: 0,
        data: [],
        boundaryGap: true,
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART_COLORS.text, fontSize: 11, formatter: chartTimeLabel },
        splitLine: { show: false },
      },
      {
        type: "category",
        gridIndex: 1,
        data: [],
        boundaryGap: true,
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
      {
        type: "value",
        gridIndex: 2,
        show: false,
        min: 0,
      },
    ],
    yAxis: [
      {
        scale: true,
        gridIndex: 0,
        position: "right",
        splitLine: { lineStyle: { color: CHART_COLORS.grid } },
        axisLabel: {
          color: CHART_COLORS.text,
          fontSize: 11,
          formatter: (value) => Number(value).toFixed(5),
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        scale: true,
        gridIndex: 1,
        position: "right",
        axisLabel: { color: CHART_COLORS.text, fontSize: 10, formatter: (v) => Math.round(v) },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      {
        type: "category",
        gridIndex: 2,
        position: "left",
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        data: [],
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
      {
        type: "slider",
        xAxisIndex: [0, 1],
        height: 14,
        bottom: 0,
        borderColor: CHART_COLORS.border,
        backgroundColor: "rgba(255,255,255,0.02)",
        fillerColor: "rgba(138,108,255,0.12)",
        dataBackground: {
          lineStyle: { color: CHART_COLORS.text, opacity: 0.35 },
          areaStyle: { color: "rgba(255,255,255,0.05)" },
        },
        selectedDataBackground: {
          lineStyle: { color: CHART_COLORS.cvdTop },
          areaStyle: { color: "rgba(138,108,255,0.15)" },
        },
        handleStyle: { color: CHART_COLORS.cvdTop },
        textStyle: { color: CHART_COLORS.text, fontSize: 10 },
      },
      {
        type: "inside",
        yAxisIndex: [0, 1],
        start: 0,
        end: 100,
        zoomOnMouseWheel: false,
        moveOnMouseMove: false,
        moveOnMouseWheel: false,
      },
    ],
    series: [
      {
        id: "candles",
        name: "Precio",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: [],
        itemStyle: {
          color: CHART_COLORS.up,
          color0: CHART_COLORS.down,
          borderColor: CHART_COLORS.up,
          borderColor0: CHART_COLORS.down,
        },
        markArea: { silent: true, label: { show: false }, data: [] },
        markLine: { silent: true, symbol: "none", data: [] },
        markPoint: { silent: true, data: [] },
      },
      {
        id: "cvdPos",
        name: "CVD",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: [],
        showSymbol: false,
        connectNulls: true,
        silent: true,
        lineStyle: { width: 1.2, color: CHART_COLORS.cvdTop },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(138,108,255,0.30)" },
              { offset: 1, color: "rgba(138,108,255,0.02)" },
            ],
          },
        },
        emphasis: { disabled: true },
      },
      {
        id: "cvdNeg",
        name: "CVD negativo",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: [],
        showSymbol: false,
        connectNulls: true,
        silent: true,
        lineStyle: { width: 1.2, color: CHART_COLORS.cvdBottom },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(255,93,108,0.02)" },
              { offset: 1, color: "rgba(255,93,108,0.30)" },
            ],
          },
        },
        emphasis: { disabled: true },
      },
      {
        id: "vp",
        name: "Volume Profile",
        type: "bar",
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: [],
        barWidth: "100%",
        silent: true,
        itemStyle: {
          color: (p) => {
            const idx = p.data?.[1] ?? 0;
            const row = vpSortedRows[idx];
            const price = row?.price ?? 0;
            if (row && row.delta !== undefined && Math.abs(row.delta) > 0.0001) {
              return row.delta >= 0 ? "rgba(46,230,168,0.45)" : "rgba(255,93,108,0.45)";
            }
            return vpData && price >= vpData.val && price <= vpData.vah
              ? "rgba(138,108,255,0.65)"
              : "rgba(138,108,255,0.22)";
          },
          borderRadius: 2,
        },
        label: { show: false },
        emphasis: { disabled: true },
      },
    ],
  };
}

/* ============================================================
   Modos de gráfico (selector #chartMode)
   classic | footprint | heatmap | vp | event
   ============================================================ */

function buildDerivedBaseOption(dmode) {
  // Base para footprint / heatmap / event: un solo grid de precio a todo lo ancho.
  const customSeries =
    dmode === "footprint"
      ? {
          id: "footprint",
          name: "Footprint",
          type: "custom",
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: [],
          clip: true,
          z: 3,
          renderItem: footprintRenderItem,
        }
      : {
          id: "heatmap",
          name: "Liquidez",
          type: "custom",
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: [],
          clip: true,
          silent: true,
          z: 1,
          renderItem: heatmapRenderItem,
        };
  const opt = {
    animation: false,
    backgroundColor: "transparent",
    textStyle: { color: CHART_COLORS.text, fontFamily: "'DM Sans', sans-serif", fontSize: 12 },
    tooltip: {
      trigger: dmode === "footprint" ? "item" : "axis",
      axisPointer: {
        type: "cross",
        lineStyle: { color: "rgba(255,255,255,0.2)" },
        label: { backgroundColor: "#1d2333", color: "#e6e9f2" },
      },
      backgroundColor: "rgba(13,17,28,0.92)",
      borderColor: CHART_COLORS.border,
      textStyle: { color: "#e6e9f2", fontSize: 12 },
      formatter: dmode === "footprint" ? footprintTooltip : chartTooltip,
    },
    grid: [{ left: 64, right: 14, top: 6, height: "76%", containLabel: false }],
    xAxis: [
      {
        type: "category",
        gridIndex: 0,
        data: [],
        boundaryGap: true,
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisTick: { show: false },
        axisLabel: { color: CHART_COLORS.text, fontSize: 11, formatter: chartTimeLabel },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        type: "value",
        scale: true,
        gridIndex: 0,
        position: "right",
        splitLine: { lineStyle: { color: CHART_COLORS.grid } },
        axisLabel: {
          color: CHART_COLORS.text,
          fontSize: 11,
          formatter: (value) => Number(value).toFixed(5),
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start: 0, end: 100 },
      {
        type: "slider",
        xAxisIndex: 0,
        height: 14,
        bottom: 0,
        borderColor: CHART_COLORS.border,
        backgroundColor: "rgba(255,255,255,0.02)",
        fillerColor: "rgba(138,108,255,0.12)",
        dataBackground: {
          lineStyle: { color: CHART_COLORS.text, opacity: 0.35 },
          areaStyle: { color: "rgba(255,255,255,0.05)" },
        },
        selectedDataBackground: {
          lineStyle: { color: CHART_COLORS.cvdTop },
          areaStyle: { color: "rgba(138,108,255,0.15)" },
        },
        handleStyle: { color: CHART_COLORS.cvdTop },
        textStyle: { color: CHART_COLORS.text, fontSize: 10 },
      },
    ],
    series: [
      {
        id: "candles",
        name: "Precio",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: [],
        barWidth: dmode === "footprint" ? 5 : 7,
        z: dmode === "footprint" ? 4 : 3,
        itemStyle: {
          color: CHART_COLORS.up,
          color0: CHART_COLORS.down,
          borderColor: CHART_COLORS.up,
          borderColor0: CHART_COLORS.down,
          opacity: dmode === "heatmap" ? 0.9 : 0.85,
        },
        markArea: { silent: true, label: { show: false }, data: [] },
        markLine: { silent: true, symbol: "none", data: [] },
        markPoint: { silent: true, data: [] },
      },
      customSeries,
    ],
  };
  return opt;
}

function buildEventBarsOption() {
  const opt = buildDerivedBaseOption("event");
  opt.series.pop(); // quita la serie derivada; solo velas por evento
  opt.tooltip.trigger = "axis";
  opt.tooltip.formatter = chartTooltip;
  opt.xAxis[0].axisLabel.formatter = eventBarLabel;
  // Velas ancho relativo: ocupan todo el ancho del contenedor sin huecos
  // laterales, aunque la API devuelva pocas barras de eventos.
  opt.series[0].barWidth = "80%";
  return opt;
}

function footprintRenderItem(params, api) {
  const x = api.coord([api.value(0), api.value(1)])[0];
  const y = api.coord([api.value(0), api.value(1)])[1];
  if (x == null || y == null || !isFinite(x) || !isFinite(y)) {
    return { type: "group", children: [] };
  }
  const stall = chartState.fpData && chartState.fpData.step ? chartState.fpData.step : 0.0001;
  const w = Math.max(api.size([1, 0])[0], 1);
  const h = Math.max(api.size([0, stall])[1], 1);
  const delta = api.value(4);
  const bid = api.value(2);
  const ask = api.value(3);
  const maxAbs = chartState.fpMaxDelta || 1;
  const alpha = Math.min(Math.abs(delta) / maxAbs, 1) * 0.5 + 0.05;
  const up = delta >= 0;
  const fill = up ? `rgba(46,230,168,${alpha})` : `rgba(255,93,108,${alpha})`;
  const children = [
    {
      type: "rect",
      shape: { x, y, width: w, height: h, x2: 0, y2: 0, r: 0 },
      style: { fill, stroke: "rgba(255,255,255,0.04)", lineWidth: 1 },
    },
  ];
  // Matriz Bid × Ask: numérica cuando la celda es mínimamente ancha (zoomeado o
  // pocas columnas visibles); si no, quedan solo los rectángulos de delta.
  if (w >= 16 && h >= 8) {
    const fs = Math.max(7, Math.min(10, Math.floor(w / 4)));
    const bidTxt = String(Number(bid).toFixed(0));
    const askTxt = String(Number(ask).toFixed(0));
    const sideX = w * 0.24;
    children.push(
      {
        type: "text",
        style: {
          text: bidTxt,
          x: x + sideX,
          y: y + h * 0.5,
          textAlign: "center",
          textVerticalAlign: "middle",
          fill: delta >= 0 ? "#ffb3bf" : "#ffe0e4",
          font: `${fs}px 'DM Sans', sans-serif`,
        },
      },
      {
        type: "text",
        style: {
          text: askTxt,
          x: x + w - sideX,
          y: y + h * 0.5,
          textAlign: "center",
          textVerticalAlign: "middle",
          fill: delta >= 0 ? "#a9f5d8" : "#9be8c8",
          font: `${fs}px 'DM Sans', sans-serif`,
        },
      }
    );
  }
  return { type: "group", children };
}

// Heatmap / mapa de liquidez como serie CUSTOM renderItem. El heatmap nativo de
// ECharts no puede dimensionar celdas sobre un eje Y continuo (type:"value"),
// así que pintamos las franjas de liquidez a mano, igual que el footprint: cada
// celda [x (categoría), y (precio exacto del ladder), valor, lo, hi] → rect en
// [x, y] con ancho = banda del eje X y alto = bandas de precio reales lo/hi
// (puntos medios entre niveles adyacentes del ladder). La serie queda con
// z:1 (de fondo) y las velas con z:3 (delante).
const HM_STOPS = [
  { t: 0, r: 138, g: 108, b: 255, a: 0 },
  { t: 0.4, r: 138, g: 108, b: 255, a: 0.12 },
  { t: 0.7, r: 255, g: 200, b: 87, a: 0.3 },
  { t: 1, r: 255, g: 180, b: 40, a: 0.42 },
];

function heatmapColor(t) {
  const v = Math.min(Math.max(t, 0), 1);
  let i = 0;
  while (i < HM_STOPS.length - 2 && v > HM_STOPS[i + 1].t) i++;
  const s0 = HM_STOPS[i];
  const s1 = HM_STOPS[i + 1];
  const f = s1.t - s0.t ? (v - s0.t) / (s1.t - s0.t) : 0;
  const r = Math.round(s0.r + (s1.r - s0.r) * f);
  const g = Math.round(s0.g + (s1.g - s0.g) * f);
  const b = Math.round(s0.b + (s1.b - s0.b) * f);
  const a = s0.a + (s1.a - s0.a) * f;
  return `rgba(${r},${g},${b},${a.toFixed(3)})`;
}

function heatmapRenderItem(params, api) {
  const cx = api.value(0);
  const x = api.coord([cx, api.value(1)])[0];
  const lo = api.value(3);
  const hi = api.value(4);
  const step = chartState.hmPriceStep || 0;
  const yTop = api.coord([cx, hi != null ? hi : api.value(1) + step / 2])[1];
  const yBot = api.coord([cx, lo != null ? lo : api.value(1) - step / 2])[1];
  if (x == null || yTop == null || yBot == null || !isFinite(x) || !isFinite(yTop) || !isFinite(yBot)) {
    return { type: "group", children: [] };
  }
  const w = Math.max(api.size([1, 0])[0], 1);
  const h = Math.max(Math.abs(yBot - yTop), 1);
  const raw = api.value(2);
  const val = typeof raw === "number" && isFinite(raw) ? Math.max(raw, 0) : 0;
  const maxV = chartState.hmMaxV || 1;
  return {
    type: "rect",
    // api.coord devuelve el CENTRO de la banda en el eje de categoría
    // (boundaryGap:true): centramos el rect para que cada columna quede bajo la
    // vela. En vertical usamos los límites de precio reales de la fila
    // (puntos medios del ladder), así el mosaico no deja costuras.
    shape: { x: x - w / 2, y: Math.min(yTop, yBot), width: w, height: h, r: 0 },
    style: {
      fill: heatmapColor(val / maxV),
      stroke: "rgba(255,255,255,0.03)",
      lineWidth: 1,
    },
  };
}

function footprintTooltip(params) {
  const p = Array.isArray(params) ? params[0] : params;
  if (!p || !p.data) return "";
  const d = p.data;
  const t = d.time;
  const digits = Math.abs(d.price) >= 1 ? 5 : 6;
  const side = d.delta >= 0 ? "COMPRA" : "VENTA";
  return [
    `<div style="font-weight:600">${chartNiceTime(t)}</div>`,
    `Precio: <b>${Number(d.price).toFixed(digits)}</b>`,
    `Bid: ${Math.round(d.bid)} · Ask: ${Math.round(d.ask)}`,
    `Delta: <b style="color:${d.delta >= 0 ? CHART_COLORS.up : CHART_COLORS.down}">${d.delta >= 0 ? "+" : ""}${Number(d.delta).toFixed(2)}</b> (${side})`,
  ].join("<br>");
}

function applyFootprint(fp) {
  if (!fp || !Array.isArray(fp.bars)) return;
  chartState.fpData = fp;
  if (!chart) return;
  // El payload del servidor cubre SOLO la ventana [nueva] (últimas N velas tras
  // la llamada MT5); el eje X usa esos timestamps reales, no los de lastCandles
  // (que tiene hasta 1000 velas).
  // NOTA: ECharts v6 no concatena los timestamps NUMÉRICOS del eje category con
  // api.coord() (devuelve ~4e11 px => celdas fuera de viewport y con clip:true
  // el renderItem nunca se ejecuta). Usamos claves string para que las celdas
  // del footprint se dibujen en su banda equidistante.
  const cat = fp.bars.map((b) => String(b.time));
  const inCat = new Set(cat);
  const candles = lastCandles.filter((c) => inCat.has(String(c.time)));
  const cells = [];
  let maxAbs = 1;
  for (let bi = 0; bi < fp.bars.length; bi++) {
    const b = fp.bars[bi];
    const t = String(cat[bi]);
    for (const lv of b.levels) {
      const d = lv.delta;
      if (Math.abs(d) > maxAbs) maxAbs = Math.abs(d);
      cells.push({ value: [t, lv.price, lv.bid, lv.ask, d], time: b.time, price: lv.price, bid: lv.bid, ask: lv.ask, delta: d });
    }
  }
  chartState.fpMaxDelta = maxAbs;
  chart.setOption({
    xAxis: [{ data: cat }],
    series: [
      { id: "candles", data: candles.map(candleToOhlc) },
      { id: "footprint", data: cells },
    ],
  });
}

function applyHeatmap(hm) {
  if (!hm || !Array.isArray(hm.data)) return;
  chartState.hmData = hm;
  if (!chart) return;
  const cat0 = chartState.mode === "event" ? [] : lastCandles.map((c) => c.time);
  // El servidor manda [t, i, v] con t = ÍNDICE de vela e i = índice de nivel.
  // Traducimos ambos a valores reales: x = times[t] (timestamp), y = ladder[i].
  // El eje X del heatmap se mantiene de CATEGORÍA (claves string); el eje Y es
  // de VALOR con el precio exacto del ladder, y las velas se superponen encima.
  // Cada celda se emite como [x, y, v, lo, hi]: lo/hi son los límites de precio
  // reales (puntos medios entre niveles adyacentes del ladder) para que el
  // renderItem dimensione cada franja sin costuras, incluso si el paso varía.
  const times = (hm.times || cat0).map((t) => String(t));
  const ladder = hm.ladder && hm.ladder.length ? hm.ladder.map(Number) : [];
  const step = ladder.length > 1 ? ladder[1] - ladder[0] : 0;
  chartState.hmPriceStep = step;
  const cellLimits = (i, p) => [
    i > 0 ? (ladder[i - 1] + p) / 2 : p - step / 2,
    i < ladder.length - 1 ? (p + ladder[i + 1]) / 2 : p + step / 2,
  ];
  const cells = ladder.length && times.length
    ? hm.data
        .map((row) => {
          const li = Number(row[1]);
          const x = times[row[0]] !== undefined ? times[row[0]] : String(row[0]);
          const p = ladder[li] !== undefined ? ladder[li] : row[1];
          const [lo, hi] = ladder[li] !== undefined ? cellLimits(li, p) : [undefined, undefined];
          return [x, p, row[2], lo, hi];
        })
        .filter((row) => row[0] !== undefined && row[1] !== undefined)
    : hm.data.map((row) => [String(row[0]), row[1], row[2]]);
  const maxV = hm.data.reduce((m, row) => Math.max(m, Number(row[2]) || 0), 0) || 1;
  chartState.hmMaxV = maxV;
  // Aire en el eje Y: dos pasos del ladder arriba y abajo, para que las mechas
  // extremas no queden pegadas al borde del canvas (media franja ya la cubre el
  // pad mínimo que necesita la fila extrema para no quedar cortada).
  const yPad = step * 2;
  const inTimes = new Set(times);
  const candles = lastCandles.filter((c) => inTimes.has(String(c.time)));
  chart.setOption({
    yAxis: [
      {
        min: ladder.length ? ladder[0] - yPad : undefined,
        max: ladder.length ? ladder[ladder.length - 1] + yPad : undefined,
      },
    ],
    xAxis: [{ data: times }],
    series: [
      { id: "candles", z: 3, data: candles.map(candleToOhlc) },
      { id: "heatmap", z: 1, data: cells },
    ],
  });
}

async function loadFootprint(fit) {
  const symbol = chartState.symbol;
  const tf = chartState.tf;
  if (!symbol) return;
  try {
    const res = await fetch(
      `/api/analysis/footprint/${encodeURIComponent(symbol)}?timeframe=${tf}&bars=80&rows=12${fixtureMode ? "&mode=test" : ""}`
    );
    if (!res.ok) {
      // Un 404/500 silencioso dejaba el gráfico con velas estándar sin explicación.
      const err = await res.json().catch(() => null);
      const msg = err && err.error ? `Footprint: ${err.error}` : `Footprint: HTTP ${res.status}`;
      if (fixtureMode) chartMsg(msg);
      else chartMsg(msg, { label: "Usar fixture de test (sin MT5)", handler: enableFixtureMode });
      return;
    }
    chartMsg(null);
    applyFootprint(await res.json());
    if (fit) chart.setOption({ dataZoom: [{ start: 0, end: 100 }], animation: false });
  } catch (err) {
    chartMsg(`Footprint: ${err.message}`);
  }
}

async function loadHeatmap(fit) {
  const symbol = chartState.symbol;
  const tf = chartState.tf;
  if (!symbol) return;
  try {
    const res = await fetch(
      `/api/analysis/heatmap/${encodeURIComponent(symbol)}?timeframe=${tf}&bars=150&levels=64${fixtureMode ? "&mode=test" : ""}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      const msg = err && err.error ? `Heatmap: ${err.error}` : `Heatmap: HTTP ${res.status}`;
      if (fixtureMode) chartMsg(msg);
      else chartMsg(msg, { label: "Usar fixture de test (sin MT5)", handler: enableFixtureMode });
      return;
    }
    chartMsg(null);
    applyHeatmap(await res.json());
    if (fit) chart.setOption({ dataZoom: [{ start: 0, end: 100 }], animation: false });
  } catch (err) {
    chartMsg(`Heatmap: ${err.message}`);
  }
}

function applyEventBars(bars) {
  if (!bars || !Array.isArray(bars) || !bars.length) return;
  chartState.eventBars = bars;
  if (!chart) return;
  // Catálogo equidistante: el eje X es CATEGORÍA indexado por barra de evento.
  // Se usan los timestamps como data (para que tooltip/drawing mantengan coords
  // reales) pero la etiqueta se muestra como número de orden de la barra.
  const cat = bars.map((b) => b.time);
  const total = Math.max(cat.length, 1);
  const show = Math.min(320, total);
  const start = Math.max(0, 100 - (show / total) * 100);
  chart.setOption({
    xAxis: [{ data: cat, axisLabel: { formatter: eventBarLabel } }],
    series: [
      {
        id: "candles",
        markArea: { data: [] },
        markLine: { data: [] },
        markPoint: { data: [] },
        data: bars.map((b) => [b.open, b.close, b.low, b.high]),
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: 0, start, end: 100 },
      {
        type: "slider",
        xAxisIndex: 0,
        start,
        end: 100,
        height: 14,
        bottom: 0,
        borderColor: CHART_COLORS.border,
        backgroundColor: "rgba(255,255,255,0.02)",
        fillerColor: "rgba(138,108,255,0.12)",
        dataBackground: {
          lineStyle: { color: CHART_COLORS.text, opacity: 0.35 },
          areaStyle: { color: "rgba(255,255,255,0.05)" },
        },
        selectedDataBackground: {
          lineStyle: { color: CHART_COLORS.cvdTop },
          areaStyle: { color: "rgba(138,108,255,0.15)" },
        },
        handleStyle: { color: CHART_COLORS.cvdTop },
        textStyle: { color: CHART_COLORS.text, fontSize: 10 },
      },
    ],
  });
}

async function loadEventBars(fit) {
  const symbol = chartState.symbol;
  const tf = chartState.tf;
  if (!symbol) return;
  const mode = els.evMode ? els.evMode.value : "volbar";
  const param = els.evParam ? Math.max(1, parseInt(els.evParam.value, 10) || 500) : 500;
  try {
    const res = await fetch(
      `/api/analysis/eventbars/${encodeURIComponent(symbol)}?timeframe=${tf}&bars=1000&mode=${mode}&param=${param}`
    );
    if (!res.ok) return;
    const data = await res.json();
    if (!data || !Array.isArray(data.bars)) return;
    applyEventBars(data.bars);
    if (fit) chart.setOption({ dataZoom: [{ start: 0, end: 100 }], animation: false });
  } catch (_) {}
}

function setChartMode(mode) {
  if (!chartModeSupported(mode)) return;
  chartState.mode = mode;
  const btns = els.chartMode ? els.chartMode.querySelectorAll("button[data-mode]") : [];
  btns.forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  if (els.evControls) els.evControls.hidden = mode !== "event";
  updateTfGroupDisabled();
  const src = MODE_SOURCE[mode] || MODE_SOURCE.classic;
  if (els.sourceChip) {
    els.sourceChip.textContent = fixtureMode && (mode === "footprint" || mode === "heatmap")
      ? `${src} · TEST`
      : src;
    els.sourceChip.classList.toggle("synthetic", src.indexOf("SINTÉTICO") !== -1);
  }
  // Resetea overlays derivados antes de recargar.
  vpData = null;
  cvdOverlayOn = false;
  if (els.btnCvd) els.btnCvd.classList.remove("active");
  journalOverlayOn = false;
  lastPatternData = null;
  AGENT_OVERLAYS.markArea = [];
  AGENT_OVERLAYS.markPoint = [];
  SETUP_OVERLAY.markLine = [];
  SETUP_OVERLAY.markPoint = [];
  loadCandles(true);
}

function chartModeSupported(mode) {
  return ["classic", "footprint", "heatmap", "vp", "event"].includes(mode);
}

// En Event Bars el agrupamiento de la vela lo controla el parámetro de
// ticks/volumen (evParam), no el timeframe: los botones M1..W1 se desactivan
// para evitar el conflicto de temporalidad mientras el modo esté activo.
function updateTfGroupDisabled() {
  const disabled = chartState.mode === "event";
  const tfBtns = els.tfGroup ? els.tfGroup.querySelectorAll("button[data-tf]") : [];
  tfBtns.forEach((b) => (b.disabled = disabled));
}

function initChart() {
  if (chart || typeof echarts === "undefined") return;
  chart = echarts.init(els.chartEl);
  chart.setOption(baseChartOption());
  chartOptionIsDerived = false;
  window.DrawingTools?.attach(chart, {
    getSymbol: () => chartState.symbol,
    getTimeframe: () => chartState.tf,
    getBars: () => lastCandles,
  });
  if (vpData) applyVolumeProfile(vpData);
  window.addEventListener("resize", () => {
    if (chart) chart.resize();
    if (ofChart) ofChart.resize();
  });
}

// Orden de ECharts para velas: [Open, Close, Low, High] (valores numéricos)
const candleToOhlc = (c) => [
  parseFloat(c.open),
  parseFloat(c.close),
  parseFloat(c.low),
  parseFloat(c.high),
];

function chartSyncData() {
  if (!chart) return;
  const cat = lastCandles.map((c) => c.time);
  // En los modos derivados (footprint/heatmap) solo existe un grid: actualizar
  // el eje X de velas no puede referenciar un segundo eje que no existe.
  if (chartState.mode === "footprint" || chartState.mode === "heatmap") {
    chart.setOption({
      xAxis: [{ data: cat }],
      series: [{ id: "candles", data: lastCandles.map(candleToOhlc) }],
    });
    return;
  }
  // El eje X y la serie de velas se actualizan SIEMPRE juntos (mismo setOption):
  // si llega una vela con timestamp nuevo, crece xAxis.data; si es el mismo, se
  // actualiza la vela en su posición.
  chart.setOption({
    xAxis: [{ data: cat }, { data: cat }],
    series: [{ data: lastCandles.map(candleToOhlc) }],
  });
}

function applyLiveBar(bar) {
  if (auditActive) return; // el gráfico muestra un audit, no velas en vivo
  if (!chart || !bar || bar.time === undefined) return;
  if (chartState.mode === "footprint" || chartState.mode === "heatmap" || chartState.mode === "event") {
    // En los modos derivados las barras se reconstruyen desde el snapshot
    // sintético (refetch debounced). Solo se actualiza la cotización en vivo.
    scheduleDerivedRefresh();
    return;
  }
  const idx = chartIndexMap.get(bar.time);
  if (idx !== undefined && idx < lastCandles.length) {
    lastCandles[idx] = bar;
  } else {
    chartIndexMap.set(bar.time, lastCandles.length);
    lastCandles.push(bar);
  }
  chartSyncData();
  cvdSubRefresh();
  window.DrawingTools?.onBars?.(lastCandles);
  if (lastPatternData) redrawPatterns();
}

/* ---- Patrones SMC (FVG / Order Blocks / Liquidity Sweeps) ---- */

// Overlays dibujados por el agente (anotaciones y alertas), fusionados en cada
// setPatternZones para que sobrevivan a los refrescos periódicos del gráfico.
const AGENT_OVERLAYS = { markArea: [], markPoint: [] };
const AGENT_ALERTS = []; // {id, symbol, price, label, triggered, side, conditions, timeframe, expiresAt}
const SETUP_OVERLAY = { markLine: [], markPoint: [] }; // bandera Entry + SL/TP del calculador determinista
let lastPatternData = null;

function setPatternZones(data) {
  if (!chart) return;
  if (chartState.mode === "event") return; // las velas por evento usan su propio eje X
  lastPatternData = data;
  const patterns = data.patterns || {};
  const lastT = lastCandles.length ? lastCandles[lastCandles.length - 1].time : null;
  const labelTf = chartState.tf || "M15";

  const areaData = [];
  for (const f of patterns.fvgs || []) {
    if (f.mitigated) continue; // las zonas mitigadas se eliminan de pantalla
    const isBull = f.type === "BULLISH_FVG";
    areaData.push([
      {
        xAxis: f.start_time,
        yAxis: f.bottom,
        itemStyle: {
          color: isBull ? "rgba(38,166,154,0.22)" : "rgba(239,83,80,0.22)",
          borderColor: isBull ? "#26a69a" : "#ef5350",
          borderType: "dashed",
        },
        label: { show: true, color: isBull ? "#26a69a" : "#ef5350", fontSize: 10, position: "insideTop" },
        name: `${isBull ? "Bullish" : "Bearish"} FVG ${labelTf}`,
      },
      { xAxis: lastT, yAxis: f.top },
    ]);
  }
  for (const ob of patterns.order_blocks || []) {
    areaData.push([
      {
        xAxis: ob.start_time,
        yAxis: ob.bottom,
        itemStyle: { color: "rgba(41,98,255,0.30)", borderColor: "#2962ff", borderType: "solid" },
        label: { show: true, color: "#82b1ff", fontSize: 10, position: "insideTop" },
        name: `Order Block ${labelTf}`,
      },
      { xAxis: lastT, yAxis: ob.top },
    ]);
  }

  const lineData = [];
  if (data.pdh != null) {
    lineData.push({
      yAxis: data.pdh,
      lineStyle: { color: "rgba(255,93,108,0.7)", type: "dashed" },
      label: { show: true, formatter: "PDH", color: "rgba(255,93,108,0.9)", fontSize: 10, position: "insideEndTop" },
    });
  }
  if (data.pdl != null) {
    lineData.push({
      yAxis: data.pdl,
      lineStyle: { color: "rgba(46,230,168,0.7)", type: "dashed" },
      label: { show: true, formatter: "PDL", color: "rgba(46,230,168,0.9)", fontSize: 10, position: "insideEndBottom" },
    });
  }

  const pointData = [];
  const sweeps = patterns.sweeps || [];
  const cutoff = lastT != null ? lastT - 48 * 3600 : null; // solo últimas 48h
  const seen = {}; // 1 solo evento por nivel (barrido inicial)
  for (const s of sweeps) {
    if (cutoff != null && s.time < cutoff) continue;
    if (seen[s.type]) continue;
    seen[s.type] = true;
    const isPdh = s.type === "PDH_SWEEP";
    pointData.push({
      coord: [s.time, s.wick_extreme],
      value: isPdh ? "PDH" : "PDL",
      symbol: isPdh ? "arrowDown" : "arrowUp",
      symbolSize: 14,
      symbolOffset: isPdh ? [0, -6] : [0, 6],
      itemStyle: { color: isPdh ? "#ff5d6c" : "#2ee6a8", borderColor: "transparent" },
      label: { show: false },
    });
  }

  // Fusionar overlays del agente (anotaciones + alertas) con las marcas del motor
  for (const item of AGENT_OVERLAYS.markArea) areaData.push(item);
  for (const item of AGENT_OVERLAYS.markPoint) pointData.push(item);
  for (const al of AGENT_ALERTS) {
    if (al.symbol && al.symbol !== chartState.symbol) continue;
    if (al.expired) continue;
    const conds = al.conditions || [];
    const hasC = conds.length > 0;
    const ttlBadge = al.expiresAt ? (" TTL " + al.expiresAt.slice(11, 16)) : "";
    const condBadge = hasC ? (" [" + conds.map(c => c.type === "killzone" ? (c.name || "KZ") : c.type === "smc" ? "SMC" : c.type).join("+") + "]") : "";
    const labelTxt = (al.label || "ALERT " + al.symbol) + condBadge + ttlBadge;
    lineData.push({
      id: "alert_" + al.id,
      yAxis: al.price,
      lineStyle: {
        color: al.triggered ? "rgba(255,61,61,0.9)" : hasC ? "rgba(88,166,255,0.9)" : "rgba(255,179,0,0.9)",
        width: 2,
        type: "dashed",
      },
      label: {
        show: true,
        formatter: labelTxt,
        color: al.triggered ? "#ff3d3d" : hasC ? "#58a6ff" : "#ffb300",
        fontSize: 10,
        position: "insideEndTop",
      },
    });
  }

  // Líneas SL/TP del journal (proyección retroactiva de operaciones cerradas)
  if (journalOverlayOn) {
    for (const j of journalOverlay) {
      if (j.symbol && j.symbol !== chartState.symbol) continue;
      const isSl = j.line_type === "sl";
      lineData.push({
        id: "journal_" + j.id,
        yAxis: j.line_price,
        lineStyle: {
          color: isSl ? "rgba(255,93,108,0.8)" : "rgba(46,230,168,0.8)",
          width: 1,
          type: "dotted",
        },
        label: {
          show: true,
          formatter: isSl ? "SL " + j.result : "TP " + j.result,
          color: isSl ? "#ff5d6c" : "#2ee6a8",
          fontSize: 9,
          position: "insideEndTop",
        },
      });
    }
  }

  // Setup determinista (⚡ Calcular Setup): bandera de entrada + líneas SL/TP.
  for (const item of SETUP_OVERLAY.markLine) lineData.push(item);
  for (const item of SETUP_OVERLAY.markPoint) pointData.push(item);

  // Limpiar marcas previas antes de aplicar las nuevas: los merges de data
  // en ECharts son por índice y dejarían restos si la lista nueva es más corta.
  chart.setOption({
    series: [{ markArea: { data: [] }, markLine: { data: [] }, markPoint: { data: [] } }],
  });
  chart.setOption({
    series: [
      {
        id: "candles",
        markArea: { silent: true, data: areaData },
        markLine: { silent: true, symbol: "none", data: lineData },
        markPoint: { silent: true, data: pointData },
      },
    ],
  });
}

function applyChartActions(payload) {
  if (!chart || !payload) return;
  if (payload.symbol && payload.symbol !== chartState.symbol) {
    toast(`Análisis de ${payload.symbol} · no se dibuja en el gráfico ${chartState.symbol}. Asígnale ese símbolo para verlo.`, "err");
    return;
  }
  if (payload.timeframe && payload.timeframe !== chartState.tf) {
    toast(`Análisis en ${payload.timeframe} (el gráfico está en ${chartState.tf}). Las marcas se dibujan en sus coordenadas reales.`);
  }
  const e = payload.echarts || {};
  if (Array.isArray(e.markArea)) AGENT_OVERLAYS.markArea.push(...e.markArea);
  if (Array.isArray(e.markPoint)) AGENT_OVERLAYS.markPoint.push(...e.markPoint);
  if (Array.isArray(e.draw)) window.DrawingTools?.addAgentDrawings?.(e.draw);
  if (AGENT_OVERLAYS.markArea.length > 12) AGENT_OVERLAYS.markArea.splice(0, AGENT_OVERLAYS.markArea.length - 12);
  if (AGENT_OVERLAYS.markPoint.length > 12) AGENT_OVERLAYS.markPoint.splice(0, AGENT_OVERLAYS.markPoint.length - 12);
  redrawPatterns();
  if (payload.view) focusChartView(payload.view);
}

function focusChartView(view) {
  if (!chart || !view || view.start_time == null || view.end_time == null) return;
  const padT = Math.max(1800, (view.end_time - view.start_time) * 0.25);
  const t0 = view.start_time - padT;
  const t1 = view.end_time + padT;
  const pr = Math.max((view.price_max - view.price_min) * 0.15, 5e-4);
  const lo = view.price_min - pr;
  const hi = view.price_max + pr;
  try {
    const dz = chart.getOption().dataZoom || [];
    dz.forEach((c, i) => {
      if (c.xAxisIndex != null) {
        chart.dispatchAction({ type: "dataZoom", dataZoomIndex: i, startValue: t0, endValue: t1 });
      } else if (c.yAxisIndex != null) {
        chart.dispatchAction({ type: "dataZoom", dataZoomIndex: i, startValue: lo, endValue: hi });
      }
    });
  } catch (e) {}
}

function redrawPatterns() {
  if (!chart) return;
  setPatternZones(lastPatternData || { patterns: {}, pdh: null, pdl: null });
}

function clearSetupOverlay() {
  if (SETUP_OVERLAY.markLine.length || SETUP_OVERLAY.markPoint.length) {
    SETUP_OVERLAY.markLine = [];
    SETUP_OVERLAY.markPoint = [];
    redrawPatterns();
  }
}

async function calcularSetup() {
  if (!chart) {
    toast("El gráfico aún no está listo.", "err");
    return;
  }
  const symbol = chartState.symbol || "EURUSD";
  const tf = chartState.tf || "M15";
  const btn = els.btnSetupEval;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(
      `/api/chart/setup-eval?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast(`Setup no disponible: ${(err && err.error) || "estado " + res.status}`, "err");
      return;
    }
    pushSetupOverlay(await res.json());
  } catch (err) {
    toast(`Error evaluando setup: ${err.message}`, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function pushSetupOverlay(data) {
  if (!data) return;
  SETUP_OVERLAY.markLine = Array.isArray(data.echarts?.markLine) ? data.echarts.markLine : [];
  SETUP_OVERLAY.markPoint = Array.isArray(data.echarts?.markPoint) ? data.echarts.markPoint : [];
  const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(5));
  const dir = data.direction === "BUY" ? "BUY" : "SELL";
  const base = `Setup ${dir} · score ${Number(data.score).toFixed(1)}`;
  if (!data.approved) {
    const why = (data.reasons && data.reasons.length ? data.reasons.join(" · ") : "no alcanza el umbral");
    toast(`${base} → NO dibujado: ${why}`, "err");
  } else {
    toast(`${base} → Entry ${fmt(data.entry)} · SL ${fmt(data.sl)} · TP ${fmt(data.tp)}`, "ok");
  }
  redrawPatterns();
  if (data.view && data.view.start_time != null && data.view.end_time != null) {
    focusChartView(data.view);
  }
}

function applyVolumeProfile(data) {
  if (!data || !Array.isArray(data.profile)) return;
  vpData = data;
  vpSortedRows = data.profile.sort((a, b) => a.price - b.price);
  if (!chart) return;
  chart.setOption({
    yAxis: [{}, {}, { type: "category", data: vpSortedRows.map((r) => r.price) }],
    xAxis: [{}, {}, { min: 0 }],
    series: [
      { id: "vp", data: vpSortedRows.map((r, i) => [r.vol, i]) },
    ],
  });
  if (chartState.mode === "vp") {
    const line = (price, color, label) => ({
      yAxis: price,
      lineStyle: { color, type: "dashed", width: 1 },
      label: { show: true, formatter: label, color, position: "insideEndTop", fontSize: 10 },
      silent: true,
    });
    chart.setOption({
      series: [
        {
          id: "candles",
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              line(data.poc, "#ffe082", "PoC"),
              line(data.vah, "#82b1ff", "VAH"),
              line(data.val, "#82b1ff", "VAL"),
            ],
          },
        },
      ],
    });
    redrawPatterns(); // restaura markLines de patrones/agente encima de los niveles VP
    showVolumeProfile();
  }
}

function loadVolumeProfile() {
  if (!chartState.symbol) return;
  const bins = Math.max(30, Math.min(60, Math.round(((els.chartEl && els.chartEl.clientHeight) || 400) / 6)));
  const tf = chartState.mode === "vp" ? chartState.tf : "H1";

  fetch(`/api/volume-profile/${chartState.symbol}?timeframe=${tf}&bins=${bins}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data && Array.isArray(data.profile)) {
        applyVolumeProfile(data);
        if (vpVisible) showVolumeProfile();
      }
    })
    .catch(() => {});
}

function showVolumeProfile() {
  vpVisible = true;
  if (!chart) return;
  chart.setOption({
    grid: [{ left: 64 }, { left: 64 }, { left: 66, right: "84%", top: 6, height: "56%", show: true }],
    xAxis: [{}, {}, { show: false }],
    yAxis: [{}, {}, { show: false }],
    series: [{ id: "vp", show: true, z: 5 }],
  });
}

function toggleVolumeProfile() {
  vpVisible = !vpVisible;
  if (vpVisible) {
    if (!vpData) loadVolumeProfile();
    else if (chart) {
      applyVolumeProfile(vpData);
      showVolumeProfile();
    }
  } else if (chart) {
    chart.setOption({
      grid: [{ left: 64 }, { left: 64 }, { left: 66, right: "84%", top: 6, height: "56%", show: false }],
      series: [{ id: "vp", show: false }],
    });
  }
}

function loadJournalOverlay() {
  if (!chartState.symbol) return;
  fetch(`/api/journal/overlay?symbol=${chartState.symbol}&days=30`)
    .then((r) => (r.ok ? r.json() : []))
    .then((list) => {
      journalOverlay = Array.isArray(list) ? list : [];
      if (journalOverlayOn) redrawPatterns();
    })
    .catch(() => {});
}

function toggleJournalOverlay() {
  journalOverlayOn = !journalOverlayOn;
  if (journalOverlayOn) {
    if (!journalOverlay.length) loadJournalOverlay();
    else redrawPatterns();
  } else {
    redrawPatterns();
  }
}

function applyChartAlert(alert) {
  if (!alert) return;
  const isExpired = alert.status === "cancelled";
  const obj = {
    id: alert.id,
    symbol: alert.symbol,
    price: Number(alert.price),
    label: alert.label || "ALERT " + alert.symbol,
    triggered: alert.status === "triggered",
    expired: isExpired,
    side: alert.side,
    conditions: alert.conditions || [],
    timeframe: alert.timeframe,
    expiresAt: alert.expires_at,
  };
  const i = AGENT_ALERTS.findIndex((a) => a.id === alert.id);
  if (i >= 0) AGENT_ALERTS[i] = obj;
  else AGENT_ALERTS.push(obj);
  if (AGENT_ALERTS.length > 20) AGENT_ALERTS.splice(0, AGENT_ALERTS.length - 20);
  redrawPatterns();
}

function loadChartAlerts() {
  fetch("/api/chart/alerts")
    .then((r) => (r.ok ? r.json() : []))
    .then((list) => {
      if (!Array.isArray(list)) return;
      for (const a of list) applyChartAlert(a);
    })
    .catch(() => {});
}

function clearPatterns() {
  if (!chart) return;
  chart.setOption({
    series: [{ markArea: { data: [] }, markLine: { data: [] }, markPoint: { data: [] } }],
  });
}

async function refreshPatterns() {
  if (!chart || !chartState.symbol || patternBusy) return;
  if (chartState.mode === "event") return;
  const tf = chartState.tf;
  if (!PATTERN_TFS.includes(tf)) {
    clearPatterns();
    return;
  }
  patternBusy = true;
  try {
    const res = await fetch(
      `/api/analysis/patterns/${encodeURIComponent(chartState.symbol)}?timeframe=${tf}&bars=1000`
    );
    if (!res.ok) {
      clearPatterns();
      return;
    }
    const data = await res.json();
    setPatternZones(data);
  } catch (err) {
    console.error("[patrones] ERROR en refreshPatterns:", err);
    clearPatterns();
  } finally {
    patternBusy = false;
  }
}

/* ---- Chartismo clásico (capas toggle por botón) ---- */

function chartismBtn(kind) {
  return kind ? document.querySelector(`#drawTools [data-kind="${kind}"]`) : null;
}

function syncChartismButtons() {
  for (const k of Object.keys(CHARTISM_GROUPS)) {
    const b = chartismBtn(k);
    if (b) b.classList.toggle("active", chartismLayers.has(k));
  }
}

function resetChartismLayers() {
  chartismLayers.clear();
  syncChartismButtons();
}

async function toggleChartism(kind) {
  if (!chart || !CHARTISM_GROUPS[kind]) return;

  const btn = chartismBtn(kind);
  if (chartismLayers.has(kind)) {
    chartismLayers.delete(kind);
    window.DrawingTools?.removeByGroup?.(kind);
    if (btn) btn.classList.remove("active");
    return;
  }

  if (btn) {
    btn.classList.add("active");
    btn.disabled = true;
  }

  try {
    const res = await fetch(
      `/api/analysis/chartism/${encodeURIComponent(chartState.symbol)}` +
        `?timeframe=${chartState.tf}&bars=300&patterns=${kind}`
    );
    if (!res.ok) throw new Error("http " + res.status);
    const data = await res.json();
    // Regenera la capa (limpia dibujos previos del grupo antes de dibujar).
    window.DrawingTools?.removeByGroup?.(kind);
    const drawings = (data.drawings || []).map((d) => ({
      ...d,
      origin: "chartism",
      group: d.group || kind,
    }));
    window.DrawingTools?.addAgentDrawings?.(drawings, "chartism");
    chartismLayers.add(kind);
    const count = (data.summary || {})[kind] || 0;
    if (count) {
      toast(`Chartismo ${CHARTISM_GROUPS[kind]}: ${count} figura(s) dibujada(s).`, "ok");
    } else {
      toast(`Sin figuras de ${CHARTISM_GROUPS[kind].toLowerCase()} en ${chartState.tf}.`, "err");
      if (btn) btn.classList.remove("active");
    }
  } catch (err) {
    chartismLayers.delete(kind);
    if (btn) btn.classList.remove("active");
    toast("No se pudo dibujar chartismo", "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function clearChartism() {
  window.DrawingTools?.removeByOrigin?.("chartism");
  chartismLayers.clear();
  syncChartismButtons();
}

function quoteDigits(price) {
  return price < 100 ? 5 : 2;
}

function applyQuote(p) {
  if (!p || p.bid == null || p.ask == null) return;
  const digits = quoteDigits(p.bid);
  let dir = "flat";
  if (chartState.lastBid !== null) {
    dir = p.bid > chartState.lastBid ? "up" : p.bid < chartState.lastBid ? "down" : "flat";
  }
  chartState.lastBid = p.bid;
  els.chartQuote.textContent = `${p.bid.toFixed(digits)} / ${p.ask.toFixed(digits)}`;
  els.chartQuote.dataset.dir = dir;
  els.tradeBuyBtn.disabled = false;
  els.tradeSellBtn.disabled = false;
}

async function fetchQuote() {
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  if (!symbol) return;
  try {
    const res = await fetch(`/api/price/${symbol}`);
    if (!res.ok) return;
    applyQuote(await res.json());
  } catch (_) {}
}

async function loadCandles(fit = false) {
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  if (!symbol) return;
  chartState.symbol = symbol;

  chartMsg("Cargando datos...");

  try {
    const res = await fetch(`/api/candles/${symbol}?timeframe=${chartState.tf}&bars=1000`);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new Error(err ? err.error : "respuesta inválida");
    }
    const data = await res.json();
    if (!data || !data.length) throw new Error("sin velas disponibles");

    initChart();
    lastCandles = data;
    chartIndexMap.clear();
    chartState.fpData = null;
    chartState.hmData = null;
    chartState.hmMaxV = 1;
    chartState.hmPriceStep = 0;

    const mode = chartState.mode;

    if (mode === "footprint") {
      chart.setOption(buildDerivedBaseOption("footprint"), { notMerge: true });
      chartOptionIsDerived = true;
      chartSyncData();
      loadFootprint(fit);
      startStream();
      chartMsg(null);
      chartState.lastBid = null;
      fetchQuote();
      window.DrawingTools?.onBars?.(data);
      return;
    }
    if (mode === "heatmap") {
      chart.setOption(buildDerivedBaseOption("heatmap"), { notMerge: true });
      chartOptionIsDerived = true;
      chartSyncData();
      loadHeatmap(fit);
      startStream();
      chartMsg(null);
      chartState.lastBid = null;
      fetchQuote();
      window.DrawingTools?.onBars?.(data);
      return;
    }
    if (mode === "event") {
      chart.setOption(buildEventBarsOption(), { notMerge: true });
      chartOptionIsDerived = true;
      chartMsg(null);
      chartState.lastBid = null;
      fetchQuote();
      startStream();
      loadEventBars(fit);
      return;
    }

    // classic / vp
    if (chartOptionIsDerived) {
      // Restaura la opción base completa (3 grids, ejes pristine) tras salir de
      // un modo derivado; si no, los ejes quedan corruptos (timestamps y
      // volúmenes crudos sobre el eje de precio).
      chart.setOption(baseChartOption(), { notMerge: true });
      chartOptionIsDerived = false;
    }
    chartSyncData();
    refreshPatterns();
    if (fit) {
      chart.setOption({
        dataZoom: [{ start: 0, end: 100 }],
        animation: false,
      });
    }
    chartMsg(null);
    chartState.lastBid = null;
    fetchQuote();
    startStream();
    loadCvdData(data, chartState.tf);
    if (mode === "vp") loadVolumeProfile();
    window.DrawingTools?.onBars?.(data);
    window.DrawingTools?.reload?.();
    resetChartismLayers();
  } catch (err) {
    chartMsg(`No hay datos para ${symbol}: ${err.message}`);
  }
}

async function loadCvdData(candles, tf) {
  const symbol = chartState.symbol;
  if (!symbol) return;
  try {
    const res = await fetch(
      `/api/analysis/cvd/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(tf)}&bars=1000`
    );
    if (!res.ok) return;
    const points = await res.json();
    if (Array.isArray(points)) {
      ofCvdTotal.length = 0;
      points.forEach((p) => ofCvdTotal.push({ time: p.time, value: p.value }));
    }
  } catch (_) {}
  cvdSubRefresh(tf);
}

let stream = null;

function startStream() {
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  if (!symbol) return;
  chartState.symbol = symbol;
  lastPatternData = null;
  AGENT_OVERLAYS.markArea = [];
  AGENT_OVERLAYS.markPoint = [];
  SETUP_OVERLAY.markLine = [];
  SETUP_OVERLAY.markPoint = [];

  if (stream) {
    stream.close();
    stream = null;
  }

  if (typeof EventSource === "undefined") return;

  stream = new EventSource(`/api/stream/${symbol}?timeframe=${chartState.tf}`);
  stream.addEventListener("message", (e) => {
    let msg;
    try {
      msg = JSON.parse(e.data);
    } catch (_) {
      return;
    }
    if (msg.type === "error" || !chart || msg.symbol !== chartState.symbol) return;
    if (msg.candle) applyLiveBar(msg.candle);
    if (msg.quote) applyQuote(msg.quote);
  });
  stream.onerror = () => {};
}

async function updateChart() {
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  if (!chart || symbol !== chartState.symbol) return;
  try {
    const res = await fetch(`/api/candle/last/${symbol}?timeframe=${chartState.tf}`);
    if (!res.ok) return;
    const bar = await res.json();
    applyLiveBar(bar);
    fetchQuote();
  } catch (_) {}
}

els.tfGroup.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tf]");
  if (!btn || btn.disabled || chartState.mode === "event") return;
  els.tfGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  chartState.tf = btn.dataset.tf;
  loadCandles(true);
});

els.chartMode.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-mode]");
  if (!btn || btn.dataset.mode === chartState.mode) return;
  setChartMode(btn.dataset.mode);
});
els.evMode.addEventListener("change", () => {
  if (chartState.mode === "event") loadEventBars(true);
});
els.evParam.addEventListener("change", () => {
  if (chartState.mode === "event") loadEventBars(true);
});

els.btnChartAssistant.addEventListener("click", analizarGrafico);
els.btnSetupEval.addEventListener("click", calcularSetup);

els.chartSymbol.addEventListener("change", () => {
  vpData = null;
  loadCandles(true);
  loadVolumeProfile();
  loadJournalOverlay();
});
els.chartSymbol.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    vpData = null;
    loadCandles(true);
    loadVolumeProfile();
    loadJournalOverlay();
  }
});

async function toggleCvdOverlay() {
  if (!chart) {
    toast("El gráfico aún no está listo.", "err");
    return;
  }
  if (cvdOverlayOn) {
    cvdOverlayOn = false;
    els.btnCvd.classList.remove("active");
    setCvdSeries(false, null);
    return;
  }
  let points;
  try {
    const res = await fetch(`/api/analysis/cvd/${encodeURIComponent(chartState.symbol)}?timeframe=${chartState.tf}&bars=1000`);
    if (!res.ok) throw new Error("estado " + res.status);
    points = await res.json();
  } catch (err) {
    toast(`Overlay CVD no disponible: ${err.message}`, "err");
    return;
  }
  if (!Array.isArray(points) || !points.length) {
    toast("Sin datos CVD (¿MT5 cerrado o símbolo sin tick data?).", "err");
    return;
  }
  cvdOverlayOn = true;
  els.btnCvd.classList.add("active");
  setCvdSeries(true, points);
}

function setCvdSeries(enabled, points) {
  if (!chart) return;
  const opt = chart.getOption();
  opt.series = (opt.series || []).filter((s) => s.id !== "cvd_overlay");
  opt.yAxis = (opt.yAxis || []).filter((a) => a.key !== CVD_AXIS_KEY);
  if (enabled && points) {
    const data = [];
    for (const p of points) {
      const idx = chartIndexMap.get(p.time);
      if (idx !== undefined) data.push([idx, p.value]);
    }
    opt.series.push({
      id: "cvd_overlay",
      name: "CVD",
      type: "line",
      yAxisIndex: 3,
      smooth: true,
      symbol: "none",
      lineStyle: { width: 1.2, color: CHART_COLORS.cvdTop, opacity: 0.85 },
      itemStyle: { color: CHART_COLORS.cvdTop },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(138,108,255,0.18)" },
            { offset: 1, color: "rgba(138,108,255,0.01)" },
          ],
        },
      },
      data,
    });
    opt.yAxis.push({
      key: CVD_AXIS_KEY,
      gridIndex: 0,
      position: "left",
      scale: true,
      show: false,
      min: "dataMin",
      max: "dataMax",
      name: "CVD",
      nameTextStyle: { color: CHART_COLORS.text },
    });
  }
  chart.setOption(opt, { notMerge: false });
}

async function loadRiskScore() {
  const badge = els.scoreBadge;
  if (!badge) return;
  const symbol = (chartState.symbol || "EURUSD").toUpperCase();
  const tf = chartState.tf || "M15";
  let d;
  try {
    const res = await fetch(`/api/risk/setup?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}`);
    if (!res.ok) {
      badge.hidden = true;
      return;
    }
    d = await res.json();
  } catch (_) {
    badge.hidden = true;
    return;
  }
  const best = [d.bull, d.bear].sort((a, b) => b.score - a.score)[0];
  const side = best === d.bull ? "B" : "BE";
  const kz = d.killzone && d.killzone.in_killzone ? ` · KZ ${d.killzone.name}` : "";
  badge.textContent = `Score ${best.score.toFixed(1)} ${side} · ${best.verdict.replace("_", " ")}${kz}`;
  badge.className =
    "score-chip " +
    (best.score >= 80 ? "high" : best.score >= 60 ? "mid" : "low");
  const parts = [];
  for (const key of ["cot", "cvd_of", "smc", "killzone"]) {
    const comp = best.components[key];
    if (comp) parts.push(`${key}=${(comp.value * (comp.weight || 20)).toFixed(1)}pt`);
  }
  badge.title =
    `${symbol} ${tf} → ${best.verdict.replace("_", " ")} (${best.score.toFixed(1)}/100)\n` +
    `Breakdown: ${parts.join(" · ")}\n` +
    `Régimen: ${d.regime.regime}${kz}\n` +
    `Invalidez BUY ${d.invalidation.BUY ?? "-"} / SELL ${d.invalidation.SELL ?? "-"}\n` +
    `Precio: ${d.current_price} (${d.time})`;
  badge.hidden = false;
}

async function loadCotBadge() {
  const badge = els.cotBadge;
  if (!badge) return;
  if ((chartState.symbol || "EURUSD").toUpperCase() !== "EURUSD") {
    badge.hidden = true;
    return;
  }
  let rep;
  try {
    const res = await fetch("/api/cot/report");
    if (!res.ok) return;
    rep = await res.json();
  } catch (_) {
    return;
  }
  badge.textContent = `COT ${rep.macro_bias} · idx ${rep.cot_index_26w}% (${rep.report_date})`;
  badge.className =
    "cot-chip " +
    (rep.macro_bias === "BULLISH" ? "bullish" : rep.macro_bias === "BEARISH" ? "bearish" : "neutral");
  badge.hidden = false;
}

els.btnCvd.addEventListener("click", toggleCvdOverlay);
if (els.btnVp) els.btnVp.addEventListener("click", toggleVolumeProfile);
if (els.btnJournal) els.btnJournal.addEventListener("click", toggleJournalOverlay);

function addBubble(text, who, typing = false) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;

  if (typing) {
    div.classList.add("typing");
    div.innerHTML = "<span></span><span></span><span></span>";
  } else if (who === "bot") {
    div.innerHTML = renderMarkdown(text);
  } else {
    div.textContent = text;
  }

  els.chatMessages.appendChild(div);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return div;
}
function addWelcome() {
  addBubble(
    "Hola, soy tu agente de trading con IA. Respondo con datos reales de tu " +
      "MT5, el order flow del 6E y tu bitácora local. Haz clic en **🪄 Analizar Gráfico con IA** " +
      "para un diagnóstico en vivo del mercado.",
    "bot"
  );
}

/* ============================================================
   Agente IA: roles + conversaciones + streaming SSE
   ============================================================ */

const TOOL_LABELS = {
  account_info: "Cuenta (balance/equity/margen)",
  positions_list: "Posiciones abiertas",
  history: "Historial MT5",
  price: "Precio de símbolo",
  orderflow_snapshot: "Order flow 6E (foto)",
  orderflow_alerts: "Alertas order flow",
  trade_query: "Operaciones en BD local",
  journal_append: "Registrar bitácora",
  journal_list: "Consultar bitácora",
  mt5_export_read: "Leer export AI Chart Assistant",
  now: "Fecha/hora",
};

let ROLES = [];

async function loadRoles() {
  try {
    const res = await fetch("/api/agent/roles");
    if (!res.ok) throw new Error();
    ROLES = await res.json();
    return ROLES;
  } catch (err) {
    return [];
  }
}

function activeConvId() {
  return localStorage.getItem("trading_conv_id") || "";
}

async function ensureConversation() {
  if (activeConvId()) return activeConvId();
  const res = await fetch("/api/agent/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Nueva conversación", role_id: "general" }),
  });
  const conv = await res.json();
  localStorage.setItem("trading_conv_id", conv.id);
  return conv.id;
}

async function newConversation() {
  const res = await fetch("/api/agent/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Nueva conversación", role_id: "general" }),
  });
  const conv = await res.json();
  localStorage.setItem("trading_conv_id", conv.id);
  els.chatMessages.innerHTML = "";
  addBubble(`Nueva conversación creada. Rol activo: «Asistente Trading».`, "bot");
}

async function analizarGrafico() {
  const symbol = els.chartSymbol.value.trim().toUpperCase() || "EURUSD";
  const tf = chartState.tf || "M15";
  let snapshot;
  try {
    const res = await fetch(`/api/analysis/chart-assistant/${encodeURIComponent(symbol)}?timeframe=${tf}`);
    if (!res.ok) throw new Error("estado " + res.status);
    snapshot = await res.json();
  } catch (err) {
    addBubble(`No pude generar el snapshot de ${symbol} en vivo: ${err.message}.`, "bot");
    return;
  }

  let extra = "";
  if (snapshot.cvd && snapshot.cvd.length) {
    const cvd = snapshot.cvd;
    const lastP = cvd[cvd.length - 1];
    const firstP = cvd[0];
    extra += `\nCVD (${snapshot.cvd_source}): acumulado ${lastP.value} (Δ ${Number((lastP.value - firstP.value).toFixed(1))} en la ventana).`;
    if (snapshot.cvd_warning) extra += `\n⚠ Aviso: ${snapshot.cvd_warning}`;
  }
  if (snapshot.cot_macro_analysis) {
    const c = snapshot.cot_macro_analysis;
    extra += `\nCOT (CFTC, ${c.report_date}): Asset Managers ${c.asset_managers_net} (Δ${c.delta_asset_managers}), ` +
      `Leveraged Funds ${c.leveraged_funds_net} (Δ${c.delta_leveraged_funds}), Non-Commercial ${c.non_commercial_net}, ` +
      `índice COT 26s ${c.cot_index_26w}% → macro_bias ${c.macro_bias}.`;
  }
  if (snapshot.risk_engine) {
    const r = snapshot.risk_engine;
    const f = (s) => `${s.score.toFixed(1)} (${s.verdict.replace("_", " ")})`;
    extra += `\nRisk Engine (determinista): BUY ${f(r.bull)} · SELL ${f(r.bear)}` +
      ` · régimen ${r.regime.regime} · killzone ${r.killzone.in_killzone ? "dentro (" + r.killzone.name + ")" : "fuera"}` +
      ` · invalidez BUY ${r.invalidation.BUY ?? "-"} / SELL ${r.invalidation.SELL ?? "-"}.`;
  }

  const msg = [
    "Analiza el siguiente snapshot técnico del gráfico y dame el diagnóstico educativo:",
    `Símbolo: ${snapshot.symbol} (${snapshot.timeframe})`,
    `Precio actual: ${snapshot.current_price}`,
    `PDH: ${snapshot.PDH} | PDL: ${snapshot.PDL}`,
    `Distancia a PDL: ${snapshot.distance_to_PDL_pips} pips | a PDH: ${snapshot.distance_to_PDH_pips} pips`,
    "Análisis SMC: " + JSON.stringify(snapshot.analysis),
    snapshot.indicator_export ? "Exportación del indicador (resumen):\n" + snapshot.indicator_export : "Sin exportación del indicador disponible.",
    extra,
    "Termina SIEMPRE con una recomendación clara: [NO OPERAR], [ESPERAR PATRÓN] o [EVALUAR ENTRADA], explicando el porqué con lenguaje sencillo en español.",
  ].join("\n");

  let chartImage = null;
  if (chart && chart.getDataURL) {
    try {
      chartImage = chart.getDataURL({ type: "png", pixelRatio: 2 });
    } catch (err) {
      chartImage = null;
    }
  }
  sendChat(msg, { skipTools: true, chartImage });
}

function escapeHtml(s) {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(txt) {
  if (!txt) return "";
  let h = escapeHtml(txt);

  h = h.replace(/^\s*[-*_]{3,}\s*$/gm, "<hr>");

  h = h.replace(/^###\s+(.*)$/gm, "<h3>$1</h3>");
  h = h.replace(/^##\s+(.*)$/gm, "<h2>$1</h2>");
  h = h.replace(/^#\s+(.*)$/gm, "<h1>$1</h1>");

  h = h.replace(/^>\s?(.*)$/gm, "<blockquote>$1</blockquote>");

  h = h.replace(/^[ \t]*[-*]\s+(.+)$/gm, "<li>$1</li>");
  h = h.replace(/^[ \t]*\d+[.)]\s+(.+)$/gm, "<li>$1</li>");

  h = h.replace(/(<li>[\s\S]*?<\/li>)(\s*<li>)/g, "$1$2");
  h = h.replace(/(?:<li>[\s\S]*?<\/li>\s*)+/g, function (m) {
    return "<ul>" + m.replace(/^<li>/gm, "<li>") + "</ul>";
  });

  h = h.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/__([^_]+?)__/g, "<strong>$1</strong>");
  h = h.replace(/(^|[^*])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
  h = h.replace(/(^|[^_])_([^_\n]+?)_/g, "$1<em>$2</em>");
  h = h.replace(/`([^`\n]+?)`/g, "<code>$1</code>");

  h = h.replace(/\n{2,}/g, "</p><p>");
  h = h.replace(/\n/g, "<br>");

  return "<p>" + h + "</p>";
}

function bubbleWithMeta(text, who) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;

  const badge = document.createElement("span");
  badge.className = "status-badge";
  badge.style.display = "none";

  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = text;

  div.appendChild(badge);
  div.appendChild(content);
  els.chatMessages.appendChild(div);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return { div, badge, content };
}

async function sendChat(text, opts = {}) {
  const value = (text || els.chatText.value).trim();
  if (!value) return;
  const skipTools = opts && opts.skipTools;
  const showUser = !skipTools;

  els.chatText.value = "";
  if (showUser) addBubble(value, "user");

  const box = bubbleWithMeta("", "bot");
  els.chatSend.disabled = true;
  const convId = (await ensureConversation());

  try {
    const res = await fetch("/api/agent/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: value,
        role_id: "general",
        conversation_id: convId,
        skip_tools: skipTools,
        chart_image: (opts && opts.chartImage) || null,
      }),
    });
    if (!res.ok) throw new Error("bad status " + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";

    while (true) {
      const { done, value: chunk } = await reader.read();
      if (done) break;
      buffer += decoder.decode(chunk, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();

      for (const ev of events) {
        if (!ev.startsWith("data: ")) continue;
        let payload;
        try {
          payload = JSON.parse(ev.slice(6));
        } catch {
          continue;
        }

        if (payload.type === "status") {
          if (skipTools) continue;
          box.badge.classList.remove("err");
          box.badge.textContent = payload.content;
          box.badge.style.display = "inline-block";
        } else if (payload.type === "tool") {
          if (skipTools) continue;
          box.badge.classList.remove("err");
          box.badge.textContent = "⚙ " + payload.content;
          box.badge.style.display = "inline-block";
        } else if (payload.type === "delta") {
          box.badge.style.display = "none";
          box.content.textContent += payload.content;
          full += payload.content;
          els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
        } else if (payload.type === "error") {
          box.badge.textContent = payload.content;
          box.badge.classList.add("err");
          box.badge.style.display = "inline-block";
        } else if (payload.type === "chart_alert") {
          applyChartAlert(payload.content);
        } else if (payload.type === "chart_actions") {
          applyChartActions(payload.content);
        }
      }
    }
    if (full) box.content.innerHTML = renderMarkdown(full);
  } catch (err) {
    box.badge.textContent = "Error de conexión: " + err.message;
    box.badge.classList.add("err");
    box.badge.style.display = "inline-block";
  } finally {
    els.chatSend.disabled = false;
  }
}

els.chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendChat();
});

els.suggestions.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) sendChat(chip.dataset.q);
});

els.newConvBtn.addEventListener("click", newConversation);

document.getElementById("refreshBtn").addEventListener("click", refreshAll);

loadRoles().then(() => {
  addWelcome();
  setTimeout(() => els.chatText.focus(), 300);
});

refreshAll();
loadChartAlerts();
loadVolumeProfile();
loadJournalOverlay();
setInterval(refreshAll, REFRESH_MS);
setInterval(() => {
  if (!stream || stream.readyState === EventSource.CLOSED) updateChart();
}, 5000);

loadCandles(true);

/* ============================================================
   Order Flow (6E Databento)
   ============================================================ */
const OF_STATUS = { connected: false, reconnects: 0 };

const ofEls = {
  conn: document.getElementById("ofConn"),
  updated: document.getElementById("ofUpdated"),
  cvd: document.getElementById("ofCvd"),
  delta: document.getElementById("ofDelta"),
  vol: document.getElementById("ofVol"),
  buySell: document.getElementById("ofBuySell"),
  buySellSub: document.getElementById("ofBuySellSub"),
  spikes: document.getElementById("ofSpikes"),
  chart: document.getElementById("ofChart"),
  alerts: document.getElementById("ofAlerts"),
  zscore: document.getElementById("ofZscore"),
  zscoreOut: document.getElementById("ofZscoreOut"),
  absorbWin: document.getElementById("ofAbsorbWin"),
  feedToggle: document.getElementById("feedToggle"),
  feedToggleLabel: document.getElementById("feedToggleLabel"),
  ofSource: document.getElementById("ofSource"),
  ofFixture: document.getElementById("ofFixture"),
  ofControls: document.getElementById("ofControls"),
  ofSourceChip: document.getElementById("ofSourceChip"),
};

function ofLoadFixtures() {
  fetch("/api/orderflow/fixtures")
    .then((r) => r.json())
    .then((resp) => {
      const sel = ofEls.ofFixture;
      sel.innerHTML = '<option value="">— escenario —</option>';
      for (const s of resp.scenarios || []) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.dataset.kind = s.kind;
        const label = s.regime ? `● ${s.regime}` : `fixture: ${s.id.replace("fixture_", "")}`;
        opt.textContent = `${label}${s.kind === "fixture" ? " (.jsonl)" : ""}`;
        sel.appendChild(opt);
      }
      if (ofSourceSelected() === "mock") ofEls.ofFixture.hidden = false;
    })
    .catch(() => {});
}

function ofSourceSelected() {
  return ofEls.ofSource ? ofEls.ofSource.value : "live";
}

function ofFixtureSelected() {
  return ofSourceSelected() === "mock" ? ofEls.ofFixture.value : null;
}

function ofApplyFeed(status) {
  if (!status) return;
  const on = !!status.enabled;
  const connected = !!status.connected;
  const mock =
    status.enabled && ("source" in status || "mode" in status)
      ? status.mode === "mock" || status.source === "mock"
      : ofSourceSelected() === "mock";
  const mockAvail = status.mock_available !== undefined ? !!status.mock_available : true;
  ofEls.feedToggle.checked = on;
  const label = on ? (connected ? "Conectado" : "Conectando...") : "Apagado";
  ofEls.feedToggleLabel.textContent = label;
  ofEls.feedToggleLabel.classList.toggle("on", on && connected);
  ofEls.feedToggleLabel.classList.toggle("off", !on);

  if (ofEls.ofControls) ofEls.ofControls.hidden = !mockAvail;
  if (ofEls.ofSource) {
    if (!mockAvail) ofEls.ofSource.value = "live";
    else if (ofEls.ofSource.value !== (mock ? "mock" : "live")) {
      ofEls.ofSource.value = mock ? "mock" : "live";
      ofEls.ofFixture.hidden = !(mockAvail && mock);
    }
  }
  if (ofEls.ofFixture) ofEls.ofFixture.hidden = !(mockAvail && mock);

  if (ofEls.ofSourceChip) {
    const chip = ofEls.ofSourceChip;
    chip.textContent = mock ? "fuente: SINTÉTICO 6E (MOCK)" : "fuente: DATABENTO 6E";
    chip.classList.toggle("mock", mock);
    chip.classList.toggle("live", !mock);
  }

  if (on && connected) {
    ofSetConn("connected", mock ? "6E MOCK en línea" : "6E en línea");
  } else if (on) {
    ofSetConn("connecting", "conectando 6E...");
  } else {
    ofSetConn("disconnected", "apagado");
  }
}

let ofChart = null;
const ofCvdPoints = []; // [ [time, cvd], ... ] para el chart order flow
const ofIndexMap = new Map(); // time -> índice en ofCvdPoints
const ofState = { cvd: 0, lastTs: null, settings: null, socket: null };

/* ---- CVD sincronizado con el gráfico principal (grid 2) ---- */
const ofCvdTotal = []; // { time: epochSeconds, value: cvd }

function cvdKeyOf(t) {
  if (t === undefined || t === null) return undefined;
  const tf = chartState.tf;
  if (tf === "D1" || tf === "W1") {
    const d = new Date(t * 1000);
    d.setUTCHours(0, 0, 0, 0);
    return Math.floor(d.getTime() / 1000);
  }
  return Math.floor(t);
}

function cvdSyncData() {
  if (!chart) return;
  const lines = new Map(); // key -> último valor del día/vela
  for (const p of ofCvdTotal) {
    const k = cvdKeyOf(p.time);
    if (k !== undefined) lines.set(k, p.value);
  }
  const cat = lastCandles.map((c) => c.time);
  const pos = [];
  const neg = [];
  for (const c of lastCandles) {
    const v = lines.get(cvdKeyOf(c.time));
    const pv = v === null || v === undefined ? null : v;
    pos.push(pv !== null && pv >= 0 ? pv : null);
    neg.push(pv !== null && pv < 0 ? pv : null);
  }
  // El eje X del grid bandas y de CVD se actualizan juntos (mismo setOption).
  chart.setOption({
    xAxis: [{ data: cat }, { data: cat }],
    series: [{}, { data: pos }, { data: neg }],
  });
}

function cvdSubRefresh(tf) {
  cvdSyncData();
}

function cvdSubPush(t, value, tf) {
  if (t === undefined || value === undefined) return;
  ofCvdTotal.push({ time: t, value: value });
  if (ofCvdTotal.length > 3000) ofCvdTotal.splice(0, ofCvdTotal.length - 3000);
  cvdSyncData();
}

function ofInitChart() {
  if (ofChart || typeof echarts === "undefined") return;
  ofChart = echarts.init(ofEls.chart);
  ofChart.setOption({
    animation: false,
    backgroundColor: "transparent",
    textStyle: { color: CHART_COLORS.text, fontFamily: "'DM Sans', sans-serif", fontSize: 12 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", lineStyle: { color: "rgba(255,255,255,0.2)" } },
      backgroundColor: "rgba(13,17,28,0.92)",
      borderColor: CHART_COLORS.border,
      textStyle: { color: "#e6e9f2", fontSize: 12 },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params;
        if (!p || p.value == null) return "";
        return `${chartNiceTime(p.value[0])}<br>CVD: <b>${Number(p.value[1]).toFixed(2)}</b>`;
      },
    },
    grid: { left: 54, right: 14, top: 8, bottom: 24 },
    xAxis: {
      type: "category",
      data: [],
      boundaryGap: false,
      axisLine: { lineStyle: { color: CHART_COLORS.border } },
      axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.text, fontSize: 10, formatter: chartTimeLabel },
      splitLine: { show: false },
    },
    yAxis: {
      scale: true,
      axisLabel: { color: CHART_COLORS.text, fontSize: 10, formatter: (v) => Math.round(v) },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: CHART_COLORS.grid } },
    },
    series: [
      {
        name: "CVD",
        type: "line",
        data: [],
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 2, color: CHART_COLORS.cvdTop },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(138,108,255,0.25)" },
              { offset: 1, color: "rgba(138,108,255,0.02)" },
            ],
          },
        },
      },
    ],
  });
}

function ofClearChart() {
  ofCvdPoints.length = 0;
  ofIndexMap.clear();
  if (ofChart) {
    ofChart.setOption({ xAxis: { data: [] }, series: [{ data: [] }] });
  }
}

function ofLoadHistory() {
  fetch("/api/orderflow/cvd")
    .then((r) => (r.ok ? r.json() : []))
    .then((series) => {
      ofInitChart();
      if (!ofChart || !Array.isArray(series) || !series.length) return;
      ofClearChart();
      ofState.lastTs = null;
      for (const p of series) {
        if (p && p.time != null && p.value != null) {
          ofIndexMap.set(Math.floor(p.time), ofCvdPoints.length);
          ofCvdPoints.push([String(Math.floor(p.time)), p.value]);
        }
      }
      ofUpdateCvdTexture();
    })
    .catch(() => {});
}

function ofUpdateCvdTexture() {
  if (!ofChart) return;
  if (ofCvdPoints.length) {
    ofChart.setOption({
      xAxis: { data: ofCvdPoints.map((d) => d[0]) },
      series: [{ data: ofCvdPoints }],
    });
  }
}

function ofUpdateCvd(ts, cvd, delta) {
  // Eje X del chart: ts del payload (epoch secs). Si el servidor no lo manda,
  // se usa el reloj local para no dejar de pintar la curva en tiempo real.
  const t = ts != null ? Math.floor(ts) : Math.floor(Date.now() / 1000);
  if (ofChart && t != null) {
    const data = ofCvdPoints;
    const idx = ofIndexMap.get(t);
    if (idx !== undefined && idx < data.length) data[idx] = [String(t), cvd];
    else {
      ofIndexMap.set(t, data.length);
      data.push([String(t), cvd]);
    }
    if (data.length > 3000) {
      const removed = data.length - 3000;
      data.splice(0, removed);
      Array.from(ofIndexMap.keys()).forEach((k) => {
        const i = ofIndexMap.get(k);
        if (i < removed) ofIndexMap.delete(k);
        else ofIndexMap.set(k, i - removed);
      });
    }
    ofChart.setOption({
      xAxis: { data: data.map((d) => d[0]) },
      series: [{ data: data }],
    });
  }
  cvdSubPush(t, cvd, chartState.tf);
  ofState.lastTs = t;
}

function ofSetConn(state, text) {
  OF_STATUS.connected = state === "connected";
  const dot = ofEls.conn.querySelector(".dot");
  dot.classList.toggle("online", state === "connected");
  dot.classList.toggle("error", state === "error");
  dot.className = "dot" + (state === "connected" ? " online" : state === "error" ? " error" : "");
  ofEls.conn.querySelector("span:last-child").textContent =
    text || (state === "connected" ? "6E en línea" : state === "error" ? "error" : "conectando...");
}

function ofRenderKpis() {
  ofEls.cvd.textContent = num(ofState.cvd, 2);
  ofEls.cvd.classList.toggle("pos", ofState.cvd > 0);
  ofEls.cvd.classList.toggle("neg", ofState.cvd < 0);
  const last = ofState.lastTrade;
  if (last) {
    ofEls.delta.textContent = (last.delta > 0 ? "+" : "") + num(last.delta, 0);
    ofEls.delta.classList.toggle("pos", last.delta > 0);
    ofEls.delta.classList.toggle("neg", last.delta < 0);
    ofEls.vol.textContent = num(last.total_vol, 0);
    ofEls.buySell.textContent = `${num(last.buy_vol, 0)} / ${num(last.sell_vol, 0)}`;
    ofEls.buySellSub.textContent = last.buy_vol >= last.sell_vol ? "domina compra" : "domina venta";
    ofEls.spikes.textContent = num(last.spike_count ?? OF_STATUS.spikeCount ?? 0, 0);
    ofEls.updated.textContent = `Actualizado ${new Date().toLocaleTimeString("es-ES")}`;
  }
}

function ofAddAlert(item) {
  const div = document.createElement("div");
  div.className = "of-alert";
  const isAbsorb = !!item.absorption;
  const direction = item.absorption ? item.absorption.direction : item.side === "A" ? "buy" : "sell";
  const badge = document.createElement("span");
  badge.className = `badge ${isAbsorb ? "absorb" : "spike"}`;
  badge.textContent = isAbsorb ? "ABSORCIÓN" : "SPIKE";
  const info = document.createElement("span");
  info.className = "info";
  info.textContent = isAbsorb
    ? `${item.price.toFixed(5)} · ${item.size} contratos · ${item.absorption.volume.toFixed(0)} contratos en ${item.absorption.level.toFixed(5)} (${item.absorption.direction})`
    : `${item.price.toFixed(5)} · ${item.size} contratos · Z-score ${item.zscore.toFixed(1)} (${item.side === "A" ? "compra" : "venta"})`;
  const time = document.createElement("span");
  time.className = "time";
  time.textContent = new Date().toLocaleTimeString("es-ES");
  div.append(badge, info, time);
  ofEls.alerts.prepend(div);
  while (ofEls.alerts.children.length > 40) ofEls.alerts.lastChild.remove();
}

function ofLoadSnapshot(snapshot) {
  if (!snapshot) return;
  ofState.cvd = snapshot.cvd || 0;
  ofState.lastTrade = {
    delta: snapshot.delta || 0,
    total_vol: snapshot.total_vol || 0,
    buy_vol: snapshot.buy_vol || 0,
    sell_vol: snapshot.sell_vol || 0,
    spike_count: snapshot.spike_count || 0,
  };
  ofRenderKpis();
}

/* ---- Ajustes en tiempo real ---- */
function ofApplySettings(s) {
  if (!s) return;
  ofState.settings = s;
  if (s.zscore_threshold != null) {
    ofEls.zscore.value = s.zscore_threshold;
    ofEls.zscoreOut.textContent = String(s.zscore_threshold);
  }
  if (s.absorb_trades != null) {
    ofEls.absorbWin.value = s.absorb_trades;
  }
}

function ofSendSettings() {
  const socket = OF_STATUS.socket;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      action: "update_settings",
      zscore_threshold: parseFloat(ofEls.zscore.value),
      absorb_trades: parseInt(ofEls.absorbWin.value, 10),
    }));
  } else {
    fetch("/api/orderflow/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        zscore_threshold: parseFloat(ofEls.zscore.value),
        absorb_trades: parseInt(ofEls.absorbWin.value, 10),
      }),
    }).catch(() => {});
  }
}

function ofSendFeed(action) {
  const mode = ofSourceSelected();
  const fixture = ofFixtureSelected();
  const body =
    action === "feed_start"
      ? { action, mode, ...(mode === "mock" && fixture ? { fixture } : {}) }
      : { action };
  const socket = OF_STATUS.socket;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(body));
  } else {
    fetch("/api/orderflow/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => {});
  }
}

function ofHandleTrade(data) {
  ofInitChart();
  ofState.cvd = data.cvd;
  ofState.lastTrade = data;
  OF_STATUS.spikeCount = data.spike_count;
  ofRenderKpis();
  ofUpdateCvd(data.ts ? Math.floor(data.ts) : undefined, data.cvd, data.delta);
  if (data.is_spike || data.absorption) ofAddAlert(data);
}

function ofConnect() {
  if (typeof WebSocket === "undefined") return;
  ofSetConn("connecting");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/orderflow`);
  OF_STATUS.socket = ws;

  ws.onopen = () => {
    OF_STATUS.reconnects = 0;
    ofSetConn("connected");
  };

  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (_) {
      return;
    }
    if (data.type === "ping") return;

    if (data.event === "status") {
      if (data.feed) ofApplyFeed(data.feed);
      else ofSetConn(data.state, data.state === "connected" ? "6E en línea" : data.state);
      if (data.settings) ofApplySettings(data.settings);
      if (data.snapshot) ofLoadSnapshot(data.snapshot);
      return;
    }

    if (data.event === "feed") {
      ofApplyFeed(data.status);
      return;
    }

    if (data.event === "config") {
      ofApplySettings(data.settings);
      return;
    }

    if (data.event === "chart_alert" && data.type === "triggered") {
      const a = data.alert || {};
      applyChartAlert(a);
      const conds = data.conditions_met || [];
      const condsTxt = conds.length ? " (" + conds.join(", ") + ")" : "";
      addBubble(`Alerta alcanzada ${a.symbol || ""}: ${a.price}${a.label ? " «" + a.label + "»" : ""}${condsTxt}`, "bot");
      return;
    }

    if (data.event === "chart_alert" && data.type === "expired") {
      const a = data.alert || {};
      applyChartAlert(a);
      addBubble(`Alerta expirada ${a.symbol || ""}: ${a.price}${a.label ? " «" + a.label + "»" : ""}`, "bot");
      return;
    }

    if (data.event === "strategy_setup") {
      applyWatcherEvent(data);
      return;
    }

    if (data.event === "trade") {
      ofHandleTrade(data);
      return;
    }

    if (data.event === "batch") {
      for (const t of data.trades || []) ofHandleTrade(t);
    }
  };

  ws.onclose = () => {
    ofSetConn("disconnected", "desconectado");
    OF_STATUS.socket = null;
    OF_STATUS.reconnects++;
    const delay = Math.min(1000 * Math.pow(1.5, OF_STATUS.reconnects), 15000);
    setTimeout(ofConnect, delay);
  };

  ws.onerror = () => ws.close();
}

ofConnect();

/* ---- Controles de ajustes ---- */
ofEls.zscore.addEventListener("input", () => {
  ofEls.zscoreOut.textContent = String(parseFloat(ofEls.zscore.value).toFixed(1));
});
ofEls.zscore.addEventListener("change", ofSendSettings);
ofEls.absorbWin.addEventListener("change", ofSendSettings);

/* ---- Interruptor de feed Databento ---- */
ofEls.feedToggle.addEventListener("change", () => {
  const action = ofEls.feedToggle.checked ? "feed_start" : "feed_stop";
  ofApplyFeed({ enabled: ofEls.feedToggle.checked, connected: false });
  if (action === "feed_start") {
    const mock = ofSourceSelected() === "mock";
    ofSetConn("connecting", mock ? "conectando MOCK 6E..." : "conectando 6E...");
    ofEls.feedToggleLabel.textContent = "Conectando...";
    ofClearChart();
  } else {
    ofEls.feedToggleLabel.textContent = "Apagado";
    ofEls.feedToggleLabel.classList.remove("on");
    ofEls.feedToggleLabel.classList.add("off");
    ofLoadHistory();
  }
  ofSendFeed(action);
});

if (ofEls.ofSource) {
  ofEls.ofSource.addEventListener("change", () => {
    const mock = ofSourceSelected() === "mock";
    ofEls.ofFixture.hidden = !mock;
    if (mock) {
      ofEls.ofSourceChip.textContent = "fuente: SINTÉTICO 6E (MOCK)";
      ofEls.ofSourceChip.classList.toggle("live", false);
      ofEls.ofSourceChip.classList.toggle("mock", true);
      ofLoadHistory();
    } else {
      ofEls.ofFixture.value = "";
      ofEls.ofSourceChip.textContent = "fuente: DATABENTO 6E";
      ofEls.ofSourceChip.classList.toggle("live", true);
      ofEls.ofSourceChip.classList.toggle("mock", false);
    }
  });
}

ofLoadFixtures();

/* Inicializar el interruptor con el estado del servidor */
fetch("/api/orderflow/feed")
  .then((r) => r.json())
  .then((status) => ofApplyFeed(status))
  .catch(() => {});

ofLoadHistory();

/* ============================================================
   Trading desde el dashboard (espejo de los EAs MQL5)
   ============================================================ */
let TRADE_CFG = null;
let STRATEGY_SUMMARY = null;
let TRADE_PREVIEW = null;
let TRADE_PENDING_ACTION = null;
let CLOSE_TICKET = null;

let toastTimer = null;
function toast(text, kind = "ok") {
  els.toast.textContent = text;
  els.toast.className = `toast ${kind}`;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.hidden = true;
  }, 4000);
}

async function loadRiskState() {
  try {
    const res = await fetch("/api/trade/config");
    if (!res.ok) return;
    const d = await res.json();
    TRADE_CFG = d.config || null;
    STRATEGY_SUMMARY = d.strategy || null;
    const risk = d.risk || {};
    const chip = els.riskChip;
    if (risk.error) {
      chip.textContent = "MT5 off";
      chip.classList.remove("blocked");
      chip.title = risk.error;
      return;
    }
    chip.classList.toggle("blocked", !!risk.blocked);
    if (risk.blocked) {
      chip.textContent = "BLOQUEADO";
      chip.title = "Operar bloqueado: " + (risk.reasons || []).join("; ");
    } else {
      const dd = money(risk.dd_daily || 0);
      const trades = `${risk.trades_today ?? 0}/${risk.max_trades_day ?? "∞"}`;
      chip.textContent = `${dd} · ${trades}`;
      chip.title =
        `Pérdida diaria ${money(risk.dd_daily || 0)} (${(risk.dd_pct || 0).toFixed(2)}%) · ` +
        `${risk.trades_today}/${risk.max_trades_day} operaciones de hoy · ` +
        `tope ${money(risk.max_loss_fixed || 0)} / ${risk.max_loss_pct}%`;
    }
  } catch (_) {}
}

async function openTradeModal(action) {
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  if (!symbol) return;
  TRADE_PENDING_ACTION = action;
  els.tradeConfirm.disabled = true;
  els.tradeConfirm.textContent = "Cargando…";
  els.tradeModal.hidden = false;
  els.tradeModalTitle.textContent = action === "BUY" ? "Confirmar COMPRA (BUY)" : "Confirmar VENTA (SELL)";
  els.tmAction.textContent = action;
  els.tmAction.className = `tradetype ${action === "BUY" ? "buy" : "sell"}`;
  els.tmNote.textContent = "";
  try {
    const res = await fetch(`/api/trade/info/${encodeURIComponent(symbol)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new Error(err && err.error ? err.error : "No se pudo cargar la información del símbolo");
    }
    TRADE_PREVIEW = await res.json();
    const sp = TRADE_PREVIEW;
    const sug = sp.suggest && sp.suggest[action];
    els.tmSymbol.textContent = sp.symbol;
    const entry = action === "BUY" ? sp.ask : sp.bid;
    els.tmEntry.textContent = entry ? entry.toFixed(sp.digits) : "--";
    els.tmVolume.value = sug && sug.lot ? sug.lot : "";
    els.tmVolume.min = sp.volume_min || 0.01;
    els.tmVolume.step = sp.volume_step || 0.01;
    const slDef = sp.config.sl_default_pips != null ? sp.config.sl_default_pips : 15;
    els.tmSl.value = slDef;
    els.tmTp.value = (parseFloat(slDef) || 0) * sp.config.tp_ratio_r;
    if (sug) {
      els.tmRisk.textContent = money(sug.risk_budget || 0);
      els.tmMargin.textContent = money(sug.margin || 0);
    } else {
      els.tmRisk.textContent = "--";
      els.tmMargin.textContent = "--";
    }
    els.tmMeta.textContent = `${sp.config.magic} · ${sp.config.comment} · riesgo ${sp.config.risk_pct}%`;
    els.tmFill.textContent =
      (sp.filling_labels || []).join(" → ") +
      ((sp.filling_modes || []).length > 1 ? "  (fallback automático)" : "");
    els.tmType.textContent = "MERCADO · ejecución inmediata";
    els.tmNote.textContent =
      "La posición se abrirá con el Magic del EA, que la gestionará (break-even / trailing / DD).";
  } catch (err) {
    els.tmNote.textContent = "Error: " + err.message;
    els.tmRisk.textContent = "--";
    els.tmMargin.textContent = "--";
  } finally {
    els.tradeConfirm.disabled = false;
    els.tradeConfirm.textContent = "Confirmar";
  }
}

async function confirmTrade() {
  if (els.tradeConfirm.disabled) return;
  const symbol = els.chartSymbol.value.trim().toUpperCase();
  const action = TRADE_PENDING_ACTION;
  if (!symbol || !action) return;

  // Previene doble envío por latencia: deshabilitar el botón ANTES del fetch.
  els.tradeConfirm.disabled = true;
  els.tradeConfirm.textContent = "Enviando…";
  try {
    const slPips = parseFloat(els.tmSl.value) || 0;
    const tpPips = parseFloat(els.tmTp.value) || 0;
    const body = {
      symbol,
      action,
      volume: parseFloat(els.tmVolume.value) || null,
      sl_pips: slPips > 0 ? slPips : null,
      tp_pips: tpPips > 0 ? tpPips : null,
    };
    const res = await fetch("/api/trade/market", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Error al enviar la orden");
    toast(
      `Orden ${data.action} ${data.symbol} x${data.volume} a ${Number(data.price).toFixed(5)}` +
        ` enviada · ${data.filling}`,
      "ok"
    );
    els.tradeModal.hidden = true;
    TRADE_PENDING_ACTION = null;
    loadRiskState();
    refreshAll();
    if (data.poi && (data.poi.poi_type || data.poi.liquidity_swept)) {
      try {
        await fetch("/api/journal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticket: String(data.ticket),
            symbol: data.symbol,
            action: data.action,
            poi_type: data.poi.poi_type,
            liquidity_swept: data.poi.liquidity_swept,
            notes: `Entrada automática: ${data.action} ${data.symbol} x${data.volume} a ${Number(data.price).toFixed(5)} (${data.filling}).`,
          }),
        });
      } catch (_) {}
    }
  } catch (err) {
    toast(err.message, "err");
  } finally {
    els.tradeConfirm.disabled = false;
    els.tradeConfirm.textContent = "Confirmar";
  }
}

function renderStrategyRules() {
  const el = document.getElementById("strategyRules");
  if (!el) return;
  const s = STRATEGY_SUMMARY;
  if (!s) {
    el.innerHTML = '<span class="muted">Sin reglas cargadas.</span>';
    return;
  }
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));
  const rows = [];

  rows.push(
    `<li><b>Riesgo por operación:</b> ${esc(s.risk_pct)}% · <b>máx trades/día:</b> ${esc(s.max_trades_day)} · ` +
    `<b>tope pérdida:</b> $${esc(s.loss_limit_fixed)} / ${esc(s.loss_limit_pct)}%`
  );
  rows.push(
    `<li><b>Setup Score:</b> mínimo ${esc(s.min_score)} · <b>R:R mín:</b> ${esc(s.min_rr)} · ` +
    `<b>TTL:</b> ${esc(s.setup_ttl_minutes)} min</li>`
  );

  const kz = (s.killzones || []).map(
    (w) => `${esc(w.name)} (${esc(w.start)}–${esc(w.end)})`
  ).join(", ");
  rows.push(
    `<li><b>Killzones:</b> ${kz ? esc(kz) : "ninguna definida"}</li>`
  );

  const ds = s.data_sources || {};
  const dsNames = {
    cot: "COT/CFTC", cvd_of: "CVD", smc: "SMC (FVG/OB/Sweep)",
    killzone: "Killzone", news: "Noticias", orderflow: "Order Flow",
  };
  const active = Object.entries(ds).filter(([, v]) => v).map(([k]) => dsNames[k] || k);
  const inactive = Object.entries(ds).filter(([, v]) => !v).map(([k]) => dsNames[k] || k);
  rows.push(
    `<li><b>Fuentes activas:</b> ${active.length ? esc(active.join(", ")) : "ninguna"} · ` +
    `<span class="muted">inactivas: ${inactive.length ? esc(inactive.join(", ")) : "ninguna"}</span></li>`
  );

  const w = s.risk_weights || {};
  const wt = Object.entries(w)
    .map(([k, v]) => `${k}: ${esc(v)}`)
    .join(" · ");
  rows.push(`<li><b>Pesos del score:</b> ${wt ? esc(wt) : "—"}</li>`);

  if (s.prop_enabled) {
    rows.push(
      `<li><b>Prop firm:</b> activo · DD diario ${esc(s.prop_max_dd_daily_pct)}% / ` +
      `total ${esc(s.prop_max_dd_total_pct)}% · tope ganancia día ${esc(s.prop_max_profit_day_pct)}%` +
      (s.prop_consistency_days ? ` · consistencia ${esc(s.prop_consistency_days)}d` : "") +
      `</li>`
    );
  } else {
    rows.push("<li><b>Prop firm:</b> desactivado</li>");
  }

  if (s.data_sources && s.data_sources.news) {
    rows.push(
      `<li><b>Gate de noticias:</b> bloquea ±${esc(s.news_buffer_min ?? 15)} min ` +
      `(impacto alto, fail-open si el calendario no responde)</li>`
    );
  }

  if (s.agent_risk_policy) {
    rows.push(`<li><b>Política de riesgo del agente:</b><div class="strategy-policy">${esc(s.agent_risk_policy)}</div></li>`);
  }

  el.innerHTML = `<ul>${rows.join("")}</ul>`;
}

function openTradeConfig() {
  const c = TRADE_CFG || {};
  renderStrategyRules();
  els.tcMagic.value = c.magic ?? 8882026;
  els.tcComment.value = c.comment ?? "Web Exec";
  els.tcRisk.value = c.risk_pct ?? 0.5;
  els.tcLossFixed.value = c.loss_limit_fixed ?? 1250;
  els.tcLossPct.value = c.loss_limit_pct ?? 2;
  els.tcMaxTrades.value = c.max_trades_day ?? 10;
  els.tcSlPips.value = c.sl_default_pips ?? 15;
  els.tcTpR.value = c.tp_ratio_r ?? 2;
  els.tcDeviation.value = c.deviation_points ?? 20;
  els.tcAllow.value = (c.symbols_allow || []).join(", ");
  loadWatcherStatus();
  els.tradeConfigModal.hidden = false;
}

function renderWatcherStatus(st) {
  if (!st || st.error) {
    els.watcherAgent.innerHTML = `<span class="muted">${esc((st && st.error) || "sin datos")}</span>`;
    return;
  }
  els.watcherStatusDot.textContent = st.enabled ? "ON" : "OFF";
  els.watcherStatusDot.classList.toggle("muted", !st.enabled);
  const syms = (st.symbols || [])
    .map((s) => `${esc(s.symbol)} ${esc(s.timeframe)}`)
    .join(", ");
  const rows = [];
  rows.push(
    `<li><b>Ciclo:</b> cada ${esc(st.scan_interval_sec)} s · ` +
    `<b>auto-ejecutar:</b> ${st.auto_execute ? "SÍ ⚠" : "no"} · ` +
    `<b>TTL dedup:</b> ${esc(st.dedup_ttl_sec)} s</li>`
  );
  rows.push(`<li><b>Vigilando:</b> ${syms || "—"}</li>`);
  const states = (st.states || []).filter(Boolean);
  if (states.length) {
    rows.push(
      states.map((x) =>
        `<li class="${x.status === "active" ? "" : "muted"}">` +
        `${esc(x.symbol)} ${esc(x.timeframe)} → <b>${esc((x.status || "").toUpperCase())}</b>` +
        ` · ${esc(x.direction || "—")} score ${esc(x.score ?? "—")}` +
        `${x.status === "executed" ? " · ejecutado" : ""}</li>`
      ).join("")
    );
  } else {
    rows.push(`<li class="muted">Sin setups pendientes en ningún símbolo.</li>`);
  }
  els.watcherAgent.innerHTML = `<ul>${rows.join("")}</ul>`;
}

function loadWatcherStatus() {
  fetch("/api/watcher/status")
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error("estado " + res.status))))
    .then((st) => {
      renderWatcherStatus(st);
      if (els.tcAutoExec && st && typeof st.auto_execute === "boolean") {
        els.tcAutoExec.checked = st.auto_execute;
      }
    })
    .catch((err) => {
      if (els.watcherAgent) els.watcherAgent.innerHTML = `<span class="muted">${esc(err.message)}</span>`;
    });
}

function applyWatcherEvent(data) {
  const label = `${data.symbol || ""} ${data.timeframe || ""}`.trim();
  if (data.type === "new") {
    toast(
      `Watcher: setup ${data.direction || ""} ${label} · score ${data.score ?? "—"} · ` +
      `entry ${fmt(data.entry ?? "")}`,
      "ok"
    );
  } else if (data.type === "closed") {
    toast(`Watcher: setup ${label} cerrado/expirado`, "err");
  } else if (data.type === "executed") {
    toast(
      `Watcher: orden auto-ejecutada ${data.direction || ""} ${label} ` +
      `${data.ticket != null ? "· ticket " + data.ticket : ""}`,
      "ok"
    );
  } else if (data.type === "executed_error") {
    toast(`Watcher: auto-ejecución falló (${label}) · ${data.error || ""}`, "err");
  }
}

async function saveTradeConfig() {
  els.tradeCfgSave.disabled = true;
  try {
    const symbols_allow = els.tcAllow.value
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    const body = {
      magic: parseInt(els.tcMagic.value, 10) || 0,
      comment: els.tcComment.value.trim() || "Web Exec",
      risk_pct: parseFloat(els.tcRisk.value) || 0.5,
      loss_limit_fixed: parseFloat(els.tcLossFixed.value) || 0,
      loss_limit_pct: parseFloat(els.tcLossPct.value) || 0,
      max_trades_day: parseInt(els.tcMaxTrades.value, 10) || 0,
      sl_default_pips: parseFloat(els.tcSlPips.value) || 15,
      tp_ratio_r: parseFloat(els.tcTpR.value) || 0,
      deviation_points: parseInt(els.tcDeviation.value, 10) || 0,
      symbols_allow,
    };
    const res = await fetch("/api/trade/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("No se pudo guardar la configuración");
    toast("Configuración de trading guardada", "ok");
    els.tradeConfigModal.hidden = true;
    loadRiskState();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    els.tradeCfgSave.disabled = false;
  }
}

function askClose(ticket) {
  CLOSE_TICKET = ticket;
  els.closeInfo.textContent = `¿Cerrar la posición #${ticket}? Se ejecutará al precio de mercado actual.`;
  els.closeModal.hidden = false;
}

async function confirmClose() {
  if (!CLOSE_TICKET || els.closeConfirm.disabled) return;
  els.closeConfirm.disabled = true;
  els.closeConfirm.textContent = "Cerrando…";
  try {
    const res = await fetch(`/api/positions/${CLOSE_TICKET}/close`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Error al cerrar la posición");
    toast(`Posición ${data.symbol} #${CLOSE_TICKET} cerrada a ${Number(data.price).toFixed(5)} · ${data.filling}`, "ok");
    els.closeModal.hidden = true;
    CLOSE_TICKET = null;
    loadRiskState();
    refreshAll();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    els.closeConfirm.disabled = false;
    els.closeConfirm.textContent = "Cerrar posición";
  }
}

/* ============================================================
   Investigación / Backtest (pipeline research/)
   ============================================================ */
let resChartObj = null;
let resSaved = null;
let resLast = null;
const RES_ENDPOINTS = {
  export: "/api/research/export",
  validate: "/api/research/validate",
  backtest: "/api/research/backtest",
  calibrate: "/api/research/calibrate",
  search: "/api/research/search",
};

function resResolve() {
  return {
    symbol: (els.resSymbol.value || "EURUSD").toUpperCase().trim(),
    timeframe: els.resTf.value || "M15",
    days: Math.max(1, parseInt(els.resDays.value, 10) || 90),
  };
}

function resBusy(on) {
  const btns = [els.resExportBtn, els.resValidateBtn, els.resBacktestBtn, els.resCalibrateBtn, els.resSearchBtn, els.resExplainBtn];
  btns.forEach((b) => {
    if (b) b.disabled = on;
  });
  if (on) {
    els.resStatus.hidden = false;
    els.resStatus.textContent =
      "Ejecutando pipeline offline (subproceso de research/run_research.py)… puede tardar unos segundos.";
    els.resStatus.className = "res-status res-info";
  }
}

function resShowStatus(kind, data) {
  const sym = resResolve();
  els.resStatus.hidden = false;
  els.resStatus.className = "res-status res-ok";
  if (kind === "search") {
    const base = Object.entries(data.base || {})
      .map(([k, v]) => `${k}=${v}`).join(", ");
    els.resStatus.textContent =
      `Grid search ${sym.symbol} ${sym.timeframe} · ${data.combos} combo(s) → Top ${(data.results || []).length} · mínimo ${data.min_filled} fills · base «${base}»` +
      (data.saved ? ` · ${data.saved}` : "");
    return;
  }
  if (kind === "validate") {
    const checks = (data && data.checks) || {};
    const nok = Object.values(checks).filter((v) => v).length;
    const n = Object.keys(checks).length;
    els.resStatus.textContent =
      `Validación ${sym.symbol} ${sym.timeframe} · ${data.n_bars} velas · ${nok}/${n} checks OK` +
      ((data.warnings || []).length ? ` · ${data.warnings.length} advertencia(s)` : "") +
      (data.lookahead_mismatches ? ` · ${data.lookahead_mismatches} fugas look-ahead` : "");
    return;
  }
  const m = (data && data.metrics) || {};
  const parts = [`${sym.symbol} ${sym.timeframe} · ${data.run ? (data.run.n_bars ?? "?") : "?"} velas`];
  if (m.n_filled != null) parts.push(`${m.n_filled} fills`);
  if (m.win_rate != null) parts.push(`WR ${num(m.win_rate, 1)}%`);
  if (m.expectancy_r != null) parts.push(`E ${num(m.expectancy_r, 2)}R`);
  if (m.profit_factor != null) parts.push(`PF ${num(m.profit_factor, 2)}`);
  if (m.max_dd_equity_pct != null) parts.push(`DD ${num(m.max_dd_equity_pct, 1)}%`);
  if (data.saved) parts.push(`› ${data.saved}`);
  els.resStatus.textContent = parts.join(" · ");
}

function resShowError(err) {
  els.resStatus.hidden = false;
  els.resStatus.textContent = (err && String(err)) || "Error ejecutando el pipeline.";
  els.resStatus.className = "res-status res-err";
}

function resKpi(label, value, cls) {
  return `<article class="res-kpi"><span class="res-kpi-label">${label}</span>` +
    `<span class="res-kpi-value ${cls || ""}">${value}</span></article>`;
}

function resRenderKpis(m) {
  els.resKpis.innerHTML = m ? [
    resKpi("Trades", num(m.n, 0)),
    resKpi("Fills", num(m.n_filled, 0)),
    resKpi("Win rate", m.win_rate != null ? num(m.win_rate, 1) + "%" : "—"),
    resKpi("Esperanza", m.expectancy_r != null ? num(m.expectancy_r, 2) + "R" : "—", m.expectancy_r != null && m.expectancy_r >= 0 ? "profit-pos" : "profit-neg"),
    resKpi("Profit factor", m.profit_factor != null ? num(m.profit_factor, 2) : "—"),
    resKpi("Max DD", m.max_dd_equity_pct != null ? num(m.max_dd_equity_pct, 2) + "%" : "—"),
    resKpi("Espiradas", m.n_expired != null ? num(m.n_expired, 0) : "—"),
    resKpi("Canceladas", m.n_cancelled != null ? num(m.n_cancelled, 0) : "—"),
  ].join("") : `<div class="res-warn">Sin métricas de este run.</div>`;
}

function resRenderEquity(trades) {
  const el = els.resChart;
  if (!el) return;
  if (!window.echarts) return;
  const closed = (trades || [])
    .filter((t) => t.pnl_r != null)
    .slice()
    .sort((a, b) => (a.fill_ts || 0) - (b.fill_ts || 0));
  const points = [{ x: "#0", y: 100, ts: null, r: 0 }];
  let eq = 100;
  closed.forEach((t, i) => {
    eq *= 1 + t.pnl_r * 0.01;
    points.push({ x: "#" + String(i + 1), y: +eq.toFixed(4), ts: t.fill_ts, r: t.pnl_r });
  });
  if (resChartObj) { resChartObj.dispose(); resChartObj = null; }
  resChartObj = echarts.init(el, null, { renderer: "canvas" });
  resChartObj.setOption({
    backgroundColor: "transparent",
    grid: { left: 48, right: 20, top: 20, bottom: 28 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(13,19,34,0.95)",
      borderColor: "rgba(255,255,255,0.15)",
      textStyle: { color: "#eef1fa", fontSize: 12 },
      formatter: (ps) => {
        const p = ps && ps[0];
        if (!p || !p.data) return "";
        const d = p.data;
        const when = d.ts ? chartNiceTime(d.ts) : "inicio";
        return `<b>${d.x}</b> · ${when}<br/>Capital ${num(d.y, 2)} · trade ${d.r != null ? num(d.r, 2) + " R" : "—"}`;
      },
    },
    xAxis: { type: "category", data: points.map((p) => p.x), axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } }, axisLabel: { color: "#67708f", fontSize: 11 } },
    yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "rgba(255,255,255,0.07)" } }, axisLabel: { color: "#67708f", fontSize: 11 } },
    series: [{
      type: "line",
      data: points.map((p) => ({ value: p.y, ...p })),
      showSymbol: false,
      lineStyle: { color: "#2ee6a8", width: 2 },
      areaStyle: { color: "rgba(46,230,168,0.10)" },
    }],
  });
}

function resSugVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return esc(JSON.stringify(v));
  return num(v, 2);
}

function resRenderSuggestions(suggestions, warnings) {
  const el = els.resSuggestions;
  if (!el) return;
  const html = [];
  if (suggestions && suggestions.length) {
    html.push('<div class="res-suggest-head">Sugerencias del calibrador (nunca escriben strategy.yaml)</div>');
    for (const s of suggestions) {
      const conf = (s.confidence || "ok").toLowerCase();
      const path = (s.path || []).join(".");
      const payload = JSON.stringify({ key: s.key, value: s.suggested, current: s.current });
      html.push(
        `<div class="res-sug-row">` +
          `<b>${esc(path || s.key || "")}</b>` +
          `<span>${resSugVal(s.current)} → <b>${resSugVal(s.suggested)}</b></span>` +
          `<span class="res-conf ${conf}">${esc(s.confidence || "ok")}</span>` +
          `<span class="res-sug-reason">${esc(s.reason || "")}</span>` +
          `<button type="button" class="btn apply-btn" data-res-apply="${esc(payload)}">Aplicar</button>` +
        `</div>`
      );
    }
  }
  for (const w of warnings || []) {
    html.push(`<div class="res-warn">⚠ ${esc(w)}</div>`);
  }
  if (html.length) el.innerHTML = html.join("");
  if (el) {
    el.querySelectorAll("[data-res-apply]").forEach((btn) => {
      btn.addEventListener("click", () => {
        try {
          const it = JSON.parse(btn.getAttribute("data-res-apply"));
          applyOpen([{ key: it.key, value: it.value, current: it.current }]);
        } catch (_) {}
      });
    });
  }
}

function resBreakdownTable(title, sub) {
  if (!sub || !Object.keys(sub).length) return "";
  const rows = Object.entries(sub)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${num(v.n, 0)} · ${num(v.n_filled, 0)} fills</td>` +
      `<td>${v.win_rate != null ? num(v.win_rate, 1) + "%" : "—"}</td>` +
      `<td>${v.expectancy_r != null ? num(v.expectancy_r, 2) + "R" : "—"}</td></tr>`)
    .join("");
  return `<table class="res-bd-table"><thead><tr><th colspan="4">${title}</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

function resRenderBreakdowns(breakdowns) {
  if (!els.resBreakdown) return;
  if (!breakdowns || !Object.keys(breakdowns).length) {
    els.resBreakdown.innerHTML = "";
    return;
  }
  const cols = [
    resBreakdownTable("Por dirección", breakdowns.by_direction),
    resBreakdownTable("Por killzone", breakdowns.by_killzone),
    resBreakdownTable("Por tipo de entrada", breakdowns.by_entry_kind),
  ].join("");
  els.resBreakdown.innerHTML = `<div class="res-breakdown-row">${cols}</div>`;
}

function resRenderTrades(trades) {
  const body = els.resTradesBody;
  if (!body) return;
  if (!trades || !trades.length) {
    body.innerHTML = "";
    return;
  }
  body.innerHTML = trades.map((t, i) => {
    const win = t.pnl_r != null && t.pnl_r > 0;
    const loss = t.pnl_r != null && t.pnl_r <= 0;
    return `<tr>` +
      `<td>${i + 1}</td>` +
      `<td title="fill ${t.fill_ts ? chartNiceTime(t.fill_ts) : "—"}">${chartNiceTime(t.signal_ts)}</td>` +
      `<td class="${t.direction === "BUY" ? "profit-pos" : "profit-neg"}">${esc(t.direction || "")}</td>` +
      `<td>${num(t.score, 1)}</td>` +
      `<td>${esc(t.killzone || "—")}</td>` +
      `<td>${esc(t.entry_kind || "—")}</td>` +
      `<td>${esc(t.status || "—")}</td>` +
      `<td>${t.entry_price != null ? num(t.entry_price, 5) : "—"}</td>` +
      `<td>${t.exit_price != null ? num(t.exit_price, 5) : "—"}</td>` +
      `<td>${esc(t.exit_reason || "—")}</td>` +
      `<td class="${win ? "profit-pos" : loss ? "profit-neg" : ""}">${t.pnl_r != null ? num(t.pnl_r, 2) + "R" : "—"}</td>` +
    `</tr>`;
  }).join("");
  body.querySelectorAll("tr").forEach((tr, i) => {
    tr.title = "Audit en el gráfico principal";
    tr.addEventListener("click", () => auditTrade(trades[i], resSaved));
  });
}

function resRender(data, kind) {
  if (!data || kind === "export") return;
  els.resResults.hidden = data.error ? true : false;
  if (data.error) { resShowError(data.error); return; }
  resSaved = data.saved || null;
  resLast = { data, kind };
  resShowStatus(kind, data);
  if (kind !== "search") { if (els.resSearch) els.resSearch.innerHTML = ""; }
  if (kind === "validate") {
    const checks = data.checks || {};
    const rows = Object.entries(checks)
      .map(([k, v]) => `<div class="res-warn" style="border-color:${v ? "rgba(46,230,168,0.35)" : "rgba(255,93,108,0.4)"};color:${v ? "var(--green)" : "var(--red)"}">${v ? "✔" : "✘"} ${esc(k)}</div>`)
      .join("");
    els.resKpis.innerHTML = rows || `<div class="res-warn">Sin checks.</div>`;
    els.resSuggestions.innerHTML = (data.warnings || []).length
      ? `<div class="res-suggest-head">Advertencias</div>` +
        data.warnings.map((w) => `<div class="res-warn">⚠ ${esc(w)}</div>`).join("")
      : "";
    els.resBreakdown.innerHTML = "";
    els.resTradesBody.innerHTML = "";
    if (els.resPlotTitle) { /* no equity para validate */ }
    if (resChartObj) { resChartObj.dispose(); resChartObj = null; }
    return;
  }
  if (kind === "search") {
    if (resChartObj) { resChartObj.dispose(); resChartObj = null; }
    els.resKpis.innerHTML = [
      resKpi("Combinaciones", num(data.combos, 0)),
      resKpi("Mejores", num((data.results || []).length, 0)),
      resKpi("Min. fills", num(data.min_filled, 0)),
      resKpi("Determinista", "sí", "profit-pos"),
    ].join("");
    els.resSuggestions.innerHTML = `<div class="res-warn">La búsqueda solo ordena resultados: nada se ha escrito en strategy.yaml.</div>`;
    els.resBreakdown.innerHTML = "";
    els.resTradesBody.innerHTML = "";
    resRenderSearch(data);
    return;
  }
  const m = data.metrics || {};
  resRenderKpis(m);
  resRenderEquity((data.run && data.run.trades) || []);
  resRenderSuggestions(data.suggestions, data.warnings);
  resRenderBreakdowns(data.breakdowns);
  resRenderTrades((data.run && data.run.trades) || []);
}

function resRenderSearch(out) {
  const el = els.resSearch;
  if (!el) return;
  if (!out || !Array.isArray(out.results)) { el.innerHTML = ""; return; }
  const baseTxt = Object.entries(out.base || {})
    .map(([k, v]) => `<span class="apply-k">${esc(k)}</span>=${num(v, 2)}`).join(", ");
  const head = `<div class="res-search-head">` +
    `Barrido de ${out.combos} combinaciones → Top ${out.results.length} (min. ${out.min_filled} fills para rankear). Base: ${baseTxt}. Clic en una fila para aplicar.</div>`;
  const rows = out.results.map((r, i) => {
    const m = r.metrics || {};
    const params = Object.entries(r.params || {})
      .map(([k, v]) => `${esc(k)}=${num(v, 2)}`).join(", ");
    return `<tr class="${i === 0 ? "rank-top" : ""}">` +
      `<td>#${i + 1}</td>` +
      `<td class="apply-k">${params}</td>` +
      `<td>${m.n_filled != null ? num(m.n_filled, 0) : "—"}</td>` +
      `<td>${m.win_rate != null ? num(m.win_rate, 1) + "%" : "—"}</td>` +
      `<td class="${m.expectancy_r != null && m.expectancy_r >= 0 ? "profit-pos" : "profit-neg"}">${m.expectancy_r != null ? num(m.expectancy_r, 2) + "R" : "—"}</td>` +
      `<td>${m.profit_factor != null ? num(m.profit_factor, 2) : "—"}</td>` +
      `<td>${m.max_dd_equity_pct != null ? num(m.max_dd_equity_pct, 2) + "%" : "—"}</td>` +
      `<td>${r.underpowered ? `<span class="res-undpw">⚠ &lt;${out.min_filled} fills</span>` : "—"}</td>` +
      `<td>${r.rank != null ? num(r.rank, 2) : "—"}</td>` +
      `<td><span class="res-rank-row-btn rank-btn" data-row-i="${i}">Aplicar</span></td>` +
    `</tr>`;
  }).join("");
  el.innerHTML = head +
    `<div class="table-wrap"><table class="res-rank-table"><thead><tr>` +
    `<th>#</th><th>Config</th><th>Fills</th><th>WR</th><th>E (R)</th><th>PF</th>` +
    `<th>DD</th><th>Nota</th><th>Rank</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
  el.querySelectorAll("[data-row-i]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = out.results[parseInt(btn.getAttribute("data-row-i"), 10)];
      const items = Object.entries(row.params || {})
        .map(([k, v]) => ({ key: k, value: v, current: (out.base || {})[k] }));
      applyOpen(items);
    });
  });
}

function resDigestFmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return num(v, 2);
}

function resExplainDigest(data, kind) {
  if (!data) return "";
  const d = [];
  const sym = resResolve();
  d.push(`Resultado de investigación · ${sym.symbol} ${sym.timeframe} · ${kind === "search" ? "Grid search (Top-N)" : kind === "calibrate" ? "Calibrar (con sugerencias)" : "Backtest"}`);
  if (kind === "search") {
    const ds = data.dataset || {};
    d.push(`Dataset: ${ds.n_bars ?? "?"} velas. Base actual (strategy.yaml): ${Object.entries(data.base || {}).map(([k, v]) => `${k}=${num(v, 2)}`).join(", ")}.`);
    d.push(`Grid: ${data.combos ?? "?"} combinaciones barridas, mínimo ${data.min_filled ?? "?"} fills para rankear.`);
    (data.results || []).forEach((r, i) => {
      const m = r.metrics || {};
      const params = Object.entries(r.params || {}).map(([k, v]) => `${k}=${num(v, 2)}`).join(", ");
      d.push(`#${i + 1} · ${params} → fills ${m.n_filled ?? "—"}, WR ${m.win_rate != null ? num(m.win_rate, 1) + "%" : "—"}, E ${m.expectancy_r != null ? num(m.expectancy_r, 2) + "R" : "—"}, PF ${m.profit_factor != null ? num(m.profit_factor, 2) : "—"}, DD ${m.max_dd_equity_pct != null ? num(m.max_dd_equity_pct, 2) + "%" : "—"}, rank ${r.rank != null ? num(r.rank, 2) : "—"}${r.underpowered ? " (⚠ muestra insuficiente)" : ""}`);
    });
    d.push("Nota: el grid search solo ordena resultados; no ha escrito nada en strategy.yaml.");
    return d.join("\n");
  }
  const m = data.metrics || {};
  d.push(`Nº de velas evaluadas: ${data.run && data.run.n_bars != null ? data.run.n_bars : "?"}`);
  const fields = [
    ["Fills ejecutados", m.n_filled, "dec0"],
    ["Operaciones ganadas", m.wins, "dec0"],
    ["Operaciones perdidas", m.losses, "dec0"],
    ["Win rate", m.win_rate != null ? num(m.win_rate, 1) + "%" : null, "raw"],
    ["Esperanza por operación", m.expectancy_r != null ? num(m.expectancy_r, 2) + "R" : null, "raw"],
    ["Esperanza en pips", m.expectancy_pips != null ? num(m.expectancy_pips, 2) + " pips" : null, "raw"],
    ["Ganancia media", m.avg_win_r != null ? num(m.avg_win_r, 2) + "R" : null, "raw"],
    ["Pérdida media", m.avg_loss_r != null ? num(m.avg_loss_r, 2) + "R" : null, "raw"],
    ["Profit factor", m.profit_factor, "dec2"],
    ["Drawdown máximo (curva 1%/trade)", m.max_dd_equity_pct != null ? num(m.max_dd_equity_pct, 2) + "%" : null, "raw"],
    ["Velas en espera (media)", m.avg_bars_pending, "dec0"],
    ["Velas mantenidas (media)", m.avg_bars_held, "dec0"],
  ];
  fields.forEach(([label, v, f]) => {
    if (v == null) return;
    d.push(`${label}: ${f === "raw" ? v : f === "dec2" ? num(v, 2) : num(v, 0)}`);
  });
  const bd = data.breakdowns || {};
  const breakdowns = [["Dirección", bd.by_direction], ["Killzone", bd.by_killzone], ["Tipo de entrada", bd.by_entry_kind]];
  breakdowns.forEach(([label, sub]) => {
    if (!sub || !Object.keys(sub).length) return;
    d.push(`Desglose por ${label.toLowerCase()}:`);
    Object.entries(sub).forEach(([k, mm]) => {
      d.push(`  ${k}: ${mm.n_filled ?? "?"} fills · WR ${mm.win_rate != null ? num(mm.win_rate, 1) + "%" : "—"} · E ${mm.expectancy_r != null ? num(mm.expectancy_r, 2) + "R" : "—"}`);
    });
  });
  if (kind === "calibrate") {
    const sugg = data.suggestions || [];
    if (sugg.length) {
      d.push("Cambios sugeridos frente a strategy.yaml (aún NO aplicados):");
      sugg.forEach((s) => {
        d.push(`  ${s.path}: de ${resDigestFmt(s.current)} → ${resDigestFmt(s.suggested)} · motivo: ${s.reason} · confianza ${s.confidence != null ? s.confidence + "%" : "?"}`);
      });
    } else {
      d.push("No hay cambios sugeridos: la configuración actual es la recomendada.");
    }
    (data.warnings || []).forEach((w) => d.push(`⚠ ${w}`));
  }
  return d.join("\n");
}

async function resExplain() {
  if (!resLast || !resLast.data) {
    toast("Primero ejecuta una investigación (Backtest, Calibrar o Buscar).", "err");
    return;
  }
  const kind = resLast.kind || "backtest";
  const digest = resExplainDigest(resLast.data, kind);
  const msg = [
    "Explica en lenguaje fácil, para un trader que quiere entender el resultado sin jerga técnica, esta investigación de mi estrategia de trading. Define con una frase sencilla qué significa WIN RATE, ESPERANZA (en R y en pips), PROFIT FACTOR y DRAWDOWN. Di con claridad si la configuración es buena o no, qué cambiarías y por qué, y termina con una conclusión clara y el siguiente paso que darías.",
    "---DATOS DE LA INVESTIGACIÓN---",
    digest,
    "---FIN---",
    "Responde siempre en español, con secciones cortas y ejemplos simples. No es consejo de inversión.",
  ].join("\n");
  sendChat(msg, { skipTools: true });
}

async function resRun(kind) {
  resBusy(true);
  try {
    const res = await fetch(RES_ENDPOINTS[kind], {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(resResolve()),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || ("estado " + res.status));
    toast(`${kind[0].toUpperCase() + kind.slice(1)} completado`, "ok");
    resRender(data, kind);
  } catch (err) {
    resShowError(err.message || String(err));
  } finally {
    resBusy(false);
  }
}

/* ---- Aplicar diff a strategy.yaml (Fase 2, con confirmación) ---- */
let applyPending = null;

function applyOpen(items) {
  applyPending = items;
  if (els.applyResult) {
    els.applyResult.hidden = true;
    els.applyResult.textContent = "";
  }
  els.applyList.innerHTML = (items || []).map((it) =>
    `<div class="apply-diff-row"><span class="apply-k">${esc(it.key)}</span>` +
    `<span class="apply-v">${it.current != null ? resSugVal(it.current) + " → " : ""}<b>${resSugVal(it.value)}</b></span></div>`
  ).join("") || `<div class="res-warn">Sin cambios.</div>`;
  els.applyModal.hidden = false;
}

function applyCloseModal() {
  els.applyModal.hidden = true;
  applyPending = null;
}

async function applyRun() {
  if (!applyPending || !applyPending.length) return;
  els.applyConfirm.disabled = true;
  try {
    const res = await fetch("/api/research/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        updates: applyPending.map((it) => ({ key: it.key, value: it.value })),
        ...resResolve(),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || ("estado " + res.status));
    const m = (data.after_payload && data.after_payload.metrics) || {};
    const applySummary = `Backtest con la config nueva: ${m.n_filled != null ? m.n_filled : "?"} fills · ` +
      `WR ${m.win_rate != null ? num(m.win_rate, 1) + "%" : "—"} · ` +
      `E ${m.expectancy_r != null ? num(m.expectancy_r, 2) + "R" : "—"} · ` +
      `DD ${m.max_dd_equity_pct != null ? num(m.max_dd_equity_pct, 2) + "%" : "—"}`;
    if (data.after_payload) {
      resRender({
        run: data.after_payload.run,
        metrics: data.after_payload.metrics,
        breakdowns: data.after_payload.breakdowns,
        suggestions: [],
        warnings: [],
        saved: data.saved,
      }, "backtest");
    }
    toast(`Config aplicada (${Object.keys(data.after_config || {}).length} cambios)`, "ok");
    els.applyList.innerHTML = `<div class="res-warn" style="border-color:rgba(46,230,168,0.35);color:var(--green)">` +
      `Config aplicada y guardada.<br/>Backup: <code>${esc(data.backup_path || "—")}</code><br/>${esc(applySummary)}</div>`;
    els.applyBackupNote.innerHTML =
      "Puedes revertir con `git checkout strategy.yaml` o restaurar la copia de backups/.";
    applyCloseModal();
  } catch (err) {
    els.applyResult.hidden = false;
    els.applyResult.textContent = "Error al aplicar: " + (err.message || String(err));
    els.applyConfirm.disabled = false;
  }
}

/* ---- Audit de un trade simulado en el gráfico (Fase 4) ---- */
let auditActive = false;
let auditPrevTf = "M15";
let auditPrevPattern = null;
let auditPrevOverlay = null;

function auditTrade(trade, saved) {
  if (!trade || !saved) return;
  auditPrevTf = chartState.tf;
  auditPrevOverlay = {
    markLine: SETUP_OVERLAY.markLine.slice(),
    markPoint: SETUP_OVERLAY.markPoint.slice(),
  };
  auditPrevPattern = lastPatternData;
  els.auditExitBtn.disabled = true;
  fetch("/api/research/audit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      saved,
      signal_ts: trade.signal_ts,
      window_before: 120,
      window_after: 80,
    }),
  })
    .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
    .then(({ ok, d }) => {
      if (!ok) throw new Error((d && d.error) || "estado " + r.status);
      renderAudit(d);
    })
    .catch((err) => {
      toast("Audit: " + (err.message || String(err)), "err");
      lastPatternData = auditPrevPattern;
    })
    .finally(() => {
      els.auditExitBtn.disabled = false;
    });
}

function renderAudit(d) {
  if (!d || !Array.isArray(d.candles) || !d.candles.length) {
    toast("Audit sin velas para dibujar.", "err");
    return;
  }
  auditActive = true;
  chartState.symbol = d.symbol;
  chartState.tf = d.timeframe || auditPrevTf;
  lastCandles = d.candles;
  chartIndexMap.clear();
  chartSyncData();

  const zone = d.zone || null;
  const patterns = { fvgs: [], order_blocks: [], sweeps: [] };
  if (zone) {
    if (zone.type && zone.type.indexOf("_FVG") !== -1) patterns.fvgs = [zone];
    else patterns.order_blocks = [zone];
  }
  setPatternZones({ patterns, pdh: null, pdl: null });

  const t = d.trade || {};
  const plan = t.plan || {};
  const markLine = [];
  if (plan.entry != null) {
    markLine.push({
      yAxis: plan.entry,
      lineStyle: { color: "#58a6ff", width: 1, type: "dashed" },
      label: { show: true, formatter: "Entry", color: "#58a6ff", fontSize: 10, position: "insideEndTop" },
    });
  }
  if (plan.sl != null) {
    markLine.push({
      yAxis: plan.sl,
      lineStyle: { color: "#ff5d6c", width: 1, type: "dotted" },
      label: { show: true, formatter: "SL", color: "#ff5d6c", fontSize: 10, position: "insideEndTop" },
    });
  }
  if (plan.tp != null) {
    markLine.push({
      yAxis: plan.tp,
      lineStyle: { color: "#2ee6a8", width: 1, type: "dotted" },
      label: { show: true, formatter: "TP", color: "#2ee6a8", fontSize: 10, position: "insideEndTop" },
    });
  }
  if (plan.invalidate != null) {
    markLine.push({
      yAxis: plan.invalidate,
      lineStyle: { color: "rgba(255,179,0,0.8)", width: 1, type: "dashed" },
      label: { show: true, formatter: "Invalidate", color: "#ffb300", fontSize: 10, position: "insideEndBottom" },
    });
  }
  SETUP_OVERLAY.markLine = markLine;
  SETUP_OVERLAY.markPoint = [];
  redrawPatterns();

  const step = d.tf_sec || 900;
  const markPoint = [];
  if (t.signal_ts != null) {
    markPoint.push({
      coord: [t.signal_ts, plan.entry],
      value: "S", symbol: "circle", symbolSize: 12,
      itemStyle: { color: "#ffffff", borderColor: "#58a6ff", borderWidth: 2 },
      label: { show: false },
    });
  }
  if (t.fill_ts != null) {
    markPoint.push({
      coord: [t.fill_ts + step * 0.5, plan.entry],
      value: "F", symbol: "triangle", symbolSize: 11,
      itemStyle: { color: "#58a6ff" }, label: { show: false },
    });
  }
  if (t.exit_ts != null && t.exit_price != null) {
    markPoint.push({
      coord: [t.exit_ts + step * 1.0, t.exit_price],
      value: "X", symbol: "cross", symbolSize: 12,
      itemStyle: { color: t.pnl_r > 0 ? "#2ee6a8" : "#ff5d6c" }, label: { show: false },
    });
  }
  chart.setOption({ series: [{ id: "candles", markPoint: { silent: true, data: markPoint } }] });

  const lo = Math.min.apply(null, d.candles.map((c) => c.low));
  const hi = Math.max.apply(null, d.candles.map((c) => c.high));
  focusChartView({
    start_time: d.candles[0].time,
    end_time: d.candles[d.candles.length - 1].time,
    price_min: lo,
    price_max: hi,
  });

  els.auditTitle.textContent =
    `AUDIT ${d.symbol} ${d.timeframe} · ${t.status || "?"} · ` +
    `${t.entry_kind || "—"} · ${t.direction || "—"} · #${t.id != null ? t.id : "—"}`;
  els.auditPlan.textContent =
    `score ${t.score != null ? num(t.score, 1) : "—"} · ` +
    `Entry ${plan.entry != null ? num(plan.entry, 5) : "—"} · ` +
    `SL ${plan.sl != null ? num(plan.sl, 5) : "—"} · ` +
    `TP ${plan.tp != null ? num(plan.tp, 5) : "—"} · ` +
    `Fill ${t.fill_ts ? chartNiceTime(t.fill_ts) : "—"} · ` +
    `Exit ${t.exit_ts ? chartNiceTime(t.exit_ts) : "—"} · ` +
    `PnL ${t.pnl_r != null ? num(t.pnl_r, 2) + "R" : "—"}`;
  els.auditBanner.hidden = false;
  toast("Audit dibujado en el gráfico principal (investigación). Usa «volver a vivo» para salir.", "ok");
}

function exitAudit() {
  auditActive = false;
  SETUP_OVERLAY.markLine = auditPrevOverlay ? auditPrevOverlay.markLine : [];
  SETUP_OVERLAY.markPoint = auditPrevOverlay ? auditPrevOverlay.markPoint : [];
  lastPatternData = auditPrevPattern;
  chartState.tf = auditPrevTf;
  els.auditBanner.hidden = true;
  loadCandles(false);
}

els.resExportBtn.addEventListener("click", () => resRun("export"));
els.resValidateBtn.addEventListener("click", () => resRun("validate"));
els.resBacktestBtn.addEventListener("click", () => resRun("backtest"));
els.resCalibrateBtn.addEventListener("click", () => resRun("calibrate"));
els.resSearchBtn.addEventListener("click", () => resRun("search"));
els.resExplainBtn.addEventListener("click", resExplain);

els.applyClose.addEventListener("click", applyCloseModal);
els.applyCancel.addEventListener("click", applyCloseModal);
els.applyModal.addEventListener("click", (e) => {
  if (e.target === els.applyModal) applyCloseModal();
});
els.applyConfirm.addEventListener("click", applyRun);
els.auditExitBtn.addEventListener("click", exitAudit);

/* ---- Wiring ---- */
els.tradeBuyBtn.addEventListener("click", () => openTradeModal("BUY"));
els.tradeSellBtn.addEventListener("click", () => openTradeModal("SELL"));
els.tradeClose.addEventListener("click", () => {
  els.tradeModal.hidden = true;
  TRADE_PENDING_ACTION = null;
});
els.tradeModal.addEventListener("click", (e) => {
  if (e.target === els.tradeModal) {
    els.tradeModal.hidden = true;
    TRADE_PENDING_ACTION = null;
  }
});
els.tradeConfirm.addEventListener("click", confirmTrade);
els.tradeCfgBtn.addEventListener("click", openTradeConfig);
els.tradeCfgClose.addEventListener("click", () => {
  els.tradeConfigModal.hidden = true;
});
els.tradeConfigModal.addEventListener("click", (e) => {
  if (e.target === els.tradeConfigModal) els.tradeConfigModal.hidden = true;
});
els.tradeCfgSave.addEventListener("click", saveTradeConfig);
  if (els.tcAutoExec) {
    els.tcAutoExec.addEventListener("change", () => {
      fetch("/api/watcher/auto-execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: els.tcAutoExec.checked }),
      })
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error("estado " + res.status))))
        .then(() => {
          toast(`Watcher auto-ejecutar ${els.tcAutoExec.checked ? "ACTIVADO ⚠" : "desactivado"}`, els.tcAutoExec.checked ? "err" : "ok");
          loadWatcherStatus();
        })
        .catch((err) => toast(err.message, "err"));
    });
  }
  if (els.watcherScan) {
    els.watcherScan.addEventListener("click", () => {
      els.watcherScan.disabled = true;
      fetch("/api/watcher/scan", { method: "POST" })
        .then((res) => (res.ok ? res.json() : Promise.reject(new Error("estado " + res.status))))
        .then((data) => {
          const evs = data.events || [];
          const detected = evs.filter((e) => ["new", "executed"].includes(e.event)).length;
          const errors = evs.filter((e) => e.event === "error");
          toast(
            `Watcher: escaneo con ${detected} setup(s) detectado(s) y ${evs.length} evento(s)` +
            (errors.length ? ` · ${errors.length} símbolo(s) sin datos` : ""),
            detected ? "ok" : "err"
          );
          loadWatcherStatus();
        })
        .catch((err) => toast(err.message, "err"))
        .finally(() => { els.watcherScan.disabled = false; });
    });
  }
els.posTable.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-ticket]");
  if (b) askClose(+b.dataset.ticket);
});

/* Chartismo clásico: botones toggle de capas + limpiar solo figuras ci */
document.querySelectorAll("#drawTools [data-kind]").forEach((b) => {
  b.addEventListener("click", () => toggleChartism(b.dataset.kind));
});
const dtChartismClear = document.getElementById("dtChartismClear");
if (dtChartismClear) {
  dtChartismClear.addEventListener("click", clearChartism);
}
els.closeConfirm.addEventListener("click", confirmClose);
els.closeCancel.addEventListener("click", () => {
  els.closeModal.hidden = true;
  CLOSE_TICKET = null;
});
els.closeModal.addEventListener("click", (e) => {
  if (e.target === els.closeModal) {
    els.closeModal.hidden = true;
    CLOSE_TICKET = null;
  }
});

loadRiskState();
setInterval(loadRiskState, 15000);
setInterval(refreshPatterns, 15000);