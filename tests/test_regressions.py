import sqlite3

import pytest

from oafc.metadata import IntegratorError, IntegratorStore
from tests.fakes import FakeMySQLStore


def _create_source(path, table_name):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE %s (id INTEGER PRIMARY KEY, value TEXT)" % table_name)


def test_discovery_skips_escaping_and_broken_symlinks(store, source_root, tmp_path):
    root, source = source_root
    outside = tmp_path.parent / (tmp_path.name + "-outside.sqlite")
    _create_source(outside, "private_data")
    (root / "escape.sqlite").symlink_to(outside)
    (root / "broken.sqlite").symlink_to(root / "missing.sqlite")

    discovered = store.discover()

    assert [item["location"] for item in discovered] == [str(source)]


def test_connection_identity_change_invalidates_derived_metadata(tmp_path):
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"
    _create_source(first, "alpha")
    _create_source(second, "beta")
    store = IntegratorStore(tmp_path / "meta.sqlite", [tmp_path])
    try:
        profile = store.save_connection({"engine": "sqlite", "name": "first", "location": str(first)})
        assert store.test_connection(profile["id"])["connected"] is True
        store.select_tables(profile["id"], ["alpha"])
        store.apply_ontology(profile["id"], store.ontology_suggestions(profile["id"]))
        assert store.workflow()["complete"] is True

        updated = store.save_connection({
            "id": profile["id"], "engine": "sqlite", "name": "second", "location": str(second)})

        assert updated["status"] == "saved"
        assert updated["last_tested_at"] is None
        assert store.selected_tables(profile["id"]) == []
        assert store.ontology(profile["id"]) == []
        assert store.workflow()["complete"] is False
    finally:
        store.close_thread_connection()


def test_selection_removes_stale_ontology(store, source_root):
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "source", "location": str(source)})
    store.test_connection(profile["id"])
    store.select_tables(profile["id"], ["products", "orders"])
    store.apply_ontology(profile["id"], store.ontology_suggestions(profile["id"]))

    store.select_tables(profile["id"], ["products"])
    assert {item["table_name"] for item in store.ontology(profile["id"])} == {"products"}

    store.select_tables(profile["id"], [])
    assert store.ontology(profile["id"]) == []
    assert store.workflow()["complete"] is False


@pytest.mark.parametrize("definition, message", [
    ({"target_type": "invented", "table_name": "products", "label": "bad"}, "target_type"),
    ({"target_type": "table", "table_name": "products", "column_name": "title", "label": "bad"},
     "cannot specify column_name"),
    ({"target_type": "column", "table_name": "products", "column_name": "missing", "label": "bad"},
     "unknown ontology column"),
    ({"target_type": "table", "table_name": "products", "label": "bad", "synonyms": [1]},
     "synonym"),
    ({"target_type": "table", "table_name": "products", "label": "bad", "synonyms": ["   "]},
     "synonym"),
    ({"target_type": "table", "table_name": "products", "label": "bad", "confidence": True},
     "confidence"),
    ({"target_type": "table", "table_name": "products", "label": "bad", "confidence": "0.5"},
     "confidence"),
    ({"target_type": "table", "table_name": "products", "label": "bad", "confidence": float("nan")},
     "confidence"),
])
def test_ontology_rejects_invalid_definitions(store, source_root, definition, message):
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "source", "location": str(source)})
    store.select_tables(profile["id"], ["products"])
    with pytest.raises(IntegratorError, match=message):
        store.apply_ontology(profile["id"], [definition])
    assert store.ontology(profile["id"]) == []


def test_mysql_selection_and_ontology_use_same_database_scope(tmp_path):
    store = FakeMySQLStore(tmp_path / "meta.db", [tmp_path], lambda _alias: "secret")
    try:
        profile = store.save_connection({
            "engine": "mysql", "name": "Warehouse", "host": "warehouse", "port": 3306,
            "username": "reader", "database_name": "analytics",
            "credential_alias": "WAREHOUSE_READONLY"})
        store.select_tables(profile["id"], [{"table_name": "catalog.products"}], ["catalog"])
        suggestions = store.ontology_suggestions(profile["id"])
        assert {item["table_name"] for item in suggestions} == {"catalog.products"}
    finally:
        store.close_thread_connection()


def test_mysql_tls_verifies_certificate_and_identity_by_default(tmp_path):
    captured = {}

    class Driver:
        class cursors:
            DictCursor = object()

        @staticmethod
        def connect(**kwargs):
            captured.update(kwargs)
            return object()

    store = IntegratorStore(tmp_path / "meta.db", [tmp_path], lambda _alias: "secret")
    try:
        profile = store.save_connection({
            "engine": "mysql", "name": "Warehouse", "host": "warehouse", "port": 3306,
            "username": "reader", "credential_alias": "WAREHOUSE_READONLY"})
        store._mysql_driver = lambda: Driver
        store._mysql_connection(profile)
        assert profile["tls_mode"] == "verify_identity"
        context = captured["ssl"]
        assert context.verify_mode == __import__("ssl").CERT_REQUIRED
        assert context.check_hostname is True
        assert "ssl_verify_cert" not in captured
        assert "ssl_verify_identity" not in captured
    finally:
        store.close_thread_connection()
