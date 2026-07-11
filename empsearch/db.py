"""Embedded database layer for OAFC.

PostgreSQL/MySQL 이 없는 로컬 환경에서도 전체 솔루션이 동작하도록
표준 라이브러리 sqlite3 로 임베디드 DB 를 구성한다.

논리 데이터 소스 (2026-07-09 스펙):
  - public                 : PostgreSQL 직원 관리 DB (15개 테이블)
  - ganada                 : 가나다 표준조직 schema (org_structure)
  - employee_salary_db     : MySQL 급여 DB (salary_payments)
  - employee_evaluation_db : MySQL 평가 DB (evaluation_scores)

Schema Graph 기준: 테이블 18개 / 컬럼 227개 / 관계 25개.
테이블 이름은 "<schema>__<table>" 로 저장하고 API 레벨에서 schema 를 분리해 노출한다.
"""

import datetime
import json
import os
import random
import sqlite3
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "empsearch.db")

_lock = threading.Lock()
_local = threading.local()
_initialized = False

SEED_EMPLOYEES = int(os.environ.get("OAFC_SEED_EMPLOYEES", "10000"))

# ---------------------------------------------------------------------------
# 논리 스키마 카탈로그: 테이블 / 컬럼 / PK / FK 정의 (총 18테이블 227컬럼 25관계)
# ---------------------------------------------------------------------------

