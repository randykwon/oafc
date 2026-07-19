from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "oafc" / "web"


def test_wizard_contains_database_analysis_flow():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for label in ["DB 탐색", "정보 저장", "테이블 선택", "온톨로지 적용"]:
        assert label in html
    for element_id in ["mysqlHost", "mysqlPort", "mysqlUsername", "mysqlTlsMode",
                       "mysqlSslCa", "databaseInventory", "analyzeDatabasesBtn", "tableList",
                       "suggestionList", "newConnectionBtn", "openAnalysisBtn", "analysisTool",
                       "analysisDatabase", "analysisQuery", "runAnalysisBtn", "analysisResult",
                       "exportAnalysisBtn"]:
        assert 'id="%s"' % element_id in html


def test_frontend_uses_mysql_inventory_and_business_metadata():
    source = (WEB / "app.js").read_text(encoding="utf-8")
    assert '"/inventory"' in source
    assert 'business_domain' in source
    assert 'usage_purpose' in source
    assert 'database=' in source
    assert 'databases:' in source
    assert 'if (!selected.length)' not in source
    assert 'OAFC_CREDENTIAL_' in (WEB / "index.html").read_text(encoding="utf-8")


def test_dynamic_html_escape_covers_attribute_quotes():
    source = (WEB / "app.js").read_text(encoding="utf-8")
    assert "&quot;" in source
    assert "&#39;" in source


def test_frontend_manages_connections_and_runs_safe_analysis():
    source = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'data-action="delete"' in source
    assert 'method: "DELETE"' in source
    assert '"/analysis/query"' in source
    assert 'max_rows:' in source and 'timeout_ms:' in source
    assert 'td.textContent' in source
    assert '/^[\\s\\x00-\\x1f]*[=+@-]/' in source
    assert 'URL.revokeObjectURL' in source


def test_frontend_connection_state_and_analysis_requests_are_scoped():
    source = (WEB / "app.js").read_text(encoding="utf-8")
    assert "activateConnection(profile, 2)" in source
    assert "state.analysisEpoch" in source
    assert "state.inventoryEpoch" in source and "state.schemaEpoch" in source
    assert "state.activeId === connectionId" in source
    assert 'addEventListener("change", function () { loadAnalysisSchema(); })' in source
    assert "return refreshConnections().then(function ()" in source
