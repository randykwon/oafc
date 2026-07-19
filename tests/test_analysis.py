import sqlite3
import time

import pytest

from oafc.metadata import IntegratorError
from tests.fakes import FakeMySQLStore


def _sqlite_profile(store, source, connected=True):
    profile = store.save_connection({
        "engine": "sqlite", "name": "Analysis", "location": str(source)})
    if connected:
        assert store.test_connection(profile["id"])["connected"] is True
    return profile


def test_sqlite_analysis_requires_tested_connection_and_limits_rows(store, source_root):
    _root, source = source_root
    with sqlite3.connect(source) as conn:
        conn.executemany(
            "INSERT INTO products(product_id,title,category,unit_price,created_at) VALUES(?,?,?,?,?)",
            [(1, "Alpha", "A", 10.5, "2026-01-01"),
             (2, "Beta", "B", 20.0, "2026-01-02"),
             (3, "Gamma", "A", 30.0, "2026-01-03")])
    profile = _sqlite_profile(store, source, connected=False)
    with pytest.raises(IntegratorError, match="test the connection"):
        store.analyze_query(profile["id"], "SELECT * FROM products")

    assert store.test_connection(profile["id"])["connected"] is True
    result = store.analyze_query(
        profile["id"],
        "SELECT product_id,title FROM products ORDER BY product_id;",
        max_rows=2, timeout_ms=2_000)

    assert result["engine"] == "sqlite"
    assert result["columns"] == ["product_id", "title"]
    assert result["rows"] == [[1, "Alpha"], [2, "Beta"]]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    assert result["max_rows"] == 2
    assert result["elapsed_ms"] >= 0


def test_analysis_allows_literals_but_serializes_binary(store, source_root):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    result = store.analyze_query(
        profile["id"], "SELECT 'DROP TABLE; -- text' AS note, X'00FF' AS payload")
    assert result["rows"] == [["DROP TABLE; -- text", "0x00ff"]]


@pytest.mark.parametrize("query, message", [
    ("", "required"),
    ("UPDATE products SET title='x'", "only SELECT or WITH"),
    ("WITH changed AS (SELECT 1) DELETE FROM products", "DELETE"),
    ("SELECT 1; SELECT 2", "one SQL statement"),
    ("SELECT 1 -- hidden statement", "comments"),
    ("SELECT /* comment */ 1", "comments"),
    ("SELECT SLEEP(1)", "unsafe or unsupported"),
    ("SELECT * FROM products INTO OUTFILE '/tmp/data'", "INTO"),
    ("SELECT * FROM products FOR UPDATE", "UPDATE"),
    ("SELECT @value := 1", "assignment"),
    ("SELECT 'x\\', SLEEP(10), 'alias\\' /* ' */", "backslash"),
    ("WITH c AS (SELECT 'x\\') UPDATE products SET title='x' WHERE 'a\\' /* ' */", "backslash"),
    ("SELECT SYS_EXEC('touch /tmp/unsafe')", "unsupported SQL function"),
    ("SELECT custom_side_effect()", "unsupported SQL function"),
    ("SELECT `custom_side_effect`()", "quoted SQL function"),
    ('SELECT "custom_side_effect"()', "quoted SQL function"),
    ("SELECT * FROM products FOR SHARE", "locking reads"),
])
def test_analysis_rejects_non_read_only_sql(store, source_root, query, message):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    with pytest.raises(IntegratorError, match=message):
        store.analyze_query(profile["id"], query)


@pytest.mark.parametrize("query", [
    "SELECT * FROM (SELECT 1 AS value) AS nested",
    "SELECT * FROM products WHERE (unit_price > 10)",
    "WITH c(value) AS (VALUES (1)) SELECT value FROM c",
    "SELECT CASE WHEN (1=1) THEN 1 ELSE 0 END AS value",
    "SELECT COUNT(*) AS count, ROUND(AVG(unit_price), 2) AS average FROM products",
])
def test_analysis_allows_common_parenthesized_select_syntax(store, source_root, query):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    result = store.analyze_query(profile["id"], query)
    assert result["columns"]


@pytest.mark.parametrize("field, value, message", [
    ("max_rows", 0, "max_rows must be between"),
    ("max_rows", 501, "max_rows must be between"),
    ("max_rows", True, "max_rows must be an integer"),
    ("timeout_ms", 99, "timeout_ms must be between"),
    ("timeout_ms", 10_001, "timeout_ms must be between"),
])
def test_analysis_validates_execution_limits(store, source_root, field, value, message):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    kwargs = {field: value}
    with pytest.raises(IntegratorError, match=message):
        store.analyze_query(profile["id"], "SELECT 1", **kwargs)


def test_sqlite_analysis_timeout_interrupts_expensive_query(store, source_root):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    query = """
        WITH RECURSIVE counter AS (
          SELECT 1 AS value UNION ALL SELECT value + 1 FROM counter WHERE value < 100000000
        ) SELECT SUM(value) FROM counter
    """
    with pytest.raises(IntegratorError, match="timed out"):
        store.analyze_query(profile["id"], query, timeout_ms=100)



def test_sqlite_analysis_lock_wait_respects_request_timeout(store, source_root):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    locker = sqlite3.connect(source, timeout=0)
    try:
        locker.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        with pytest.raises(IntegratorError, match="timed out"):
            store.analyze_query(profile["id"], "SELECT * FROM products", timeout_ms=100)
        assert time.monotonic() - started < 1.0
    finally:
        locker.rollback()
        locker.close()


def test_analysis_normalizes_non_finite_float_for_strict_json(store, source_root):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    result = store.analyze_query(profile["id"], "SELECT 1e999 AS value")
    assert result["rows"] == [["inf"]]

def test_mysql_analysis_uses_database_scope_and_truncates(tmp_path):
    store = FakeMySQLStore(tmp_path / "meta.db", [tmp_path], lambda _alias: "secret")
    try:
        profile = store.save_connection({
            "engine": "mysql", "name": "Warehouse", "host": "warehouse", "port": 3306,
            "username": "reader", "credential_alias": "WAREHOUSE_READONLY"})
        assert store.test_connection(profile["id"])["connected"] is True
        result = store.analyze_query(
            profile["id"], "SELECT event_id,product_id FROM events ORDER BY event_id",
            database="analytics", max_rows=2, timeout_ms=2_000)
        assert result["engine"] == "mysql"
        assert result["database"] == "analytics"
        assert result["columns"] == ["event_id", "product_id"]
        assert result["rows"] == [[1, 101], [2, 102]]
        assert result["truncated"] is True
        with pytest.raises(IntegratorError, match="not accessible"):
            store.analyze_query(profile["id"], "SELECT 1", database="private")
    finally:
        store.close_thread_connection()


def test_connection_list_includes_management_counts(store, source_root):
    _root, source = source_root
    profile = _sqlite_profile(store, source)
    store.select_tables(profile["id"], ["products"])
    store.apply_ontology(profile["id"], store.ontology_suggestions(profile["id"]))
    listed = store.list_connections()[0]
    assert listed["selected_table_count"] == 1
    assert listed["ontology_count"] == 6