CATALOG = {
    "public.employees": {
        "comment": "임직원 마스터 (STEEL-xxxxx 사번)",
        "columns": [
            ("employee_no", "TEXT"), ("korean_name", "TEXT"), ("english_name", "TEXT"),
            ("gender", "TEXT"), ("birth_date", "TEXT"), ("nationality", "TEXT"),
            ("hire_date", "TEXT"), ("resignation_date", "TEXT"), ("employment_type", "TEXT"),
            ("status", "TEXT"), ("current_department_code", "TEXT"), ("job_position_code", "TEXT"),
            ("work_location_code", "TEXT"), ("job_family", "TEXT"), ("marital_status", "TEXT"),
            ("military_service", "TEXT"), ("blood_type", "TEXT"), ("disability_flag", "INTEGER"),
            ("veteran_flag", "INTEGER"), ("bank_alias", "TEXT"), ("email", "TEXT"),
            ("phone", "TEXT"), ("address", "TEXT"), ("created_at", "TEXT"),
        ],
        "pk": ["employee_no"],
        "fks": [
            ("current_department_code", "public.departments", "department_code"),
            ("job_position_code", "public.job_positions", "position_code"),
            ("work_location_code", "public.work_locations", "location_code"),
        ],
    },
    "public.employee_information": {
        "comment": "임직원 기본 정보 (현재 부서/근무지 포함, 자연어 검색 기본 대상)",
        "columns": [
            ("employee_id", "TEXT"), ("employee_no", "TEXT"), ("name", "TEXT"),
            ("gender", "TEXT"), ("birth_date", "TEXT"), ("age", "INTEGER"),
            ("hire_date", "TEXT"), ("resignation_date", "TEXT"), ("years_of_service", "INTEGER"),
            ("status", "TEXT"), ("department_code", "TEXT"), ("department_name", "TEXT"),
            ("job_title", "TEXT"), ("management_level", "TEXT"), ("work_location", "TEXT"),
            ("salary_grade", "TEXT"), ("education_level", "TEXT"), ("email", "TEXT"),
            ("phone", "TEXT"), ("address", "TEXT"), ("postal_code", "TEXT"),
            ("last_promotion_date", "TEXT"), ("emergency_contact", "TEXT"),
            ("updated_at", "TEXT"),
        ],
        "pk": ["employee_id"],
        "fks": [
            ("employee_no", "public.employees", "employee_no"),
            ("department_code", "public.department_management_information", "department_code"),
        ],
    },
    "public.departments": {
        "comment": "부서 마스터",
        "columns": [
            ("department_code", "TEXT"), ("department_name", "TEXT"), ("department_name_en", "TEXT"),
            ("parent_department_code", "TEXT"), ("location_code", "TEXT"), ("department_level", "INTEGER"),
            ("cost_center", "TEXT"), ("established_date", "TEXT"), ("closed_date", "TEXT"),
            ("sort_order", "INTEGER"), ("is_active", "INTEGER"),
        ],
        "pk": ["department_code"],
        "fks": [
            ("parent_department_code", "public.departments", "department_code"),
            ("location_code", "public.work_locations", "location_code"),
        ],
    },
    "public.department_management_information": {
        "comment": "부서 관리 정보 (표준 부서)",
        "columns": [
            ("department_code", "TEXT"), ("department_name", "TEXT"), ("department_alias", "TEXT"),
            ("standard_department_code", "TEXT"), ("parent_department_code", "TEXT"),
            ("department_head_no", "TEXT"), ("org_unit_type", "TEXT"), ("location", "TEXT"),
            ("business_area", "TEXT"), ("headcount_budget", "INTEGER"), ("established_date", "TEXT"),
            ("closed_date", "TEXT"), ("is_active", "INTEGER"),
        ],
        "pk": ["department_code"],
        "fks": [
            ("parent_department_code", "public.department_management_information", "department_code"),
            ("department_head_no", "public.employees", "employee_no"),
            ("standard_department_code", "ganada.org_structure", "표준부서코드"),
        ],
    },
    "public.employee_assignments": {
        "comment": "임직원 배치 이력",
        "columns": [
            ("assignment_id", "INTEGER"), ("employee_no", "TEXT"), ("department_code", "TEXT"),
            ("job_position_code", "TEXT"), ("assignment_type", "TEXT"), ("assignment_reason", "TEXT"),
            ("start_date", "TEXT"), ("end_date", "TEXT"), ("is_current", "INTEGER"),
            ("approved_by", "TEXT"), ("note", "TEXT"),
        ],
        "pk": ["assignment_id"],
        "fks": [
            ("employee_no", "public.employees", "employee_no"),
            ("department_code", "public.departments", "department_code"),
            ("job_position_code", "public.job_positions", "position_code"),
        ],
    },
    "public.employee_department_change_history": {
        "comment": "임직원 부서 변경 히스토리 (부서이름 / 변경이전 부서이름)",
        "columns": [
            ("change_id", "INTEGER"), ("employee_id", "TEXT"), ("changed_at", "TEXT"),
            ("department_name", "TEXT"), ("previous_department_name", "TEXT"),
            ("change_reason", "TEXT"), ("approved_by", "TEXT"), ("approved_at", "TEXT"),
        ],
        "pk": ["change_id"],
        "fks": [
            ("employee_id", "public.employee_information", "employee_id"),
            ("approved_by", "public.employees", "employee_no"),
        ],
    },
    "public.employee_change_history": {
        "comment": "임직원 변경 이력 (부서/직급/상태/근무지 등)",
        "columns": [
            ("history_id", "INTEGER"), ("employee_id", "TEXT"), ("changed_at", "TEXT"),
            ("change_type", "TEXT"), ("before_value", "TEXT"), ("after_value", "TEXT"),
            ("changed_by", "TEXT"), ("change_source", "TEXT"),
        ],
        "pk": ["history_id"],
        "fks": [("employee_id", "public.employee_information", "employee_id")],
    },
    "public.employee_work_location_history": {
        "comment": "임직원 근무지 변경 이력",
        "columns": [
            ("id", "INTEGER"), ("employee_no", "TEXT"), ("work_location_code", "TEXT"),
            ("work_location_name", "TEXT"), ("start_date", "TEXT"), ("end_date", "TEXT"),
            ("change_reason", "TEXT"), ("approved_by", "TEXT"),
        ],
        "pk": ["id"],
        "fks": [
            ("employee_no", "public.employees", "employee_no"),
            ("work_location_code", "public.work_locations", "location_code"),
        ],
    },
    "public.work_locations": {
        "comment": "근무지/사업장 마스터",
        "columns": [
            ("location_code", "TEXT"), ("location_name", "TEXT"), ("city", "TEXT"),
            ("region", "TEXT"), ("address", "TEXT"), ("business_area", "TEXT"),
            ("site_type", "TEXT"), ("postal_code", "TEXT"), ("timezone", "TEXT"),
            ("is_active", "INTEGER"),
        ],
        "pk": ["location_code"],
        "fks": [],
    },
    "public.job_positions": {
        "comment": "직위/직급 마스터",
        "columns": [
            ("position_code", "TEXT"), ("position_name", "TEXT"), ("position_level", "INTEGER"),
            ("is_management", "INTEGER"), ("job_family", "TEXT"), ("grade_band", "TEXT"),
            ("min_years", "INTEGER"), ("max_years", "INTEGER"), ("description", "TEXT"),
        ],
        "pk": ["position_code"],
        "fks": [],
    },
    "public.ontology_concepts": {
        "comment": "Ontology 개념 (자연어 SQL 생성용)",
        "columns": [
            ("concept_id", "INTEGER"), ("concept_name", "TEXT"), ("concept_type", "TEXT"),
            ("description", "TEXT"), ("domain", "TEXT"), ("synonyms", "TEXT"),
            ("updated_by", "TEXT"), ("created_at", "TEXT"),
        ],
        "pk": ["concept_id"],
        "fks": [],
    },
    "public.ontology_concept_columns": {
        "comment": "Ontology 개념 - 컬럼 매핑",
        "columns": [
            ("id", "INTEGER"), ("concept_id", "INTEGER"), ("table_name", "TEXT"),
            ("column_name", "TEXT"), ("role", "TEXT"), ("confidence", "REAL"),
            ("created_at", "TEXT"),
        ],
        "pk": ["id"],
        "fks": [("concept_id", "public.ontology_concepts", "concept_id")],
    },
    "public.ontology_relationships": {
        "comment": "Ontology 개념 간 의미 관계",
        "columns": [
            ("relationship_id", "INTEGER"), ("from_concept", "INTEGER"), ("to_concept", "INTEGER"),
            ("relation_type", "TEXT"), ("confidence", "REAL"), ("approved", "INTEGER"),
            ("approved_by", "TEXT"), ("evidence", "TEXT"), ("created_at", "TEXT"),
        ],
        "pk": ["relationship_id"],
        "fks": [
            ("from_concept", "public.ontology_concepts", "concept_id"),
            ("to_concept", "public.ontology_concepts", "concept_id"),
        ],
    },
    "public.ontology_query_patterns": {
        "comment": "자연어 질의 패턴 (Query Planner)",
        "columns": [
            ("pattern_id", "INTEGER"), ("concept_id", "INTEGER"), ("pattern_text", "TEXT"),
            ("intent", "TEXT"), ("sql_template", "TEXT"), ("priority", "INTEGER"),
            ("enabled", "INTEGER"), ("updated_at", "TEXT"),
        ],
        "pk": ["pattern_id"],
        "fks": [("concept_id", "public.ontology_concepts", "concept_id")],
    },
    "public.ontology_definitions": {
        "comment": "Ontology 정의 (의미/동의어/값 매핑)",
        "columns": [
            ("id", "INTEGER"), ("project", "TEXT"), ("target_type", "TEXT"),
            ("table_name", "TEXT"), ("field_name", "TEXT"), ("label", "TEXT"),
            ("description", "TEXT"), ("synonyms", "TEXT"), ("value_map", "TEXT"),
            ("use_in_sql", "INTEGER"), ("review_note", "TEXT"), ("updated_at", "TEXT"),
        ],
        "pk": ["id"],
        "fks": [],
    },
    "ganada.org_structure": {
        "comment": "가나다 기업 표준조직 테이블",
        "columns": [
            ("표준부서코드", "TEXT"), ("표준부서_2026", "TEXT"), ("운영종료제외_표준부서명", "TEXT"),
            ("년도구분", "TEXT"), ("부서명", "TEXT"), ("고유코드_년도부서명", "TEXT"),
            ("본부단위건제", "TEXT"), ("본부단위", "TEXT"), ("실담당단위건제", "TEXT"),
            ("실담당단위", "TEXT"), ("그룹단위건제", "TEXT"), ("그룹단위", "TEXT"),
            ("공장섹션단위건제", "TEXT"), ("공장섹션단위", "TEXT"), ("가공센터단위건제", "TEXT"),
            ("가공센터단위", "TEXT"), ("조직단위", "TEXT"), ("조직직무분류", "TEXT"),
            ("조직직무세부분류", "TEXT"),
        ],
        "pk": ["표준부서코드"],
        "fks": [],
    },
    "employee_salary_db.salary_payments": {
        "comment": "임직원 월급/보상 지급 데이터 10년치 (MySQL employee_salary_db)",
        "columns": [
            ("salary_id", "INTEGER"), ("employee_no", "TEXT"), ("pay_month", "TEXT"),
            ("base_salary", "INTEGER"), ("position_allowance", "INTEGER"), ("meal_allowance", "INTEGER"),
            ("transport_allowance", "INTEGER"), ("overtime_pay", "INTEGER"), ("night_shift_pay", "INTEGER"),
            ("holiday_pay", "INTEGER"), ("bonus", "INTEGER"), ("incentive", "INTEGER"),
            ("tax_deduction", "INTEGER"), ("insurance_deduction", "INTEGER"), ("pension_deduction", "INTEGER"),
            ("welfare_deduction", "INTEGER"), ("union_fee", "INTEGER"), ("net_pay", "INTEGER"),
            ("pay_group", "TEXT"), ("payment_date", "TEXT"), ("currency", "TEXT"),
        ],
        "pk": ["salary_id"],
        "fks": [("employee_no", "public.employees", "employee_no")],
    },
    "employee_evaluation_db.evaluation_scores": {
        "comment": "임직원 평가 주기/결과/점수 (MySQL employee_evaluation_db)",
        "columns": [
            ("evaluation_id", "INTEGER"), ("employee_no", "TEXT"), ("evaluation_year", "INTEGER"),
            ("evaluation_cycle", "TEXT"), ("goal_score", "REAL"), ("competency_score", "REAL"),
            ("leadership_score", "REAL"), ("attitude_score", "REAL"), ("attendance_score", "REAL"),
            ("total_score", "REAL"), ("grade", "TEXT"), ("dept_rank", "INTEGER"),
            ("evaluator_no", "TEXT"), ("evaluator_comment", "TEXT"), ("promotion_recommended", "INTEGER"),
            ("is_final", "INTEGER"), ("finalized_at", "TEXT"),
        ],
        "pk": ["evaluation_id"],
        "fks": [
            ("employee_no", "public.employees", "employee_no"),
            ("evaluator_no", "public.employees", "employee_no"),
        ],
    },
}

