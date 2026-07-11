/* 프로젝트별 localStorage namespace (2026-07-09 스펙).
 * 핵심 키:
 *   empsearch.projects.v1          — 프로젝트 목록
 *   empsearch.currentProjectId.v1  — 현재 프로젝트 id
 *   empsearch.project.{projectId}.* — 프로젝트별 상태 저장 */
(function () {
  var LIST_KEY = "empsearch.projects.v1";
  var CURRENT_KEY = "empsearch.currentProjectId.v1";

  function loadList() {
    try {
      var raw = localStorage.getItem(LIST_KEY);
      if (raw) {
        var v = JSON.parse(raw);
        if (Array.isArray(v)) return v;
        if (v && Array.isArray(v.list)) return v.list; /* 구버전 형식 호환 */
      }
    } catch (e) { /* ignore */ }
    return [{ id: "default", name: "기본 프로젝트", createdAt: new Date().toISOString() }];
  }

  var list = loadList();
  var currentId = localStorage.getItem(CURRENT_KEY) || "default";
  if (!list.some(function (p) { return p.id === currentId; })) currentId = list[0].id;

  function save() {
    localStorage.setItem(LIST_KEY, JSON.stringify(list));
    localStorage.setItem(CURRENT_KEY, currentId);
  }
  save();

  window.EmpProjects = {
    key: function (base) {
      return "empsearch.project." + currentId + "." + base;
    },
    current: function () {
      for (var i = 0; i < list.length; i++) if (list[i].id === currentId) return list[i];
      return list[0];
    },
    list: function () { return list.slice(); },
    create: function (name) {
      var id = "p" + Date.now().toString(36);
      list.push({ id: id, name: name, createdAt: new Date().toISOString() });
      currentId = id;
      save();
      return id;
    },
    select: function (id) { currentId = id; save(); },
    remove: function (id) {
      if (id === "default") return;
      list = list.filter(function (p) { return p.id !== id; });
      if (currentId === id) currentId = "default";
      save();
    },
    getJSON: function (base, fallback) {
      try {
        var raw = localStorage.getItem(this.key(base));
        if (raw == null && currentId === "default") raw = localStorage.getItem(base); /* 구버전 키 호환 */
        if (raw) return JSON.parse(raw);
      } catch (e) { /* ignore */ }
      return fallback;
    },
    setJSON: function (base, value) {
      localStorage.setItem(this.key(base), JSON.stringify(value));
    }
  };

  /* 상단 네비게이션 렌더링 (모든 페이지 공통) */
  window.EmpNav = function (active) {
    var links = [
      ["/", "홈"],
      ["/data-manager", "Data Integrator"],
      ["/ontology", "Ontology Definer"],
      ["/agent-builder", "Agent Builder"],
      ["/agent-shop", "Agent Shop"],
      ["/schema", "Schema Graph"]
    ];
    var html = '<div class="nav-inner"><a class="brand" href="/">OAFC</a>' +
      '<span class="brand-sub">Ontology Agent Factory Creator</span><nav>';
    links.forEach(function (l) {
      html += '<a href="' + l[0] + '"' + (l[0] === active ? ' class="active"' : "") + ">" + l[1] + "</a>";
    });
    html += "</nav><div class='proj-switch'><select id='oafcProjectSelect'></select>" +
      "<button id='oafcProjectNew' title='새 프로젝트'>＋</button></div></div>";
    var bar = document.createElement("header");
    bar.className = "oafc-nav";
    bar.innerHTML = html;
    document.body.insertBefore(bar, document.body.firstChild);

    var sel = bar.querySelector("#oafcProjectSelect");
    EmpProjects.list().forEach(function (p) {
      var o = document.createElement("option");
      o.value = p.id;
      o.textContent = p.name;
      if (p.id === EmpProjects.current().id) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      EmpProjects.select(sel.value);
      location.reload();
    });
    bar.querySelector("#oafcProjectNew").addEventListener("click", function () {
      var name = prompt("새 프로젝트 이름");
      if (name) { EmpProjects.create(name); location.reload(); }
    });
  };
})();
