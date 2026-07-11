/* Schema Graph: SVG 기반 테이블/필드/관계 그래프
 * - 확대/축소(버튼+휠), 팬, 테이블 드래그 이동, 위치 저장
 * - 관계(grid) 정렬 / star 정렬, 심플 보기, 더블클릭 필드 접기
 * - 좌/우 패널 접기 + 가로 리사이즈, 하단 데이터 패널 + 세로 리사이즈
 * - 목록 클릭 시 해당 테이블 하이라이트 및 중심 이동 */
(function () {
  var embedded = (window.self !== window.top);
  if (!embedded) EmpNav("/schema");

  var SCHEMA_COLORS = {
    public: "#5b8cff", ganada: "#3ecf8e",
    employee_salary_db: "#f5b04d", employee_evaluation_db: "#ff7ab0"
  };
  var POS_KEY = "empsearch.schema.savedLayout.v1";

  var svg = document.getElementById("schemaSvg");
  var NS = "http://www.w3.org/2000/svg";
  var state = {
    tables: [], rels: [],
    pos: EmpProjects.getJSON(POS_KEY, {}),
    collapsed: {}, simple: false,
    view: { x: 0, y: 0, k: 1 },
    selected: null
  };

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function esc(s) { return String(s == null ? "" : s); }

  var rootG;

  function nodeSize(t) {
    var collapsed = state.simple || state.collapsed[t.qualified_name];
    var h = collapsed ? 46 : 46 + Math.min(t.columns.length, 14) * 14 + 6;
    return { w: 210, h: h };
  }

  function defaultLayout(kind) {
    var cx = 550, cy = 360;
    if (kind === "star") {
      // 관계가 가장 많은 테이블을 중심에
      var degree = {};
      state.rels.forEach(function (r) {
        degree[r.from_table] = (degree[r.from_table] || 0) + 1;
        degree[r.to_table] = (degree[r.to_table] || 0) + 1;
      });
      var sorted = state.tables.slice().sort(function (a, b) {
        return (degree[b.qualified_name] || 0) - (degree[a.qualified_name] || 0);
      });
      sorted.forEach(function (t, i) {
        if (i === 0) { state.pos[t.qualified_name] = { x: cx, y: cy }; return; }
        var ang = (i - 1) / (sorted.length - 1) * Math.PI * 2;
        state.pos[t.qualified_name] = { x: cx + Math.cos(ang) * 380, y: cy + Math.sin(ang) * 280 };
      });
    } else {
      // schema 별 그룹 grid
      var bySchema = {};
      state.tables.forEach(function (t) { (bySchema[t.schema] = bySchema[t.schema] || []).push(t); });
      var sx = 60;
      Object.keys(bySchema).forEach(function (s) {
        bySchema[s].forEach(function (t, i) {
          state.pos[t.qualified_name] = { x: sx + (i % 2) * 250, y: 60 + Math.floor(i / 2) * 230 };
        });
        sx += 540;
      });
    }
  }

  function render() {
    svg.innerHTML = "";
    var defs = el("defs", {}, svg);
    var marker = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#4a5a85" }, marker);

    rootG = el("g", { transform: "translate(" + state.view.x + "," + state.view.y + ") scale(" + state.view.k + ")" }, svg);

    // edges
    state.rels.forEach(function (r) {
      var p1 = state.pos[r.from_table], p2 = state.pos[r.to_table];
      if (!p1 || !p2) return;
      var s1 = nodeSize(byName(r.from_table)), s2 = nodeSize(byName(r.to_table));
      var x1 = p1.x + s1.w / 2, y1 = p1.y + s1.h / 2;
      var x2 = p2.x + s2.w / 2, y2 = p2.y + s2.h / 2;
      el("path", { "class": "edge-line", d: "M" + x1 + "," + y1 + " C" + ((x1 + x2) / 2) + "," + y1 + " " + ((x1 + x2) / 2) + "," + y2 + " " + x2 + "," + y2 }, rootG);
      var lbl = el("text", { "class": "edge-label", x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 4, "text-anchor": "middle" }, rootG);
      lbl.textContent = r.from_column + " → " + r.to_column;
    });

    // nodes
    state.tables.forEach(function (t) {
      var p = state.pos[t.qualified_name];
      if (!p) return;
      var size = nodeSize(t);
      var g = el("g", { transform: "translate(" + p.x + "," + p.y + ")", "data-table": t.qualified_name, cursor: "move" }, rootG);
      var box = el("rect", { "class": "node-box" + (state.selected === t.qualified_name ? " hl" : ""), width: size.w, height: size.h, rx: 10 }, g);
      el("rect", { width: size.w, height: 4, y: 0, rx: 2, fill: SCHEMA_COLORS[t.schema] || "#888" }, g);
      var title = el("text", { "class": "node-title", x: 10, y: 22 }, g);
      title.textContent = t.name;
      var sub = el("text", { "class": "node-schema", x: 10, y: 36 }, g);
      sub.textContent = t.schema + " · " + t.row_estimate + " rows";
      if (!state.simple && !state.collapsed[t.qualified_name]) {
        t.columns.slice(0, 14).forEach(function (c, i) {
          var cls = "node-field" + (c.is_pk ? " pk" : c.is_fk ? " fk" : "");
          var f = el("text", { "class": cls, x: 12, y: 52 + i * 14 }, g);
          f.textContent = (c.is_pk ? "🔑 " : c.is_fk ? "🔗 " : "") + c.name + " : " + c.type;
        });
        if (t.columns.length > 14) {
          var more = el("text", { "class": "node-field", x: 12, y: 52 + 14 * 14 }, g);
          more.textContent = "… " + (t.columns.length - 14) + "개 필드 더";
        }
      }
      attachNodeEvents(g, t, box);
    });
  }

  function byName(q) {
    for (var i = 0; i < state.tables.length; i++)
      if (state.tables[i].qualified_name === q) return state.tables[i];
    return { columns: [] };
  }

  function attachNodeEvents(g, t, box) {
    var drag = null;
    g.addEventListener("mousedown", function (e) {
      e.stopPropagation();
      var p = state.pos[t.qualified_name];
      drag = { sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false };
      function mv(ev) {
        drag.moved = true;
        p.x = drag.ox + (ev.clientX - drag.sx) / state.view.k;
        p.y = drag.oy + (ev.clientY - drag.sy) / state.view.k;
        render();
      }
      function up() {
        document.removeEventListener("mousemove", mv);
        document.removeEventListener("mouseup", up);
        if (!drag.moved) selectTable(t.qualified_name, false);
      }
      document.addEventListener("mousemove", mv);
      document.addEventListener("mouseup", up);
    });
    g.addEventListener("dblclick", function (e) {
      e.stopPropagation();
      state.collapsed[t.qualified_name] = !state.collapsed[t.qualified_name];
      render();
    });
  }

  /* pan & zoom */
  (function () {
    var pan = null;
    svg.addEventListener("mousedown", function (e) {
      pan = { sx: e.clientX, sy: e.clientY, ox: state.view.x, oy: state.view.y };
      function mv(ev) {
        state.view.x = pan.ox + ev.clientX - pan.sx;
        state.view.y = pan.oy + ev.clientY - pan.sy;
        render();
      }
      function up() {
        document.removeEventListener("mousemove", mv);
        document.removeEventListener("mouseup", up);
      }
      document.addEventListener("mousemove", mv);
      document.addEventListener("mouseup", up);
    });
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      zoom(e.deltaY < 0 ? 1.1 : 0.9);
    }, { passive: false });
  })();

  function zoom(f) {
    state.view.k = Math.max(0.25, Math.min(3, state.view.k * f));
    render();
  }

  function fit() {
    var xs = [], ys = [];
    state.tables.forEach(function (t) {
      var p = state.pos[t.qualified_name];
      if (!p) return;
      var s = nodeSize(t);
      xs.push(p.x, p.x + s.w); ys.push(p.y, p.y + s.h);
    });
    if (!xs.length) return;
    var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    var wrap = document.getElementById("canvasWrap");
    var w = wrap.clientWidth || window.innerWidth - 480;
    var h = wrap.clientHeight || window.innerHeight - 340;
    var k = Math.min(w / (maxX - minX + 80), h / (maxY - minY + 80), 1.5);
    if (!isFinite(k) || k <= 0.05) k = 0.5;
    state.view = { k: k, x: -minX * k + 40, y: -minY * k + 40 };
    render();
  }

  function centerOn(q) {
    var p = state.pos[q];
    if (!p) return;
    var wrap = document.getElementById("canvasWrap");
    var s = nodeSize(byName(q));
    state.view.x = wrap.clientWidth / 2 - (p.x + s.w / 2) * state.view.k;
    state.view.y = wrap.clientHeight / 2 - (p.y + s.h / 2) * state.view.k;
    render();
  }

  function selectTable(q, center) {
    state.selected = q;
    if (center !== false) centerOn(q);
    render();
    renderList();
    renderDetail(q);
    loadTableData(q);
  }

  /* left list */
  function renderList() {
    var box = document.getElementById("tableList");
    box.innerHTML = "";
    state.tables.forEach(function (t) {
      var d = document.createElement("div");
      d.className = "tbl-item" + (state.selected === t.qualified_name ? " sel" : "");
      d.innerHTML = '<span class="schema-dot" style="background:' + (SCHEMA_COLORS[t.schema] || "#888") + '"></span>' +
        "<span>" + esc(t.name) + '</span><span class="badge">' + esc(t.schema) + "</span>";
      d.addEventListener("click", function () { selectTable(t.qualified_name, true); });
      box.appendChild(d);
    });
  }

  /* right detail */
  function renderDetail(q) {
    var t = byName(q);
    var box = document.getElementById("detailPanel");
    var h = "<b>" + esc(t.qualified_name) + "</b><div class='muted'>" + esc(t.comment || "") + "</div>" +
      "<div class='muted'>rows ≈ " + t.row_estimate + "</div><hr style='border-color:var(--line)'>";
    (t.columns || []).forEach(function (c) {
      h += '<div class="detail-field"><span>' + (c.is_pk ? "🔑 " : c.is_fk ? "🔗 " : "") + esc(c.name) +
        '</span><span class="t">' + esc(c.type) + "</span></div>";
    });
    var rels = state.rels.filter(function (r) { return r.from_table === q || r.to_table === q; });
    if (rels.length) {
      h += "<h3>관계</h3>";
      rels.forEach(function (r) {
        h += '<div class="muted" style="font-size:11px">' + esc(r.from_table) + "." + esc(r.from_column) +
          " → " + esc(r.to_table) + "." + esc(r.to_column) + "</div>";
      });
    }
    box.innerHTML = h;
  }

  /* bottom data panel */
  function loadTableData(q) {
    var box = document.getElementById("bottomData");
    document.getElementById("bottomTitle").textContent = "테이블 데이터 — " + q;
    box.innerHTML = '<span class="muted">불러오는 중…</span>';
    fetch("/api/table-data?table=" + encodeURIComponent(q) + "&limit=30")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) { box.innerHTML = '<span class="chip bad">' + esc(d.error) + "</span>"; return; }
        var h = '<div class="muted">총 ' + d.total + "건 중 " + d.rows.length + '건 표시</div><div class="scroll-x"><table class="grid"><thead><tr>';
        d.columns.forEach(function (c) { h += "<th>" + esc(c) + "</th>"; });
        h += "</tr></thead><tbody>";
        d.rows.forEach(function (r) {
          h += "<tr>";
          r.forEach(function (v) { h += "<td>" + esc(v) + "</td>"; });
          h += "</tr>";
        });
        box.innerHTML = h + "</tbody></table></div>";
      });
  }

  /* toolbar */
  document.getElementById("btnZoomIn").addEventListener("click", function () { zoom(1.2); });
  document.getElementById("btnZoomOut").addEventListener("click", function () { zoom(0.83); });
  document.getElementById("btnFit").addEventListener("click", fit);
  document.getElementById("btnGridLayout").addEventListener("click", function () { defaultLayout("grid"); fit(); });
  document.getElementById("btnStarLayout").addEventListener("click", function () { defaultLayout("star"); fit(); });
  document.getElementById("btnSimple").addEventListener("click", function () { state.simple = !state.simple; render(); });
  document.getElementById("btnSavePos").addEventListener("click", function () {
    EmpProjects.setJSON(POS_KEY, state.pos);
    document.getElementById("schemaStatus").textContent = "위치 저장됨 " + new Date().toLocaleTimeString();
  });
  document.getElementById("btnResetPos").addEventListener("click", function () {
    state.pos = {};
    EmpProjects.setJSON(POS_KEY, {});
    defaultLayout("grid");
    fit();
    document.getElementById("schemaStatus").textContent = "위치 초기화됨";
  });
  /* 그래프 크게 1→2→3단계 순환 */
  var sizeStage = 1;
  var SIZE_SCALE = { 1: 1, 2: 1.4, 3: 1.9 };
  document.getElementById("btnSizeStage").addEventListener("click", function () {
    sizeStage = sizeStage % 3 + 1;
    this.textContent = "그래프 크게 " + sizeStage + "단계";
    state.view.k = SIZE_SCALE[sizeStage] * 0.6;
    render();
  });
  document.getElementById("btnLeftPanel").addEventListener("click", function () {
    document.getElementById("leftPanel").classList.toggle("collapsed");
  });
  document.getElementById("btnRightPanel").addEventListener("click", function () {
    document.getElementById("rightPanel").classList.toggle("collapsed");
  });

  /* resizers */
  function hResize(handleId, panelId, invert) {
    var handle = document.getElementById(handleId);
    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      var panel = document.getElementById(panelId);
      var start = e.clientX, w0 = panel.offsetWidth;
      function mv(ev) {
        var d = ev.clientX - start;
        panel.style.width = Math.max(140, w0 + (invert ? -d : d)) + "px";
      }
      function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); }
      document.addEventListener("mousemove", mv);
      document.addEventListener("mouseup", up);
    });
  }
  hResize("leftResize", "leftPanel", false);
  hResize("rightResize", "rightPanel", true);
  document.getElementById("bottomResize").addEventListener("mousedown", function (e) {
    e.preventDefault();
    var panel = document.getElementById("bottomPanel");
    var start = e.clientY, h0 = panel.offsetHeight;
    function mv(ev) { panel.style.height = Math.max(60, h0 - (ev.clientY - start)) + "px"; }
    function up() { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); }
    document.addEventListener("mousemove", mv);
    document.addEventListener("mouseup", up);
  });

  /* init */
  fetch("/api/schema")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      state.tables = d.tables || [];
      state.rels = d.relationships || [];
      var needLayout = state.tables.some(function (t) { return !state.pos[t.qualified_name]; });
      if (needLayout) defaultLayout("grid");
      renderList();
      fit();
      /* 초기 로드 시 레이아웃 계산이 끝나기 전에 fit 이 실행될 수 있어 한 번 더 보정 */
      requestAnimationFrame(function () { requestAnimationFrame(fit); });
    })
    .catch(function () {
      document.getElementById("schemaStatus").textContent = "서버에 연결할 수 없습니다.";
    });
})();