# 하위 호환: 07-08 버전 코드가 참조하던 TABLE_META 형태 유지
TABLE_META = dict(
    (name, {
        "comment": t["comment"],
        "pk": t["pk"],
        "fks": [{"column": c, "ref_table": rt, "ref_column": rc} for c, rt, rc in t["fks"]],
    })
    for name, t in CATALOG.items()
)


def physical_name(qualified):
    """'public.employee_information' -> 'public__employee_information'"""
    return qualified.replace(".", "__")


def logical_name(physical):
    return physical.replace("__", ".", 1)


# ---------------------------------------------------------------------------
# connection
# ---------------------------------------------------------------------------

def get_conn():
    """스레드별 sqlite3 커넥션.

    sqlite3 커넥션을 여러 스레드가 공유하면 segfault 가 발생할 수 있어
    (ThreadingHTTPServer 동시 요청) 커넥션을 threading.local 로 분리한다.
    스키마 생성/시드는 전역 락으로 1회만 수행한다.
    """
    global _initialized
    if not _initialized:
        with _lock:
            if not _initialized:
                os.makedirs(DATA_DIR, exist_ok=True)
                init = sqlite3.connect(DB_PATH)
                try:
                    # WAL: ThreadingHTTPServer 동시 요청에서 쓰기 중 읽기가
                    # 서로 막지 않게 한다 (DB 파일 속성이라 1회 설정으로 영속).
                    init.execute("PRAGMA journal_mode=WAL")
                    _create_tables(init)
                    if _count(init, "public__employee_information") == 0:
                        seed(init)
                finally:
                    init.close()
                _initialized = True
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")  # lock 대기 상한(ms)
        _local.conn = conn
    return conn


def _count(conn, table):
    try:
        return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def query(sql, params=()):
    conn = get_conn()
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = [list(r) for r in cur.fetchall()]
    return cols, rows


def execute(sql, params=()):
    conn = get_conn()
    with _lock:  # 쓰기 직렬화
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

def _create_tables(conn):
    for qualified, meta in CATALOG.items():
        cols = ", ".join('"%s" %s' % (c, t) for c, t in meta["columns"])
        conn.execute('CREATE TABLE IF NOT EXISTS %s (%s)' % (physical_name(qualified), cols))
    # 앱 내부 Ontology 저장 (public.ontology_definitions 를 실제 저장소로 사용)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ontology_defs
        ON public__ontology_definitions(project, target_type, table_name, field_name)
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# seed data (가나다 철강회사 10,000명 기준)
# ---------------------------------------------------------------------------

