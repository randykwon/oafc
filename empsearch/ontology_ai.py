"""Ontology 자동 유추 / 의미 자동 생성 휴리스틱.

테이블명, 필드명, 데이터 타입, PK/FK 여부, 테이블 comment, 업무 도메인 키워드를
근거로 의미 제안(label/description/synonyms/value_map)과 신뢰도(confidence),
근거(evidence)를 생성한다.

값 매핑 형식 (2026-07-09 스펙): 배열 JSON 이며 각 항목은 `value` 를 가진 객체다.
  [{"value": "active", "synonyms": ["재직", "재직중", "근무중"]}, ...]
"""

# 필드명 패턴 -> (label, description, synonyms, confidence)
FIELD_HINTS = [
    (("employee_no",), "직원 사번", "임직원을 고유하게 식별하는 사번 (STEEL-xxxxx)", "사번,직원번호,임직원ID", 0.95),
    (("employee_id",), "직원 식별자", "임직원 내부 식별자", "직원ID,내부식별자", 0.95),
    (("korean_name", "name"), "이름", "임직원 또는 대상의 이름", "성명,이름", 0.9),
    (("english_name",), "영문 이름", "임직원 영문 이름", "영문명", 0.88),
    (("gender",), "성별", "임직원 성별 구분", "성별", 0.92),
    (("birth",), "생년월일", "임직원 생년월일", "생일,출생일", 0.9),
    (("hire_date", "join"), "입사일", "회사 입사 시점", "입사일자,입사년도,입사", 0.92),
    (("resignation", "retire"), "퇴사일", "회사 퇴사 시점", "퇴사일자,퇴직일", 0.92),
    (("years_of_service",), "근속연수", "입사 후 경과 연수", "근속,연차,년차,근무연수", 0.93),
    (("status",), "상태 분류", "재직/휴직/퇴사 등 상태 코드", "재직상태,상태", 0.9),
    (("department_code",), "부서 코드", "소속 부서를 가리키는 표준 부서 코드", "부서코드", 0.9),
    (("previous_department",), "변경 이전 부서", "부서 변경 이전의 부서 이름", "이전부서,변경전부서", 0.9),
    (("department",), "부서/소속 조직", "임직원이 소속된 조직 단위", "부서,소속,팀,조직", 0.88),
    (("job_title", "position_name",), "직무/역할 정보", "직급 또는 직책", "직급,직책,직무", 0.85),
    (("management_level",), "관리자/리더 구분", "manager, team_lead, executive, individual_contributor 구분", "관리레벨,직위구분,관리자여부", 0.9),
    (("work_location", "location", "site"), "근무지/사업장", "근무하는 사업장 (서울 본사/포항 제철소/광양 제철소/송도 R&D 캠퍼스)", "근무지,사업장,지역", 0.88),
    (("email",), "이메일", "임직원 이메일 주소", "메일,이메일주소", 0.9),
    (("phone", "contact"), "연락처", "전화번호/연락처", "전화,연락처,전화번호", 0.85),
    (("salary_grade",), "급여 등급", "보상 밴드/급여 등급", "급여등급,연봉등급", 0.85),
    (("base_salary",), "기본급", "월 기본급", "기본급,본봉", 0.9),
    (("net_pay", "total_pay"), "실지급액", "공제 후 실지급 금액", "실수령액,실지급", 0.88),
    (("salary", "pay"), "보상/급여 데이터", "급여 또는 보상 금액", "급여,월급,연봉,보상", 0.86),
    (("bonus", "incentive"), "상여/인센티브", "보너스/상여/인센티브 금액", "보너스,상여,인센티브", 0.86),
    (("allowance",), "수당", "각종 수당 금액", "수당", 0.84),
    (("deduction", "fee"), "공제 항목", "세금/보험 등 공제 금액", "공제,세금", 0.82),
    (("grade",), "평가 등급", "성과 평가 등급 (S/A/B/C)", "등급,평가등급", 0.85),
    (("score",), "평가 점수", "성과 평가 점수", "점수,평가점수", 0.85),
    (("evaluation_cycle",), "평가 주기", "평가 주기 (연간/하반기 등)", "평가주기", 0.85),
    (("evaluation", "eval"), "평가/성과 데이터", "평가 관련 데이터", "평가,성과", 0.8),
    (("changed_at", "change_date"), "변경 시점", "변경이 발생한 일시", "변경일,변경일자", 0.85),
    (("change_type",), "유형/분류 코드", "변경의 종류 분류", "변경유형", 0.8),
    (("change_reason", "reason"), "변경 사유", "변경이 발생한 사유", "사유,이유", 0.8),
    (("established",), "설립일", "조직 설립 시점", "설립일자,창설일", 0.8),
    (("parent",), "상위 조직", "상위 부서/조직 참조", "상위부서,모조직", 0.82),
    (("is_", "has_", "flag", "enabled", "approved", "recommended", "final", "active", "current"),
     "사용/승인 여부", "boolean 성 여부 필드", "여부", 0.8),
    (("month",), "월 구분", "연-월 기간 구분", "월,지급월", 0.8),
    (("year",), "연도 구분", "연도 기간 구분", "년도,연도", 0.8),
    (("concept",), "Ontology 개념", "자연어 SQL 생성을 위한 개념 참조", "개념", 0.82),
    (("pattern",), "질의 패턴", "자연어 질의 패턴", "패턴", 0.82),
    (("confidence",), "신뢰도", "자동 생성 신뢰도 점수", "신뢰도", 0.85),
    (("synonym",), "동의어", "동의어 목록", "동의어", 0.85),
]

