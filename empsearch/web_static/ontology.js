/* Ontology Definer (2026-07-09 스펙)
 * 1. 온톨로지 생성  — 전체/선택 자동 실행, 진행 팝업, 생성 결과 검토
 * 2. 온톨로지 편집  — 선택 시 기존 정의 자동 로딩, 리뷰 메모 분리, 값 매핑 검증
 * 의미 관계 분석    — value_of/structured_fk/maps_to_column/alias_of/policy_of/evidence_for
 * 3. 버전관리       — export/import, git tree 버전, 테이블/필드 단위 삭제 */
(function () {
  EmpNav("/ontology");

  var K = {
    versions: "empsearch.ontology.versions.v1",
    relations: "empsearch.ontology.semanticRelations.v1",
    docs: "empsearch.dataIntegration.documents.v1"
  };
  var project = EmpProjects.current().id;

  var state = {
    schema: { tables: [], relationships: [] },
    defs: [],
    selType: "field", selTable: null, selField: null,
    reviewQueue: [],
    relations: EmpProjects.getJSON(K.relations, []),
    relSel: null,
    relView: 0, relDepth: 1
  };
  var REL_VIEWS = ["관계 중심", "정형데이터소스", "DB 테이블", "비정형데이터"];

  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function $(id) { return document.getElementById(id); }
  function api(path, opts) { return fetch(path, opts).then(function (r) { return r.json(); }); }
  function post(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });
  }
  function saveRelations() { EmpProjects.setJSON(K.relations, state.relations); }
  function usedDocs() {
    return EmpProjects.getJSON(K.docs, []).filter(function (d) { return d.inUse; });
  }

  /* ================= 리뷰 메모 / 값 매핑 유틸 (스펙 명시 함수) ================= */

  var REVIEW_MARK = "[리뷰 메모]";

  /* description 에서 본문과 [리뷰 메모] 블록을 분리한다. */
  function splitDescriptionReviewNotes(description) {
    var text = description || "";
    var idx = text.indexOf(REVIEW_MARK);
    if (idx < 0) return { description: text.trim(), reviewNote: "" };
    return {
      description: text.slice(0, idx).trim(),
      reviewNote: text.slice(idx + REVIEW_MARK.length).trim()
    };
  }

  /* 본문 + 리뷰 메모를 저장용 description 으로 합친다. (중복 누적 방지) */
  function descriptionWithReviewNotes(description, reviewNote) {
    var base = splitDescriptionReviewNotes(description).description;
    if (!reviewNote) return base;
    return base + "\n\n" + REVIEW_MARK + "\n" + reviewNote;
  }

  /* 값 매핑 입력 검증: 배열 JSON, 각 항목은 객체이고 value 를 가져야 한다.
   * synonyms 는 배열 또는 문자열만 허용한다. 실패 시 Error throw. */
  function parseValueMappingsInput(raw) {
    raw = (raw || "").trim();
    if (!raw) return [];
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      throw new Error("값 매핑이 올바른 JSON 이 아닙니다: " + e.message);
    }
    if (!Array.isArray(parsed)) {
      throw new Error("값 매핑은 배열 JSON 이어야 합니다. 예: [{\"value\": \"active\", \"synonyms\": [\"재직\"]}]");
    }
    parsed.forEach(function (item, i) {
      if (typeof item !== "object" || item === null || Array.isArray(item)) {
        throw new Error("값 매핑 " + (i + 1) + "번째 항목이 객체가 아닙니다.");
      }
      if (!("value" in item) || String(item.value).trim() === "") {
        throw new Error("값 매핑 " + (i + 1) + "번째 항목에 value 가 없습니다.");
      }
      if ("synonyms" in item && !Array.isArray(item.synonyms) && typeof item.synonyms !== "string") {
        throw new Error("값 매핑 " + (i + 1) + "번째 항목의 synonyms 는 배열 또는 문자열이어야 합니다.");
      }
    });
    return parsed;
  }

  /* 동의어 입력: 쉼표 구분 문자열 또는 JSON 배열 허용 */
  function parseSynonymsInput(raw) {
    raw = (raw || "").trim();
    if (!raw) return "";
    if (raw[0] === "[") {
      var arr;
      try { arr = JSON.parse(raw); }
      catch (e) { throw new Error("동의어 JSON 배열 형식이 잘못되었습니다: " + e.message); }
      if (!Array.isArray(arr)) throw new Error("동의어는 배열 또는 문자열이어야 합니다.");
      return arr.join(",");
    }
    return raw;
  }

  /* 편집 폼 -> 저장 payload. 검증 실패 시 오류 메시지 표시 후 null. */
  function currentOntologyFormPayload() {
    var vm, syn;
    try {
      vm = parseValueMappingsInput($("edMap").value);
      syn = parseSynonymsInput($("edSyn").value);
    } catch (e) {
      $("edStatus").innerHTML = '<span class="chip bad">' + esc(e.message) + "</span>";
      return null;
    }
    var note = $("edNote").value.trim();
    return {
      target_type: state.selType || "field",
      table_name: state.selTable,
      field_name: state.selField || "",
      label: $("edLabel").value.trim(),
      description: descriptionWithReviewNotes($("edDesc").value.trim(), note),
      synonyms: syn,
      value_map: vm,
      use_in_sql: $("edUseSql").checked,
      review_note: note
    };
  }

  /* 정의 -> 편집 폼 반영 (필드 전환 시 이전 값이 남지 않도록 항상 전체 초기화) */
  function fillForm(d) {
    d = d || {};
    var split = splitDescriptionReviewNotes(d.description || "");
    $("edLabel").value = d.label || "";
    $("edDesc").value = split.description;
    $("edNote").value = split.reviewNote || d.review_note || "";
    $("edSyn").value = d.synonyms || "";
    var vm = d.value_map;
    $("edMap").value = (Array.isArray(vm) && vm.length) || (vm && !Array.isArray(vm) && Object.keys(vm).length)
      ? JSON.stringify(vm, null, 2) : "";
    $("edUseSql").checked = d.use_in_sql !== false;
    $("edStatus").textContent = "";
  }

  /* 현재 선택(테이블/필드)의 기존 정의를 찾아 로딩. 없으면 폼 초기화. */
  function loadDefinitionForCurrentSelection() {
    var d = state.defs.filter(function (x) {
      return x.table_name === state.selTable && (x.field_name || "") === (state.selField || "");
    })[0];
    fillForm(d || {});
    return d || null;
  }

  /* ================= 탭 ================= */
  document.querySelectorAll("#ontTabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#ontTabs button").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      ["generate", "edit", "relation", "version"].forEach(function (t) {
        $("tab-" + t).hidden = (t !== b.dataset.tab);
      });
      if (b.dataset.tab === "relation") { renderRelList(); renderRelGraph(); }
      if (b.dataset.tab === "version") { renderVersions(); fillDeleteSelectors(); }
    });
  });

  /* ================= 데이터 로드 ================= */
  function loadAll(cb) {
    Promise.all([
      api("/api/schema"),
      api("/api/ontology?project=" + encodeURIComponent(project))
    ]).then(function (rs) {
      state.schema = rs[0];
      state.defs = rs[1].definitions || [];
      renderGenTargets(); renderTree(); renderDefs(); renderDocsPanel(); fillDeleteSelectors();
      if (cb) cb();
    });
  }

  function reloadDefs(cb) {
    api("/api/ontology?project=" + encodeURIComponent(project)).then(function (d) {
      state.defs = d.definitions || [];
      renderDefs(); renderTree(); fillDeleteSelectors();
      if (cb) cb();
    });
  }

  /* ================= 1. 온톨로지 생성 ================= */
  function renderGenTargets() {
    var box = $("genTables");
    box.innerHTML = "";
    state.schema.tables.forEach(function (t) {
      var l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" value="' + esc(t.qualified_name) + '" checked> ' +
        esc(t.qualified_name) + ' <span class="badge">' + t.columns.length + " fields</span>";
      box.appendChild(l);
    });
    var dbox = $("genDocs");
    var docs = usedDocs();
    dbox.innerHTML = docs.length ? "" : "사용 지정된 문서가 없습니다. (Data Integrator 에서 지정)";
    docs.forEach(function (doc) {
      var l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" value="' + esc(doc.filename || doc.url) + '" checked> 📄 ' +
        esc(doc.filename || doc.url);
      dbox.appendChild(l);
    });
  }

  $("btnGenAllTables").addEventListener("click", function () {
    var inputs = $("genTables").querySelectorAll("input");
    var all = Array.prototype.every.call(inputs, function (i) { return i.checked; });
    inputs.forEach(function (i) { i.checked = !all; });
  });

  function showProgress(steps) {
    var box = $("progressSteps");
    box.innerHTML = "";
    steps.forEach(function (s, i) {
      var d = document.createElement("div");
      d.className = "progress-step pending";
      d.id = "pstep" + i;
      d.innerHTML = '<span class="st">○</span> ' + esc(s);
      box.appendChild(d);
    });
    $("progressModal").hidden = false;
  }
  function stepDone(i) {
    var d = $("pstep" + i);
    if (d) { d.className = "progress-step done"; d.querySelector(".st").textContent = "✔"; }
  }
  function hideProgress() {
    setTimeout(function () { $("progressModal").hidden = true; }, 500);
  }

  function runAutomate(tables, docNames) {
    showProgress(["DB / schema / table / field 분석", "필드 의미 자동 부여",
      "값 매핑 자동 생성", "비정형 문서 온톨로지 반영", "관계 Ontology 자동 생성"]);
    stepDone(0);
    post("/api/ontology/automate", { project: project, save: true, tables: tables })
      .then(function (d) {
        stepDone(1); stepDone(2);
        /* 비정형 문서 정의 저장 */
        var docDefs = usedDocs().filter(function (doc) {
          return !docNames || docNames.indexOf(doc.filename || doc.url) >= 0;
        }).map(function (doc) {
          return {
            target_type: "unstructured",
            table_name: "unstructured:" + (doc.filename || doc.url),
            field_name: "",
            label: (doc.filename || doc.url || "").replace(/\.[^.]+$/, ""),
            description: doc.summary || "",
            synonyms: (doc.keywords || []).slice(0, 8).join(","),
            value_map: [], use_in_sql: false
          };
        });
        var p = docDefs.length
          ? post("/api/ontology/import", { project: project, definitions: docDefs })
          : Promise.resolve({});
        return p.then(function () {
          stepDone(3);
          analyzeRelations(); /* 관계 Ontology 자동 생성 */
          stepDone(4);
          hideProgress();
          state.reviewQueue = (d.suggestions || []).sort(function (a, b) { return b.confidence - a.confidence; });
          $("genSummary").innerHTML = '<span class="chip good">정의 ' + d.saved +
            "건 생성/갱신</span> <span class='chip'>비정형 " + docDefs.length +
            "건</span> <span class='chip'>관계 후보 " + state.relations.length + "건</span>";
          renderReviewQueue();
          reloadDefs();
        });
      })
      .catch(function (e) {
        hideProgress();
        $("genSummary").innerHTML = '<span class="chip bad">실행 실패: ' + esc(e) + "</span>";
      });
  }

  $("btnGenAll").addEventListener("click", function () { runAutomate(null, null); });
  $("btnGenSelected").addEventListener("click", function () {
    var tables = [], docs = [];
    $("genTables").querySelectorAll("input:checked").forEach(function (i) { tables.push(i.value); });
    $("genDocs").querySelectorAll("input:checked").forEach(function (i) { docs.push(i.value); });
    if (!tables.length && !docs.length) { alert("생성 대상을 선택하세요."); return; }
    runAutomate(tables.length ? tables : [], docs);
  });

  function renderReviewQueue() {
    var box = $("reviewQueue");
    if (!state.reviewQueue.length) { box.innerHTML = ""; return; }
    box.innerHTML = "";
    state.reviewQueue.slice(0, 80).forEach(function (s, idx) {
      var card = document.createElement("div");
      card.className = "review-card" + (s._done ? " applied" : "");
      card.innerHTML = "<b>" + esc(s.label) + "</b> " +
        '<span class="badge">' + esc(s.target_type) + "</span>" +
        '<span class="badge">신뢰도 ' + s.confidence + "</span>" +
        '<div class="muted" style="font-size:10px">' + esc(s.table_name) +
        (s.field_name ? "." + esc(s.field_name) : "") + "</div>" +
        '<div class="conf-bar"><div class="conf-fill" style="width:' + Math.round(s.confidence * 100) + '%"></div></div>' +
        '<div style="font-size:12px">' + esc(s.description) + "</div>" +
        '<div class="evidence">근거: ' + (s.evidence || []).map(esc).join(" · ") + "</div>" +
        '<div class="btn-row" style="margin-top:6px">' +
        '<button class="small ghost" data-act="edit">편집으로 이동</button>' +
        '<button class="small danger" data-act="exclude">제외 (정의 삭제)</button></div>';
      card.querySelector('[data-act="edit"]').addEventListener("click", function () {
        document.querySelector('#ontTabs button[data-tab="edit"]').click();
        selectTarget(s.target_type, s.table_name, s.field_name || "");
      });
      card.querySelector('[data-act="exclude"]').addEventListener("click", function () {
        post("/api/ontology/delete", {
          project: project, target_type: s.target_type,
          table_name: s.table_name, field_name: s.field_name || ""
        }).then(function () {
          state.reviewQueue.splice(idx, 1);
          renderReviewQueue();
          reloadDefs();
        });
      });
      box.appendChild(card);
    });
  }

  /* ================= 2. 온톨로지 편집 ================= */
  function hasDef(table, field) {
    return state.defs.some(function (d) {
      return d.table_name === table && (d.field_name || "") === (field || "");
    });
  }

  function renderTree() {
    var box = $("semTree");
    box.innerHTML = "";
    state.schema.tables.forEach(function (t) {
      var div = document.createElement("div");
      div.className = "tree-table";
      var head = document.createElement("div");
      head.className = "t-head" + (state.selTable === t.qualified_name && !state.selField ? " sel" : "");
      head.innerHTML = "<span>📋 " + esc(t.name) + "</span>" +
        (hasDef(t.qualified_name, "") ? '<span style="color:var(--good)">●</span>' : "");
      head.addEventListener("click", function () {
        selectTarget("table", t.qualified_name, "");
      });
      div.appendChild(head);
      var fl = document.createElement("div");
      fl.className = "tree-fields";
      t.columns.forEach(function (c) {
        var f = document.createElement("div");
        f.className = "tree-field" + (state.selTable === t.qualified_name && state.selField === c.name ? " sel" : "");
        f.innerHTML = "<span>" + (c.is_pk ? "🔑 " : "") + esc(c.name) + "</span>" +
          (hasDef(t.qualified_name, c.name) ? '<span class="has-def">●</span>' : "");
        f.addEventListener("click", function () {
          selectTarget("field", t.qualified_name, c.name);
        });
        fl.appendChild(f);
      });
      div.appendChild(fl);
      box.appendChild(div);
    });
  }

  function renderDocsPanel() {
    var docs = usedDocs();
    var box = $("semDocs");
    if (!docs.length) { box.innerHTML = "사용 지정된 문서가 없습니다. (Data Integrator 에서 지정)"; return; }
    box.innerHTML = "";
    docs.forEach(function (doc) {
      var name = "unstructured:" + (doc.filename || doc.url);
      var d = document.createElement("div");
      d.className = "tree-field";
      d.style.cursor = "pointer";
      d.innerHTML = "<span>📄 " + esc(doc.filename || doc.url) + "</span>" +
        (hasDef(name, "") ? '<span class="has-def">●</span>' : "");
      d.addEventListener("click", function () {
        selectTarget("unstructured", name, "");
      });
      box.appendChild(d);
    });
  }

  /* 테이블/필드 선택: 기존 정의가 있으면 자동 로딩, 없으면 폼 초기화 */
  function selectTarget(type, table, field) {
    state.selType = type;
    state.selTable = table;
    state.selField = field;
    $("edTable").value = table;
    $("edField").value = field || "(테이블 전체)";
    loadDefinitionForCurrentSelection();
    renderTree();
    renderDefs();
  }

  function renderDefs() {
    $("defCount").textContent = state.defs.length;
    var box = $("defList");
    if (!state.defs.length) { box.innerHTML = "정의가 없습니다. 온톨로지 생성 탭에서 자동 실행하세요."; return; }
    box.innerHTML = "";
    state.defs.forEach(function (d) {
      var sel = state.selTable === d.table_name && (state.selField || "") === (d.field_name || "");
      var e = document.createElement("div");
      e.className = "def-item" + (sel ? " sel" : "");
      e.innerHTML = "<b>" + esc(d.label || "(라벨 없음)") + "</b>" +
        '<span class="badge">' + esc(d.target_type) + "</span>" +
        (d.use_in_sql ? '<span class="badge" style="color:var(--good)">SQL</span>' : "") +
        '<div class="path">' + esc(d.table_name) + (d.field_name ? "." + esc(d.field_name) : "") + "</div>";
      e.addEventListener("click", function () {
        selectTarget(d.target_type, d.table_name, d.field_name || "");
      });
      box.appendChild(e);
    });
  }

  $("btnDefSave").addEventListener("click", function () {
    if (!state.selTable) { alert("테이블/필드를 먼저 선택하세요."); return; }
    var payload = currentOntologyFormPayload();
    if (!payload) return; /* 검증 실패 - 오류 메시지 표시됨 */
    post("/api/ontology", { project: project, definition: payload }).then(function () {
      reloadDefs(function () {
        loadDefinitionForCurrentSelection();
        $("edStatus").innerHTML = '<span class="chip good">저장됨</span>';
      });
    });
  });

  $("btnDefDelete").addEventListener("click", function () {
    if (!state.selTable) return;
    post("/api/ontology/delete", {
      project: project, target_type: state.selType || "field",
      table_name: state.selTable, field_name: state.selField || ""
    }).then(function () {
      $("edStatus").innerHTML = '<span class="chip warn">삭제됨</span>';
      reloadDefs(function () { fillForm({}); });
    });
  });

  $("btnInferOne").addEventListener("click", function () {
    if (!state.selTable) { alert("테이블/필드를 먼저 선택하세요."); return; }
    post("/api/ontology/infer", {
      tables: [state.selTable], fields: state.selField ? [state.selField] : null
    }).then(function (d) {
      var s = (d.suggestions || []).filter(function (x) {
        return (x.field_name || "") === (state.selField || "");
      })[0] || (d.suggestions || [])[0];
      if (!s) { $("edStatus").textContent = "제안 없음"; return; }
      fillForm(s);
      $("edStatus").innerHTML = '<span class="chip good">자동 유추 반영 (신뢰도 ' + s.confidence + ")</span>";
    });
  });

  /* ================= 의미 관계 분석 ================= */
  function analyzeRelations() {
    var rels = [];
    var seen = {};
    function add(r) {
      var key = r.type + "|" + r.from + "|" + r.to;
      if (seen[key]) return;
      seen[key] = 1;
      var old = state.relations.filter(function (x) { return x.key === key; })[0];
      r.key = key;
      r.status = old ? old.status : "pending";
      r.id = old ? old.id : "rel" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
      rels.push(r);
    }
    /* structured_fk: DB FK 정의 */
    state.schema.relationships.forEach(function (r) {
      add({
        type: "structured_fk", from: r.from_table, to: r.to_table,
        fromLabel: r.from_table + "." + r.from_column, toLabel: r.to_table + "." + r.to_column,
        confidence: 0.98, reason: "DB Foreign Key 정의"
      });
    });
    /* maps_to_column: 동일 컬럼명 */
    var colIndex = {};
    state.schema.tables.forEach(function (t) {
      t.columns.forEach(function (c) {
        (colIndex[c.name] = colIndex[c.name] || []).push(t.qualified_name);
      });
    });
    Object.keys(colIndex).forEach(function (col) {
      var ts = colIndex[col];
      if (ts.length < 2 || ["name", "id", "created_at", "updated_at"].indexOf(col) >= 0) return;
      for (var i = 1; i < Math.min(ts.length, 4); i++) {
        add({
          type: "maps_to_column", from: ts[0], to: ts[i],
          fromLabel: ts[0] + "." + col, toLabel: ts[i] + "." + col,
          confidence: 0.8, reason: "동일 컬럼명 '" + col + "' — 의미 매핑 후보"
        });
      }
    });
    /* alias_of: Ontology 동의어가 다른 필드 라벨/이름과 일치 */
    var defsByLabel = {};
    state.defs.forEach(function (d) {
      if (d.label) (defsByLabel[d.label] = defsByLabel[d.label] || []).push(d);
    });
    Object.keys(defsByLabel).forEach(function (label) {
      var ds = defsByLabel[label];
      if (ds.length < 2) return;
      for (var i = 1; i < Math.min(ds.length, 4); i++) {
        if (ds[0].table_name === ds[i].table_name) continue;
        add({
          type: "alias_of",
          from: ds[0].table_name, to: ds[i].table_name,
          fromLabel: ds[0].table_name + "." + (ds[0].field_name || ""),
          toLabel: ds[i].table_name + "." + (ds[i].field_name || ""),
          confidence: 0.75, reason: "동일 온톨로지 표시명 '" + label + "'"
        });
      }
    });
    /* 비정형 문서 기반: value_of / policy_of / evidence_for */
    usedDocs().forEach(function (doc) {
      var fname = (doc.filename || doc.url || "").toLowerCase();
      var text = ((doc.content_preview || "") + " " + (doc.keywords || []).join(" ") + " " +
        (doc.summary || "")).toLowerCase();
      var isPolicy = /policy|정책|규정|rule|guideline|가이드|notice/.test(fname + " " + text.slice(0, 200));
      state.schema.tables.forEach(function (t) {
        var hits = [], valueHits = [];
        t.columns.forEach(function (c) {
          if (text.indexOf(c.name.toLowerCase()) >= 0) hits.push(c.name);
        });
        state.defs.forEach(function (d) {
          if (d.table_name !== t.qualified_name) return;
          (Array.isArray(d.value_map) ? d.value_map : []).forEach(function (item) {
            var words = [item.value].concat(item.synonyms || []);
            words.forEach(function (w) {
              if (w && String(w).length > 1 && text.indexOf(String(w).toLowerCase()) >= 0 &&
                  valueHits.indexOf(d.field_name) < 0) valueHits.push(d.field_name);
            });
          });
        });
        var docNode = "doc:" + (doc.filename || doc.url);
        if (valueHits.length) {
          add({
            type: "value_of", from: docNode, to: t.qualified_name,
            fromLabel: doc.filename || doc.url, toLabel: t.qualified_name,
            confidence: Math.min(0.95, 0.6 + valueHits.length * 0.1),
            reason: "문서가 필드 값/값 동의어를 언급: " + valueHits.slice(0, 5).join(", ")
          });
        }
        if (hits.length) {
          add({
            type: isPolicy ? "policy_of" : "evidence_for",
            from: docNode, to: t.qualified_name,
            fromLabel: doc.filename || doc.url, toLabel: t.qualified_name,
            confidence: Math.min(0.95, 0.5 + hits.length * 0.08),
            reason: (isPolicy ? "정책/규정 문서가 " : "문서가 근거로 ") +
              "필드를 언급: " + hits.slice(0, 6).join(", ")
          });
        }
      });
    });
    state.relations = rels;
    saveRelations();
  }

  $("btnRelAnalyze").addEventListener("click", function () {
    analyzeRelations();
    renderRelList(); renderRelGraph();
  });

  function relFiltered() {
    var type = $("relTypeFilter").value, st = $("relStatusFilter").value,
        q = $("relSearch").value.trim().toLowerCase();
    return state.relations.filter(function (r) {
      if (type && r.type !== type) return false;
      if (st && r.status !== st) return false;
      if (q && (r.fromLabel + " " + r.toLabel + " " + r.reason).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }

  ["relTypeFilter", "relStatusFilter"].forEach(function (id) {
    $(id).addEventListener("change", function () { renderRelList(); renderRelGraph(); });
  });
  $("relSearch").addEventListener("input", function () { renderRelList(); renderRelGraph(); });

  $("btnRelAutoApprove").addEventListener("click", function () {
    var th = parseFloat($("relAutoThreshold").value) || 0.85;
    var n = 0;
    state.relations.forEach(function (r) {
      if (r.status === "pending" && r.confidence >= th) { r.status = "approved"; n++; }
    });
    saveRelations();
    renderRelList(); renderRelGraph();
    $("relDetail").innerHTML = '<span class="chip good">신뢰도 ' + th + " 이상 " + n + "건 자동 승인</span>";
  });

  var STATUS_LABEL = { approved: "승인", pending: "승인대기", excluded: "제외" };

  function renderRelList() {
    var rels = relFiltered();
    $("relCount").textContent = rels.length;
    var box = $("relList");
    if (!rels.length) { box.innerHTML = '<div class="muted">관계 후보가 없습니다. 자동 관계 분석을 실행하세요.</div>'; return; }
    box.innerHTML = "";
    rels.forEach(function (r) {
      var d = document.createElement("div");
      d.className = "rel-item" + (state.relSel === r.id ? " sel" : "");
      d.innerHTML = '<span class="st-' + r.status + '">●</span> <b>' + esc(r.type) + "</b> " +
        '<span class="badge">' + r.confidence.toFixed(2) + "</span>" +
        "<div>" + esc(r.fromLabel) + " → " + esc(r.toLabel) + "</div>";
      d.addEventListener("click", function () {
        state.relSel = r.id;
        renderRelList(); renderRelGraph(); renderRelDetail(r);
      });
      box.appendChild(d);
    });
  }

  function renderRelDetail(r) {
    $("relDetail").innerHTML = "<b>" + esc(r.type) + "</b> " +
      '<span class="chip">신뢰도 ' + r.confidence.toFixed(2) + "</span>" +
      '<span class="chip ' + (r.status === "approved" ? "good" : r.status === "excluded" ? "bad" : "warn") + '">' +
      esc(STATUS_LABEL[r.status]) + "</span>" +
      "<div style='margin:6px 0'>" + esc(r.fromLabel) + " → " + esc(r.toLabel) + "</div>" +
      '<div class="muted">근거: ' + esc(r.reason) + "</div>" +
      '<div class="btn-row" style="margin-top:8px">' +
      '<button class="small good" id="btnRelApprove">승인</button>' +
      '<button class="small danger" id="btnRelExclude">제외</button>' +
      '<button class="small ghost" id="btnRelPending">승인대기로</button></div>';
    function setSt(st) {
      r.status = st;
      saveRelations();
      renderRelList(); renderRelGraph(); renderRelDetail(r);
    }
    $("btnRelApprove").addEventListener("click", function () { setSt("approved"); });
    $("btnRelExclude").addEventListener("click", function () { setSt("excluded"); });
    $("btnRelPending").addEventListener("click", function () { setSt("pending"); });
  }

  $("btnRelView").addEventListener("click", function () {
    state.relView = (state.relView + 1) % REL_VIEWS.length;
    this.textContent = "보기: " + REL_VIEWS[state.relView];
    renderRelGraph();
  });
  $("btnRelDepth").addEventListener("click", function () {
    state.relDepth = state.relDepth % 3 + 1;
    this.textContent = "그래프 " + state.relDepth + "단계";
    renderRelGraph();
  });

  function renderRelGraph() {
    var svg = $("relSvg");
    var NS = "http://www.w3.org/2000/svg";
    svg.innerHTML = "";
    var rels = relFiltered();
    var DOC_TYPES = ["value_of", "policy_of", "evidence_for"];
    if (state.relView === 1) rels = rels.filter(function (r) { return DOC_TYPES.indexOf(r.type) < 0; });
    if (state.relView === 2) rels = rels.filter(function (r) { return r.type === "structured_fk"; });
    if (state.relView === 3) rels = rels.filter(function (r) { return DOC_TYPES.indexOf(r.type) >= 0; });

    var center = null;
    if (state.relSel) {
      var sel = state.relations.filter(function (r) { return r.id === state.relSel; })[0];
      if (sel) center = sel.from;
    }
    if (center) {
      var keep = {}; keep[center] = 0;
      for (var d = 0; d < state.relDepth; d++) {
        rels.forEach(function (r) {
          if (keep[r.from] !== undefined && keep[r.to] === undefined) keep[r.to] = d + 1;
          if (keep[r.to] !== undefined && keep[r.from] === undefined) keep[r.from] = d + 1;
        });
      }
      rels = rels.filter(function (r) { return keep[r.from] !== undefined && keep[r.to] !== undefined; });
    }

    var nodes = {};
    rels.forEach(function (r) { nodes[r.from] = 1; nodes[r.to] = 1; });
    var names = Object.keys(nodes);
    if (!names.length) {
      var t0 = document.createElementNS(NS, "text");
      t0.setAttribute("x", 20); t0.setAttribute("y", 30);
      t0.setAttribute("fill", "#93a0bd"); t0.setAttribute("font-size", "12");
      t0.textContent = "표시할 관계가 없습니다. 자동 관계 분석을 실행하거나 필터를 조정하세요.";
      svg.appendChild(t0);
      return;
    }
    var W = svg.clientWidth || 700, H = svg.clientHeight || 380;
    var pos = {};
    var cx = W / 2, cy = H / 2;
    names.forEach(function (n, i) {
      if (center && n === center) { pos[n] = { x: cx, y: cy }; return; }
      var idx = center ? i - (names.indexOf(center) < i ? 1 : 0) : i;
      var total = center ? names.length - 1 : names.length;
      var ang = idx / Math.max(1, total) * Math.PI * 2;
      var rad = Math.min(W, H) / 2 - 60;
      pos[n] = { x: cx + Math.cos(ang) * rad, y: cy + Math.sin(ang) * rad };
    });

    rels.forEach(function (r) {
      var p1 = pos[r.from], p2 = pos[r.to];
      var line = document.createElementNS(NS, "line");
      line.setAttribute("x1", p1.x); line.setAttribute("y1", p1.y);
      line.setAttribute("x2", p2.x); line.setAttribute("y2", p2.y);
      line.setAttribute("class", "rel-edge " + r.status);
      line.addEventListener("click", function () {
        state.relSel = r.id;
        renderRelList(); renderRelDetail(r);
      });
      svg.appendChild(line);
    });
    names.forEach(function (n) {
      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", "rel-node" + (center === n ? " center" : ""));
      var c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", pos[n].x); c.setAttribute("cy", pos[n].y); c.setAttribute("r", 22);
      if (n.indexOf("doc:") === 0) c.setAttribute("fill", "#2c3a2f");
      g.appendChild(c);
      var t = document.createElementNS(NS, "text");
      t.setAttribute("x", pos[n].x); t.setAttribute("y", pos[n].y + 36);
      var label = n.replace(/^doc:/, "📄 ").split(".").pop();
      t.textContent = label.length > 22 ? label.slice(0, 21) + "…" : label;
      g.appendChild(t);
      g.addEventListener("click", function () {
        var first = state.relations.filter(function (r) { return r.from === n || r.to === n; })[0];
        if (first) { state.relSel = first.id; renderRelGraph(); renderRelList(); }
      });
      svg.appendChild(g);
    });
  }

  /* ================= 3. 버전관리 ================= */
  $("btnExport").addEventListener("click", function () {
    var payload = { exportedAt: new Date().toISOString(), project: project,
      definitions: state.defs, relations: state.relations };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "oafc-ontology-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
  });

  $("btnImport").addEventListener("click", function () { $("importFile").click(); });
  $("importFile").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var payload = JSON.parse(reader.result);
        post("/api/ontology/import", { project: project, definitions: payload.definitions || [] })
          .then(function (d) {
            if (payload.relations) { state.relations = payload.relations; saveRelations(); }
            $("verStatus").innerHTML = '<span class="chip good">Import 완료: 정의 ' + d.saved + "건</span>";
            reloadDefs();
          });
      } catch (e) { alert("Import 실패: " + e.message); }
    };
    reader.readAsText(f);
  });

  $("btnVerCreate").addEventListener("click", function () {
    var name = $("verName").value.trim() || ("버전 " + new Date().toLocaleString());
    var vers = EmpProjects.getJSON(K.versions, []);
    vers.unshift({ id: "v" + Date.now().toString(36), name: name, at: new Date().toISOString(),
      definitions: state.defs, relations: state.relations });
    EmpProjects.setJSON(K.versions, vers.slice(0, 20));
    $("verName").value = "";
    renderVersions();
  });

  function renderVersions() {
    var vers = EmpProjects.getJSON(K.versions, []);
    var box = $("verTree");
    if (!vers.length) { box.innerHTML = '<div class="muted">저장된 버전이 없습니다.</div>'; return; }
    box.innerHTML = "";
    vers.forEach(function (v, i) {
      var d = document.createElement("div");
      d.className = "ver-item";
      d.innerHTML = "<b>" + esc(v.name) + "</b>" + (i === 0 ? ' <span class="chip good">최신</span>' : "") +
        '<div class="muted">' + new Date(v.at).toLocaleString() +
        " · 정의 " + (v.definitions || []).length + "건, 관계 " + (v.relations || []).length + "건</div>" +
        '<div class="btn-row" style="margin-top:4px">' +
        '<button class="small good" data-act="restore">복원</button>' +
        '<button class="small danger" data-act="del">삭제</button></div>';
      d.querySelector('[data-act="restore"]').addEventListener("click", function () {
        if (!confirm("현재 Ontology 를 이 버전으로 복원할까요?")) return;
        post("/api/ontology/bulk-delete", { project: project, scope: "all" })
          .then(function () {
            return post("/api/ontology/import", { project: project, definitions: v.definitions || [] });
          })
          .then(function () {
            state.relations = v.relations || [];
            saveRelations();
            $("verStatus").innerHTML = '<span class="chip good">버전 복원 완료</span>';
            reloadDefs();
          });
      });
      d.querySelector('[data-act="del"]').addEventListener("click", function () {
        EmpProjects.setJSON(K.versions, EmpProjects.getJSON(K.versions, []).filter(function (x) { return x.id !== v.id; }));
        renderVersions();
      });
      box.appendChild(d);
    });
  }

  function fillDeleteSelectors() {
    var tsel = $("delTableSel");
    tsel.innerHTML = "";
    state.schema.tables.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.qualified_name; o.textContent = t.qualified_name;
      tsel.appendChild(o);
    });
    var fsel = $("delFieldSel");
    fsel.innerHTML = "";
    state.defs.filter(function (d) { return d.field_name; }).forEach(function (d) {
      var o = document.createElement("option");
      o.value = d.table_name + "|" + d.field_name;
      o.textContent = d.table_name + "." + d.field_name;
      fsel.appendChild(o);
    });
  }

  $("btnDelTable").addEventListener("click", function () {
    var t = $("delTableSel").value;
    if (!t || !confirm(t + " 테이블의 Ontology 를 모두 삭제할까요?")) return;
    post("/api/ontology/bulk-delete", { project: project, scope: "table", table: t })
      .then(function (d) {
        $("verStatus").innerHTML = '<span class="chip warn">' + d.deleted + "건 삭제</span>";
        reloadDefs();
      });
  });

  $("btnDelField").addEventListener("click", function () {
    var v = $("delFieldSel").value;
    if (!v) return;
    var parts = v.split("|");
    if (!confirm(parts[0] + "." + parts[1] + " 정의를 삭제할까요?")) return;
    post("/api/ontology/bulk-delete", {
      project: project, scope: "field", table: parts[0], field: parts[1]
    }).then(function (d) {
      $("verStatus").innerHTML = '<span class="chip warn">' + d.deleted + "건 삭제</span>";
      reloadDefs();
    });
  });

  $("btnDelAll").addEventListener("click", function () {
    if (!confirm("전체 Ontology 정의를 삭제할까요?")) return;
    post("/api/ontology/bulk-delete", { project: project, scope: "all" })
      .then(function (d) {
        $("verStatus").innerHTML = '<span class="chip warn">' + d.deleted + "건 삭제</span>";
        reloadDefs();
      });
  });

  $("btnResetMeta").addEventListener("click", function () {
    if (!confirm("생성 메타데이터(Ontology 정의)를 초기화할까요?")) return;
    post("/api/generated-metadata/reset", { project: project }).then(function () {
      $("verStatus").innerHTML = '<span class="chip warn">초기화 완료</span>';
      reloadDefs();
    });
  });

  /* ================= init ================= */
  loadAll();
})();