_SURNAMES = "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 전 홍".split()
_GIVEN1 = "민 서 지 도 하 주 시 예 수 은 태 준 현 승 유 재 진 성 동 영".split()
_GIVEN2 = "준 윤 우 원 호 연 아 은 빈 서 영 현 석 훈 희 진 규 림 솔 결".split()
_ENG = "Kim Lee Park Choi Jung Kang Cho Yoon Jang Lim Han Oh Seo Shin Kwon Hwang Ahn Song Jeon Hong".split()

# 근무지 4곳 (스펙: 서울 본사 / 포항 제철소 / 광양 제철소 / 송도 R&D 캠퍼스)
_LOCATIONS = [
    ("L100", "서울 본사", "서울", "본사", 0.445),
    ("L200", "포항 제철소", "포항", "생산", 0.267),
    ("L300", "광양 제철소", "광양", "생산", 0.238),
    ("L400", "송도 R&D 캠퍼스", "인천", "연구", 0.050),
]

# 부서 19개 (스펙 예시 부서명 포함)
_DEPARTMENTS = [
    ("D100", "경영기획본부", None, "L100", "경영지원"),
    ("D110", "인사문화실", "D100", "L100", "경영지원"),
    ("D120", "재무관리실", "D100", "L100", "경영지원"),
    ("D130", "전략기획팀", "D100", "L100", "경영지원"),
    ("D200", "포항생산본부", None, "L200", "생산"),
    ("D210", "포항제선공장", "D200", "L200", "생산"),
    ("D220", "포항제강공장", "D200", "L200", "생산"),
    ("D230", "포항압연공장", "D200", "L200", "생산"),
    ("D240", "포항설비정비섹션", "D200", "L200", "생산"),
    ("D300", "광양생산본부", None, "L300", "생산"),
    ("D310", "광양압연공장", "D300", "L300", "생산"),
    ("D320", "광양품질섹션", "D300", "L300", "품질"),
    ("D330", "광양물류섹션", "D300", "L300", "물류"),
    ("D400", "영업본부", None, "L100", "영업"),
    ("D410", "국내영업팀", "D400", "L100", "영업"),
    ("D420", "해외영업팀", "D400", "L100", "영업"),
    ("D500", "기술연구소", None, "L400", "R&D"),
    ("D510", "신소재연구팀", "D500", "L400", "R&D"),
    ("D520", "데이터플랫폼팀", "D500", "L400", "IT"),
]

_JOB_POSITIONS = [
    ("P1", "사원", 1, 0, "일반", "G1", 0),
    ("P2", "대리", 2, 0, "일반", "G2", 2),
    ("P3", "과장", 3, 0, "일반", "G3", 6),
    ("P4", "차장", 4, 1, "일반", "G4", 10),
    ("P5", "부장", 5, 1, "일반", "G5", 15),
    ("P6", "임원", 6, 1, "경영", "EX", 20),
]

_ORG_ROWS = [
    ("STD001", "경영기획본부", "경영기획본부", "2026", "경영기획본부", "2026-경영기획본부",
     "본부", "경영기획본부", "", "", "", "", "", "", "", "", "경영기획본부", "경영지원", "기획"),
    ("STD002", "인사문화실", "인사문화실", "2026", "인사문화실", "2026-인사문화실",
     "본부", "경영기획본부", "실", "인사문화실", "", "", "", "", "", "", "인사문화실", "경영지원", "인사"),
    ("STD003", "재무관리실", "재무관리실", "2026", "재무관리실", "2026-재무관리실",
     "본부", "경영기획본부", "실", "재무관리실", "", "", "", "", "", "", "재무관리실", "경영지원", "재무"),
    ("STD004", "포항생산본부", "포항생산본부", "2026", "포항생산본부", "2026-포항생산본부",
     "본부", "포항생산본부", "", "", "", "", "", "", "", "", "포항생산본부", "생산", "생산총괄"),
    ("STD005", "포항제선공장", "포항제선공장", "2026", "포항제선공장", "2026-포항제선공장",
     "본부", "포항생산본부", "실", "제선담당", "그룹", "제선그룹", "공장", "포항제선공장", "", "", "포항제선공장", "생산", "제선"),
    ("STD006", "포항압연공장", "포항압연공장", "2026", "포항압연공장", "2026-포항압연공장",
     "본부", "포항생산본부", "실", "압연담당", "그룹", "압연그룹", "공장", "포항압연공장", "센터", "열연가공센터", "포항압연공장", "생산", "압연"),
    ("STD007", "포항설비정비섹션", "포항설비정비섹션", "2026", "포항설비정비섹션", "2026-포항설비정비섹션",
     "본부", "포항생산본부", "실", "설비담당", "그룹", "정비그룹", "공장섹션", "설비정비섹션", "", "", "포항설비정비섹션", "생산", "설비정비"),
    ("STD008", "광양생산본부", "광양생산본부", "2026", "광양생산본부", "2026-광양생산본부",
     "본부", "광양생산본부", "", "", "", "", "", "", "", "", "광양생산본부", "생산", "생산총괄"),
    ("STD009", "광양압연공장", "광양압연공장", "2026", "광양압연공장", "2026-광양압연공장",
     "본부", "광양생산본부", "실", "압연담당", "그룹", "압연그룹", "공장", "광양압연공장", "센터", "냉연가공센터", "광양압연공장", "생산", "압연"),
    ("STD010", "광양품질섹션", "광양품질섹션", "2026", "광양품질섹션", "2026-광양품질섹션",
     "본부", "광양생산본부", "실", "품질담당", "그룹", "품질그룹", "공장섹션", "품질섹션", "", "", "광양품질섹션", "품질", "품질관리"),
    ("STD011", "영업본부", "영업본부", "2026", "영업본부", "2026-영업본부",
     "본부", "영업본부", "", "", "", "", "", "", "", "", "영업본부", "영업", "영업총괄"),
    ("STD012", "기술연구소", "기술연구소", "2026", "기술연구소", "2026-기술연구소",
     "본부", "기술연구소", "", "", "", "", "", "", "", "", "기술연구소", "R&D", "연구총괄"),
]


