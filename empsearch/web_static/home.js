/* OAFC 홈: 메뉴 카드 + 서버 요약 + 프로젝트별 메트릭 */
(function () {
  EmpNav("/");

  var MENUS = [
    ["/data-manager", "🔌", "Data Integrator", "RDB · 파일/URL · Cloud Storage · Lakehouse Pipeline · 멀티모달 수집과 선택"],
    ["/ontology", "🧠", "Ontology Definer", "온톨로지 생성 · 편집 · 의미 관계 분석 · 버전관리"],
    ["/agent-builder", "🛠️", "Agent Builder", "Chat / Scenario / Manual / Flow Studio 로 Agent 설계 · 테스트"],
    ["/agent-shop", "🏬", "Agent Shop", "생성 Agent 실행 · 관리 · 백업 · 복원 (임직원 검색 Agent 포함)"],
    ["/schema", "🕸️", "Schema Graph", "DB / schema / table / field 관계도와 테이블 데이터 조회"]
  ];

  var grid = document.getElementById("menuGrid");
  MENUS.forEach(function (m) {
    var a = document.createElement("a");
    a.className = "menu-card";
    a.href = m[0];
    a.innerHTML = '<div class="icon">' + m[1] + "</div><h3>" + m[2] + "</h3><p>" + m[3] + "</p>";
    grid.appendChild(a);
  });

  function count(base) {
    var v = EmpProjects.getJSON(base, []);
    if (Array.isArray(v)) return v.length;
    if (v && typeof v === "object") return Object.keys(v).length;
    return 0;
  }

  var wrap = document.getElementById("homeMetrics");
  function render(list) {
    wrap.innerHTML = "";
    list.forEach(function (m) {
      var d = document.createElement("div");
      d.className = "metric";
      d.innerHTML = '<div class="v">' + m[1] + '</div><div class="k">' + m[0] + "</div>";
      wrap.appendChild(d);
    });
  }

  var metrics = [
    ["Pipeline", count("empsearch.dataManager.pipelines.v1")],
    ["Dataset", count("empsearch.dataManager.datasets.v1")],
    ["의미 관계", count("empsearch.ontology.semanticRelations.v1")],
    ["Agent", count("empsearch.agentBuilder.catalog.v1")]
  ];
  render(metrics);

  fetch("/api/summary")
    .then(function (r) { return r.json(); })
    .then(function (s) {
      metrics = [
        ["직원", (s.employees || 0).toLocaleString()],
        ["부서", s.departments || 0],
        ["근무지", s.work_locations || 0],
        ["테이블", s.tables || 0],
        ["컬럼", s.columns || 0],
        ["관계", s.relationships || 0]
      ].concat(metrics);
      render(metrics);
    })
    .catch(function () { /* 서버 미기동 시 무시 */ });

  fetch("/api/ontology?project=" + encodeURIComponent(EmpProjects.current().id))
    .then(function (r) { return r.json(); })
    .then(function (d) {
      metrics.push(["Ontology 정의", (d.definitions || []).length]);
      render(metrics);
    })
    .catch(function () { /* ignore */ });
})();
