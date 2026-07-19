import os

import pytest

from oafc.metadata import EnvironmentCredentialResolver, IntegratorError
from tests.fakes import FakeMySQLStore


def test_sqlite_discovery_and_analysis(store, source_root):
    _root, source = source_root
    discovered = store.discover()
    assert [item["location"] for item in discovered] == [str(source)]
    assert discovered[0]["table_count"] == 3

    profile = store.save_connection({
        "engine": "sqlite", "name": "Commerce", "location": str(source),
        "credential_alias": "LOCAL_READONLY",
    })
    tested = store.test_connection(profile["id"])
    assert tested["connected"] is True
    assert tested["database_count"] == 1

    inventory = store.inventory(profile["id"])
    assert inventory["totals"]["table_count"] == 2
    assert inventory["totals"]["view_count"] == 1

    schema = store.schema(profile["id"])
    assert {table["qualified_name"] for table in schema["tables"]} == {
        "products", "orders", "product_titles"}
    assert schema["totals"]["relationship_count"] == 1


def test_business_table_selection_limits_ontology(store, source_root):
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "Source", "location": str(source)})
    assert store.test_connection(profile["id"])["connected"] is True
    selected = store.select_tables(profile["id"], [{
        "table_name": "products", "business_domain": "catalog",
        "usage_purpose": "Canonical product lookup",
    }])
    assert selected[0]["business_domain"] == "catalog"
    suggestions = store.ontology_suggestions(profile["id"])
    assert {item["table_name"] for item in suggestions} == {"products"}
    assert suggestions[0]["semantic_type"] == "catalog"
    assert suggestions[0]["description"] == "Canonical product lookup"

    definitions = store.apply_ontology(profile["id"], suggestions)
    assert len(definitions) == 6
    assert store.workflow()["complete"] is True

    with pytest.raises(IntegratorError, match="selected business table"):
        store.apply_ontology(profile["id"], [{
            "target_type": "table", "table_name": "orders", "label": "Orders"}])


def test_secret_and_path_boundaries(store, source_root, tmp_path):
    _root, source = source_root
    with pytest.raises(IntegratorError, match="raw secrets"):
        store.save_connection({
            "engine": "sqlite", "location": str(source), "name": "unsafe", "password": "raw"})
    outside = tmp_path.parent / "outside.sqlite"
    outside.touch()
    with pytest.raises(IntegratorError, match="outside configured"):
        store.save_connection({"engine": "sqlite", "location": str(outside), "name": "outside"})


def test_environment_credential_alias(monkeypatch):
    resolver = EnvironmentCredentialResolver()
    monkeypatch.setenv("OAFC_CREDENTIAL_WAREHOUSE_READONLY", "resolved-secret")
    assert resolver("warehouse-readonly") == "resolved-secret"
    monkeypatch.delenv("OAFC_CREDENTIAL_WAREHOUSE_READONLY")
    with pytest.raises(IntegratorError, match="not configured"):
        resolver("warehouse-readonly")


def test_mysql_server_inventory_schema_and_business_scope(tmp_path):
    store = FakeMySQLStore(tmp_path / "meta.db", [tmp_path], lambda _alias: "secret")
    profile = store.save_connection({
        "engine": "mysql", "name": "Warehouse", "host": "warehouse",
        "port": 3306, "username": "reader", "credential_alias": "WAREHOUSE_READONLY",
    })
    assert "password" not in profile
    tested = store.test_connection(profile["id"])
    assert tested["connected"] is True
    assert tested["database_count"] == 3
    assert tested["table_count"] == 12

    inventory = store.inventory(profile["id"])
    assert inventory["server"]["version"] == "8.0.40"
    assert inventory["server"]["max_connections"] == 250
    assert inventory["totals"]["data_bytes"] == 12388
    assert [item["name"] for item in inventory["databases"] if not item["system"]] == [
        "analytics", "catalog"]
    assert inventory["databases"][0]["routine_count"] == 2

    schema = store.schema(profile["id"], ["analytics", "catalog"])
    assert {table["qualified_name"] for table in schema["tables"]} == {
        "analytics.events", "catalog.products"}
    assert schema["totals"] == {
        "table_count": 2, "view_count": 0, "column_count": 4, "relationship_count": 1}
    event_table = [table for table in schema["tables"] if table["qualified_name"] == "analytics.events"][0]
    assert event_table["index_count"] == 2
    assert event_table["columns"][0]["primary_key"] is True

    selected = store.select_tables(profile["id"], [{
        "table_name": "analytics.events", "business_domain": "behavior",
        "usage_purpose": "Behavior trend analysis",
    }])
    assert selected[0]["usage_purpose"] == "Behavior trend analysis"
    suggestions = store.ontology_suggestions(profile["id"])
    assert {item["table_name"] for item in suggestions} == {"analytics.events"}
    assert suggestions[0]["semantic_type"] == "behavior"
    store.close_thread_connection()