def seed(conn):
    rng = random.Random(20260709)
    today = datetime.date(2026, 7, 9)
    now = today.isoformat()

    for qualified in CATALOG:
        conn.execute("DELETE FROM %s" % physical_name(qualified))

    # 근무지
    conn.executemany(
        "INSERT INTO public__work_locations VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(c, n, city, {"서울": "수도권", "인천": "수도권", "포항": "영남권", "광양": "호남권"}[city],
          "%s 산업단지 %d" % (city, i + 1), area,
          "본사" if area == "본사" else "사업장", "0%d123" % (i + 1), "Asia/Seoul", 1)
         for i, (c, n, city, area, _) in enumerate(_LOCATIONS)])

    # 직위
    conn.executemany(
        "INSERT INTO public__job_positions VALUES (?,?,?,?,?,?,?,?,?)",
        [(c, n, lv, mg, fam, gb, my, my + 8, "%s 직급" % n)
         for c, n, lv, mg, fam, gb, my in _JOB_POSITIONS])

    # 부서 (departments + department_management_information)
    for i, (code, name, parent, loc, area) in enumerate(_DEPARTMENTS):
        est = "%d-01-01" % rng.randint(1968, 2015)
        conn.execute(
            "INSERT INTO public__departments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (code, name, "Dept-" + code, parent, loc, 1 if parent is None else 2,
             "CC-" + code, est, None, i, 1))
        std = "STD%03d" % min(12, i + 1)
        loc_name = dict((c, n) for c, n, _, _, _ in _LOCATIONS)[loc]
        conn.execute(
            "INSERT INTO public__department_management_information VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (code, name, name.replace("본부", "").replace("공장", ""), std, parent,
             None, "본부" if parent is None else "팀/공장", loc_name, area,
             rng.randint(30, 900), est, None, 1))

    # 표준조직
    conn.executemany(
        "INSERT INTO ganada__org_structure VALUES (%s)" % ",".join(["?"] * 19), _ORG_ROWS)

    # 임직원
    n_emp = SEED_EMPLOYEES
    loc_codes, loc_weights = zip(*[(l[0], l[4]) for l in _LOCATIONS])
    depts_by_loc = {}
    for code, name, parent, loc, area in _DEPARTMENTS:
        depts_by_loc.setdefault(loc, []).append((code, name))
    dept_name_by_code = dict((c, n) for c, n, _, _, _ in _DEPARTMENTS)
    loc_name_by_code = dict((c, n) for c, n, _, _, _ in _LOCATIONS)

    employees, infos = [], []
    assignments, dept_changes, emp_changes, loc_changes = [], [], [], []
    evals, salaries = [], []
    assignment_id = 0

    for i in range(1, n_emp + 1):
        emp_no = "STEEL-%05d" % i
        emp_id = "E%05d" % i
        name = rng.choice(_SURNAMES) + rng.choice(_GIVEN1) + rng.choice(_GIVEN2)
        eng = rng.choice(_ENG) + " " + rng.choice(["Min", "Seo", "Ji", "Ha", "Joon", "Yeon"])
        gender = rng.choice(["male", "female"])
        birth_year = rng.randint(1963, 2003)
        birth = "%d-%02d-%02d" % (birth_year, rng.randint(1, 12), rng.randint(1, 28))
        hire_year = max(birth_year + 19, rng.randint(1985, 2026))
        hire = "%d-%02d-%02d" % (min(hire_year, 2026), rng.randint(1, 12), rng.randint(1, 28))
        years = max(0, today.year - hire_year)
        loc = rng.choices(loc_codes, weights=loc_weights)[0]
        dcode, dname = rng.choice(depts_by_loc[loc])
        r = rng.random()
        if r < 0.9656:
            status, resigned = "active", None
        elif r < 0.9899:
            status, resigned = "on_leave", None
        else:
            status = "resigned"
            rs_year = min(2026, hire_year + rng.randint(1, 25))
            resigned = "%d-%02d-%02d" % (rs_year, rng.randint(1, 12), rng.randint(1, 28))
        r = rng.random()
        if r < 0.05:
            level, pos = "executive", "P6"
        elif r < 0.16:
            level, pos = "manager", rng.choice(["P4", "P5"])
        elif r < 0.31:
            level, pos = "team_lead", rng.choice(["P3", "P4"])
        else:
            level, pos = "individual_contributor", rng.choice(["P1", "P2", "P3"])
        title = dict((c, n) for c, n, _, _, _, _, _ in _JOB_POSITIONS)[pos]
        email = "%s@ganada-steel.co.kr" % emp_no.lower().replace("-", "")

        employees.append((
            emp_no, name, eng, gender, birth, "KR", hire, resigned,
            rng.choice(["정규직", "정규직", "정규직", "계약직"]), status, dcode, pos, loc,
            rng.choice(["생산", "일반", "연구", "영업", "IT"]),
            rng.choice(["기혼", "미혼"]),
            rng.choice(["군필", "미필", "해당없음"]) if gender == "male" else "해당없음",
            rng.choice(["A", "B", "O", "AB"]), 0, 0, "bank-" + emp_id,
            email, "010-%04d-%04d" % (rng.randint(0, 9999), rng.randint(0, 9999)),
            "%s 시내" % loc_name_by_code[loc].split()[0], now))
        infos.append((
            emp_id, emp_no, name, gender, birth, today.year - birth_year, hire, resigned,
            years, status, dcode, dname, title, level, loc_name_by_code[loc],
            rng.choice(["SG1", "SG2", "SG3", "SG4"]),
            rng.choice(["고졸", "학사", "석사", "박사"]), email,
            "010-%04d-%04d" % (rng.randint(0, 9999), rng.randint(0, 9999)),
            "%s 시내" % loc_name_by_code[loc].split()[0],
            "%05d" % rng.randint(10000, 99999),
            "%d-01-01" % rng.randint(max(hire_year, 2015), 2026),
            "010-%04d-%04d" % (rng.randint(0, 9999), rng.randint(0, 9999)), now))

        # 배치/변경 이력: 평균 ~9건/인 (스펙: 변경 이력 약 92,000 row)
        prev_dept = dname
        year = hire_year
        assignment_id += 1
        assignments.append((assignment_id, emp_no, dcode, pos, "입사배치", "신규 입사",
                            hire, None, 1, None, None))
        n_changes = rng.randint(2, 6)
        for _ in range(n_changes):
            year += rng.randint(1, 4)
            if year >= today.year:
                break
            nd_code, nd_name = rng.choice(_DEPARTMENTS)[:2]
            if nd_name == prev_dept:
                continue
            at = "%d-%02d-01" % (year, rng.randint(1, 12))
            approver = "STEEL-%05d" % rng.randint(1, max(1, i - 1)) if i > 1 else None
            dept_changes.append((emp_id, at, nd_name, prev_dept,
                                 rng.choice(["정기 인사이동", "조직 개편", "본인 요청 전보", "승진 배치"]),
                                 approver, at))
            emp_changes.append((emp_id, at, "department", prev_dept, nd_name, approver, "HR 시스템"))
            prev_dept = nd_name
        # 상태/직급 등 기타 변경 이력 추가 (총 ~9건/인)
        for _ in range(rng.randint(5, 9)):
            y = rng.randint(hire_year, today.year - 1) if hire_year < today.year else today.year
            at = "%d-%02d-01" % (y, rng.randint(1, 12))
            ct = rng.choice(["job_title", "status", "work_location", "salary_grade"])
            emp_changes.append((emp_id, at, ct, "이전값", "변경값", None, "HR 시스템"))
        # 근무지 이력
        loc_changes.append((emp_no, loc, loc_name_by_code[loc], hire, None, "입사 배치", None))

        # 평가 (최근 5년, 상/하반기 중 연 1회 축약)
        for ey in range(2021, 2026):
            if ey < hire_year:
                continue
            grade = rng.choice(["S", "A", "A", "B", "B", "B", "C"])
            base = {"S": 95, "A": 88, "B": 78, "C": 62}[grade]
            gs = base + rng.uniform(-3, 3)
            evals.append((emp_no, ey, rng.choice(["연간", "하반기"]), round(gs, 1),
                          round(gs + rng.uniform(-5, 5), 1), round(gs + rng.uniform(-8, 4), 1),
                          round(gs + rng.uniform(-4, 4), 1), round(gs + rng.uniform(-2, 2), 1),
                          round(gs, 1), grade,
                          rng.randint(1, 40), "STEEL-%05d" % rng.randint(1, n_emp),
                          "", 1 if grade == "S" else 0, 1, "%d-12-20" % ey))

        # 월급 (10년치, 분기 대표월로 축약 저장)
        base_pay = rng.randint(280, 950) * 10000
        for y in range(2017, 2027):
            if y < hire_year:
                continue
            for m in (3, 6, 9, 12):
                if y == 2026 and m > 6:
                    break
                pay = int(base_pay * (1 + 0.03 * (y - hire_year)))
                bonus = int(pay * rng.uniform(0.3, 0.8)) if m == 12 else 0
                overtime = rng.randint(0, 30) * 10000
                tax = int(pay * 0.08)
                ins = int(pay * 0.045)
                net = pay + bonus + overtime - tax - ins
                salaries.append((emp_no, "%d-%02d" % (y, m), pay, 100000, 130000, 100000,
                                 overtime, 0, 0, bonus, 0, tax, ins, int(pay * 0.04),
                                 10000, 15000, net, "정규", "%d-%02d-25" % (y, m), "KRW"))

    conn.executemany("INSERT INTO public__employees VALUES (%s)" % ",".join(["?"] * 24), employees)
    conn.executemany("INSERT INTO public__employee_information VALUES (%s)" % ",".join(["?"] * 24), infos)
    conn.executemany("INSERT INTO public__employee_assignments VALUES (%s)" % ",".join(["?"] * 11), assignments)
    conn.executemany(
        "INSERT INTO public__employee_department_change_history "
        "(employee_id, changed_at, department_name, previous_department_name, change_reason, approved_by, approved_at) "
        "VALUES (?,?,?,?,?,?,?)", dept_changes)
    conn.executemany(
        "INSERT INTO public__employee_change_history "
        "(employee_id, changed_at, change_type, before_value, after_value, changed_by, change_source) "
        "VALUES (?,?,?,?,?,?,?)", emp_changes)
    conn.executemany(
        "INSERT INTO public__employee_work_location_history "
        "(employee_no, work_location_code, work_location_name, start_date, end_date, change_reason, approved_by) "
        "VALUES (?,?,?,?,?,?,?)", loc_changes)
    conn.executemany(
        "INSERT INTO employee_evaluation_db__evaluation_scores "
        "(employee_no, evaluation_year, evaluation_cycle, goal_score, competency_score, leadership_score, "
        " attitude_score, attendance_score, total_score, grade, dept_rank, evaluator_no, evaluator_comment, "
        " promotion_recommended, is_final, finalized_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", evals)
    conn.executemany(
        "INSERT INTO employee_salary_db__salary_payments "
        "(employee_no, pay_month, base_salary, position_allowance, meal_allowance, transport_allowance, "
        " overtime_pay, night_shift_pay, holiday_pay, bonus, incentive, tax_deduction, insurance_deduction, "
        " pension_deduction, welfare_deduction, union_fee, net_pay, pay_group, payment_date, currency) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", salaries)

    # Query Planner 시드 (개념/패턴)
    concepts = [
        (1, "임직원", "entity", "회사에 소속된 직원", "HR", "직원,사원,임직원", "system", now),
        (2, "부서", "entity", "조직 단위", "HR", "부서,팀,조직", "system", now),
        (3, "근무지", "entity", "사업장 위치", "HR", "근무지,사업장,지역", "system", now),
        (4, "관리자", "role", "management_level 이 manager 인 임직원", "HR", "manager,매니저,관리자", "system", now),
        (5, "근속연수", "measure", "입사 후 경과 연수", "HR", "근속,연차,년차", "system", now),
    ]
    conn.executemany("INSERT INTO public__ontology_concepts VALUES (?,?,?,?,?,?,?,?)", concepts)
    conn.executemany(
        "INSERT INTO public__ontology_concept_columns VALUES (?,?,?,?,?,?,?)",
        [(1, 1, "public.employee_information", "employee_no", "identifier", 0.98, now),
         (2, 2, "public.employee_information", "department_name", "attribute", 0.95, now),
         (3, 3, "public.employee_information", "work_location", "attribute", 0.95, now),
         (4, 4, "public.employee_information", "management_level", "classifier", 0.95, now),
         (5, 5, "public.employee_information", "years_of_service", "measure", 0.95, now)])
    conn.executemany(
        "INSERT INTO public__ontology_relationships VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, 1, 2, "belongs_to", 0.95, 1, "system", "employee.department_code", now),
         (2, 1, 3, "works_at", 0.95, 1, "system", "employee.work_location_code", now),
         (3, 4, 1, "subtype_of", 0.9, 1, "system", "management_level=manager", now)])
    conn.executemany(
        "INSERT INTO public__ontology_query_patterns VALUES (?,?,?,?,?,?,?,?)",
        [(1, 5, "{N}년 이상 근무", "years_of_service_gte",
          "years_of_service >= {N}", 10, 1, now),
         (2, 5, "{N}년차 이상", "years_of_service_gte",
          "years_of_service >= {N}", 10, 1, now),
         (3, 4, "manager가 아닌", "level_not_manager",
          "management_level != 'manager'", 20, 1, now)])

    conn.commit()


