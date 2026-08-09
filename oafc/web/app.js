(function () {
  "use strict";

  var state = {
    step: 1,
    discoveries: [],
    connections: [],
    activeId: null,
    activeProfile: null,
    schema: null,
    inventory: null,
    suggestions: [],
    analysisSchema: null,
    analysisResult: null,
    analysisEpoch: 0,
    analysisQueryEpoch: 0,
    inventoryEpoch: 0,
    schemaEpoch: 0
  };

  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function token() {
    try { return sessionStorage.getItem("oafc.apiToken") || ""; } catch (_error) { return ""; }
  }
  function setToken(value) {
    try { sessionStorage.setItem("oafc.apiToken", value); } catch (_error) { /* session only */ }
  }

  function request(path, options, retried) {
    options = Object.assign({}, options || {});
    var headers = new Headers(options.headers || {});
    var currentToken = token();
    if (currentToken) headers.set("X-OAFC-Token", currentToken);
    options.headers = headers;
    return fetch(path, options).then(function (response) {
      if (response.status === 401 && !retried) {
        var entered = prompt("OAFC API token을 입력하세요.");
        if (entered) {
          setToken(entered);
          return request(path, options, true);
        }
      }
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(body.error || ("HTTP " + response.status));
        return body;
      });
    });
  }
  function jsonOptions(method, body) {
    return { method: method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) };
  }
  function toast(message) {
    var el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { el.hidden = true; }, 3200);
  }
  function notice(id, message, kind) {
    var el = $(id);
    el.className = "notice " + (kind || "neutral");
    el.textContent = message;
  }
  function formatBytes(bytes) {
    if (bytes == null) return "n/a";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KiB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MiB";
  }

  function showStep(step) {
    if (step === 3 && (!state.activeProfile || state.activeProfile.status !== "connected")) {
      toast("먼저 연결정보를 저장하고 연결 테스트를 완료하세요.");
      return;
    }
    if (step === 4 && (!state.schema || !selectedNames().length)) {
      toast("온톨로지 단계 전에 사용할 테이블을 선택하세요.");
      return;
    }
    state.step = step;
    document.querySelectorAll(".stage").forEach(function (section) {
      var active = section.id === "step" + step;
      section.hidden = !active;
      section.classList.toggle("active", active);
    });
    document.querySelectorAll(".step").forEach(function (button) {
      var number = Number(button.dataset.step);
      button.classList.toggle("active", number === step);
      button.classList.toggle("done", number < step);
    });
    if (step === 3 && state.activeId) {
      loadInventory().then(function (current) { if (current !== false) return loadSchema(); });
    }
    if (step === 4 && state.activeId) loadApplied();
  }

  function updateEngineFields() {
    var mysql = $("profileEngine").value === "mysql";
    $("mysqlFields").hidden = !mysql;
    $("sqliteLocationField").hidden = mysql;
    $("profileLocation").required = !mysql;
    $("mysqlHost").required = mysql;
    $("mysqlUsername").required = mysql;
  }
  $("profileEngine").addEventListener("change", updateEngineFields);

  function refreshWorkflow() {
    return request("/api/workflow").then(function (data) {
      $("workflowSummary").textContent = "연결 " + data.connection_count + " · 선택 테이블 " +
        data.selected_table_count + " · 온톨로지 " + data.ontology_count;
    }).catch(function (error) {
      $("workflowSummary").textContent = "서버 상태 확인 실패";
      toast(error.message);
    });
  }

  function refreshConnections() {
    return request("/api/connections").then(function (data) {
      state.connections = data.connections || [];
      renderConnections();
      if (state.activeId) {
        var current = state.connections.filter(function (item) { return item.id === state.activeId; })[0];
        if (current) {
          state.activeProfile = current;
          $("connectionBadge").textContent = current.status;
        }
      }
      $("openAnalysisBtn").disabled = !state.activeProfile || state.activeProfile.status !== "connected";
    });
  }

  function renderConnections() {
    var list = $("connectionList");
    $("connectionCount").textContent = state.connections.length;
    if (!state.connections.length) {
      list.className = "connection-list empty";
      list.textContent = "저장된 연결이 없습니다.";
      return;
    }
    list.className = "connection-list";
    list.innerHTML = "";
    state.connections.forEach(function (profile) {
      var item = document.createElement("article");
      item.className = "connection-item" + (profile.id === state.activeId ? " active" : "");
      item.innerHTML = '<div class="connection-main" tabindex="0"><b>' + esc(profile.name) +
        '</b><small>' + esc(profile.location) + '</small><div class="state ' +
        (profile.status === "connected" ? "connected" : "") + '">' + esc(profile.status) +
        (profile.last_tested_at ? " · " + esc(profile.last_tested_at) : "") + '</div>' +
        '<div class="connection-meta"><span>' + esc(profile.engine.toUpperCase()) +
        '</span><span>테이블 ' + Number(profile.selected_table_count || 0) +
        '</span><span>온톨로지 ' + Number(profile.ontology_count || 0) + '</span></div></div>' +
        '<div class="connection-actions"><button data-action="edit">편집</button>' +
        '<button data-action="test">재검증</button><button data-action="delete" class="danger">삭제</button></div>';
      var main = item.querySelector(".connection-main");
      main.addEventListener("click", function () { activateConnection(profile); });
      main.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") activateConnection(profile);
      });
      item.querySelector("[data-action=edit]").addEventListener("click", function () {
        activateConnection(profile, 2);
      });
      item.querySelector("[data-action=test]").addEventListener("click", function () {
        activateConnection(profile);
        testActiveConnection();
      });
      item.querySelector("[data-action=delete]").addEventListener("click", function () { deleteConnection(profile); });
      list.appendChild(item);
    });
  }

  function activateConnection(profile, targetStep) {
    state.analysisEpoch += 1;
    state.analysisQueryEpoch += 1;
    state.inventoryEpoch += 1;
    state.schemaEpoch += 1;
    state.activeId = profile.id;
    state.activeProfile = profile;
    state.schema = null;
    state.inventory = null;
    state.suggestions = [];
    state.analysisSchema = null;
    state.analysisResult = null;
    $("profileName").value = profile.name;
    $("profileEngine").value = profile.engine;
    $("profileLocation").value = profile.location || "";
    $("mysqlHost").value = profile.host || "";
    $("mysqlPort").value = profile.port || 3306;
    $("mysqlUsername").value = profile.username || "";
    $("mysqlDatabase").value = profile.database_name || "";
    $("mysqlTlsMode").value = profile.tls_mode || "verify_identity";
    $("mysqlSslCa").value = profile.ssl_ca || "";
    $("credentialAlias").value = profile.credential_alias || "";
    updateEngineFields();
    $("connectionBadge").textContent = profile.status;
    $("testConnectionBtn").disabled = false;
    $("openAnalysisBtn").disabled = profile.status !== "connected";
    $("runAnalysisBtn").disabled = false;
    renderConnections();
    if (targetStep) {
      showStep(targetStep);
    } else if (profile.status === "connected") {
      showStep(3);
    } else {
      showStep(2);
    }
  }

  function clearActiveConnection() {
    state.analysisEpoch += 1;
    state.analysisQueryEpoch += 1;
    state.inventoryEpoch += 1;
    state.schemaEpoch += 1;
    state.activeId = null;
    state.activeProfile = null;
    state.schema = null;
    state.inventory = null;
    state.suggestions = [];
    state.analysisSchema = null;
    state.analysisResult = null;
    $("profileName").value = "";
    $("profileEngine").value = "sqlite";
    $("profileLocation").value = "";
    $("mysqlHost").value = "";
    $("mysqlPort").value = "3306";
    $("mysqlUsername").value = "";
    $("mysqlDatabase").value = "";
    $("mysqlTlsMode").value = "verify_identity";
    $("mysqlSslCa").value = "";
    $("credentialAlias").value = "";
    $("connectionBadge").textContent = "미저장";
    $("testConnectionBtn").disabled = true;
    $("openAnalysisBtn").disabled = true;
    updateEngineFields();
    renderConnections();
  }

  function deleteConnection(profile) {
    if (!confirm("'" + profile.name + "' 연결과 선택 테이블·온톨로지를 삭제할까요?")) return;
    var wasActive = state.activeId === profile.id;
    request("/api/connections/" + encodeURIComponent(profile.id), { method: "DELETE" })
      .then(function () {
        if (wasActive) clearActiveConnection();
        return Promise.all([refreshConnections(), refreshWorkflow()]);
      }).then(function () {
        toast("연결을 삭제했습니다.");
        if (wasActive && state.connections.length) activateConnection(state.connections[0]);
        else if (!state.connections.length) showStep(1);
      }).catch(function (error) { toast(error.message); });
  }

  $("newConnectionBtn").addEventListener("click", function () {
    clearActiveConnection();
    notice("connectionResult", "새 연결을 만들려면 SQLite를 탐색하거나 MySQL 서버를 등록하세요.", "neutral");
    showStep(1);
  });

  $("mysqlSetupBtn").addEventListener("click", function () {
    state.activeId = null;
    state.activeProfile = null;
    state.inventory = null;
    state.schema = null;
    $("profileName").value = "MySQL Analysis Server";
    $("profileEngine").value = "mysql";
    $("profileLocation").value = "";
    $("mysqlHost").value = "";
    $("mysqlPort").value = "3306";
    $("mysqlUsername").value = "";
    $("mysqlDatabase").value = "";
    $("mysqlTlsMode").value = "verify_identity";
    $("mysqlSslCa").value = "";
    $("credentialAlias").value = "";
    $("connectionBadge").textContent = "미저장";
    $("testConnectionBtn").disabled = true;
    $("openAnalysisBtn").disabled = true;
    updateEngineFields();
    renderConnections();
    notice("connectionResult", "MySQL 서버 주소와 읽기 전용 계정 정보를 입력하세요.", "neutral");
    showStep(2);
  });

  $("discoverBtn").addEventListener("click", function () {
    var button = this;
    button.disabled = true;
    button.textContent = "탐색 중…";
    notice("discoveryStatus", "허용된 디렉터리를 검사하고 있습니다.", "neutral");
    request("/api/discovery").then(function (data) {
      state.discoveries = data.databases || [];
      renderDiscoveries();
      var available = state.discoveries.filter(function (item) { return item.available; }).length;
      notice("discoveryStatus", "DB " + state.discoveries.length + "개 발견 · 사용 가능 " + available + "개", available ? "good" : "neutral");
    }).catch(function (error) {
      notice("discoveryStatus", error.message, "bad");
    }).finally(function () {
      button.disabled = false;
      button.textContent = "다시 탐색";
    });
  });

  function renderDiscoveries() {
    var list = $("discoveryList");
    list.innerHTML = "";
    state.discoveries.forEach(function (database) {
      var card = document.createElement("article");
      card.className = "db-card" + (database.available ? "" : " unavailable");
      card.innerHTML = "<h3>" + esc(database.name) + "</h3>" +
        "<div class=\"db-meta\"><span class=\"db-path\" title=\"" + esc(database.location) + "\">" +
        esc(database.location) + "</span><span>SQLite · " + formatBytes(database.size_bytes) +
        " · 테이블 " + database.table_count + "개</span>" +
        (database.error ? "<span>" + esc(database.error) + "</span>" : "") + "</div>";
      var choose = document.createElement("button");
      choose.className = database.available ? "primary" : "";
      choose.disabled = !database.available;
      choose.textContent = database.available ? "이 DB 선택" : "사용할 수 없음";
      choose.addEventListener("click", function () {
        state.activeId = null;
        state.activeProfile = null;
        $("profileName").value = database.name.replace(/\.(db|sqlite|sqlite3)$/i, "");
        $("profileEngine").value = "sqlite";
        $("profileLocation").value = database.location;
        $("mysqlHost").value = "";
        $("mysqlUsername").value = "";
        $("mysqlDatabase").value = "";
        $("mysqlTlsMode").value = "verify_identity";
        $("mysqlSslCa").value = "";
        $("credentialAlias").value = "";
        updateEngineFields();
        $("connectionBadge").textContent = "미저장";
        $("testConnectionBtn").disabled = true;
        $("openAnalysisBtn").disabled = true;
        renderConnections();
        notice("connectionResult", "발견된 DB 정보를 확인하고 저장하세요.", "neutral");
        showStep(2);
      });
      card.appendChild(choose);
      list.appendChild(card);
    });
  }

  $("connectionForm").addEventListener("submit", function (event) {
    event.preventDefault();
    var payload = {
      id: state.activeId || undefined,
      name: $("profileName").value.trim(),
      engine: $("profileEngine").value,
      location: $("profileLocation").value,
      host: $("mysqlHost").value.trim(),
      port: Number($("mysqlPort").value || 3306),
      username: $("mysqlUsername").value.trim(),
      database_name: $("mysqlDatabase").value.trim(),
      tls_mode: $("mysqlTlsMode").value,
      ssl_ca: $("mysqlSslCa").value.trim(),
      credential_alias: $("credentialAlias").value.trim()
    };
    notice("connectionResult", "연결정보를 저장하고 있습니다.", "neutral");
    request("/api/connections", jsonOptions("POST", payload)).then(function (profile) {
      state.activeId = profile.id;
      state.activeProfile = profile;
      $("connectionBadge").textContent = profile.status;
      $("testConnectionBtn").disabled = false;
      notice("connectionResult", "연결정보가 저장되었습니다. 이제 실제 연결을 확인하세요.", "good");
      return Promise.all([refreshConnections(), refreshWorkflow()]);
    }).catch(function (error) {
      notice("connectionResult", error.message, "bad");
    });
  });

  function testActiveConnection() {
    if (!state.activeId) return;
    var button = $("testConnectionBtn");
    button.disabled = true;
    notice("connectionResult", "원본 DB를 읽기 전용으로 열어 연결을 확인합니다.", "neutral");
    request("/api/connections/" + encodeURIComponent(state.activeId) + "/test", jsonOptions("POST", {}))
      .then(function (result) {
        if (!result.connected) throw new Error(result.error || "연결할 수 없습니다.");
        notice("connectionResult", "연결 성공 · " + result.engine.toUpperCase() + " " + result.version +
          " · DB " + result.database_count + "개 · 테이블 " + result.table_count + "개", "good");
        return refreshConnections().then(function () { showStep(3); });
      }).catch(function (error) {
        return refreshConnections().then(function () {
          notice("connectionResult", error.message, "bad");
          showStep(2);
        });
      }).finally(function () {
        button.disabled = false;
        refreshWorkflow();
      });
  }

  $("testConnectionBtn").addEventListener("click", testActiveConnection);


  function loadInventory() {
    if (!state.activeId) return Promise.resolve(false);
    var connectionId = state.activeId;
    var requestEpoch = ++state.inventoryEpoch;
    $("databaseInventory").className = "database-inventory empty";
    $("databaseInventory").textContent = "서버와 DB inventory를 분석하는 중…";
    return request("/api/connections/" + encodeURIComponent(connectionId) + "/inventory")
      .then(function (inventory) {
        if (state.activeId !== connectionId || state.inventoryEpoch !== requestEpoch) return false;
        state.inventory = inventory;
        renderInventory();
        return true;
      }).catch(function (error) {
        if (state.activeId !== connectionId || state.inventoryEpoch !== requestEpoch) return false;
        $("databaseInventory").textContent = error.message;
        toast(error.message);
        return false;
      });
  }

  function renderInventory() {
    var inventory = state.inventory;
    if (!inventory) return;
    var server = inventory.server || {}, totals = inventory.totals || {};
    $("serverInfo").innerHTML =
      "<div class=\"metric\"><b>" + esc(server.version || "-") + "</b><span>서버 버전</span></div>" +
      "<div class=\"metric\"><b>" + (totals.database_count || 0) + "</b><span>DB</span></div>" +
      "<div class=\"metric\"><b>" + (totals.table_count || 0) + "</b><span>테이블</span></div>" +
      "<div class=\"metric\"><b>" + (totals.view_count || 0) + "</b><span>뷰</span></div>" +
      "<div class=\"metric\"><b>" + formatBytes(totals.data_bytes) + "</b><span>데이터</span></div>" +
      "<div class=\"metric\"><b>" + formatBytes(totals.index_bytes) + "</b><span>인덱스</span></div>";
    var list = $("databaseInventory");
    list.className = "database-inventory";
    list.innerHTML = "";
    var configured = (state.activeProfile && state.activeProfile.database_name || "")
      .split(",").map(function (name) { return name.trim(); }).filter(Boolean);
    (inventory.databases || []).forEach(function (database) {
      var card = document.createElement("label");
      card.className = "database-card" + (database.system ? " system" : "");
      var checked = inventory.engine === "sqlite" || (!database.system &&
        (!configured.length || configured.indexOf(database.name) !== -1));
      card.innerHTML = "<input type=\"checkbox\" value=\"" + esc(database.name) + "\" " + (checked ? "checked" : "") +
        "><b>" + esc(database.name) + (database.system ? " · system" : "") + "</b>" +
        "<small>table " + database.table_count + " · view " + database.view_count +
        " · rows≈" + (database.estimated_rows == null ? "n/a" : database.estimated_rows.toLocaleString()) +
        "<br>data " + formatBytes(database.data_bytes) + " · index " + formatBytes(database.index_bytes) +
        " · routine " + database.routine_count + " · trigger " + database.trigger_count +
        "<br>" + esc(database.default_character_set || "") + " / " + esc(database.default_collation || "") + "</small>";
      list.appendChild(card);
    });
  }

  function selectedDatabases() {
    return Array.from(document.querySelectorAll("#databaseInventory input:checked"))
      .map(function (input) { return input.value; });
  }

  $("analyzeDatabasesBtn").addEventListener("click", function () { loadSchema(); });

  function loadSchema() {
    if (!state.activeId) return Promise.resolve(false);
    var connectionId = state.activeId;
    var requestEpoch = ++state.schemaEpoch;
    var engine = state.activeProfile && state.activeProfile.engine;
    $("tableList").className = "table-list empty";
    $("tableList").textContent = "스키마를 불러오는 중…";
    var path = "/api/connections/" + encodeURIComponent(connectionId) + "/schema";
    if (engine === "mysql") {
      var databases = selectedDatabases();
      if (!databases.length) {
        $("tableList").textContent = "분석할 DB를 하나 이상 선택하세요.";
        return Promise.resolve(false);
      }
      path += "?" + databases.map(function (name) { return "database=" + encodeURIComponent(name); }).join("&");
    }
    return request(path)
      .then(function (schema) {
        if (state.activeId !== connectionId || state.schemaEpoch !== requestEpoch) return false;
        state.schema = schema;
        state.activeProfile = schema.connection;
        renderSchema();
        return true;
      }).catch(function (error) {
        if (state.activeId !== connectionId || state.schemaEpoch !== requestEpoch) return false;
        $("tableList").textContent = error.message;
        toast(error.message);
        return false;
      });
  }

  function renderSchema() {
    var tables = state.schema ? state.schema.tables || [] : [];
    var columns = tables.reduce(function (sum, table) { return sum + table.columns.length; }, 0);
    $("schemaSummary").innerHTML = "<div class=\"metric\"><b>" + tables.length + "</b><span>테이블 / 뷰</span></div>" +
      "<div class=\"metric\"><b>" + columns + "</b><span>컬럼</span></div>" +
      "<div class=\"metric\"><b>" + (state.schema.relationships || []).length + "</b><span>관계</span></div>";
    var list = $("tableList");
    list.className = "table-list";
    list.innerHTML = "";
    tables.forEach(function (table) {
      var label = document.createElement("label");
      label.className = "table-card" + (table.selected ? " selected" : "");
      var qualified = table.qualified_name || table.name;
      /* 검색 색인: 테이블명 + 전체 컬럼명 (컬럼 검색 지원) */
      label.dataset.search = (qualified + " " + table.columns.map(function (c) { return c.name; }).join(" ")).toLowerCase();
      label.innerHTML = "<input class=\"table-check\" type=\"checkbox\" value=\"" + esc(qualified) + "\" " + (table.selected ? "checked" : "") +
        "><div><b>" + esc(qualified) + "</b><small> · " + esc(table.kind) + " · " + esc(table.engine || "") +
        " · rows≈" + (table.estimated_rows == null ? "n/a" : table.estimated_rows.toLocaleString()) +
        " · data " + formatBytes(table.data_bytes) + " · index " + formatBytes(table.index_bytes) +
        " · 컬럼 " + table.columns.length + "</small></div><small>" +
        table.columns.filter(function (column) { return column.primary_key; }).length + " PK · " + table.index_count + " IDX</small>" +
        "<div class=\"column-chips\">" + table.columns.slice(0, 12).map(function (column) {
          return "<span class=\"chip\">" + esc(column.name) + " · " + esc(column.column_type || column.type || "untyped") + "</span>";
        }).join("") + (table.columns.length > 12 ? "<span class=\"chip\">+" + (table.columns.length - 12) + "</span>" : "") + "</div>" +
        "<div class=\"business-fields\"><input data-field=\"domain\" placeholder=\"업무 도메인 (예: catalog)\" value=\"" + esc(table.business_domain || "") + "\" " + (table.selected ? "" : "disabled") +
        "><input data-field=\"purpose\" placeholder=\"사용 목적 (예: 상품 기준정보 분석)\" value=\"" + esc(table.usage_purpose || "") + "\" " + (table.selected ? "" : "disabled") + "></div>";
      var checkbox = label.querySelector(".table-check");
      checkbox.addEventListener("change", function () {
        label.classList.toggle("selected", checkbox.checked);
        label.querySelectorAll(".business-fields input").forEach(function (input) { input.disabled = !checkbox.checked; });
        updateSelectionCount();
        applyTableFilter();
      });
      list.appendChild(label);
    });
    if (!tables.length) {
      list.className = "table-list empty";
      list.textContent = "이 DB에는 사용자 테이블이나 뷰가 없습니다.";
    }
    updateSelectionCount();
    applyTableFilter();
  }

  /* 검색어 + 상태 필터(전체/선택됨/미선택)를 카드 표시에 반영한다. */
  function applyTableFilter() {
    var query = ($("tableSearch").value || "").trim().toLowerCase();
    var mode = state.tableFilter || "all";
    var shown = 0;
    document.querySelectorAll("#tableList .table-card").forEach(function (card) {
      var checked = card.querySelector(".table-check").checked;
      var matchQuery = !query || (card.dataset.search || "").indexOf(query) !== -1;
      var matchMode = mode === "all" || (mode === "selected" && checked) || (mode === "unselected" && !checked);
      var visible = matchQuery && matchMode;
      card.hidden = !visible;
      if (visible) shown += 1;
    });
    var empty = $("tableFilterEmpty");
    if (empty) empty.hidden = shown > 0 || !document.querySelectorAll("#tableList .table-card").length;
  }

  function updateSelectionCount() {
    var total = document.querySelectorAll("#tableList .table-check").length;
    var selected = document.querySelectorAll("#tableList .table-check:checked").length;
    $("selectedCount").textContent = selected;
    $("totalCount").textContent = total;
    $("saveBtnCount").textContent = selected;
  }

  function selectedDetails() {
    return Array.from(document.querySelectorAll("#tableList .table-card")).filter(function (card) {
      return card.querySelector(".table-check").checked;
    }).map(function (card) {
      return {
        table_name: card.querySelector(".table-check").value,
        business_domain: card.querySelector("[data-field=domain]").value.trim(),
        usage_purpose: card.querySelector("[data-field=purpose]").value.trim()
      };
    });
  }
  function selectedNames() { return selectedDetails().map(function (item) { return item.table_name; }); }
  function applyCheck(input, checked) {
    if (input.checked === checked) return;
    input.checked = checked;
    var card = input.closest(".table-card");
    card.classList.toggle("selected", checked);
    card.querySelectorAll(".business-fields input").forEach(function (el) { el.disabled = !checked; });
  }
  function setAllTables(checked) {
    document.querySelectorAll("#tableList .table-check").forEach(function (input) { applyCheck(input, checked); });
    updateSelectionCount();
    applyTableFilter();
  }
  function setVisibleTables(checked) {
    document.querySelectorAll("#tableList .table-card").forEach(function (card) {
      if (!card.hidden) applyCheck(card.querySelector(".table-check"), checked);
    });
    updateSelectionCount();
    applyTableFilter();
  }
  $("selectAllBtn").addEventListener("click", function () { setAllTables(true); });
  $("clearAllBtn").addEventListener("click", function () { setAllTables(false); });
  $("selectVisibleBtn").addEventListener("click", function () { setVisibleTables(true); });
  $("tableSearch").addEventListener("input", applyTableFilter);
  document.querySelectorAll(".table-filters .chip-toggle").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll(".table-filters .chip-toggle").forEach(function (b) { b.classList.remove("active"); });
      button.classList.add("active");
      state.tableFilter = button.dataset.filter;
      applyTableFilter();
    });
  });
  $("saveSelectionBtn").addEventListener("click", function () {
    var selected = selectedDetails();
    request("/api/connections/" + encodeURIComponent(state.activeId) + "/tables", jsonOptions("PUT", {
      tables: selected,
      databases: state.activeProfile && state.activeProfile.engine === "mysql" ? selectedDatabases() : undefined
    }))
      .then(function () {
        toast(selected.length ?
          "업무테이블 " + selected.length + "개와 사용 목적을 저장했습니다." :
          "모든 업무테이블 선택과 관련 온톨로지를 해제했습니다.");
        return Promise.all([loadSchema(), refreshWorkflow()]);
      }).then(function () { if (selected.length) showStep(4); })
      .catch(function (error) { toast(error.message); });
  });

  /* -- Relationship Discovery (Data Knowledge Builder) -- */
  function confidenceClass(score) {
    return score >= 0.7 ? "high" : score >= 0.5 ? "mid" : "low";
  }
  function renderRelationships(data) {
    state.relationships = data.relationships || [];
    var s = data.summary || {};
    $("relationshipSummary").innerHTML =
      "<div class=\"metric\"><b>" + (s.entity_count || 0) + "</b><span>엔티티</span></div>" +
      "<div class=\"metric\"><b>" + (s.physical || 0) + "</b><span>물리 FK</span></div>" +
      "<div class=\"metric\"><b>" + (s.inferred || 0) + "</b><span>추론 관계</span></div>" +
      "<div class=\"metric\"><b>" + (s.approved || 0) + "</b><span>승인됨</span></div>";
    var list = $("relationshipList");
    var rels = state.relationships;
    if (!rels.length) {
      list.className = "relationship-list empty";
      list.textContent = "발견된 관계가 없습니다. 테이블을 더 선택하거나 스키마를 확인하세요.";
      return;
    }
    list.className = "relationship-list";
    list.innerHTML = "";
    rels.forEach(function (r, index) {
      var pct = Math.round(r.confidence * 100);
      var filled = Math.round(r.confidence * 10);
      var pips = "";
      for (var i = 0; i < 10; i += 1) pips += "<i class=\"pip" + (i < filled ? " on" : "") + "\"></i>";
      var status = r.status || "candidate";
      var row = document.createElement("div");
      row.className = "relationship-row " + confidenceClass(r.confidence) + " status-" + status;
      row.innerHTML =
        "<div class=\"rel-head\"><b>" + esc(r.from_entity) + "</b> <span class=\"rel-pred\">" +
        esc(r.predicate) + "</span> <b>" + esc(r.to_entity) + "</b>" +
        "<span class=\"rel-status " + status + "\">" +
        (status === "approved" ? "승인됨" : status === "rejected" ? "제외" : "후보") + "</span>" +
        "<span class=\"rel-method " + esc(r.method) + "\">" + (r.method === "physical_fk" ? "물리 FK" : "추론") + "</span></div>" +
        "<div class=\"rel-cols\">" + esc(r.from_table) + "." + esc(r.from_column) + " → " +
        esc(r.to_table) + "." + esc(r.to_column) + "</div>" +
        "<div class=\"rel-conf\"><div class=\"conf-pips\">" + pips + "</div><b>" + pct + "%</b></div>" +
        "<div class=\"rel-evidence\">" + (r.evidence || []).map(function (e) {
          return "<span class=\"chip\">" + esc(e) + "</span>"; }).join("") + "</div>" +
        "<div class=\"rel-actions\">" +
        "<button class=\"ghost small\" data-decide=\"approved\">승인</button>" +
        "<button class=\"ghost small\" data-decide=\"rejected\">제외</button></div>";
      row.querySelector("[data-decide=approved]").addEventListener("click", function () { decideRelationship(index, "approved"); });
      row.querySelector("[data-decide=rejected]").addEventListener("click", function () { decideRelationship(index, "rejected"); });
      list.appendChild(row);
    });
  }
  function decideRelationship(index, status) {
    var r = (state.relationships || [])[index];
    if (!r) return;
    var payload = {
      from_table: r.from_table, from_column: r.from_column,
      to_table: r.to_table, to_column: r.to_column,
      predicate: r.predicate, method: r.method, confidence: r.confidence,
      evidence: r.evidence, status: status
    };
    request("/api/connections/" + encodeURIComponent(state.activeId) + "/relationships",
      jsonOptions("PUT", { relationships: [payload] }))
      .then(function () {
        toast(status === "approved" ? "관계를 승인해 Semantic Model 에 저장했습니다." : "관계를 제외했습니다.");
        return loadRelationships();
      }).catch(function (error) { toast(error.message); });
  }
  function loadRelationships() {
    return request("/api/connections/" + encodeURIComponent(state.activeId) + "/relationships")
      .then(function (data) { renderRelationships(data); })
      .catch(function (error) {
        $("relationshipList").textContent = error.message;
        toast(error.message);
      });
  }
  $("discoverRelBtn").addEventListener("click", function () {
    if (!state.activeId) { toast("먼저 연결을 선택하세요."); return; }
    var button = this;
    button.disabled = true;
    button.textContent = "발견 중…";
    $("relationshipList").className = "relationship-list empty";
    $("relationshipList").textContent = "컬럼명·데이터 타입·값 중첩을 분석하는 중…";
    loadRelationships().finally(function () {
      button.disabled = false;
      button.textContent = "관계 다시 발견";
    });
  });

  $("suggestBtn").addEventListener("click", function () {
    var button = this;
    button.disabled = true;
    notice("ontologyStatus", "선택한 테이블과 컬럼 구조를 분석하고 있습니다.", "neutral");
    request("/api/connections/" + encodeURIComponent(state.activeId) + "/ontology/suggest", jsonOptions("POST", {}))
      .then(function (data) {
        state.suggestions = data.suggestions || [];
        renderSuggestions();
        notice("ontologyStatus", "초안 " + state.suggestions.length + "개 생성 · 내용을 검토한 뒤 적용하세요.", "good");
        $("applyOntologyBtn").disabled = !state.suggestions.length;
      }).catch(function (error) {
        notice("ontologyStatus", error.message, "bad");
      }).finally(function () { button.disabled = false; });
  });

  function renderSuggestions() {
    var list = $("suggestionList");
    list.innerHTML = "";
    state.suggestions.forEach(function (suggestion, index) {
      var row = document.createElement("div");
      row.className = "ontology-row";
      row.dataset.index = index;
      var target = suggestion.table_name + (suggestion.column_name ? "." + suggestion.column_name : "");
      row.innerHTML = "<div class=\"target\"><b>" + esc(suggestion.target_type) + "</b><br>" + esc(target) +
        "<br><span>" + esc(suggestion.semantic_type) + " · " + Math.round(suggestion.confidence * 100) + "%</span></div>" +
        "<input data-field=\"label\" value=\"" + esc(suggestion.label) + "\" aria-label=\"Label\">" +
        "<input data-field=\"description\" value=\"" + esc(suggestion.description) + "\" aria-label=\"Description\">" +
        "<input data-field=\"synonyms\" value=\"" + esc((suggestion.synonyms || []).join(", ")) + "\" aria-label=\"Synonyms\">";
      list.appendChild(row);
    });
  }

  $("applyOntologyBtn").addEventListener("click", function () {
    var definitions = state.suggestions.map(function (suggestion, index) {
      var row = document.querySelector(".ontology-row[data-index=\"" + index + "\"]");
      return Object.assign({}, suggestion, {
        label: row.querySelector("[data-field=label]").value.trim(),
        description: row.querySelector("[data-field=description]").value.trim(),
        synonyms: row.querySelector("[data-field=synonyms]").value.split(",").map(function (item) { return item.trim(); }).filter(Boolean)
      });
    });
    if (definitions.some(function (item) { return !item.label; })) {
      toast("모든 정의에 label을 입력하세요.");
      return;
    }
    var button = this;
    button.disabled = true;
    request("/api/connections/" + encodeURIComponent(state.activeId) + "/ontology/apply",
      jsonOptions("POST", { definitions: definitions }))
      .then(function (data) {
        renderApplied(data.definitions || []);
        notice("ontologyStatus", "온톨로지 정의 " + data.definitions.length + "개를 적용했습니다.", "good");
        toast("DB Integrator 시나리오가 완료되었습니다.");
        refreshWorkflow();
      }).catch(function (error) {
        notice("ontologyStatus", error.message, "bad");
      }).finally(function () { button.disabled = false; });
  });

  function loadApplied() {
    if (!state.activeId) return Promise.resolve();
    return request("/api/connections/" + encodeURIComponent(state.activeId) + "/ontology")
      .then(function (data) { renderApplied(data.definitions || []); })
      .catch(function (error) { toast(error.message); });
  }
  function renderApplied(definitions) {
    $("ontologyCount").textContent = definitions.length;
    var list = $("appliedList");
    if (!definitions.length) {
      list.className = "applied-list empty";
      list.textContent = "적용된 정의가 없습니다.";
      return;
    }
    list.className = "applied-list";
    list.innerHTML = definitions.map(function (item) {
      var target = item.table_name + (item.column_name ? "." + item.column_name : "");
      return "<div class=\"applied-item\"><b>" + esc(item.label) + "</b><span>" + esc(target) + " · " +
        esc(item.semantic_type) + "</span></div>";
    }).join("");
  }

  /* -- Enterprise Business Model (통합 Semantic Model) -- */
  function renderSemanticModel(model) {
    state.semanticModel = model;
    var s = model.summary || {};
    $("modelSummary").innerHTML =
      "<div class=\"metric\"><b>" + (s.entity_count || 0) + "</b><span>엔티티</span></div>" +
      "<div class=\"metric\"><b>" + (s.attribute_count || 0) + "</b><span>속성</span></div>" +
      "<div class=\"metric\"><b>" + (s.relationship_count || 0) + "</b><span>승인 관계</span></div>" +
      "<div class=\"metric\"><b>" + Math.round((s.coverage || 0) * 100) + "%</b><span>정의 커버리지</span></div>";
    var view = $("modelView");
    var entities = model.entities || [];
    if (!entities.length) {
      view.className = "model-view empty";
      view.textContent = "선택된 업무 테이블이 없습니다. 3단계에서 테이블을 선택하세요.";
      $("exportModelBtn").disabled = true;
      return;
    }
    view.className = "model-view";
    var html = entities.map(function (e) {
      var attrs = (e.attributes || []).slice(0, 8).map(function (a) {
        return "<span class=\"chip\">" + esc(a.label) + " · " + esc(a.semantic_type) + "</span>";
      }).join("");
      var more = (e.attributes || []).length > 8 ? "<span class=\"chip\">+" + (e.attributes.length - 8) + "</span>" : "";
      return "<div class=\"model-entity" + (e.defined ? " defined" : "") + "\">" +
        "<div class=\"model-entity-head\"><b>" + esc(e.entity) + "</b>" +
        (e.business_domain ? "<span class=\"rel-pred\">" + esc(e.business_domain) + "</span>" : "") +
        "<span class=\"model-table\">" + esc(e.table) + "</span></div>" +
        (e.description ? "<div class=\"model-desc\">" + esc(e.description) + "</div>" : "") +
        "<div class=\"column-chips\">" + attrs + more + "</div></div>";
    }).join("");
    var rels = (model.relationships || []).map(function (r) {
      return "<div class=\"model-rel\"><b>" + esc(r.from_entity) + "</b> <span class=\"rel-pred\">" +
        esc(r.predicate) + "</span> <b>" + esc(r.to_entity) + "</b>" +
        "<span class=\"model-conf\">" + Math.round(r.confidence * 100) + "%</span></div>";
    }).join("");
    view.innerHTML = "<div class=\"model-entities\">" + html + "</div>" +
      (rels ? "<div class=\"model-rels\"><span class=\"eyebrow\">RELATIONSHIPS</span>" + rels + "</div>" : "");
    $("exportModelBtn").disabled = false;
  }
  function loadSemanticModel() {
    return request("/api/connections/" + encodeURIComponent(state.activeId) + "/semantic-model")
      .then(function (model) { renderSemanticModel(model); })
      .catch(function (error) { $("modelView").textContent = error.message; toast(error.message); });
  }
  $("buildModelBtn").addEventListener("click", function () {
    if (!state.activeId) { toast("먼저 연결을 선택하세요."); return; }
    var button = this;
    button.disabled = true;
    $("modelView").className = "model-view empty";
    $("modelView").textContent = "엔티티·관계·온톨로지를 통합하는 중…";
    loadSemanticModel().finally(function () { button.disabled = false; });
  });
  $("exportModelBtn").addEventListener("click", function () {
    if (!state.semanticModel) return;
    var name = (state.activeProfile && state.activeProfile.name || "semantic-model")
      .replace(/[^a-zA-Z0-9_-]+/g, "_");
    var blob = new Blob([JSON.stringify(state.semanticModel, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = name + ".semantic-model.json";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("Semantic Model JSON을 내보냈습니다.");
  });

  function quoteAnalysisTable(name) {
    if (!state.activeProfile || state.activeProfile.engine !== "mysql") {
      return "\"" + String(name).replace(/\"/g, "\"\"") + "\"";
    }
    return String(name).split(".").map(function (part) {
      return "`" + part.replace(/`/g, "``") + "`";
    }).join(".");
  }

  function renderAnalysisDatabases(inventory) {
    var select = $("analysisDatabase");
    select.innerHTML = "";
    var databases = (inventory.databases || []).filter(function (item) { return !item.system; });
    databases.forEach(function (database) {
      var option = document.createElement("option");
      option.value = inventory.engine === "mysql" ? database.name : "";
      option.textContent = database.name;
      select.appendChild(option);
    });
    $("analysisDatabaseField").hidden = inventory.engine !== "mysql";
    if (inventory.engine === "mysql" && state.activeProfile.database_name) {
      var preferred = state.activeProfile.database_name.split(",")[0].trim();
      if (databases.some(function (item) { return item.name === preferred; })) select.value = preferred;
    }
  }

  function loadAnalysisSchema(epoch) {
    if (!state.activeId) return Promise.resolve();
    var requestEpoch = epoch || ++state.analysisEpoch;
    var connectionId = state.activeId;
    var path = "/api/connections/" + encodeURIComponent(connectionId) + "/schema";
    var database = $("analysisDatabase").value;
    if (state.activeProfile.engine === "mysql" && database) {
      path += "?database=" + encodeURIComponent(database);
    }
    $("analysisSchemaList").className = "analysis-schema-list empty";
    $("analysisSchemaList").textContent = "스키마를 불러오는 중…";
    return request(path).then(function (schema) {
      if (state.activeId !== connectionId || state.analysisEpoch !== requestEpoch) return;
      state.analysisSchema = schema;
      renderAnalysisSchema();
    }).catch(function (error) {
      if (state.activeId !== connectionId || state.analysisEpoch !== requestEpoch) return;
      $("analysisSchemaList").textContent = error.message;
      notice("analysisStatus", error.message, "bad");
    });
  }

  function renderAnalysisSchema() {
    var list = $("analysisSchemaList");
    var tables = state.analysisSchema ? state.analysisSchema.tables || [] : [];
    list.className = "analysis-schema-list";
    list.innerHTML = "";
    tables.forEach(function (table) {
      var card = document.createElement("article");
      card.className = "analysis-table";
      var qualified = table.qualified_name || table.name;
      card.innerHTML = "<b>" + esc(qualified) + "</b><small>" + esc(table.kind) + " · 컬럼 " +
        table.columns.length + " · " + esc(table.columns.slice(0, 6).map(function (column) {
          return column.name;
        }).join(", ")) + (table.columns.length > 6 ? " …" : "") + "</small>" +
        "<div class=\"analysis-table-actions\"><button data-action=\"preview\">미리보기</button>" +
        "<button data-action=\"count\">행 수</button></div>";
      card.querySelector("[data-action=preview]").addEventListener("click", function () {
        $("analysisQuery").value = "SELECT * FROM " + quoteAnalysisTable(qualified);
        $("analysisQuery").focus();
      });
      card.querySelector("[data-action=count]").addEventListener("click", function () {
        $("analysisQuery").value = "SELECT COUNT(*) AS row_count FROM " + quoteAnalysisTable(qualified);
        runAnalysis();
      });
      list.appendChild(card);
    });
    if (!tables.length) {
      list.className = "analysis-schema-list empty";
      list.textContent = "분석할 테이블이 없습니다.";
    }
    notice("analysisStatus", "읽기 전용 분석 준비 완료 · 테이블 " + tables.length + "개", "good");
  }

  function loadAnalysisContext() {
    if (!state.activeId) return Promise.resolve();
    var connectionId = state.activeId;
    var requestEpoch = ++state.analysisEpoch;
    $("analysisConnectionName").textContent = state.activeProfile.name;
    notice("analysisStatus", "DB inventory와 스키마를 불러오고 있습니다.", "neutral");
    return request("/api/connections/" + encodeURIComponent(connectionId) + "/inventory")
      .then(function (inventory) {
        if (state.activeId !== connectionId || state.analysisEpoch !== requestEpoch) return;
        state.inventory = inventory;
        renderAnalysisDatabases(inventory);
        return loadAnalysisSchema(requestEpoch);
      }).catch(function (error) {
        if (state.activeId === connectionId && state.analysisEpoch === requestEpoch) {
          notice("analysisStatus", error.message, "bad");
        }
      });
  }

  function openAnalysis() {
    if (!state.activeProfile || state.activeProfile.status !== "connected") {
      toast("분석 전에 연결 테스트를 완료하세요.");
      return;
    }
    document.querySelectorAll(".stage").forEach(function (section) {
      section.hidden = true;
      section.classList.remove("active");
    });
    document.querySelectorAll(".step").forEach(function (button) { button.classList.remove("active"); });
    $("analysisTool").hidden = false;
    $("analysisTool").classList.add("active");
    state.analysisResult = null;
    $("analysisResultSummary").innerHTML = "";
    $("analysisResult").className = "analysis-result empty";
    $("analysisResult").textContent = "쿼리를 실행하면 결과가 여기에 표시됩니다.";
    $("exportAnalysisBtn").disabled = true;
    loadAnalysisContext();
  }

  function renderAnalysisResult(result) {
    state.analysisResult = result;
    $("analysisResultSummary").innerHTML =
      "<div class=\"metric\"><b>" + result.row_count + "</b><span>표시 행</span></div>" +
      "<div class=\"metric\"><b>" + result.columns.length + "</b><span>컬럼</span></div>" +
      "<div class=\"metric\"><b>" + result.elapsed_ms + " ms</b><span>실행 시간</span></div>" +
      (result.truncated ? "<div class=\"metric\"><b>LIMIT</b><span>결과 잘림</span></div>" : "");
    var container = $("analysisResult");
    container.className = "analysis-result";
    container.innerHTML = "";
    var table = document.createElement("table");
    table.className = "result-table";
    var head = document.createElement("thead");
    var headRow = document.createElement("tr");
    result.columns.forEach(function (column) {
      var th = document.createElement("th");
      th.textContent = column;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = document.createElement("tbody");
    result.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (value) {
        var td = document.createElement("td");
        td.textContent = value == null ? "NULL" : String(value);
        td.title = td.textContent;
        if (value == null) td.className = "null";
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    container.appendChild(table);
    $("exportAnalysisBtn").disabled = !result.rows.length;
    notice("analysisStatus", "쿼리 실행 완료" + (result.truncated ? " · 최대 행 제한으로 일부만 표시" : ""), "good");
  }

  function runAnalysis() {
    if (!state.activeId) return;
    var query = $("analysisQuery").value.trim();
    if (!query) { toast("실행할 SELECT 쿼리를 입력하세요."); return; }
    var connectionId = state.activeId;
    var contextEpoch = state.analysisEpoch;
    var requestEpoch = ++state.analysisQueryEpoch;
    var button = $("runAnalysisBtn");
    button.disabled = true;
    notice("analysisStatus", "읽기 전용 트랜잭션에서 쿼리를 실행하고 있습니다.", "neutral");
    request("/api/connections/" + encodeURIComponent(connectionId) + "/analysis/query",
      jsonOptions("POST", {
        query: query,
        database: state.activeProfile.engine === "mysql" ? $("analysisDatabase").value : undefined,
        max_rows: Number($("analysisMaxRows").value),
        timeout_ms: Number($("analysisTimeout").value)
      }))
      .then(function (result) {
        if (state.activeId === connectionId && state.analysisEpoch === contextEpoch &&
            state.analysisQueryEpoch === requestEpoch) {
          renderAnalysisResult(result);
        }
      }).catch(function (error) {
        if (state.activeId !== connectionId || state.analysisEpoch !== contextEpoch ||
            state.analysisQueryEpoch !== requestEpoch) return;
        notice("analysisStatus", error.message, "bad");
        toast(error.message);
      }).finally(function () {
        if (state.activeId === connectionId && state.analysisEpoch === contextEpoch &&
            state.analysisQueryEpoch === requestEpoch) button.disabled = false;
      });
  }

  function askNaturalLanguage() {
    if (!state.activeId) return;
    var question = $("nlQuestion").value.trim();
    if (!question) { toast("질문을 입력하세요."); return; }
    var connectionId = state.activeId;
    var button = $("nlAskBtn");
    var evidence = $("nlEvidence");
    button.disabled = true;
    evidence.hidden = true;
    request("/api/connections/" + encodeURIComponent(connectionId) + "/analysis/nl-to-sql",
      jsonOptions("POST", { question: question }))
      .then(function (result) {
        if (state.activeId !== connectionId) return;
        $("analysisQuery").value = result.sql;
        var ev = result.evidence || {};
        var parts = [];
        if (ev.entity) parts.push('<span class="nlq-chip">엔티티 · ' + esc(ev.entity) + "</span>");
        if (ev.table) parts.push('<span class="nlq-chip">테이블 · ' + esc(ev.table) + "</span>");
        if (ev.join) {
          parts.push('<span class="nlq-chip join">조인 · ' + esc(ev.join.entity) +
            " (신뢰도 " + Math.round((ev.join.confidence || 0) * 100) + "%)</span>");
          parts.push('<span class="nlq-chip join">ON · ' + esc(ev.join.on) + "</span>");
        }
        if (ev.intent) parts.push('<span class="nlq-chip">의도 · ' + esc(ev.intent) + "</span>");
        if (ev.group_by) parts.push('<span class="nlq-chip">그룹 · ' + esc(ev.group_by) + "</span>");
        if (Array.isArray(ev.columns) && ev.columns.length) {
          parts.push('<span class="nlq-chip">컬럼 · ' + esc(ev.columns.join(", ")) + "</span>");
        }
        var note = result.note ? '<p class="nlq-note">' + esc(result.note) + "</p>" : "";
        evidence.innerHTML = '<div class="nlq-chips">' + parts.join("") + "</div>" + note +
          '<p class="nlq-hint">초안 SQL을 검토한 뒤 <b>쿼리 실행</b>으로 실행하세요.</p>';
        evidence.hidden = false;
        notice("analysisStatus", "자연어 질문을 SELECT 초안으로 변환했습니다. 검토 후 실행하세요.", "neutral");
      }).catch(function (error) {
        if (state.activeId !== connectionId) return;
        notice("analysisStatus", error.message, "bad");
        toast(error.message);
      }).finally(function () {
        if (state.activeId === connectionId) button.disabled = false;
      });
  }

  function csvCell(value) {
    if (value == null) return "";
    var text = String(value);
    if (/^[\s\x00-\x1f]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }

  $("openAnalysisBtn").addEventListener("click", openAnalysis);
  $("closeAnalysisBtn").addEventListener("click", function () { showStep(state.step || 3); });
  $("refreshAnalysisSchemaBtn").addEventListener("click", loadAnalysisContext);
  $("analysisDatabase").addEventListener("change", function () { loadAnalysisSchema(); });
  $("runAnalysisBtn").addEventListener("click", runAnalysis);
  $("nlAskBtn").addEventListener("click", askNaturalLanguage);
  $("nlQuestion").addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); askNaturalLanguage(); }
  });
  $("clearAnalysisBtn").addEventListener("click", function () {
    $("analysisQuery").value = "";
    $("analysisQuery").focus();
  });
  $("analysisQuery").addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runAnalysis();
    }
  });
  $("exportAnalysisBtn").addEventListener("click", function () {
    if (!state.analysisResult) return;
    var lines = [state.analysisResult.columns.map(csvCell).join(",")].concat(
      state.analysisResult.rows.map(function (row) { return row.map(csvCell).join(","); }));
    var blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "oafc-analysis-" + new Date().toISOString().replace(/[:.]/g, "-") + ".csv";
    link.click();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 0);
  });

  document.querySelectorAll(".step").forEach(function (button) {
    button.addEventListener("click", function () { showStep(Number(button.dataset.step)); });
  });
  $("backToDiscover").addEventListener("click", function () { showStep(1); });
  $("backToProfile").addEventListener("click", function () { showStep(2); });
  $("backToTables").addEventListener("click", function () { showStep(3); });

  updateEngineFields();
  Promise.all([refreshConnections(), refreshWorkflow()]).then(function () {
    if (state.connections.length) activateConnection(state.connections[0]);
    else showStep(1);
  });
})();
