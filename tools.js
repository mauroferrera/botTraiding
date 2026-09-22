(function () {
  "use strict";

  var chart = null;
  var opts = { getSymbol: function () { return ""; }, getTimeframe: function () { return "M15"; }, getBars: function () { return []; } };
  var cat = [];
  var catIdx = new Map();
  var items = [];
  var els = [];
  var draft = null;
  var activeTool = "cursor";
  var selectedId = null;
  var dragRef = null;
  var saveTimer = null;

  var TOOLS = ["cursor", "line", "hline", "rect", "measure", "text", "delete"];

  function pickColor(it) {
    if (it.origin === "chartism") return "#58a6ff";
    if (it.tool === "hline") return "#c084fc";
    if (it.tool === "rect") return "#58a6ff";
    if (it.tool === "measure") return "#ffb300";
    if (it.tool === "text") return "#e6e9f2";
    return it.origin === "agent" ? "#2ee6a8" : "#e0b34f";
  }

  function sigDigits(price) {
    var a = Math.abs(price);
    if (!isFinite(a)) return 5;
    if (a >= 1000) return 2;
    if (a >= 10) return 3;
    return 5;
  }

  function pipSize(price) {
    var a = Math.abs(price);
    if (a >= 100) return 0.01;
    if (a >= 10) return 0.001;
    return 0.0001;
  }

  function ix(t) {
    var i = catIdx.get(t);
    return i == null ? 0 : i;
  }

  function measureLabel(it) {
    var dp = Math.abs(it.p1 - it.p0);
    var pips = dp / pipSize(it.p0);
    var digits = sigDigits(it.p0);
    var a0 = it.at0 != null ? it.at0 : it.t0;
    var a1 = it.at1 != null ? it.at1 : it.t1;
    var hrs = Math.abs(a1 - a0) / 3600;
    var tTxt = hrs >= 24 ? (hrs / 24).toFixed(1) + "d" : hrs >= 1 ? hrs.toFixed(1) + "h" : Math.round(hrs * 60) + "m";
    return pips.toFixed(1) + " pips \u00b7 " + dp.toFixed(digits) + " \u00b7 " + tTxt;
  }

  function mkId() {
    return Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  }

  function zr() {
    return chart ? chart.getZr() : null;
  }

  function zgraphic() {
    return window.echarts && window.echarts.graphic;
  }

  function pxOf(i, price) {
    if (!chart || !cat.length || i == null) return null;
    var p = chart.convertToPixel({ gridIndex: 0 }, [i, price]);
    return p && isFinite(p[0]) && isFinite(p[1]) ? { x: p[0], y: p[1] } : null;
  }

  function shapeGeom(item) {
    var n = cat.length;
    var last = Math.max(n - 1, 0);
    if (item.tool === "hline") {
      return { a: { i: 0, p: item.p0 }, b: { i: last, p: item.p0 } };
    }
    return {
      a: { i: ix(item.t0), p: item.p0 },
      b: { i: item.t1 != null ? ix(item.t1) : ix(item.t0), p: item.p1 != null ? item.p1 : item.p0 },
    };
  }

  function drawItemEls(item, isDraft) {
    var g = zgraphic();
    var z = zr();
    if (!g || !z) return;
    var geom = shapeGeom(item);
    var pa = pxOf(geom.a.i, geom.a.p);
    var pb = pxOf(geom.b.i, geom.b.p);
    var color = pickColor(item);
    var sel = !isDraft && item.id === selectedId;

    if (item.tool === "text") {
      if (!pa) return;
      var elT = new g.Text({
        style: { text: item.text || "", x: 0, y: 0, textAlign: "left", textBaseline: "bottom", fill: color, font: "12px Inter, system-ui, sans-serif" },
        position: [pa.x, pa.y - 4],
        zlevel: 100,
      });
      elT.__raw = { kind: "text", item: item };
      els.push(elT);
      z.add(elT);
      return;
    }
    if (!pa || !pb) return;

    if (item.tool === "rect") {
      var elR = new g.Rect({
        shape: { x: Math.min(pa.x, pb.x), y: Math.min(pa.y, pb.y), width: Math.abs(pb.x - pa.x), height: Math.abs(pb.y - pa.y) },
        style: { fill: "rgba(88,166,255,0.10)", stroke: color, lineWidth: sel ? 2 : 1.5 },
        zlevel: 100,
      });
      elR.__raw = { kind: "rect", item: item };
      els.push(elR);
      z.add(elR);
    } else {
      var elL = new g.Line({
        shape: { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y },
        style: { stroke: color, lineWidth: sel ? 2 : 1.5, lineDash: item.tool === "measure" ? [3, 3] : null, lineCap: "round" },
        zlevel: 100,
      });
      elL.__raw = { kind: item.tool === "hline" ? "hline" : "line", item: item };
      els.push(elL);
      z.add(elL);
      if (item.tool === "measure" && item.t1 != null && item.p1 != null) {
        var elM = new g.Text({
          style: { text: measureLabel(item), x: 0, y: 0, textAlign: "center", textBaseline: "bottom", fill: color, font: "11px Inter, system-ui, sans-serif" },
          position: [(pa.x + pb.x) / 2, (pa.y + pb.y) / 2 - 6],
          zlevel: 100,
        });
        elM.__raw = { kind: "text", item: item };
        els.push(elM);
        z.add(elM);
      }
    }

    if (sel && item.tool !== "text") {
      addHandle(pa.x, pa.y, item, 0);
      if (item.tool !== "hline") addHandle(pb.x, pb.y, item, 1);
    }
  }

  function addHandle(x, y, item, which) {
    var g = zgraphic();
    var z = zr();
    if (!g || !z) return;
    var elH = new g.Circle({
      shape: { cx: x, cy: y, r: 5 },
      style: { fill: "#ffffff", stroke: "#7c8cf8", lineWidth: 2 },
      zlevel: 101,
    });
    elH.__raw = { kind: "handle", item: item, which: which };
    els.push(elH);
    z.add(elH);
  }

  function renderNow() {
    var z = zr();
    if (!z) return;
    while (els.length) z.remove(els.pop());
    items.forEach(function (it) {
      drawItemEls(it, false);
    });
    if (draft) drawItemEls(draft, true);
    z.refresh();
    updateHint();
  }

  function reflowEls() {
    var z = zr();
    if (!z || !els.length) return;
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var r = el.__raw;
      if (!r) continue;
      var it = r.item;
      var geom = shapeGeom(it);
      var sel = it.id === selectedId;
      if (r.kind === "text") {
        var pa = pxOf(geom.a.i, geom.a.p);
        if (pa) el.attr({ position: [pa.x, pa.y - 4] });
      } else if (r.kind === "handle") {
        var pt = r.which === 0 ? pxOf(geom.a.i, geom.a.p) : pxOf(geom.b.i, geom.b.p);
        if (pt) el.attr({ shape: { cx: pt.x, cy: pt.y, r: 5 } });
      } else {
        var a = pxOf(geom.a.i, geom.a.p);
        var b = pxOf(geom.b.i, geom.b.p);
        if (!a || !b) continue;
        if (r.kind === "rect") {
          el.attr({ shape: { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) }, style: { stroke: pickColor(it), lineWidth: sel ? 2 : 1.5 } });
        } else {
          el.attr({ shape: { x1: a.x, y1: a.y, x2: b.x, y2: b.y }, style: { stroke: pickColor(it), lineWidth: sel ? 2 : 1.5 } });
        }
      }
    }
    z.refresh();
  }

  function updateHint() {
    var hint = document.getElementById("drawHint");
    if (!hint) return;
    hint.textContent = items.length ? String(items.length) : "";
  }

  function grid0Rect() {
    if (!chart) return null;
    var g = chart.getModel().getComponent("grid", 0);
    var cs = g && g.coordinateSystem;
    return cs && typeof cs.getRect === "function" ? cs.getRect() : null;
  }

  function insideGrid0(px, py) {
    var r = grid0Rect();
    if (!r) return true;
    return px >= r.x && px <= r.x + r.width && py >= r.y && py <= r.y + r.height;
  }

  function warnOutside(px) {
    if (!px) return;
    var r = grid0Rect();
    if (!r) return;
    if (px.x < r.x || px.x > r.x + r.width || px.y < r.y || px.y > r.y + r.height) {
      var hint = document.getElementById("drawHint");
      if (hint) hint.textContent = "Dibuj\u00e1 dentro del gr\u00e1fico.";
    }
  }

  function pxToData(px, py) {
    if (!chart || !cat.length) return null;
    if (!insideGrid0(px, py)) return null;
    var v = chart.convertFromPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [px, py]);
    if (!v || !isFinite(v[0]) || !isFinite(v[1])) return null;
    var i = Math.round(v[0]);
    if (i < 0 || i >= cat.length) return null;
    return { t: cat[i], price: v[1] };
  }

  function evPx(e) {
    var ev = e && e.event ? e.event : e;
    if (ev && ev.offsetX != null && ev.offsetY != null) return { x: ev.offsetX, y: ev.offsetY };
    if (ev && ev.clientX != null && chart) {
      var rect = chart.getDom().getBoundingClientRect();
      return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
    }
    return null;
  }

  function shiftT(t, dt) {
    if (dt === 0 || !cat.length) return t;
    var i = (catIdx.get(t) || 0) + dt;
    if (i < 0) i = 0;
    if (i >= cat.length) i = cat.length - 1;
    return cat[i];
  }

  function barDelta(curT, startT) {
    return (catIdx.get(curT) || 0) - (catIdx.get(startT) || 0);
  }

  function setTool(t) {
    if (TOOLS.indexOf(t) < 0) t = "cursor";
    activeTool = t;
    draft = null;
    dragRef = null;
    updateHint();
    var buttons = document.querySelectorAll("#drawTools [data-tool]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].classList.toggle("active", buttons[i].dataset.tool === t);
    }
    zoomCE(activeTool === "line" || activeTool === "rect" || activeTool === "measure" || activeTool === "hline" || activeTool === "text");
    if (t === "cursor") clearSelection();
  }

  function zoomCE(disabled) {
    if (!chart) return;
    var opt = chart.getOption();
    if (!Array.isArray(opt.dataZoom)) return;
    var dz = [];
    for (var i = 0; i < opt.dataZoom.length; i++) {
      var d = opt.dataZoom[i];
      if (d.type === "inside") {
        var copy = {};
        for (var k in d) copy[k] = d[k];
        copy.disabled = !!disabled;
        dz.push(copy);
      }
    }
    if (!dz.length) return;
    chart.setOption({ dataZoom: dz });
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(persist, 400);
  }

  function persist() {
    var symbol = opts.getSymbol();
    if (!symbol || !chart) return;
    fetch("/api/chart/drawings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: symbol, timeframe: opts.getTimeframe(), drawings: items }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("http " + r.status);
      })
      .catch(function () {
        if (window.toast) toast("No se pudieron guardar los dibujos", "err");
      });
  }

  function reload() {
    var symbol = opts.getSymbol();
    if (!symbol) return;
    fetch("/api/chart/drawings?symbol=" + encodeURIComponent(symbol) + "&timeframe=" + encodeURIComponent(opts.getTimeframe()))
      .then(function (r) {
        if (!r.ok) throw new Error("http " + r.status);
        return r.json();
      })
      .then(function (data) {
        var list = Array.isArray(data && data.drawings) ? data.drawings : [];
        items = [];
        for (var i = 0; i < list.length && items.length < 120; i++) {
          var it = list[i];
          if (!it || !it.tool) continue;
          var origin = it.origin === "user" ? "user" : it.origin === "agent" ? "agent" : "chartism";
          items.push({ id: it.id || mkId(), origin: origin, tool: it.tool, t0: it.t0, p0: it.p0, t1: it.t1, p1: it.p1, text: it.text || "", group: it.group && typeof it.group === "string" ? it.group : undefined });
        }
        selectedId = null;
        renderNow();
      })
      .catch(function () {
        renderNow();
      });
  }

  function addItem(it) {
    var entry = Object.assign({ id: mkId(), origin: "user" }, it);
    items.push(entry);
    selectedId = entry.id;
    renderNow();
    scheduleSave();
  }

  function addAgentDrawings(draws, origin) {
    if (!Array.isArray(draws) || !draws.length || !chart) return;
    origin = origin === "chartism" ? "chartism" : "agent";
    var map = new Map();
    items.forEach(function (it) {
      map.set(it.id, it);
    });
    draws.forEach(function (raw) {
      if (!raw || !raw.tool || raw.p0 == null) return;
      if (raw.tool !== "hline" && raw.t0 == null) return;
      var id = raw.id || mkId();
      map.set(id, {
        id: id,
        origin: origin,
        tool: raw.tool,
        t0: raw.t0 != null ? raw.t0 : null,
        p0: raw.p0,
        t1: raw.t1 != null ? raw.t1 : null,
        p1: raw.p1 != null ? raw.p1 : null,
        text: raw.text || "",
        group: raw.group && typeof raw.group === "string" ? raw.group : undefined,
      });
    });
    items = Array.from(map.values());
    if (items.length > 120) items = items.slice(items.length - 120);
    renderNow();
    scheduleSave();
  }

  function removeByGroup(group) {
    if (!group) return;
    var before = items.length;
    items = items.filter(function (it) {
      return !(it.origin === "chartism" && it.group === group);
    });
    if (items.length === before) return;
    if (selectedId) selectedId = null;
    renderNow();
    scheduleSave();
  }

  function removeByOrigin(origin) {
    if (!origin) return;
    var before = items.length;
    items = items.filter(function (it) {
      return it.origin !== origin;
    });
    if (items.length === before) return;
    if (selectedId) selectedId = null;
    renderNow();
    scheduleSave();
  }

  function clearAll() {
    items = [];
    selectedId = null;
    renderNow();
    scheduleSave();
  }

  function removeSelected() {
    if (!selectedId) return;
    for (var i = 0; i < items.length; i++) {
      if (items[i].id === selectedId) {
        items.splice(i, 1);
        selectedId = null;
        renderNow();
        scheduleSave();
        return;
      }
    }
  }

  function clearSelection() {
    if (selectedId) {
      selectedId = null;
      renderNow();
    }
  }

  function maybePlace(px) {
    if (!px) return null;
    return pxToData(px.x, px.y);
  }

  function commitDraft(fin) {
    var t1 = fin && fin.t != null ? fin.t : draft.t1;
    var p1 = fin ? fin.price : draft.p1;
    if (t1 === draft.t0 && Math.abs(p1 - draft.p0) < pipSize(draft.p0) / 10) {
      var tool0 = draft.tool;
      draft = null;
      renderNow();
      return tool0;
    }
    var tool = draft.tool;
    var it = { tool: tool, t0: draft.t0, p0: draft.p0, t1: t1, p1: p1 };
    draft = null;
    addItem(it);
    return tool;
  }

  function segDist(px, a, b) {
    var dx = b.x - a.x;
    var dy = b.y - a.y;
    var len2 = dx * dx + dy * dy;
    var t = len2 ? ((px.x - a.x) * dx + (px.y - a.y) * dy) / len2 : 0;
    t = t < 0 ? 0 : t > 1 ? 1 : t;
    var cx = a.x + t * dx;
    var cy = a.y + t * dy;
    var ddx = px.x - cx;
    var ddy = px.y - cy;
    return Math.sqrt(ddx * ddx + ddy * ddy);
  }

  function hitTestEls(px) {
    if (!px) return null;
    var i, el, r, sh, d;
    for (i = 0; i < els.length; i++) {
      el = els[i];
      r = el.__raw;
      if (!r || r.kind !== "handle" || !r.item || r.item.id !== selectedId) continue;
      sh = el.shape;
      d = Math.sqrt((px.x - sh.cx) * (px.x - sh.cx) + (px.y - sh.cy) * (px.y - sh.cy));
      if (d <= 9) return { item: r.item, which: r.which, mode: "handle" };
    }
    var best = null;
    for (var j = 0; j < els.length; j++) {
      el = els[j];
      r = el.__raw;
      if (!r || r.kind === "handle") continue;
      var it = r.item;
      var g2 = shapeGeom(it);
      var pa = pxOf(g2.a.i, g2.a.p);
      if (!pa) continue;
      var pb = pxOf(g2.b.i, g2.b.p);
      var d2;
      if (r.kind === "rect") {
        if (!pb) continue;
        var x1 = Math.min(pa.x, pb.x);
        var x2 = Math.max(pa.x, pb.x);
        var y1 = Math.min(pa.y, pb.y);
        var y2 = Math.max(pa.y, pb.y);
        if (px.x >= x1 - 4 && px.x <= x2 + 4 && px.y >= y1 - 4 && px.y <= y2 + 4) {
          d2 = 0;
        } else {
          d2 = Math.min(
            segDist(px, { x: x1, y: y1 }, { x: x2, y: y1 }),
            segDist(px, { x: x2, y: y1 }, { x: x2, y: y2 }),
            segDist(px, { x: x2, y: y2 }, { x: x1, y: y2 }),
            segDist(px, { x: x1, y: y2 }, { x: x1, y: y1 })
          );
        }
      } else if (r.kind === "text") {
        d2 = Math.sqrt((px.x - pa.x) * (px.x - pa.x) + (px.y - (pa.y - 4)) * (px.y - (pa.y - 4))) - 30;
      } else {
        if (!pb) continue;
        d2 = segDist(px, pa, pb);
      }
      if (d2 < 10 && (!best || d2 < best.d)) best = { item: it, d: d2 };
    }
    return best ? { item: best.item, mode: "body" } : null;
  }

  function onZrDown(e) {
    if (!chart) return;
    var px = evPx(e);
    if (!px) return;

    if (activeTool === "cursor") {
      var hit = hitTestEls(px);
      if (hit) {
        selectedId = hit.item.id;
        renderNow();
        var startPt = pxToData(px.x, px.y);
        dragRef = {
          item: hit.item,
          base: { t0: hit.item.t0, t1: hit.item.t1, p0: hit.item.p0, p1: hit.item.p1 },
          startT: startPt ? startPt.t : hit.item.t0,
          startP: startPt ? startPt.price : hit.item.p0,
          mode: hit.mode,
          who: hit.which != null ? hit.which : 0,
          moved: false,
        };
        return;
      }
      clearSelection();
      renderNow();
      return;
    }

    if (activeTool === "delete") {
      var hit2 = hitTestEls(px);
      if (hit2) {
        removeItemById(hit2.item.id);
        renderNow();
        scheduleSave();
      }
      return;
    }

    if (draft) {
      var fin = maybePlace(px);
      if (!fin) {
        warnOutside(px);
        return;
      }
      commitDraft(fin);
      return;
    }

    if (activeTool === "text") {
      var d = maybePlace(px);
      if (!d) {
        warnOutside(px);
        return;
      }
      var txt = window.prompt("Texto de la etiqueta:", "");
      if (txt == null) return;
      addItem({ tool: "text", t0: d.t, p0: d.price, text: txt.slice(0, 60) });
      return;
    }

    if (activeTool === "hline") {
      var dh = maybePlace(px);
      if (!dh) {
        warnOutside(px);
        return;
      }
      addItem({ tool: "hline", p0: dh.price });
      return;
    }

    var d0 = maybePlace(px);
    if (!d0) {
      warnOutside(px);
      return;
    }
    draft = { tool: activeTool, t0: d0.t, p0: d0.price, t1: d0.t, p1: d0.price };
    renderNow();
  }

  function onZrMove(e) {
    if (!chart) return;
    var px = evPx(e);
    if (!px) return;

    if (activeTool === "cursor" && chart.getDom()) {
      chart.getDom().style.cursor = hitTestEls(px) ? "pointer" : "";
    }

    if (draft && (activeTool === "line" || activeTool === "rect" || activeTool === "measure")) {
      var d = pxToData(px.x, px.y);
      if (!d) return;
      draft.t1 = d.t;
      draft.p1 = d.price;
      renderNow();
      return;
    }

    if (!dragRef) return;
    var it = dragRef.item;
    var cur = pxToData(px.x, px.y);
    if (!cur) return;
    var base = dragRef.base;

    if (it.tool === "text" || dragRef.mode === "body") {
      var dT = barDelta(cur.t, dragRef.startT);
      var dP = cur.price - dragRef.startP;
      if (it.tool === "text") {
        it.t0 = shiftT(base.t0, dT);
        it.p0 = base.p0 + dP;
      } else if (it.tool === "hline") {
        it.p0 = cur.price;
      } else {
        it.t0 = shiftT(base.t0, dT);
        it.t1 = base.t1 != null ? shiftT(base.t1, dT) : null;
        it.p0 = it.t1 == null ? base.p0 : base.p0 + dP;
        it.p1 = base.p1 != null ? base.p1 + dP : null;
      }
      dragRef.moved = true;
      renderNow();
      return;
    }

    if (dragRef.mode === "handle") {
      var cur2 = pxToData(px.x, px.y);
      if (!cur2) return;
      if (it.tool === "hline") {
        it.p0 = cur2.price;
      } else if (dragRef.who === 0) {
        it.t0 = cur2.t;
        it.p0 = cur2.price;
      } else {
        it.t1 = cur2.t;
        it.p1 = cur2.price;
      }
      dragRef.moved = true;
      renderNow();
    }
  }

  function onZrUp(e) {
    if (draft && (draft.tool === "line" || draft.tool === "rect" || draft.tool === "measure")) {
      var px = evPx(e);
      var fin = px ? maybePlace(px) : null;
      commitDraft(fin);
      return;
    }
    if (dragRef && dragRef.moved) scheduleSave();
    dragRef = null;
  }

  function removeItemById(id) {
    if (!id) return;
    for (var i = 0; i < items.length; i++) {
      if (items[i].id === id) {
        items.splice(i, 1);
        if (selectedId === id) selectedId = null;
        return;
      }
    }
  }

  function onKey(e) {
    if (e.key === "Escape") {
      if (activeTool !== "cursor") {
        setTool("cursor");
      } else if (draft) {
        draft = null;
        renderNow();
      } else {
        selectedId = null;
        renderNow();
      }
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && activeTool === "cursor" && selectedId) {
      e.preventDefault();
      removeSelected();
    }
  }

  function onZrRendered() {
    reflowEls();
  }

  function attach(instance, api) {
    if (!instance) return;
    if (chart && chart !== instance) {
      var oldZr = chart.getZr();
      oldZr.off("mousedown", onZrDown);
      oldZr.off("mousemove", onZrMove);
      oldZr.off("mouseup", onZrUp);
      oldZr.off("rendered", onZrRendered);
    }
    chart = instance;
    if (api) {
      opts.getSymbol = api.getSymbol || opts.getSymbol;
      opts.getTimeframe = api.getTimeframe || opts.getTimeframe;
      opts.getBars = api.getBars || opts.getBars;
    }
    var z = chart.getZr();
    z.on("mousedown", onZrDown);
    z.on("mousemove", onZrMove);
    z.on("mouseup", onZrUp);
    z.on("rendered", onZrRendered);
    window.addEventListener("keydown", onKey);
    if (items.length || draft) renderNow();
    setTool(activeTool);
    console.info("DrawingTools v6 attach OK - symbol:", opts.getSymbol(), "tf:", opts.getTimeframe());
  }

  function initToolbar() {
    var toolbar = document.getElementById("drawTools");
    if (!toolbar) return;
    var btns = toolbar.querySelectorAll("[data-tool]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        setTool(this.dataset.tool);
      });
    }
    var clearBtn = document.getElementById("dtClear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (!items.length) return;
        if (window.confirm("\u00bfBorrar todos los dibujos del gr\u00e1fico?")) clearAll();
      });
    }
    setTool("cursor");
  }
  initToolbar();

  function onBars(bars) {
    if (!Array.isArray(bars) || !bars.length) return;
    cat = bars.map(function (b) {
      return b.time;
    });
    catIdx = new Map();
    for (var i = 0; i < cat.length; i++) catIdx.set(cat[i], i);
    if (items.length || draft) renderNow();
  }

  window.DrawingTools = {
    attach: attach,
    onBars: onBars,
    reload: reload,
    addAgentDrawings: addAgentDrawings,
    removeByGroup: removeByGroup,
    removeByOrigin: removeByOrigin,
    setTool: setTool,
  };
})();