# ---------------------------------------------------------------------------
# schema introspection (논리 스키마 노출)
# ---------------------------------------------------------------------------

def get_schema():
    conn = get_conn()
    tables = []
    for qualified, meta in CATALOG.items():
        phys = physical_name(qualified)
        schema_name, table_name = qualified.split(".", 1)
        fk_cols = set(c for c, _, _ in meta["fks"])
        cols = [{
            "name": cname,
            "type": ctype,
            "is_pk": cname in meta["pk"],
            "is_fk": cname in fk_cols,
            "comment": "",
        } for cname, ctype in meta["columns"]]
        tables.append({
            "schema": schema_name,
            "name": table_name,
            "qualified_name": qualified,
            "comment": meta["comment"],
            "columns": cols,
            "row_estimate": _count(conn, '"%s"' % phys),
        })
    relationships = [{
        "from_table": qualified, "from_column": c,
        "to_table": rt, "to_column": rc,
    } for qualified, meta in CATALOG.items() for c, rt, rc in meta["fks"]]
    return {"tables": tables, "relationships": relationships,
            "engine": "embedded-sqlite",
            "note": "PostgreSQL/MySQL 미설치 환경용 임베디드 모드"}


def get_summary():
    """/api/summary — 직원/부서/근무지 요약."""
    conn = get_conn()
    _, status_rows = query(
        "SELECT status, COUNT(*) FROM public__employee_information GROUP BY status")
    _, loc_rows = query(
        "SELECT work_location, COUNT(*) FROM public__employee_information "
        "GROUP BY work_location ORDER BY 2 DESC")
    _, dept_rows = query(
        "SELECT department_name, COUNT(*) FROM public__employee_information "
        "GROUP BY department_name ORDER BY 2 DESC LIMIT 8")
    schema = get_schema()
    total_cols = sum(len(t["columns"]) for t in schema["tables"])
    return {
        "employees": _count(conn, "public__employee_information"),
        "departments": _count(conn, "public__departments"),
        "work_locations": _count(conn, "public__work_locations"),
        "change_history_rows": _count(conn, "public__employee_change_history"),
        "tables": len(schema["tables"]),
        "columns": total_cols,
        "relationships": len(schema["relationships"]),
        "status_distribution": dict((r[0], r[1]) for r in status_rows),
        "location_distribution": dict((r[0], r[1]) for r in loc_rows),
        "top_departments": dict((r[0], r[1]) for r in dept_rows),
    }


