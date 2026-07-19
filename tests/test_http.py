import contextlib
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from oafc.server import create_server
from tests.fakes import FakeMySQLStore


@contextlib.contextmanager
def running_server(store, token=""):
    server = create_server("127.0.0.1", 0, store, api_token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def call(base, path, method="GET", payload=None, token="", headers=None):
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + path, data=data, method=method, headers=request_headers)
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read()
    content_type = response.headers.get_content_type()
    body = json.loads(raw.decode()) if content_type == "application/json" else raw
    return response.status, body


def test_http_sqlite_workflow(store, source_root):
    _root, source = source_root
    with running_server(store) as base:
        status, home = call(base, "/")
        assert status == 200 and b"DB Integrator" in home

        status, discovered = call(base, "/api/discovery")
        assert status == 200 and discovered["databases"][0]["location"] == str(source)

        status, profile = call(base, "/api/connections", "POST", {
            "engine": "sqlite", "name": "Commerce", "location": str(source)})
        assert status == 201
        connection_id = profile["id"]

        status, tested = call(base, "/api/connections/%s/test" % connection_id, "POST", {})
        assert status == 200 and tested["connected"] is True

        status, inventory = call(base, "/api/connections/%s/inventory" % connection_id)
        assert status == 200 and inventory["totals"]["table_count"] == 2

        status, schema = call(base, "/api/connections/%s/schema" % connection_id)
        assert status == 200 and schema["totals"]["column_count"] == 12

        status, selected = call(base, "/api/connections/%s/tables" % connection_id, "PUT", {
            "tables": [{"table_name": "products", "business_domain": "catalog",
                        "usage_purpose": "Product lookup"}]})
        assert status == 200 and selected["tables"][0]["business_domain"] == "catalog"

        status, drafts = call(base, "/api/connections/%s/ontology/suggest" % connection_id, "POST", {})
        assert status == 200 and {item["table_name"] for item in drafts["suggestions"]} == {"products"}

        status, applied = call(base, "/api/connections/%s/ontology/apply" % connection_id, "POST", {
            "definitions": drafts["suggestions"]})
        assert status == 200 and len(applied["definitions"]) == 6

        status, workflow = call(base, "/api/workflow")
        assert status == 200 and workflow["complete"] is True


def test_http_security_boundaries(store):
    with running_server(store, token="test-token") as base:
        status, _body = call(base, "/api/workflow")
        assert status == 401
        status, _body = call(base, "/api/workflow", token="test-token")
        assert status == 200
        status, body = call(base, "/api/connections", "POST", {}, token="test-token",
                            headers={"Origin": "https://outside.example"})
        assert status == 403 and "Cross-origin" in body["error"]

        request = urllib.request.Request(
            base + "/api/connections", data=b"{}", method="POST",
            headers={"Authorization": "Bearer test-token", "Content-Type": "text/plain"})
        with pytest.raises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(request, timeout=5)
        assert rejected.value.code == 415


def test_http_mysql_inventory_and_database_filter(tmp_path):
    store = FakeMySQLStore(tmp_path / "meta.db", [tmp_path], lambda _alias: "secret")
    profile = store.save_connection({
        "engine": "mysql", "name": "Warehouse", "host": "warehouse", "port": 3306,
        "username": "reader", "credential_alias": "WAREHOUSE_READONLY"})
    with running_server(store) as base:
        status, inventory = call(base, "/api/connections/%s/inventory" % profile["id"])
        assert status == 200 and inventory["totals"]["database_count"] == 3
        query = urllib.parse.urlencode([("database", "analytics"), ("database", "catalog")])
        status, schema = call(base, "/api/connections/%s/schema?%s" % (profile["id"], query))
        assert status == 200
        assert {table["qualified_name"] for table in schema["tables"]} == {
            "analytics.events", "catalog.products"}
    store.close_thread_connection()


def test_external_bind_requires_token_and_hosts(store):
    with pytest.raises(ValueError, match="OAFC_API_TOKEN"):
        create_server("0.0.0.0", 0, store)


def test_http_read_only_analysis_and_connection_delete(store, source_root):
    _root, source = source_root
    with running_server(store) as base:
        status, profile = call(base, "/api/connections", "POST", {
            "engine": "sqlite", "name": "Managed", "location": str(source)})
        assert status == 201
        connection_id = profile["id"]
        status, _tested = call(base, "/api/connections/%s/test" % connection_id, "POST", {})
        assert status == 200

        status, result = call(base, "/api/connections/%s/analysis/query" % connection_id,
                              "POST", {"query": "SELECT 1 AS value", "max_rows": 50,
                                       "timeout_ms": 2000})
        assert status == 200
        assert result["columns"] == ["value"]
        assert result["rows"] == [[1]]
        assert result["truncated"] is False

        status, non_finite = call(base, "/api/connections/%s/analysis/query" % connection_id,
                                  "POST", {"query": "SELECT 1e999 AS value"})
        assert status == 200 and non_finite["rows"] == [["inf"]]

        status, rejected = call(base, "/api/connections/%s/analysis/query" % connection_id,
                                "POST", {"query": "DELETE FROM products"})
        assert status == 400
        assert "only SELECT or WITH" in rejected["error"]

        status, listed = call(base, "/api/connections")
        assert status == 200
        assert listed["connections"][0]["selected_table_count"] == 0
        assert listed["connections"][0]["ontology_count"] == 0

        status, deleted = call(base, "/api/connections/%s" % connection_id, "DELETE")
        assert status == 200 and deleted["deleted"] is True
        status, _missing = call(base, "/api/connections/%s" % connection_id)
        assert status == 404
