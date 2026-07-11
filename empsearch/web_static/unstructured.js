/* Data Integrator: 연결/테이블/카탈로그/Cloud Storage/Lakehouse Pipeline/비정형/멀티모달 */
(function () {
  EmpNav("/data-manager");

  var K = {
    profiles: "empsearch.dataManager.dbProfiles.v1",
    history: "empsearch.dataManager.dbConnectionHistory.v1",
    snapshots: "empsearch.dataManager.schemaSnapshots.v1",
    usage: "empsearch.dataManager.tableUsage.v1",
    datasets: "empsearch.dataManager.datasets.v1",
    storage: "empsearch.dataManager.storageProfiles.v1",
    pipelines: "empsearch.dataManager.pipelines.v1",
    docs: "empsearch.dataIntegration.documents.v1",
    selection: "empsearch.dataIntegration.selection.v1"
  };

  var DB_DEFAULTS = {
    postgresql: { port: "5432", host: "Host", db: "Database", ph: "empsearch" },
    oracle: { port: "1521", host: "Host", db: "Service Name / SID", ph: "ORCL" },
    mysql: { port: "3306", host: "Host", db: "Database", ph: "hr" },
    mariadb: { port: "3306", host: "Host", db: "Database", ph: "hr" },
    sqlserver: { port: "1433", host: "Host", db: "Database", ph: "master" },
    sqlite: { port: "-", host: "파일 경로", db: "DB 파일", ph: "./data/app.db" }
  };

  var PIPELINE_STEPS = ["Source Discovery", "Extract / Transcribe / OCR",
    "Profile & Quality Check", "Iceberg Snapshot Commit", "Ontology Sync", "Agent Dataset Publish"];

  var schemaCache = null;
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function get(k, fb) { return EmpProjects.getJSON(k, fb); }
  function set(k, v) { EmpProjects.setJSON(k, v); }
  function $(id) { return document.getElementById(id); }

  function loadSchema(cb) {
    if (schemaCache) return cb(schemaCache);
    fetch("/api/schema").then(function (r) { return r.json(); }).then(function (d) {
      schemaCache = d; cb(d);
    }).catch(function () { cb({ tables: [], relationships: [] }); });
  }

  /* ---------------- 탭 / 서브메뉴 ---------------- */
  document.querySelectorAll("#mainTabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#mainTabs button").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      ["structured", "unstructured", "multimodal"].forEach(function (t) {
        $("tab-" + t).hidden = (t !== b.dataset.tab);
      });
      if (b.dataset.tab === "multimodal") renderMultimodal();
    });
  });
  document.querySelectorAll("#structuredMenu button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#structuredMenu button").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      document.querySelectorAll(".di-sec").forEach(function (s) { s.hidden = true; });
      $("sec-" + b.dataset.sec).hidden = false;
      var init = { sources: renderSources, tables: renderTableManage, catalog: renderCatalog,
                   storage: renderStorage, pipeline: renderPipelines }[b.dataset.sec];
      if (init) init();
    });
  });

  /* ---------------- 연결 및 테스트 ---------------- */
  /* 연결 이름 자동 추천 */
  function suggestName() {
    if ($("dbName").dataset.userEdited === "1") return;
    var t = $("dbType").value, h = $("dbHost").value || "localhost", d = $("dbDatabase").value;
    $("dbName").value = t + "@" + h + (d ? "/" + d : "");
  }
  $("dbName").addEventListener("input", function () { this.dataset.userEdited = "1"; });
  ["dbHost", "dbDatabase"].forEach(function (id) { $(id).addEventListener("input", suggestName); });

  $("dbType").addEventListener("change", function () {
    var d = DB_DEFAULTS[this.value];
    $("dbPort").value = d.port === "-" ? "" : d.port;
    $("dbPort").placeholder = d.port;
    $("dbHostLabel").textContent = d.host;
    $("dbDatabaseLabel").textContent = d.db;
    $("dbDatabase").placeholder = d.ph;
    suggestName();
  });

  function profileFromForm() {
    return {
      id: "db" + Date.now().toString(36),
      type: $("dbType").value, name: $("dbName").value || ($("dbType").value + " 연결"),
      host: $("dbHost").value, port: $("dbPort").value,
      database: $("dbDatabase").value, user: $("dbUser").value,
      credAlias: $("dbCredAlias").value, createdAt: new Date().toISOString()
    };
  }

  function pushHistory(entry) {
    var h = get(K.history, []);
    h.unshift(entry);
    set(K.history, h.slice(0, 30));
    renderHistory();
  }

  $("btnDbTest").addEventListener("click", function () {
    var p = profileFromForm();
    var box = $("dbTestResult");
    box.innerHTML = "연결 테스트 중…";
    fetch("/api/database-info").then(function (r) { return r.json(); }).then(function (info) {
      var real = (p.type === "postgresql" || p.type === "mysql" || p.type === "mariadb");
      var msg = real
        ? "✅ 연결 성공 (임베디드 모드로 응답). engine: " + info.engine
        : "✅ 연결 프로필 검증 완료. " + p.type + " 서버 드라이버 연동은 향후 backend connector 과제입니다.";
      box.innerHTML = '<span class="chip good">' + esc(msg) + "</span>";
      pushHistory({ at: new Date().toISOString(), name: p.name, type: p.type, result: "success" });
    }).catch(function () {
      box.innerHTML = '<span class="chip bad">서버에 연결할 수 없습니다.</span>';
      pushHistory({ at: new Date().toISOString(), name: p.name, type: p.type, result: "fail" });
    });
  });

  $("btnDbInfo").addEventListener("click", function () {
    fetch("/api/database-info").then(function (r) { return r.json(); }).then(function (info) {
      var h = '<pre class="code">' + esc(JSON.stringify(info, null, 2)) + "</pre>";
      $("dbTestResult").innerHTML = h;
    });
  });

  $("btnDbSave").addEventListener("click", function () {
    var list = get(K.profiles, []);
    list.push(profileFromForm());
    set(K.profiles, list);
    renderProfiles();
    $("dbTestResult").innerHTML = '<span class="chip good">프로필 저장됨</span>';
  });

  function renderProfiles() {
    var list = get(K.profiles, []);
    var box = $("dbProfileList");
    if (!list.length) { box.innerHTML = "저장된 연결이 없습니다."; return; }
    box.innerHTML = "";
    list.forEach(function (p) {
      var d = document.createElement("div");
      d.className = "list-item";
      d.innerHTML = "<b>" + esc(p.name) + '</b> <span class="badge">' + esc(p.type) + "</span>" +
        '<div class="muted">' + esc(p.host || "-") + ":" + esc(p.port || "-") + " / " + esc(p.database || "-") +
        (p.credAlias ? " · alias: " + esc(p.credAlias) : "") + "</div>" +
        '<div class="btn-row"><button class="small ghost" data-act="tables">테이블 정보 가져오기</button>' +
        '<button class="small danger" data-act="del">삭제</button></div>';
      d.querySelector('[data-act="del"]').addEventListener("click", function (e) {
        e.stopPropagation();
        set(K.profiles, get(K.profiles, []).filter(function (x) { return x.id !== p.id; }));
        renderProfiles();
      });
      d.querySelector('[data-act="tables"]').addEventListener("click", function (e) {
        e.stopPropagation();
        document.querySelector('#structuredMenu button[data-sec="tables"]').click();
      });
      box.appendChild(d);
    });
  }

  function renderHistory() {
    var h = get(K.history, []);
    $("dbHistoryList").innerHTML = h.length
      ? h.slice(0, 10).map(function (e) {
          return '<div class="muted" style="font-size:11px">' +
            (e.result === "success" ? "✅" : "❌") + " " + esc(e.name) + " (" + esc(e.type) + ") — " +
            new Date(e.at).toLocaleString() + "</div>";
        }).join("")
      : "히스토리가 없습니다.";
  }

  /* ---------------- 연결된 데이터 소스 ---------------- */
  function renderSources() {
    loadSchema(function (d) {
      var bySchema = {};
      (d.tables || []).forEach(function (t) {
        var s = bySchema[t.schema] = bySchema[t.schema] || { tables: 0, rows: 0 };
        s.tables++; s.rows += t.row_estimate;
      });
      var box = $("sourceCards");
      box.innerHTML = "";
      var labels = {
        public: "직원관리 DB (PostgreSQL 시뮬레이션)",
        ganada: "가나다 표준조직 schema",
        employee_salary_db: "급여 DB (MySQL 시뮬레이션)",
        employee_evaluation_db: "평가 DB (MySQL 시뮬레이션)"
      };
      Object.keys(bySchema).forEach(function (s) {
        var c = document.createElement("div");
        c.className = "src-card";
        c.innerHTML = "<h4>🗄️ " + esc(s) + "</h4><div class='muted'>" + esc(labels[s] || "") + "</div>" +
          '<div style="margin-top:6px"><span class="chip">' + bySchema[s].tables + ' tables</span>' +
          '<span class="chip">' + bySchema[s].rows.toLocaleString() + " rows</span></div>";
        c.addEventListener("click", function () {
          document.querySelector('#structuredMenu button[data-sec="tables"]').click();
        });
        box.appendChild(c);
      });
      get(K.profiles, []).forEach(function (p) {
        var c = document.createElement("div");
        c.className = "src-card";
        c.innerHTML = "<h4>🔌 " + esc(p.name) + "</h4><div class='muted'>" + esc(p.type) + " · " +
          esc(p.host || "-") + "</div><div style='margin-top:6px'><span class='chip warn'>외부 프로필</span></div>";
        box.appendChild(c);
      });
    });
  }

  /* ---------------- 테이블 관리 ---------------- */
  var selectedTable = null;
  function renderTableManage() {
    loadSchema(function (d) {
      var schemas = [];
      (d.tables || []).forEach(function (t) { if (schemas.indexOf(t.schema) < 0) schemas.push(t.schema); });
      var checksBox = $("schemaChecks");
      var checked = get("empsearch.dataManager.schemaFilter.v1", null) || schemas;
      checksBox.innerHTML = "";
      schemas.forEach(function (s) {
        var l = document.createElement("label");
        l.className = "f";
        l.style.marginBottom = "4px";
        l.innerHTML = '<input type="checkbox" class="doc-check" value="' + esc(s) + '"' +
          (checked.indexOf(s) >= 0 ? " checked" : "") + "> " + esc(s);
        l.querySelector("input").addEventListener("change", function () {
          var now = [];
          checksBox.querySelectorAll("input:checked").forEach(function (i) { now.push(i.value); });
          set("empsearch.dataManager.schemaFilter.v1", now);
          renderTableList(d, now);
        });
        checksBox.appendChild(l);
      });
      renderTableList(d, checked);
    });
  }

  function renderTableList(d, schemas) {
    var usage = get(K.usage, {});
    var box = $("tableManageList");
    box.innerHTML = "";
    (d.tables || []).filter(function (t) { return schemas.indexOf(t.schema) >= 0; }).forEach(function (t) {
      var q = t.qualified_name;
      var used = usage[q] !== false;
      var row = document.createElement("div");
      row.className = "tbl-row" + (used ? "" : " disabled") + (selectedTable === q ? " sel" : "");
      row.innerHTML = '<input type="checkbox" class="doc-check"' + (used ? " checked" : "") + ">" +
        '<span class="grow">' + esc(t.name) + '</span><span class="badge">' + esc(t.schema) + "</span>" +
        '<span class="muted">' + t.row_estimate.toLocaleString() + "</span>";
      row.querySelector("input").addEventListener("change", function (e) {
        usage[q] = e.target.checked;
        set(K.usage, usage);
        row.classList.toggle("disabled", !e.target.checked);
      });
      row.addEventListener("click", function (e) {
        if (e.target.tagName === "INPUT") return;
        selectedTable = q;
        box.querySelectorAll(".tbl-row").forEach(function (r) { r.classList.remove("sel"); });
        row.classList.add("sel");
        renderTableDetail(t, d);
      });
      box.appendChild(row);
    });
  }

  function renderTableDetail(t, d) {
    var box = $("tableManageDetail");
    var h = "<b>" + esc(t.qualified_name) + "</b><div class='muted'>" + esc(t.comment || "") +
      " · rows ≈ " + t.row_estimate.toLocaleString() + "</div>" +
      '<div class="btn-row" style="margin:8px 0"><button class="small good" id="btnSetTarget">작업 대상으로 지정</button></div><h3>필드</h3>';
    t.columns.forEach(function (c) {
      h += '<div class="detail-field" style="display:flex;justify-content:space-between;font-size:12px;border-bottom:1px dashed var(--line);padding:2px 0">' +
        "<span>" + (c.is_pk ? "🔑 " : c.is_fk ? "🔗 " : "") + esc(c.name) + '</span><span class="muted">' + esc(c.type) + "</span></div>";
    });
    var rels = (d.relationships || []).filter(function (r) {
      return r.from_table === t.qualified_name || r.to_table === t.qualified_name;
    });
    if (rels.length) {
      h += "<h3>관계</h3>" + rels.map(function (r) {
        return '<div class="muted" style="font-size:11px">' + esc(r.from_table) + "." + esc(r.from_column) +
          " → " + esc(r.to_table) + "." + esc(r.to_column) + "</div>";
      }).join("");
    }
    box.innerHTML = h;
    $("btnSetTarget").addEventListener("click", function () {
      var sel = get(K.selection, {});
      sel.workTargetTable = t.qualified_name;
      set(K.selection, sel);
      alert("작업 대상 테이블로 지정: " + t.qualified_name);
    });
  }

  /* ---------------- Data Catalog ---------------- */
  function renderCatalog() {
    renderSnapshots();
    renderDatasets();
    loadSchema(function (d) {
      var box = $("dsTables");
      box.innerHTML = "";
      (d.tables || []).forEach(function (t) {
        var l = document.createElement("label");
        l.style.cssText = "display:flex;gap:6px;align-items:center;font-size:12px";
        l.innerHTML = '<input type="checkbox" class="doc-check" value="' + esc(t.qualified_name) + '"> ' + esc(t.qualified_name);
        box.appendChild(l);
      });
      var m = $("catalogMetrics");
      var snaps = get(K.snapshots, []), ds = get(K.datasets, []),
          pls = get(K.pipelines, []), st = get(K.storage, []);
      m.innerHTML = [["Snapshot", snaps.length], ["Dataset", ds.length],
        ["Pipeline", pls.length], ["Storage", st.length],
        ["테이블", (d.tables || []).length]].map(function (x) {
          return '<div class="metric"><div class="v">' + x[1] + '</div><div class="k">' + x[0] + "</div></div>";
        }).join("");
    });
  }

  $("btnSnapshot").addEventListener("click", function () {
    loadSchema(function (d) {
      var snaps = get(K.snapshots, []);
      snaps.unshift({
        id: "snap-" + Date.now().toString(36),
        at: new Date().toISOString(),
        tables: (d.tables || []).map(function (t) {
          return { name: t.qualified_name, rows: t.row_estimate, cols: t.columns.length };
        })
      });
      set(K.snapshots, snaps.slice(0, 20));
      renderSnapshots();
    });
  });

  $("btnSnapshotDiff").addEventListener("click", function () {
    var snaps = get(K.snapshots, []);
    var box = $("snapshotDiff");
    if (snaps.length < 2) { box.innerHTML = '<div class="muted">Snapshot 이 2개 이상 필요합니다.</div>'; return; }
    var a = snaps[1], b = snaps[0];
    var mapA = {}; a.tables.forEach(function (t) { mapA[t.name] = t; });
    var lines = [];
    b.tables.forEach(function (t) {
      var prev = mapA[t.name];
      if (!prev) lines.push("+ " + t.name + " (신규)");
      else if (prev.rows !== t.rows) lines.push("~ " + t.name + " rows " + prev.rows + " → " + t.rows);
    });
    a.tables.forEach(function (t) {
      if (!b.tables.some(function (x) { return x.name === t.name; })) lines.push("- " + t.name + " (삭제)");
    });
    box.innerHTML = "<h3>Snapshot Diff (" + a.id + " → " + b.id + ")</h3><pre class='code'>" +
      esc(lines.length ? lines.join("\n") : "변경 없음") + "</pre>";
  });

  function renderSnapshots() {
    var snaps = get(K.snapshots, []);
    $("snapshotTimeline").innerHTML = snaps.length
      ? snaps.map(function (s) {
          return '<div class="snap-item"><b>' + esc(s.id) + "</b> · " + new Date(s.at).toLocaleString() +
            ' · <span class="muted">' + s.tables.length + " tables</span></div>";
        }).join("")
      : '<div class="muted">Snapshot 이 없습니다.</div>';
  }

  $("btnDsCreate").addEventListener("click", function () {
    var tables = [];
    $("dsTables").querySelectorAll("input:checked").forEach(function (i) { tables.push(i.value); });
    if (!$("dsName").value || !tables.length) { alert("Dataset 이름과 테이블을 선택하세요."); return; }
    var ds = get(K.datasets, []);
    ds.unshift({ id: "ds-" + Date.now().toString(36), name: $("dsName").value,
      layer: $("dsLayer").value, tables: tables, at: new Date().toISOString() });
    set(K.datasets, ds);
    $("dsName").value = "";
    renderDatasets();
  });

  function renderDatasets() {
    var ds = get(K.datasets, []);
    var box = $("dsList");
    if (!ds.length) { box.innerHTML = "Dataset 이 없습니다."; return; }
    box.innerHTML = "";
    ds.forEach(function (d) {
      var e = document.createElement("div");
      e.className = "list-item";
      e.innerHTML = "<b>" + esc(d.name) + '</b> <span class="chip ' +
        (d.layer === "gold" ? "warn" : d.layer === "silver" ? "" : "good") + '">' + esc(d.layer) + "</span>" +
        '<div class="muted">' + d.tables.map(esc).join(", ") + "</div>" +
        '<button class="small danger" style="margin-top:6px">삭제</button>';
      e.querySelector("button").addEventListener("click", function () {
        set(K.datasets, get(K.datasets, []).filter(function (x) { return x.id !== d.id; }));
        renderDatasets();
      });
      box.appendChild(e);
    });
  }

  /* ---------------- Cloud Storage ---------------- */
  $("btnStTest").addEventListener("click", function () {
    var name = $("stName").value || "storage 연결";
    $("stTestResult").innerHTML = '<span class="chip good">✅ ' + esc(name) +
      " 연결 시뮬레이션 성공 — 실제 SDK/secret manager 연동은 backend connector 과제</span>";
  });

  $("btnStSave").addEventListener("click", function () {
    var p = {
      id: "st" + Date.now().toString(36),
      name: $("stName").value || "storage 연결",
      provider: $("stProvider").value, kind: $("stKind").value,
      bucket: $("stBucket").value, prefix: $("stPrefix").value,
      region: $("stRegion").value, credAlias: $("stCred").value,
      at: new Date().toISOString()
    };
    var list = get(K.storage, []);
    list.unshift(p);
    set(K.storage, list);
    renderStorage();
    $("stTestResult").innerHTML = '<span class="chip good">Storage 프로필 저장됨</span>';
  });

  function renderStorage() {
    var list = get(K.storage, []);
    var box = $("stList");
    if (!list.length) { box.innerHTML = "저장된 Storage 프로필이 없습니다."; return; }
    box.innerHTML = "";
    list.forEach(function (p) {
      var d = document.createElement("div");
      d.className = "list-item";
      d.innerHTML = "<b>" + esc(p.name) + '</b> <span class="badge">' + esc(p.provider) + "</span>" +
        '<span class="badge">' + esc(p.kind) + "</span>" +
        '<div class="muted">' + esc(p.bucket || "-") + "/" + esc(p.prefix || "") +
        " · " + esc(p.region || "-") + " · alias: " + esc(p.credAlias || "-") + "</div>" +
        '<div class="btn-row"><button class="small good" data-act="pl">Pipeline 소스로 지정</button>' +
        '<button class="small danger" data-act="del">삭제</button></div>';
      d.querySelector('[data-act="del"]').addEventListener("click", function () {
        set(K.storage, get(K.storage, []).filter(function (x) { return x.id !== p.id; }));
        renderStorage();
      });
      d.querySelector('[data-act="pl"]').addEventListener("click", function () {
        var sel = get(K.selection, {});
        sel.pipelineSourceProfile = p.id;
        set(K.selection, sel);
        document.querySelector('#structuredMenu button[data-sec="pipeline"]').click();
        setTimeout(function () {
          $("plStorageProfile").value = p.id;
          $("plSource").value = p.kind === "block" ? "block" : "object";
        }, 0);
      });
      box.appendChild(d);
    });
  }

  /* ---------------- Lakehouse Pipeline ---------------- */
  function initPipelineForm() {
    var box = $("plSteps");
    if (!box.children.length) {
      PIPELINE_STEPS.forEach(function (s, i) {
        var l = document.createElement("label");
        l.innerHTML = '<input type="checkbox" value="' + esc(s) + '"' + (i < 4 ? " checked" : "") + "> " + esc(s);
        box.appendChild(l);
      });
    }
    var sel = $("plStorageProfile");
    sel.innerHTML = '<option value="">-</option>';
    get(K.storage, []).forEach(function (p) {
      var o = document.createElement("option");
      o.value = p.id; o.textContent = p.name;
      sel.appendChild(o);
    });
    var pre = get(K.selection, {}).pipelineSourceProfile;
    if (pre) sel.value = pre;
  }

  $("btnPlCreate").addEventListener("click", function () {
    if (!$("plName").value) { alert("Pipeline 이름을 입력하세요."); return; }
    var steps = [];
    $("plSteps").querySelectorAll("input:checked").forEach(function (i) { steps.push(i.value); });
    var pls = get(K.pipelines, []);
    pls.unshift({
      id: "pl" + Date.now().toString(36),
      name: $("plName").value, source: $("plSource").value,
      storageProfile: $("plStorageProfile").value || null,
      layer: $("plLayer").value, schedule: $("plSchedule").value,
      steps: steps, runs: [], at: new Date().toISOString()
    });
    set(K.pipelines, pls);
    $("plName").value = "";
    renderPipelines();
  });

  function renderPipelines() {
    initPipelineForm();
    var pls = get(K.pipelines, []);
    var box = $("plList");
    if (!pls.length) { box.innerHTML = "생성된 Pipeline 이 없습니다."; return; }
    box.innerHTML = "";
    pls.forEach(function (p) {
      var d = document.createElement("div");
      d.className = "list-item";
      var lastRun = p.runs && p.runs[0];
      d.innerHTML = "<b>" + esc(p.name) + '</b> <span class="chip">' + esc(p.source) + "</span>" +
        '<span class="chip ' + (p.layer === "gold" ? "warn" : "") + '">' + esc(p.layer) + "</span>" +
        '<span class="chip">' + esc(p.schedule) + "</span>" +
        '<div class="muted">' + p.steps.map(esc).join(" → ") + "</div>" +
        (lastRun ? '<div class="muted">최근 실행: ' + esc(lastRun.snapshotId) + " · " + new Date(lastRun.at).toLocaleString() + "</div>" : "") +
        '<div class="btn-row"><button class="small good" data-act="run">실행 시뮬레이션</button>' +
        '<button class="small danger" data-act="del">삭제</button></div>';
      d.querySelector('[data-act="run"]').addEventListener("click", function () { runPipeline(p.id); });
      d.querySelector('[data-act="del"]').addEventListener("click", function () {
        set(K.pipelines, get(K.pipelines, []).filter(function (x) { return x.id !== p.id; }));
        renderPipelines();
      });
      box.appendChild(d);
    });
  }

  function runPipeline(id) {
    var pls = get(K.pipelines, []);
    var p = pls.filter(function (x) { return x.id === id; })[0];
    if (!p) return;
    var snapshotId = "iceberg-snap-" + Date.now().toString(16);
    var docs = get(K.docs, []);
    var mmCount = docs.filter(function (d) { return ["image", "audio", "video"].indexOf(d.kind) >= 0; }).length;
    var lines = ["▶ Pipeline: " + p.name + " (" + p.layer + " / " + p.schedule + ")"];
    p.steps.forEach(function (s, i) {
      var extra = "";
      if (s === "Source Discovery") extra = " — source=" + p.source + (p.storageProfile ? ", storage=" + p.storageProfile : "");
      if (s === "Extract / Transcribe / OCR") extra = " — 멀티모달 자산 " + mmCount + "건 후보";
      if (s === "Iceberg Snapshot Commit") extra = " — snapshot id: " + snapshotId;
      lines.push("  [" + (i + 1) + "/" + p.steps.length + "] " + s + " ✔" + extra);
    });
    lines.push("✅ 실행 완료 (시뮬레이션) " + new Date().toLocaleString());
    p.runs = p.runs || [];
    p.runs.unshift({ at: new Date().toISOString(), snapshotId: snapshotId, log: lines.join("\n") });
    set(K.pipelines, pls);
    $("plLog").textContent = lines.join("\n");
    renderPipelines();
  }

  /* ---------------- 비정형 데이터 ---------------- */
  var selectedDoc = null;

  $("btnUpload").addEventListener("click", function () {
    var files = $("fileInput").files;
    if (!files.length) { alert("파일을 선택하세요."); return; }
    var fd = new FormData();
    for (var i = 0; i < files.length; i++) fd.append("files", files[i]);
    $("unstructuredStatus").textContent = "분석 중…";
    fetch("/api/unstructured/upload", { method: "POST", body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var docs = get(K.docs, []);
        (d.results || []).forEach(function (r) {
          r.id = "doc" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
          r.at = new Date().toISOString();
          docs.unshift(r);
        });
        set(K.docs, docs);
        $("unstructuredStatus").innerHTML = '<span class="chip good">' + (d.results || []).length + "개 파일 분석 완료</span>";
        renderDocs();
      })
      .catch(function (e) { $("unstructuredStatus").innerHTML = '<span class="chip bad">업로드 실패: ' + esc(e) + "</span>"; });
  });

  $("btnUrl").addEventListener("click", function () {
    var url = $("urlInput").value.trim();
    if (!url) return;
    $("unstructuredStatus").textContent = "URL 분석 중…";
    fetch("/api/unstructured/url", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url })
    }).then(function (r) { return r.json(); })
      .then(function (r) {
        if (r.error) { $("unstructuredStatus").innerHTML = '<span class="chip bad">' + esc(r.error) + "</span>"; return; }
        r.id = "doc" + Date.now().toString(36);
        r.at = new Date().toISOString();
        r.filename = r.title || r.url;
        var docs = get(K.docs, []);
        docs.unshift(r);
        set(K.docs, docs);
        $("unstructuredStatus").innerHTML = '<span class="chip good">URL 분석 완료</span>';
        renderDocs();
      });
  });

  $("btnUseAll").addEventListener("click", function () {
    var docs = get(K.docs, []);
    docs.forEach(function (d) { d.inUse = true; });
    set(K.docs, docs);
    renderDocs();
    $("unstructuredStatus").innerHTML = '<span class="chip good">전체 ' + docs.length + "개 문서를 Ontology 분석 대상으로 지정</span>";
  });

  $("btnUseSelected").addEventListener("click", function () {
    var docs = get(K.docs, []);
    var n = 0;
    docs.forEach(function (d) {
      d.inUse = !!d.checked;
      if (d.inUse) n++;
    });
    set(K.docs, docs);
    renderDocs();
    $("unstructuredStatus").innerHTML = '<span class="chip good">선택 문서 ' + n + "개 사용 지정</span>";
  });

  function renderDocs() {
    var docs = get(K.docs, []);
    $("docCount").textContent = docs.length;
    var box = $("docList");
    if (!docs.length) { box.innerHTML = "수집된 문서가 없습니다."; return; }
    box.innerHTML = "";
    docs.forEach(function (doc) {
      var d = document.createElement("div");
      d.className = "list-item doc-item" + (selectedDoc === doc.id ? " sel" : "");
      d.innerHTML = '<input type="checkbox" class="doc-check"' + (doc.checked ? " checked" : "") + ">" +
        "<b>" + esc(doc.filename || doc.url) + "</b>" +
        '<span class="chip kind-tag' + (doc.inUse ? " good" : "") + '">' + esc(doc.kind_label || doc.kind) +
        (doc.inUse ? " · 사용중" : "") + "</span>" +
        '<div class="muted">' + (doc.keywords || []).slice(0, 6).map(esc).join(", ") + "</div>";
      d.querySelector("input").addEventListener("change", function (e) {
        var docs2 = get(K.docs, []);
        docs2.forEach(function (x) { if (x.id === doc.id) x.checked = e.target.checked; });
        set(K.docs, docs2);
      });
      d.addEventListener("click", function (e) {
        if (e.target.tagName === "INPUT") return;
        selectedDoc = doc.id;
        renderDocs();
        renderDocDetail(doc);
      });
      box.appendChild(d);
    });
  }

  function renderDocDetail(doc) {
    var h = "<b>" + esc(doc.filename || doc.url) + "</b> " +
      '<span class="chip">' + esc(doc.kind_label || doc.kind) + "</span>" +
      (doc.size ? '<span class="chip">' + doc.size.toLocaleString() + " bytes</span>" : "") +
      (doc.text_length ? '<span class="chip">텍스트 ' + doc.text_length.toLocaleString() + "자</span>" : "");
    if ((doc.keywords || []).length) {
      h += "<h3>주요 용어</h3>" + doc.keywords.map(function (k) { return '<span class="chip">' + esc(k) + "</span>"; }).join("");
    }
    if (doc.multimodal_hints) {
      h += "<h3>멀티모달 처리 힌트</h3>" + doc.multimodal_hints.map(function (k) {
        return '<span class="chip warn">' + esc(k) + "</span>";
      }).join("");
      if (doc.pipeline_candidate) h += '<div class="muted" style="margin-top:6px">Pipeline 후보: ' + esc(doc.pipeline_candidate) + "</div>";
    }
    if (doc.summary) h += "<h3>분석 내용</h3><div>" + esc(doc.summary) + "</div>";
    if (doc.content_preview) h += "<h3>파일 내용</h3><pre class='code' style='max-height:300px;overflow:auto'>" + esc(doc.content_preview) + "</pre>";
    $("docDetail").innerHTML = h;
    var docs = get(K.docs, []);
    docs.forEach(function (x) { if (x.id === doc.id) x.lastViewed = new Date().toISOString(); });
    set(K.docs, docs);
  }

  /* ---------------- 멀티모달 분석 ---------------- */
  function renderMultimodal() {
    var docs = get(K.docs, []).filter(function (d) { return ["image", "audio", "video"].indexOf(d.kind) >= 0; });
    var kinds = { image: 0, audio: 0, video: 0 };
    var totalSize = 0, totalText = 0;
    docs.forEach(function (d) { kinds[d.kind]++; totalSize += d.size || 0; totalText += d.text_length || 0; });
    $("mmMetrics").innerHTML = [
      ["자산 수", docs.length], ["이미지", kinds.image], ["음성", kinds.audio], ["영상", kinds.video],
      ["총 크기", (totalSize / 1024).toFixed(1) + "KB"], ["추출 텍스트", totalText + "자"]
    ].map(function (x) {
      return '<div class="metric"><div class="v">' + x[1] + '</div><div class="k">' + x[0] + "</div></div>";
    }).join("");
    var box = $("mmList");
    if (!docs.length) {
      box.innerHTML = "멀티모달 자산이 없습니다. 비정형 데이터 탭에서 이미지/음성/영상 파일을 업로드하세요.";
      return;
    }
    box.innerHTML = "";
    docs.forEach(function (doc) {
      var d = document.createElement("div");
      d.className = "list-item";
      d.innerHTML = "<b>" + esc(doc.filename) + '</b> <span class="chip warn">' + esc(doc.kind_label) + "</span>" +
        '<span class="chip">' + ((doc.size || 0) / 1024).toFixed(1) + "KB</span>" +
        "<div style='margin-top:4px'>" + (doc.multimodal_hints || []).map(function (k) {
          return '<span class="chip">' + esc(k) + "</span>";
        }).join("") + "</div>" +
        (doc.pipeline_candidate ? '<div class="muted">Pipeline 후보: ' + esc(doc.pipeline_candidate) + "</div>" : "");
      box.appendChild(d);
    });
  }

  /* ---------------- init ---------------- */
  renderProfiles();
  renderHistory();
  renderDocs();
})();
