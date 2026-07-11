"""OAFC 핵심 기능 테스트 (2026-07-09 스펙 기준)."""

import pytest

from empsearch import db, nlq, ontology_ai


@pytest.fixture(scope="module")
def schema():
    db.get_conn()
    return db.get_schema()


def test_schema_counts(schema):
    """Schema Graph 기준: 테이블 18 / 컬럼 227 / 관계 25."""
    assert len(schema["tables"]) == 18
    assert sum(len(t["columns"]) for t in schema["tables"]) == 227
    assert len(schema["relationships"]) == 25


def test_summary(schema):
    s = db.get_summary()
    assert s["employees"] == db.SEED_EMPLOYEES
    assert s["departments"] == 19
    assert s["work_locations"] == 4
    assert set(s["status_distribution"]) == {"active", "on_leave", "resigned"}


def test_manager_negation():
    """'manager가 아닌'은 manager 를 제외하고, 'manager인'은 team_lead 를 포함하지 않는다."""
    r_not = nlq.answer("manager가 아닌 재직중인 서울 근무 여성 직원 몇 명이야?")
    assert "management_level != 'manager'" in r_not["sql"]
    r_is = nlq.answer("서울 근무 manager인 사람 알려줘")
    idx = r_is["columns"].index("management_level")
    levels = set(row[idx] for row in r_is["rows"])
    assert levels == {"manager"}


def test_years_of_service_condition():
    """근속연수 조건: '18년 이상 근무', '15년차 이상' 인식."""
    r = nlq.answer("광양 근무자 중 여성 18년 이상 근무하고 manager인 사람만 뽑아줘")
    assert "years_of_service >= '18'" in r["sql"]
    assert "work_location LIKE '%광양%'" in r["sql"]
    idx = r["columns"].index("years_of_service")
    assert all(row[idx] >= 18 for row in r["rows"])
    r2 = nlq.answer("포항에 근무하는 15년차 이상 여성 관리자를 찾아줘")
    assert "years_of_service >= '15'" in r2["sql"]


def test_org_structure_and_timeline():
    """표준조직 검색과 STEEL 사번 이력 조회."""
    r = nlq.answer("가나다 표준조직 2026 생산 조직을 보여줘")
    assert r["used_tables"] == ["ganada.org_structure"]
    assert r["row_count"] > 0
    tl = db.get_timeline("STEEL-00001")
    assert tl["employee"]["employee_no"] == "STEEL-00001"
    assert tl["event_count"] > 0
    r2 = nlq.answer("STEEL-00001 이력을 보여줘")
    assert r2["kind"] == "timeline"


def test_ontology_roundtrip_and_review_note():
    """Ontology 저장/조회/삭제와 값 매핑(배열)/동의어 검증."""
    project = "pytest"
    db.ontology_bulk_delete("all", project=project)
    defn = {
        "target_type": "field",
        "table_name": "public.employee_information",
        "field_name": "status",
        "label": "재직 상태",
        "description": "본문 설명\n\n[리뷰 메모]\n확인 필요",
        "synonyms": ["재직상태", "상태"],
        "value_map": [{"value": "active", "synonyms": ["재직", "재직중"]}],
        "use_in_sql": True,
    }
    db.ontology_save(defn, project)
    defs = db.ontology_list(project)
    assert len(defs) == 1
    saved = defs[0]
    assert saved["synonyms"] == "재직상태,상태"
    assert saved["value_map"][0]["value"] == "active"
    # synonyms 는 배열/문자열만 허용
    with pytest.raises(ValueError):
        db.ontology_save(dict(defn, field_name="x", synonyms={"bad": 1}), project)
    assert db.ontology_bulk_delete(
        "field", "public.employee_information", "status", project) == 1


def test_status_negation_not_active():
    """'재직중이 아닌' 은 status != 'active' (긴 표현 우선 매칭 회귀 방지)."""
    r = nlq.answer("재직중이 아닌 서울 근무 직원 몇 명이야?")
    assert "status != 'active'" in r["sql"]
    assert "status = 'active'" not in r["sql"]
    # marital_status(다른 테이블 컬럼)가 잘못 섞이지 않는다
    assert "marital_status" not in r["sql"]
    r2 = nlq.answer("휴직중이 아닌 직원 몇 명?")
    assert "status != 'on_leave'" in r2["sql"]


def test_marital_status_not_polluted_by_status_map():
    """marital_status 는 status 값 매핑(재직/휴직/퇴사)을 물려받지 않는다."""
    col = {"name": "marital_status", "type": "TEXT", "is_pk": False, "is_fk": False}
    info = ontology_ai.infer_field("public.employees", col)
    assert info["field_name"] == "marital_status"
    assert info["value_map"] == []
    # 반대로 실제 status 필드는 값 매핑을 받아야 한다
    status_info = ontology_ai.infer_field(
        "public.employee_information",
        {"name": "status", "type": "TEXT", "is_pk": False, "is_fk": False})
    assert status_info["value_map"]


def test_value_map_whitelist_blocks_injection():
    """employee_information 에 없는 필드/주입 문자열은 SQL 조건으로 쓰지 않는다."""
    proj = "pytest_sec"
    db.ontology_bulk_delete("all", project=proj)
    db.ontology_save({
        "target_type": "field", "table_name": "public.employee_information",
        "field_name": "status=1 OR 1=1--", "label": "x",
        "value_map": [{"value": "z", "synonyms": ["주입키워드"]}], "use_in_sql": True,
    }, proj)
    r = nlq.answer("주입키워드 직원 몇 명?", project=proj)
    assert "1=1" not in r["sql"]
    db.ontology_bulk_delete("all", project=proj)


def test_automate_generates_245(schema):
    """전체 자동 생성: 테이블 18 + 필드 227 = 245건 제안."""
    suggestions = ontology_ai.infer_for_tables(schema["tables"])
    assert len(suggestions) == 245
    by_type = {}
    for s in suggestions:
        by_type[s["target_type"]] = by_type.get(s["target_type"], 0) + 1
    assert by_type["table"] == 18
    assert by_type["field"] == 227
    # 테이블 자동 보정 (MySQL DB 자동 보정 스펙)
    resolved, note = db.resolve_table("employee_salary_db.evaluation_scores")
    assert resolved == "employee_evaluation_db.evaluation_scores"
    assert note
