/* Agent Shop (2026-07-09 스펙)
 * Agent Catalog 표시/실행/삭제/백업/복원, 전체 데이터 구조 패널,
 * Agent 상세(데이터 소스/도구/운영 규칙), 결과에 SQL/데이터/Ontology 근거 표시 */
(function () {
  EmpNav("/agent-shop");

  var K = { catalog: "empsearch.agentBuilder.catalog.v1" };

  var BUILTIN = {
    id: "builtin-empsearch",
    name: "임직원 검색 Agent",
    description: "자연어로 임직원/부서/이력/평가/급여를 검색하는 기본 Agent. Ontology 정보를 활용해 SQL 을 생성한다.",
    mode: "기본 제공", agentType: "Tool-Using Agent",
    tables: ["public.employee_information", "public.department_management_information",
      "public.employee_department_change_history", "ganada.org_structure"],
    docs: [], tools: ["자연어 SQL 생성", "테이블 리포트", "Ontology Query Planner"],
    rules: "개인 식별 정보는 검색 결과에 필요한 범위만 표시한다.",
    useOntology: true,
    flow: ["input_parser", "ontology_mapper", "natural_language_sql", "table_report"],
    builtin: true
  };

  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function $(id) { return document.getElementById(id); }
  function agents() { return EmpProjects.getJSON(K.catalog, []); }

  /* ---------------- 전체 데이터 구조 패널 ---------------- */
  fetch("/api/schema").then(function (r) { return r.json(); }).then(function (d) {
    var bySchema = {};
    (d.tables || []).forEach(function (t) {
      (bySchema[t.schema] = bySchema[t.schema] || []).push(t);
    });
    var h = "";
    Object.keys(bySchema).forEach(function (s) {
      h += '<div class="ds-schema">🗄️ ' + esc(s) + "</div>";
      bySchema[s].forEach(function (t) {
        h += '<div class="ds-table"><span>' + esc(t.name) + '</span><span>' +
          t.row_estimate.toLocaleString() + "</span></div>";
      });
    });
    $("dataStructure").innerHTML = h || "데이터 구조가 없습니다.";
  }).catch(function () {
    $("dataStructure").textContent = "서버에 연결할 수 없습니다.";
  });

  /* ---------------- Catalog ---------------- */
  function render() {
    var grid = $("agentGrid");
    grid.innerHTML = "";
    var list = [BUILTIN].concat(agents());
    list.forEach(function (a) {
      var card = document.createElement("div");
      card.className = "agent-card";
      card.innerHTML =
        '<div class="head"><div class="avatar">' + (a.builtin ? "🤖" : "🛠️") + "</div>" +
        "<div><h3>" + esc(a.name) + "</h3>" +
        '<span class="badge">' + esc(a.agentType || a.mode || "-") + "</span>" +
        (a.useOntology ? '<span class="badge" style="color:var(--good)">Ontology</span>' : "") +
        "</div></div>" +
        '<div class="desc">' + esc(a.description || "-") + "</div>" +
        '<div class="chips">' + (a.tables || []).slice(0, 3).map(function (t) {
          return '<span class="chip">📋 ' + esc(t.split(".").pop()) + "</span>";
        }).join("") +
        ((a.tables || []).length > 3 ? '<span class="chip">+' + ((a.tables || []).length - 3) + "</span>" : "") + "</div>" +
        '<div class="muted" style="font-size:11px">🔧 ' + (a.tools || []).join(", ") + "</div>" +
        '<div class="foot">' +
        '<button class="small" data-act="run">실행</button>' +
        '<button class="small ghost" data-act="detail">상세</button>' +
        (a.builtin ? "" : '<button class="small danger" data-act="del">삭제</button>') +
        "</div>";
      card.querySelector('[data-act="run"]').addEventListener("click", function () { openRun(a, false); });
      card.querySelector('[data-act="detail"]').addEventListener("click", function () { openRun(a, true); });
      var del = card.querySelector('[data-act="del"]');
      if (del) del.addEventListener("click", function () {
        if (!confirm('"' + a.name + '" Agent 를 삭제할까요?')) return;
        EmpProjects.setJSON(K.catalog, agents().filter(function (x) { return x.id !== a.id; }));
        render();
      });
      grid.appendChild(card);
    });
  }

  /* ---------------- 실행 / 상세 ---------------- */
  function openRun(a, showDetail) {
    $("runTitle").textContent = "▶ " + a.name;
    var h = "";
    if (showDetail) {
      h += '<div class="detail-block"><b>데이터 소스</b><div>' +
        (a.tables || []).map(function (t) { return '<span class="chip">📋 ' + esc(t) + "</span>"; }).join("") +
        (a.docs || []).map(function (d) { return '<span class="chip good">📄 ' + esc(d) + "</span>"; }).join("") +
        "</div></div>" +
        '<div class="detail-block"><b>사용 도구</b><div>' +
        (a.tools || []).map(function (t) { return '<span class="chip warn">🔧 ' + esc(t) + "</span>"; }).join("") +
        "</div></div>" +
        '<div class="detail-block"><b>운영 규칙</b><div class="muted">' + esc(a.rules || "-") + "</div></div>" +
        '<div class="detail-block"><b>Flow</b><div class="muted">' + (a.flow || []).join(" → ") + "</div></div>";
      if (a.systemPrompt) {
        h += '<details class="detail-block"><summary>System Prompt</summary><pre class="code">' +
          esc(a.systemPrompt) + "</pre></details>";
      }
    }
    $("agentDetail").innerHTML = h;
    $("runResult").innerHTML = '<span class="muted">Agent 에게 질의를 입력하세요.</span>';
    $("runModal").hidden = false;
    $("runInput").focus();
  }

  $("btnRunClose").addEventListener("click", function () { $("runModal").hidden = true; });
  $("runModal").addEventListener("click", function (e) { if (e.target === this) this.hidden = true; });

  function runQuery() {
    var q = $("runInput").value.trim();
    if (!q) return;
    $("runResult").textContent = "실행 중…";
    fetch("/api/agent", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, project: EmpProjects.current().id })
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        var h = "<b>" + esc(d.summary) + "</b>";
        if ((d.columns || []).length) {
          h += '<div class="scroll-x" style="max-height:300px;overflow:auto;margin-top:8px"><table class="grid"><thead><tr>' +
            d.columns.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead><tbody>" +
            (d.rows || []).map(function (r) {
              return "<tr>" + r.map(function (v) { return "<td>" + esc(v) + "</td>"; }).join("") + "</tr>";
            }).join("") + "</tbody></table></div>";
        }
        /* 사용한 데이터/Ontology/지식 근거 */
        h += '<div style="margin-top:8px">' +
          (d.used_tables || []).map(function (t) { return '<span class="chip">📋 ' + esc(t) + "</span>"; }).join("") +
          (d.used_ontology || []).map(function (o) {
            return '<span class="chip good">🧠 ' + esc(o.field + (o.negated ? " ≠ " : " = ") + o.value) + "</span>";
          }).join("") + "</div>";
        h += '<details style="margin-top:8px"><summary class="muted">생성된 SQL</summary><pre class="code">' +
          esc(d.sql) + "</pre></details>";
        $("runResult").innerHTML = h;
      })
      .catch(function (e) { $("runResult").innerHTML = '<span class="chip bad">실행 실패: ' + esc(e) + "</span>"; });
  }
  $("btnRunGo").addEventListener("click", runQuery);
  $("runInput").addEventListener("keydown", function (e) { if (e.key === "Enter") runQuery(); });

  /* ---------------- 백업 / 복원 ---------------- */
  $("btnBackup").addEventListener("click", function () {
    var payload = { exportedAt: new Date().toISOString(), project: EmpProjects.current().id, agents: agents() };
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "oafc-agents-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
  });

  $("btnRestore").addEventListener("click", function () { $("restoreFile").click(); });
  $("restoreFile").addEventListener("change", function () {
    var f = this.files[0];
    if (!f) return;
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var payload = JSON.parse(reader.result);
        var incoming = payload.agents || [];
        var cur = agents();
        var ids = {};
        cur.forEach(function (a) { ids[a.id] = 1; });
        incoming.forEach(function (a) { if (!ids[a.id]) cur.push(a); });
        EmpProjects.setJSON(K.catalog, cur);
        render();
        alert("복원 완료: " + incoming.length + "건 (중복 제외 병합)");
      } catch (e) { alert("복원 실패: " + e.message); }
    };
    reader.readAsText(f);
  });

  render();
})();
