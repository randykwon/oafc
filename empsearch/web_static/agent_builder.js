/* Agent Builder (2026-07-09 스펙)
 * Chat / Scenario / Manual / Flow Studio + Production Agent Factory
 * Capability Map, Agent Critic, System Prompt 생성, JSON 내보내기,
 * Prompt/Test Harness, 생성완료 -> Agent Shop (empsearch.agentBuilder.catalog.v1) */
(function () {
  EmpNav("/agent-builder");

  var K = {
    catalog: "empsearch.agentBuilder.catalog.v1",
    docs: "empsearch.dataIntegration.documents.v1",
    testHistory: "empsearch.agentBuilder.testHistory.v1"
  };

  var FLOW_NODES = ["input_parser", "ontology_mapper", "natural_language_sql", "table_report",
    "document_retriever", "evidence_graph", "report_generator", "evaluator"];
  var TOOLS = ["자연어 SQL 생성", "Ontology Query Planner", "테이블 리포트", "근거 그래프", "데이터 구조 탐색"];
  var FACTORY_STAGES = [
    ["Discover", "데이터/Ontology 자산 탐색과 요구사항 정의"],
    ["Design Canvas", "Agent 구조와 흐름 설계"],
    ["Runtime Configure", "모델/도구/제한 설정"],
    ["Quality Gates", "평가 세트와 품질 기준"],
    ["Deployment Pipeline", "배포 채널과 승인 절차"],
    ["Operations", "모니터링과 운영 대응"],
    ["Governance", "권한/감사/정책 준수"]
  ];
  var SAMPLES = [
    "광양 근무자 중 여성 18년 이상 근무하고 manager인 사람만 뽑아줘",
    "광양 근무자 중 여성 18년 이상 근무하고 manager가 아닌 사람만 뽑아줘",
    "포항에 근무하는 15년차 이상 여성 관리자를 찾아줘",
    "가나다 표준조직 2026 생산 조직을 보여줘",
    "STEEL-00001 이력을 보여줘",
    "2024년 S등급 평가 받은 사람",
    "2025년 월급 데이터 보여줘"
  ];

  var draft = null;
  var schemaCache = { tables: [] };
  var ontologyCount = 0;
  var flowCanvas = [];

  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function $(id) { return document.getElementById(id); }
  function catalog() { return EmpProjects.getJSON(K.catalog, []); }

  /* ---------------- 모드 탭 ---------------- */
  document.querySelectorAll("#modeTabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#modeTabs button").forEach(function (x) { x.classList.remove("on"); });
      b.classList.add("on");
      ["chat", "scenario", "manual", "flow", "factory"].forEach(function (m) {
        $("mode-" + m).hidden = (m !== b.dataset.mode);
      });
    });
  });

  /* ---------------- 설계 초안 공통 ---------------- */
  function newDraft(base) {
    draft = Object.assign({
      name: "", description: "", mode: "", approach: "Top-down",
      agentType: "Tool-Using Agent",
      tables: [], docs: [], tools: TOOLS.slice(0, 3),
      useOntology: true, rules: "", systemPrompt: "",
      flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report"],
      factoryStages: {}, createdAt: new Date().toISOString()
    }, base);
    renderDraft();
  }

  function buildSystemPrompt(d) {
    var lines = [
      "당신은 OAFC 에서 생성된 '" + d.name + "' Agent 입니다.",
      "목적: " + (d.description || "임직원 데이터 질의 응답"),
      "",
      "사용 가능한 데이터 소스:",
    ];
    d.tables.forEach(function (t) { lines.push("- " + t); });
    if (d.docs.length) {
      lines.push("", "참고 비정형 문서:");
      d.docs.forEach(function (x) { lines.push("- " + x); });
    }
    lines.push("", "사용 도구: " + d.tools.join(", "));
    if (d.useOntology) lines.push("Ontology 정의(동의어, 값 매핑)와 승인된 의미 관계를 조건 해석에 활용합니다.");
    if (d.rules) lines.push("", "운영 규칙:", d.rules);
    lines.push("", "항상 생성한 SQL 과 사용한 데이터/Ontology 근거를 함께 제시합니다.");
    return lines.join("\n");
  }

  /* Agent Critic: 설계 초안 점검 */
  function critique(d) {
    var issues = [];
    if (!d.tables.length) issues.push("데이터 소스(테이블)가 선택되지 않았습니다.");
    if (!d.tools.length) issues.push("사용 도구가 없습니다. 최소 1개 이상 선택하세요.");
    if (d.tools.indexOf("자연어 SQL 생성") >= 0 && !d.useOntology)
      issues.push("자연어 SQL 도구는 Ontology 활용 시 정확도가 올라갑니다.");
    if (!d.rules) issues.push("운영 규칙이 비어 있습니다. 민감 데이터 접근 규칙을 권장합니다.");
    if (!d.systemPrompt) issues.push("System Prompt 가 아직 생성되지 않았습니다.");
    if (d.flow.indexOf("evaluator") < 0) issues.push("flow 에 evaluator 단계가 없어 품질 게이트가 약합니다.");
    return issues;
  }

  function renderDraft() {
    if (!draft) { $("draftView").textContent = "아직 설계가 없습니다."; return; }
    $("draftView").innerHTML = "<b>" + esc(draft.name || "(이름 없음)") + "</b>" +
      '<span class="badge">' + esc(draft.mode) + "</span>" +
      '<span class="badge">' + esc(draft.agentType) + "</span>" +
      "<div style='margin:6px 0'>" + esc(draft.description || "-") + "</div>" +
      "<div>" + draft.tables.map(function (t) { return '<span class="chip">📋 ' + esc(t.split(".").pop()) + "</span>"; }).join("") +
      draft.docs.map(function (d) { return '<span class="chip good">📄 ' + esc(d) + "</span>"; }).join("") + "</div>" +
      (draft.useOntology ? '<span class="chip good">🧠 Ontology 활용</span>' : "") +
      (draft.rules ? '<div class="muted" style="margin-top:4px">운영 규칙: ' + esc(draft.rules.slice(0, 80)) + "</div>" : "");
    /* Capability Map */
    $("capabilityMap").innerHTML = "<h3 class='muted'>Capability Map</h3>" +
      draft.tools.map(function (t) { return '<span class="chip warn">🔧 ' + esc(t) + "</span>"; }).join("");
    /* Agent Critic */
    var issues = critique(draft);
    $("criticView").innerHTML = "<h3 class='muted'>Agent Critic</h3>" +
      (issues.length
        ? issues.map(function (i) { return '<div class="critic-item">⚠ ' + esc(i) + "</div>"; }).join("")
        : '<div class="critic-item ok">✔ 설계 점검 통과</div>');
    /* Flow */
    $("flowView").innerHTML = "<h3 class='muted'>Agent Flow</h3>" + draft.flow.map(function (n, i) {
      return '<div class="flow-step"><span class="n">' + (i + 1) + "</span> " + esc(n) + "</div>";
    }).join("");
  }

  /* ---------------- Chat Studio ---------------- */
  $("btnChatAnalyze").addEventListener("click", function () {
    var idea = $("chatStudioInput").value.trim();
    if (!idea) return;
    $("chatStudioInput").value = "";
    var log = $("chatStudioLog");
    log.innerHTML += '<div class="u">🙋 ' + esc(idea) + "</div>";

    var flow = ["input_parser", "ontology_mapper"];
    var tables = ["public.employee_information"];
    var tools = ["자연어 SQL 생성", "테이블 리포트"];
    if (/이력|변경|이동|전보|히스토리/.test(idea)) tables.push("public.employee_department_change_history", "public.employee_change_history");
    if (/평가|성과|고과/.test(idea)) tables.push("employee_evaluation_db.evaluation_scores");
    if (/급여|월급|연봉|보상/.test(idea)) tables.push("employee_salary_db.salary_payments");
    if (/조직|표준부서/.test(idea)) tables.push("ganada.org_structure");
    if (/문서|정책|규정|가이드/.test(idea)) {
      flow.push("document_retriever", "evidence_graph");
      tools.push("근거 그래프");
    }
    flow.push("natural_language_sql", "table_report");
    if (/리포트|보고|report/.test(idea)) flow.push("report_generator");
    flow.push("evaluator");

    newDraft({
      name: (idea.length > 24 ? idea.slice(0, 22) + "…" : idea) + " Agent",
      description: idea, mode: "Chat Studio",
      tables: tables, tools: tools, flow: flow
    });
    draft.systemPrompt = buildSystemPrompt(draft);
    renderDraft();
    log.innerHTML += '<div class="b">🤖 설계 초안을 생성했습니다.<br>' +
      "- 추천 데이터: " + tables.map(esc).join(", ") + "<br>" +
      "- 추천 도구: " + tools.join(", ") + "<br>" +
      "- Flow: " + flow.join(" → ") + "<br>" +
      "우측 초안을 확인하고 Test Harness 로 검증한 뒤 생성완료를 누르세요.</div>";
    log.scrollTop = log.scrollHeight;
  });

  /* ---------------- Scenario Studio ---------------- */
  function renderScenarios() {
    var scenarios = [
      {
        name: "임직원 검색 Agent", desc: "자연어로 임직원을 검색하고 SQL/근거와 함께 답하는 기본 Agent",
        tables: ["public.employee_information", "public.department_management_information"],
        tools: ["자연어 SQL 생성", "테이블 리포트"],
        flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report"]
      },
      {
        name: "부서 이동 분석 Agent", desc: "부서 변경 히스토리 기반 이동 패턴 리포트",
        tables: ["public.employee_department_change_history", "public.employee_information"],
        tools: ["자연어 SQL 생성", "테이블 리포트", "데이터 구조 탐색"],
        flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report", "report_generator"]
      },
      {
        name: "평가/보상 인사이트 Agent", desc: "평가 등급과 급여 데이터를 연결한 인사이트 (MySQL 소스)",
        tables: ["employee_evaluation_db.evaluation_scores", "employee_salary_db.salary_payments", "public.employee_information"],
        tools: ["자연어 SQL 생성", "Ontology Query Planner", "테이블 리포트"],
        flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report", "evaluator"]
      },
      {
        name: "표준조직 탐색 Agent", desc: "가나다 표준조직(org_structure) 검색과 조직 구조 안내",
        tables: ["ganada.org_structure", "public.department_management_information"],
        tools: ["자연어 SQL 생성", "데이터 구조 탐색"],
        flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report"]
      },
      {
        name: "HR 정책 근거 Agent", desc: "비정형 HR 문서에서 근거를 찾아 정형 데이터와 함께 답변",
        tables: ["public.employee_information"],
        tools: ["근거 그래프", "테이블 리포트"],
        flow: ["input_parser", "ontology_mapper", "document_retriever", "evidence_graph", "report_generator"]
      }
    ];
    var box = $("scenarioList");
    box.innerHTML = "";
    scenarios.forEach(function (s) {
      var d = document.createElement("div");
      d.className = "scn-card";
      d.innerHTML = "<h4>" + esc(s.name) + "</h4><div class='muted'>" + esc(s.desc) + "</div>" +
        "<div style='margin:6px 0'>" + s.tables.map(function (t) { return '<span class="chip">' + esc(t) + "</span>"; }).join("") + "</div>" +
        '<div class="muted" style="font-size:11px">' +
        (ontologyCount ? "Ontology 정의 " + ontologyCount + "건 활용 가능" : "Ontology 정의 없음 — 먼저 생성 권장") + "</div>" +
        '<button class="small" style="margin-top:6px">이 시나리오로 설계</button>';
      d.querySelector("button").addEventListener("click", function () {
        newDraft({
          name: s.name, description: s.desc, mode: "Scenario Studio",
          approach: "Meet in the middle", tables: s.tables, tools: s.tools, flow: s.flow
        });
        draft.systemPrompt = buildSystemPrompt(draft);
        renderDraft();
      });
      box.appendChild(d);
    });
  }

  /* ---------------- Manual Studio ---------------- */
  function renderManual() {
    var tBox = $("mTables");
    tBox.innerHTML = "";
    schemaCache.tables.forEach(function (t) {
      var l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" value="' + esc(t.qualified_name) + '"> ' + esc(t.qualified_name);
      tBox.appendChild(l);
    });
    var docs = EmpProjects.getJSON(K.docs, []).filter(function (d) { return d.inUse; });
    var dBox = $("mDocs");
    dBox.innerHTML = docs.length ? "" : "사용 지정된 문서가 없습니다.";
    docs.forEach(function (doc) {
      var l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" value="' + esc(doc.filename || doc.url) + '"> 📄 ' + esc(doc.filename || doc.url);
      dBox.appendChild(l);
    });
    var toolBox = $("mTools");
    toolBox.innerHTML = "";
    TOOLS.forEach(function (t, i) {
      var l = document.createElement("label");
      l.innerHTML = '<input type="checkbox" value="' + esc(t) + '"' + (i < 3 ? " checked" : "") + "> " + esc(t);
      toolBox.appendChild(l);
    });
  }

  function manualToDraft() {
    var tables = [], docs = [], tools = [];
    $("mTables").querySelectorAll("input:checked").forEach(function (i) { tables.push(i.value); });
    $("mDocs").querySelectorAll("input:checked").forEach(function (i) { docs.push(i.value); });
    $("mTools").querySelectorAll("input:checked").forEach(function (i) { tools.push(i.value); });
    return {
      name: $("mName").value.trim(), description: $("mDesc").value.trim(),
      mode: "Manual Studio", approach: $("mApproach").value, agentType: $("mType").value,
      tables: tables, docs: docs, tools: tools,
      useOntology: $("mUseOntology").checked, rules: $("mRules").value.trim(),
      flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report", "evaluator"]
    };
  }

  $("btnManualApply").addEventListener("click", function () {
    var base = manualToDraft();
    if (!base.name) { alert("Agent 이름을 입력하세요."); return; }
    newDraft(base);
    draft.systemPrompt = buildSystemPrompt(draft);
    renderDraft();
  });

  $("btnGenPrompt").addEventListener("click", function () {
    var base = manualToDraft();
    if (!base.name) base.name = "(이름 미정 Agent)";
    var prompt = buildSystemPrompt(base);
    var view = $("mPromptView");
    view.style.display = "block";
    view.textContent = prompt;
    if (draft) { draft.systemPrompt = prompt; renderDraft(); }
  });

  /* ---------------- Flow Studio ---------------- */
  function renderPalette() {
    var box = $("flowPalette");
    box.innerHTML = "";
    FLOW_NODES.forEach(function (n) {
      var d = document.createElement("div");
      d.className = "node";
      d.textContent = n;
      d.addEventListener("click", function () {
        flowCanvas.push(n);
        renderFlowCanvas();
      });
      box.appendChild(d);
    });
  }

  function renderFlowCanvas() {
    var box = $("flowCanvas");
    if (!flowCanvas.length) {
      box.classList.add("muted");
      box.innerHTML = "팔레트에서 노드를 클릭해 추가하세요.";
      return;
    }
    box.classList.remove("muted");
    box.innerHTML = "";
    flowCanvas.forEach(function (n, i) {
      var d = document.createElement("div");
      d.className = "fnode";
      d.innerHTML = '<span class="n" style="color:var(--accent);font-weight:700">' + (i + 1) + "</span> " +
        esc(n) + '<span class="rm" title="제거">✕</span>';
      d.querySelector(".rm").addEventListener("click", function () {
        flowCanvas.splice(i, 1);
        renderFlowCanvas();
      });
      box.appendChild(d);
    });
  }

  $("btnFlowClear").addEventListener("click", function () { flowCanvas = []; renderFlowCanvas(); });
  $("btnFlowApply").addEventListener("click", function () {
    if (!flowCanvas.length) { alert("Flow Canvas 에 노드를 추가하세요."); return; }
    var name = $("flowName").value.trim() || "flow-agent";
    newDraft({
      name: name + " Agent", description: "Flow Studio 로 설계한 workflow Agent",
      mode: "Flow Studio", agentType: "Workflow Agent",
      tables: ["public.employee_information"], flow: flowCanvas.slice(),
      trigger: $("flowTrigger").value
    });
    draft.systemPrompt = buildSystemPrompt(draft);
    renderDraft();
  });

  /* ---------------- Production Agent Factory ---------------- */
  function renderFactory() {
    var box = $("factoryStages");
    box.innerHTML = "";
    FACTORY_STAGES.forEach(function (s) {
      var done = draft && draft.factoryStages && draft.factoryStages[s[0]];
      var d = document.createElement("div");
      d.className = "stage-item" + (done ? " done" : "");
      d.innerHTML = '<span class="st">' + (done ? "✅" : "○") + "</span>" +
        "<div><b>" + esc(s[0]) + '</b><div class="desc">' + esc(s[1]) + "</div></div>" +
        '<button class="small ghost">' + (done ? "완료 해제" : "완료 처리") + "</button>";
      d.querySelector("button").addEventListener("click", function () {
        if (!draft) { alert("먼저 Studio 에서 설계 초안을 만드세요."); return; }
        draft.factoryStages = draft.factoryStages || {};
        draft.factoryStages[s[0]] = !draft.factoryStages[s[0]];
        renderFactory();
        renderDraft();
      });
      box.appendChild(d);
    });
  }

  /* ---------------- Test Harness ---------------- */
  SAMPLES.forEach(function (s) {
    var o = document.createElement("option");
    o.value = s; o.textContent = s;
    $("thSamples").appendChild(o);
  });
  $("btnThApply").addEventListener("click", function () {
    $("thInput").value = $("thSamples").value;
  });

  $("btnThRun").addEventListener("click", function () {
    var q = $("thInput").value.trim();
    if (!q) return;
    $("thResult").textContent = "테스트 실행 중…";
    fetch("/api/agent", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, project: EmpProjects.current().id })
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        var h = "<b>" + esc(d.summary) + "</b>";
        if ((d.rows || []).length && (d.columns || []).length) {
          h += '<div class="scroll-x" style="max-height:200px;overflow:auto;margin-top:6px"><table class="grid"><thead><tr>' +
            d.columns.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead><tbody>" +
            d.rows.slice(0, 10).map(function (r) {
              return "<tr>" + r.map(function (v) { return "<td>" + esc(v) + "</td>"; }).join("") + "</tr>";
            }).join("") + "</tbody></table></div>";
        }
        h += '<details style="margin-top:6px"><summary class="muted">생성된 SQL / 근거</summary><pre class="code">' + esc(d.sql) + "</pre>" +
          (d.used_tables || []).map(function (t) { return '<span class="chip">📋 ' + esc(t) + "</span>"; }).join("") +
          (d.used_ontology || []).map(function (o) {
            return '<span class="chip good">🧠 ' + esc(o.field + (o.negated ? " ≠ " : " = ") + o.value) + "</span>";
          }).join("") + "</details>";
        $("thResult").innerHTML = h;
        var hist = EmpProjects.getJSON(K.testHistory, []);
        hist.unshift({ at: new Date().toISOString(), q: q, summary: d.summary, sql: d.sql });
        EmpProjects.setJSON(K.testHistory, hist.slice(0, 30));
        renderTestHistory();
      })
      .catch(function (e) { $("thResult").innerHTML = '<span class="chip bad">테스트 실패: ' + esc(e) + "</span>"; });
  });

  function renderTestHistory() {
    var hist = EmpProjects.getJSON(K.testHistory, []);
    $("thHistory").innerHTML = hist.length
      ? hist.map(function (h) {
          return '<div class="th-item"><b>' + esc(h.q) + "</b><div class='muted'>" + esc(h.summary) +
            " · " + new Date(h.at).toLocaleString() + "</div></div>";
        }).join("")
      : "테스트 이력이 없습니다.";
  }

  /* ---------------- 생성완료 / JSON 내보내기 / Catalog ---------------- */
  $("btnComplete").addEventListener("click", function () {
    if (!draft || !draft.name) { alert("먼저 Studio 에서 Agent 를 설계하세요."); return; }
    if (!draft.systemPrompt) draft.systemPrompt = buildSystemPrompt(draft);
    var agents = catalog();
    agents.unshift(Object.assign({ id: "agent" + Date.now().toString(36), builtin: false }, draft));
    EmpProjects.setJSON(K.catalog, agents);
    renderCatalog();
    $("completeStatus").innerHTML = '<span class="chip good">✅ Agent Shop 에 등록됨</span> <a href="/agent-shop">Agent Shop 열기 →</a>';
  });

  $("btnExportJson").addEventListener("click", function () {
    if (!draft) { alert("내보낼 설계가 없습니다."); return; }
    if (!draft.systemPrompt) draft.systemPrompt = buildSystemPrompt(draft);
    var blob = new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "oafc-agent-" + (draft.name || "draft").replace(/\s+/g, "_") + ".json";
    a.click();
  });

  function renderCatalog() {
    var agents = catalog();
    $("catalogCount").textContent = agents.length;
    var box = $("catalogList");
    if (!agents.length) { box.innerHTML = "생성된 Agent 가 없습니다."; return; }
    box.innerHTML = "";
    agents.forEach(function (a) {
      var d = document.createElement("div");
      d.className = "cat-item";
      d.innerHTML = "<b>" + esc(a.name) + '</b> <span class="badge">' + esc(a.agentType || a.mode || "-") + "</span>" +
        '<div class="muted">' + (a.tables || []).length + " tables · " + (a.tools || []).length + " tools</div>";
      box.appendChild(d);
    });
  }

  /* ---------------- init ---------------- */
  fetch("/api/schema").then(function (r) { return r.json(); }).then(function (d) {
    schemaCache = d;
    renderManual();
  });
  fetch("/api/ontology?project=" + encodeURIComponent(EmpProjects.current().id))
    .then(function (r) { return r.json(); })
    .then(function (d) { ontologyCount = (d.definitions || []).length; renderScenarios(); })
    .catch(function () { renderScenarios(); });
  renderPalette();
  renderFlowCanvas();
  renderFactory();
  renderTestHistory();
  renderCatalog();
})();