TABLE_HINTS = [
    (("employees",), "임직원 마스터 데이터", "임직원 한 명당 한 행인 마스터 테이블 (STEEL-xxxxx 사번)."),
    (("employee_information",), "임직원 주체 데이터", "임직원 기본 정보 테이블. 현재 부서/근무지/근속연수를 포함한다."),
    (("department_management",), "조직/부서 기준 데이터", "표준 부서를 관리하는 기준 정보 테이블."),
    (("departments",), "조직/부서 기준 데이터", "부서 마스터 테이블."),
    (("department_change_history",), "변경 이력 데이터", "임직원 부서 변경 이력. 부서이름과 변경이전 부서이름으로 구성된다."),
    (("work_location_history",), "변경 이력 데이터", "임직원 근무지 변경 이력."),
    (("change_history", "history"), "변경 이력 데이터", "시간에 따른 변경 이력을 기록하는 테이블."),
    (("assignments",), "배치 이력 데이터", "임직원 부서/직위 배치 이력."),
    (("work_locations",), "근무지 기준 데이터", "사업장/근무지 마스터."),
    (("job_positions",), "직위 기준 데이터", "직위/직급 마스터."),
    (("org_structure",), "조직/부서 기준 데이터", "가나다 기업 표준조직 구조 테이블."),
    (("salary",), "보상/급여 데이터", "임직원 급여/보상 지급 데이터 테이블 (MySQL employee_salary_db)."),
    (("evaluation",), "평가/성과 데이터", "임직원 평가 주기/결과/점수 테이블 (MySQL employee_evaluation_db)."),
    (("ontology_concepts",), "Ontology 메타데이터", "자연어 SQL 을 위한 개념 정의."),
    (("ontology_concept_columns",), "Ontology 메타데이터", "개념-컬럼 매핑."),
    (("ontology_relationships",), "Ontology 메타데이터", "개념 간 의미 관계."),
    (("ontology_query_patterns",), "Ontology 메타데이터", "자연어 질의 패턴 (Query Planner)."),
    (("ontology_definitions",), "Ontology 메타데이터", "테이블/필드 의미 정의 저장소."),
]

# 코드성 필드 기본 값 매핑 (배열 형식)
DEFAULT_VALUE_MAPS = {
    "gender": [
        {"value": "female", "synonyms": ["여성", "여자", "female"]},
        {"value": "male", "synonyms": ["남성", "남자", "male"]},
    ],
    "status": [
        {"value": "active", "synonyms": ["재직", "재직중", "근무중"]},
        {"value": "on_leave", "synonyms": ["휴직", "휴직중"]},
        {"value": "resigned", "synonyms": ["퇴사", "퇴직"]},
    ],
    "management_level": [
        {"value": "manager", "synonyms": ["manager", "매니저", "관리자"]},
        {"value": "team_lead", "synonyms": ["팀리드", "파트장", "리더"]},
        {"value": "executive", "synonyms": ["임원"]},
        {"value": "individual_contributor", "synonyms": ["실무자", "일반 직원", "비관리자"]},
    ],
    "__boolean__": [
        {"value": "true", "synonyms": ["예", "해당", "true", "Y"]},
        {"value": "false", "synonyms": ["아니오", "미해당", "false", "N"]},
    ],
}


