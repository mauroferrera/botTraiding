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
const chartIndexMap = new Map(); // time -> índice en lastCandles

const PATTERN_TFS = ["M1", "M5", "M15", "M30", "H1", "H4"];
let patternBusy = false;
let cvdOverlayOn = false;
let journalOverlay = []; // líneas de SL/TP del journal para el símbolo activo
let journalOverlayOn = false;

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

function chartMsg(text) {
  els.chartMsg.textContent = text || "";
  els.chartMsg.classList.toggle("hidden", !text);
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

function chartTooltip(params) {
  const arr = Array.isArray(params) ? params : [params];
  const candle = arr.find((p) => p.seriesType === "candlestick");
  if (candle) {
    const c = lastCandles[candle.dataIndex];
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
            const price = vpSortedRows[idx]?.price ?? 0;
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

function initChart() {
  if (chart || typeof echarts === "undefined") return;
  chart = echarts.init(els.chartEl);
  chart.setOption(baseChartOption());
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
  // El eje X y la serie de velas se actualizan SIEMPRE juntos (mismo setOption):
  // si llega una vela con timestamp nuevo, crece xAxis.data; si es el mismo, se
  // actualiza la vela en su posición.
  chart.setOption({
    xAxis: [{ data: cat }, { data: cat }],
    series: [{ data: lastCandles.map(candleToOhlc) }],
  });
}

function applyLiveBar(bar) {
  if (!chart || !bar || bar.time === undefined) return;
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
}

function loadVolumeProfile() {
  if (!chartState.symbol) return;
  const bins = Math.max(30, Math.min(60, Math.round(((els.chartEl && els.chartEl.clientHeight) || 400) / 6)));
  fetch(`/api/volume-profile/${chartState.symbol}?timeframe=H1&bins=${bins}`)
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
    window.DrawingTools?.onBars?.(data);
    window.DrawingTools?.reload?.();
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
  if (!btn) return;
  els.tfGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  chartState.tf = btn.dataset.tf;
  loadCandles(true);
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
};

function ofApplyFeed(status) {
  if (!status) return;
  const on = !!status.enabled;
  const connected = !!status.connected;
  ofEls.feedToggle.checked = on;
  const label = on ? (connected ? "Conectado" : "Conectando...") : "Apagado";
  ofEls.feedToggleLabel.textContent = label;
  ofEls.feedToggleLabel.classList.toggle("on", on && connected);
  ofEls.feedToggleLabel.classList.toggle("off", !on);
  if (on && connected) {
    ofSetConn("connected", "6E en línea");
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

function ofUpdateCvd(ts, cvd, delta) {
  const t = ts ? Math.floor(ts) : undefined;
  if (ofChart && t != null) {
    const data = ofCvdPoints;
    const idx = ofIndexMap.get(t);
    if (idx !== undefined && idx < data.length) data[idx] = [t, cvd];
    else {
      ofIndexMap.set(t, data.length);
      data.push([t, cvd]);
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
  const socket = OF_STATUS.socket;
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action }));
  } else {
    fetch("/api/orderflow/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).catch(() => {});
  }
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
      ofInitChart();
      ofState.cvd = data.cvd;
      ofState.lastTrade = data;
      OF_STATUS.spikeCount = data.spike_count;
      ofRenderKpis();
      ofUpdateCvd(data.ts ? Math.floor(data.ts) : undefined, data.cvd, data.delta);
      if (data.is_spike || data.absorption) ofAddAlert(data);
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
    ofSetConn("connecting", "conectando 6E...");
    ofEls.feedToggleLabel.textContent = "Conectando...";
  } else {
    ofEls.feedToggleLabel.textContent = "Apagado";
    ofEls.feedToggleLabel.classList.remove("on");
    ofEls.feedToggleLabel.classList.add("off");
  }
  ofSendFeed(action);
});

/* Inicializar el interruptor con el estado del servidor */
fetch("/api/orderflow/feed")
  .then((r) => r.json())
  .then((status) => ofApplyFeed(status))
  .catch(() => {});

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