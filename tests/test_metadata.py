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


def test_relationship_discovery_physical_and_inferred(store, source_root):
    """Data Knowledge Builder: 물리 FK 는 confidence 1.0, 추론 관계는 다중 신호로 산출."""
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "Commerce", "location": str(source)})
    assert store.test_connection(profile["id"])["connected"] is True

    result = store.discover_relationships(profile["id"])
    assert result["summary"]["entity_count"] == 3          # products, orders, product_titles
    rels = result["relationships"]
    assert rels, "expected at least one relationship"

    # 물리 FK: orders.product_id -> products.product_id
    fk = [r for r in rels if r["method"] == "physical_fk"]
    assert fk and fk[0]["confidence"] == 1.0
    assert fk[0]["from_table"] == "orders" and fk[0]["to_table"] == "products"
    assert fk[0]["predicate"] == "belongs_to"
    assert "Orders belongs_to Products" == fk[0]["label"]

    # 모든 관계는 evidence 와 0~1 confidence 를 가진다
    assert all(r["evidence"] for r in rels)
    assert all(0.0 <= r["confidence"] <= 1.0 for r in rels)
    # confidence 내림차순 정렬
    assert [r["confidence"] for r in rels] == sorted([r["confidence"] for r in rels], reverse=True)


def test_relationship_approval_persists_with_provenance(store, source_root):
    """관계 승인/제외 저장: Provenance(validated_at) 기록, 재발견 시 status 병합."""
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "Commerce", "location": str(source)})
    assert store.test_connection(profile["id"])["connected"] is True

    fk = [r for r in store.discover_relationships(profile["id"])["relationships"]
          if r["method"] == "physical_fk"][0]
    assert fk["status"] == "candidate"

    decision = {k: fk[k] for k in ("from_table", "from_column", "to_table", "to_column",
                                   "predicate", "method", "confidence", "evidence")}
    decision["status"] = "approved"
    saved = store.save_relationships(profile["id"], [decision])
    assert len(saved) == 1
    assert saved[0]["status"] == "approved"
    assert saved[0]["validated_at"] and saved[0]["validated_by"] == "user"

    # 재발견 시 승인 상태가 병합된다
    again = store.discover_relationships(profile["id"])
    assert again["summary"]["approved"] == 1
    approved = [r for r in again["relationships"] if r["status"] == "approved"]
    assert approved and approved[0]["from_table"] == fk["from_table"]

    # 제외하면 저장에서 삭제된다
    decision["status"] = "rejected"
    assert store.save_relationships(profile["id"], [decision]) == []
    assert store.discover_relationships(profile["id"])["summary"]["approved"] == 0


def test_semantic_model_integrates_entities_and_relationships(store, source_root):
    """Semantic Model: 선택 테이블(엔티티)+온톨로지 속성+승인 관계를 통합한다."""
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "Commerce", "location": str(source)})
    assert store.test_connection(profile["id"])["connected"] is True
    store.select_tables(profile["id"], [
        {"table_name": "products", "business_domain": "catalog", "usage_purpose": "제품 기준정보"},
        {"table_name": "orders", "business_domain": "sales", "usage_purpose": "주문"},
    ])
    store.apply_ontology(profile["id"], store.ontology_suggestions(profile["id"]))
    # 물리 FK 관계 승인
    fk = [r for r in store.discover_relationships(profile["id"])["relationships"]
          if r["method"] == "physical_fk"][0]
    decision = {k: fk[k] for k in ("from_table", "from_column", "to_table", "to_column",
                                   "predicate", "method", "confidence", "evidence")}
    decision["status"] = "approved"
    store.save_relationships(profile["id"], [decision])

    model = store.semantic_model(profile["id"])
    assert model["summary"]["entity_count"] == 2
    assert model["summary"]["defined_entity_count"] == 2   # 온톨로지 적용됨
    assert model["summary"]["coverage"] == 1.0
    assert model["summary"]["attribute_count"] > 0
    # 승인 관계가 provenance 와 함께 포함된다
    assert model["summary"]["relationship_count"] == 1
    rel = model["relationships"][0]
    assert rel["from_entity"] == "Orders" and rel["to_entity"] == "Products"
    assert rel["provenance"]["validated_by"] == "user" and rel["provenance"]["validated_at"]
    # 엔티티는 속성(컬럼 의미)을 가진다
    entity = [e for e in model["entities"] if e["table"] == "products"][0]
    assert entity["business_domain"] == "catalog" and entity["attributes"]


def test_nl_to_sql_drafts_safe_readonly_query(store, source_root):
    """자연어 → 읽기전용 SELECT 초안: 엔티티/컬럼 매칭 + 집계, 검증기 통과."""
    _root, source = source_root
    profile = store.save_connection({"engine": "sqlite", "name": "Commerce", "location": str(source)})
    assert store.test_connection(profile["id"])["connected"] is True
    store.select_tables(profile["id"], [
        {"table_name": "products", "business_domain": "catalog", "usage_purpose": "제품"},
        {"table_name": "orders", "business_domain": "sales", "usage_purpose": "주문"},
    ])
    store.apply_ontology(profile["id"], store.ontology_suggestions(profile["id"]))

    count = store.nl_to_sql(profile["id"], "how many products")
    assert count["evidence"]["table"] == "products"
    assert count["evidence"]["intent"] == "건수"
    assert "COUNT(*)" in count["sql"]
    # 생성 SQL 은 읽기전용 검증기를 통과해야 한다
    assert store._validated_analysis_sql(count["sql"])
    # 실제 실행되어야 한다
    result = store.analyze_query(profile["id"], count["sql"])
    assert result["row_count"] == 1

    colq = store.nl_to_sql(profile["id"], "order quantity and total amount")
    assert colq["evidence"]["table"] == "orders"
    assert "quantity" in colq["sql"]
    assert store._validated_analysis_sql(colq["sql"])

    # 한국어 "별 … 수" → group-by + COUNT (order_status 로 그룹)
    grouped = store.nl_to_sql(profile["id"], "상태별 주문 수")
    assert grouped["evidence"]["table"] == "orders"
    assert grouped["evidence"]["intent"] == "건수"
    assert grouped["evidence"]["group_by"] == "order_status"
    assert "GROUP BY" in grouped["sql"] and "COUNT(*)" in grouped["sql"]
    assert store._validated_analysis_sql(grouped["sql"])

    with pytest.raises(IntegratorError):
        store.nl_to_sql(profile["id"], "   ")