def resolve_table(qualified):
    """schema.table 보정: 지정 schema 에 없어도 같은 인스턴스에서
    테이블명이 유일하게 발견되면 자동 보정한다. (MySQL DB 자동 보정 스펙)"""
    if qualified in CATALOG:
        return qualified, None
    tname = qualified.split(".", 1)[-1]
    hits = [q for q in CATALOG if q.split(".", 1)[1] == tname]
    if len(hits) == 1:
        return hits[0], "'%s' 를 '%s' 로 자동 보정했습니다." % (qualified, hits[0])
    raise ValueError("unknown table: %s" % qualified)


def get_table_data(qualified, limit=50):
    resolved, note = resolve_table(qualified)
    limit = max(1, min(int(limit), 500))
    cols, rows = query('SELECT * FROM "%s" LIMIT %d' % (physical_name(resolved), limit))
    out = {"table": resolved, "columns": cols, "rows": rows,
           "total": _count(get_conn(), '"%s"' % physical_name(resolved))}
    if note:
        out["corrected"] = note
    return out


def search_employees(q=None, department=None, status=None, location=None, limit=50):
    """/api/employees — 직원 검색."""
    conds, params = [], []
    if q:
        conds.append("(name LIKE ? OR employee_no LIKE ? OR employee_id LIKE ?)")
        params += ["%" + q + "%"] * 3
    if department:
        conds.append("department_name LIKE ?")
        params.append("%" + department + "%")
    if status:
        conds.append("status = ?")
        params.append(status)
    if location:
        conds.append("work_location LIKE ?")
        params.append("%" + location + "%")
    sql = ("SELECT employee_no, name, gender, status, department_name, job_title, "
           "management_level, work_location, hire_date, years_of_service "
           "FROM public__employee_information")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY employee_no LIMIT %d" % max(1, min(int(limit), 200))
    cols, rows = query(sql, params)
    return {"columns": cols, "rows": rows, "count": len(rows)}


