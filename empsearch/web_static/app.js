/* 챗봇: 자연어 -> SQL 임직원 검색. 최신 결과를 상단에 배치한다. */
(function () {
  EmpNav("/chatbots");

  var SAMPLES = [
    "광양 근무자 중 여성 18년 이상 근무하고 manager인 사람만 뽑아줘",
    "광양 근무자 중 여성 18년 이상 근무하고 manager가 아닌 사람만 뽑아줘",
    "포항에 근무하는 15년차 이상 여성 관리자를 찾아줘",
    "가나다 표준조직 2026 생산 조직을 보여줘",
    "STEEL-00001 이력을 보여줘",
    "휴직중인 직원 몇 명이야?",
    "부서 변경 이력 보여줘",
    "2024년 S등급 평가 받은 사람",
    "2025년 월급 데이터 보여줘"
  ];

  var log = document.getElementById("chatLog");
  var input = document.getElementById("chatInput");

  var samplesEl = document.getElementById("chatSamples");
  SAMPLES.forEach(function (s) {
    var c = document.createElement("span");
    c.className = "chip";
    c.textContent = s;
    c.addEventListener("click", function () { input.value = s; send(); });
    samplesEl.appendChild(c);
  });

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderTable(cols, rows) {
    if (!cols.length) return "";
    var h = '<div class="result-table-wrap"><table class="grid"><thead><tr>';
    cols.forEach(function (c) { h += "<th>" + esc(c) + "</th>"; });
    h += "</tr></thead><tbody>";
    rows.forEach(function (r) {
      h += "<tr>";
      r.forEach(function (v) { h += "<td>" + esc(v) + "</td>"; });
      h += "</tr>";
    });
    return h + "</tbody></table></div>";
  }

  function renderAnswer(d) {
    var h = "<div><b>" + esc(d.summary) + "</b></div>";
    if (d.error) h += '<div class="chip bad">오류: ' + esc(d.error) + "</div>";
    h += renderTable(d.columns || [], d.rows || []);
    h += '<div class="meta-line">';
    (d.used_tables || []).forEach(function (t) { h += '<span class="chip">📋 ' + esc(t) + "</span>"; });
    (d.used_ontology || []).forEach(function (o) {
      var label = o.field + (o.negated ? " ≠ " : " = ") + o.value;
      h += '<span class="chip good">🧠 ' + esc(label) + "</span>";
    });
    h += "</div>";
    h += '<details class="sql-toggle"><summary class="muted">생성된 SQL 보기</summary><pre class="code">' +
      esc(d.sql) + "</pre></details>";
    return h;
  }

  function send() {
    var q = input.value.trim();
    if (!q) return;
    input.value = "";

    var msg = document.createElement("div");
    msg.className = "chat-msg";
    msg.innerHTML = '<div class="q">' + esc(q) + '</div><div class="a muted">검색 중…</div>';
    log.insertBefore(msg, log.firstChild); /* 최신 결과 상단 배치 */

    fetch("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, project: EmpProjects.current().id })
    }).then(function (r) { return r.json(); })
      .then(function (d) { msg.querySelector(".a").innerHTML = renderAnswer(d); })
      .catch(function (e) {
        msg.querySelector(".a").innerHTML = '<span class="chip bad">서버 오류: ' + esc(e) + "</span>";
      });
  }

  document.getElementById("chatSend").addEventListener("click", send);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
})();