def _match_hints(name):
    low = (name or "").lower()
    for keys, label, desc, syn, conf in FIELD_HINTS:
        for k in keys:
            if k in low:
                return label, desc, syn, conf, "필드명에 '%s' 패턴 포함" % k
    return None


def infer_field(table_name, column):
    """column: {name, type, is_pk, is_fk}"""
    name = column.get("name", "")
    low = name.lower()
    evidence = []
    m = _match_hints(name)
    if m:
        label, desc, syn, conf, ev = m
        evidence.append(ev)
    else:
        label = name.replace("_", " ")
        desc = "%s 테이블의 %s 필드" % (table_name, name)
        syn = ""
        conf = 0.4
        evidence.append("사전 정의 패턴 없음 - 필드명 기반 기본 제안")

    if column.get("is_pk"):
        conf = min(0.98, conf + 0.05)
        evidence.append("Primary Key")
    if column.get("is_fk"):
        conf = min(0.98, conf + 0.03)
        evidence.append("Foreign Key - 다른 테이블 참조")
    ctype = (column.get("type") or "").upper()
    if ctype:
        evidence.append("데이터 타입 %s" % ctype)

    value_map = []
    for key, vm in DEFAULT_VALUE_MAPS.items():
        # 정확 일치만 적용: 'marital_status' 가 'status' 값 매핑을 물려받는 오염을 막는다.
        if key != "__boolean__" and key == low:
            value_map = vm
            evidence.append("기본 코드성 필드 값 매핑 후보 적용")
            break
    if not value_map and (low.startswith("is_") or low.startswith("has_")
                          or low.endswith("_flag") or low in ("enabled", "approved")):
        value_map = DEFAULT_VALUE_MAPS["__boolean__"]
        evidence.append("boolean 성격 필드 - 기본 boolean 값 매핑 적용")

    return {
        "target_type": "field",
        "table_name": table_name,
        "field_name": name,
        "label": label,
        "description": desc,
        "synonyms": syn,
        "value_map": value_map,
        "use_in_sql": True,
        "confidence": round(conf, 2),
        "evidence": evidence,
    }


def infer_table(table):
    qname = table.get("qualified_name") or table.get("name", "")
    low = qname.lower()
    evidence = ["테이블명 '%s'" % qname]
    label, desc, conf = None, None, 0.5
    for keys, tlabel, tdesc in TABLE_HINTS:
        for k in keys:
            if k in low:
                label, desc, conf = tlabel, tdesc, 0.9
                evidence.append("테이블명에 '%s' 패턴 포함" % k)
                break
        if label:
            break
    if not label:
        label = table.get("name", qname)
        desc = table.get("comment") or ("%s 테이블" % qname)
    if table.get("comment"):
        evidence.append("테이블 comment: %s" % table["comment"])
        conf = min(0.95, conf + 0.05)
    return {
        "target_type": "table",
        "table_name": qname,
        "field_name": "",
        "label": label,
        "description": desc,
        "synonyms": "",
        "value_map": [],
        "use_in_sql": True,
        "confidence": round(conf, 2),
        "evidence": evidence,
    }


def infer_for_tables(tables, only_tables=None, only_fields=None):
    """의미 자동 생성: 테이블/필드 제안 목록.

    only_tables: 대상 테이블 qualified name 리스트 (None 이면 전체)
    only_fields: 대상 필드명 리스트 (None 이면 전체)
    """
    if isinstance(only_tables, str):
        only_tables = [only_tables]
    suggestions = []
    for t in tables:
        qname = t["qualified_name"]
        if only_tables and qname not in only_tables:
            continue
        suggestions.append(infer_table(t))
        for col in t["columns"]:
            if only_fields and col["name"] not in only_fields:
                continue
            suggestions.append(infer_field(qname, col))
    return suggestions