def get_timeline(employee_no):
    """/api/timeline/{employee_no} — 직원 이력 조회."""
    cols, rows = query(
        "SELECT employee_id, employee_no, name, status, department_name, job_title, "
        "management_level, work_location, hire_date, years_of_service "
        "FROM public__employee_information WHERE employee_no = ? OR employee_id = ?",
        (employee_no, employee_no))
    if not rows:
        return {"error": "직원을 찾을 수 없습니다: %s" % employee_no}
    emp = dict(zip(cols, rows[0]))
    _, dept_rows = query(
        "SELECT changed_at, previous_department_name, department_name, change_reason "
        "FROM public__employee_department_change_history WHERE employee_id = ? "
        "ORDER BY changed_at", (emp["employee_id"],))
    _, change_rows = query(
        "SELECT changed_at, change_type, before_value, after_value "
        "FROM public__employee_change_history WHERE employee_id = ? "
        "ORDER BY changed_at", (emp["employee_id"],))
    events = [{"at": r[0], "type": "department",
               "detail": "%s → %s (%s)" % (r[1], r[2], r[3])} for r in dept_rows]
    events += [{"at": r[0], "type": r[1],
                "detail": "%s → %s" % (r[2], r[3])} for r in change_rows]
    events.sort(key=lambda e: e["at"])
    return {"employee": emp, "events": events, "event_count": len(events)}


# ---------------------------------------------------------------------------
# ontology persistence (public.ontology_definitions 사용)
# ---------------------------------------------------------------------------

_ONT = "public__ontology_definitions"


def ontology_list(project="default"):
    cols, rows = query(
        "SELECT id, target_type, table_name, field_name, label, description, synonyms, "
        "value_map, use_in_sql, review_note, updated_at "
        "FROM %s WHERE project=? ORDER BY table_name, field_name" % _ONT, (project,))
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        try:
            d["value_map"] = json.loads(d["value_map"]) if d["value_map"] else []
        except (ValueError, TypeError):
            d["value_map"] = []
        d["use_in_sql"] = bool(d["use_in_sql"])
        out.append(d)
    return out


def ontology_save(defn, project="default"):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    execute(
        "INSERT INTO %s "
        "(project, target_type, table_name, field_name, label, description, synonyms, "
        " value_map, use_in_sql, review_note, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(project, target_type, table_name, field_name) DO UPDATE SET "
        "label=excluded.label, description=excluded.description, synonyms=excluded.synonyms, "
        "value_map=excluded.value_map, use_in_sql=excluded.use_in_sql, "
        "review_note=excluded.review_note, updated_at=excluded.updated_at" % _ONT,
        (project,
         defn.get("target_type", "field"),
         defn.get("table_name") or "",
         defn.get("field_name") or "",
         defn.get("label") or "",
         defn.get("description") or "",
         _synonyms_text(defn.get("synonyms")),
         json.dumps(defn.get("value_map") or [], ensure_ascii=False),
         1 if defn.get("use_in_sql", True) else 0,
         defn.get("review_note") or "",
         now))


def _synonyms_text(value):
    """synonyms 는 배열 또는 문자열만 허용한다."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, str):
        return value.strip()
    raise ValueError("synonyms 는 배열 또는 문자열이어야 합니다.")


def ontology_delete(target_type, table_name, field_name, project="default"):
    return execute(
        "DELETE FROM %s WHERE project=? AND target_type=? AND table_name=? AND field_name=?" % _ONT,
        (project, target_type, table_name or "", field_name or ""))


def ontology_bulk_delete(scope, table_name=None, field_name=None, project="default"):
    if scope == "all":
        return execute("DELETE FROM %s WHERE project=?" % _ONT, (project,))
    if scope == "table" and table_name:
        return execute("DELETE FROM %s WHERE project=? AND table_name=?" % _ONT,
                       (project, table_name))
    if scope == "field" and table_name and field_name:
        return execute("DELETE FROM %s WHERE project=? AND table_name=? AND field_name=?" % _ONT,
                       (project, table_name, field_name))
    return 0


def ontology_import(definitions, project="default"):
    saved = 0
    for d in definitions:
        ontology_save(d, project)
        saved += 1
    return saved


def reset_generated_metadata(project="default"):
    n = execute("DELETE FROM %s WHERE project=?" % _ONT, (project,))
    return {"deleted_ontology_definitions": n}
