"""자연어 -> SQL 변환 (임직원 검색 Agent 실행 엔진).

규칙 기반 파서로 한국어 질의를 임베디드 DB SQL 로 변환한다.
Ontology 정의(동의어, 값 매핑)가 저장되어 있으면 조건 해석에 활용한다.

핵심 처리 (2026-07-09 스펙):
  - manager / team_lead / individual_contributor / executive 정확 구분
  - "manager가 아닌" 등 부정 조건 처리
  - 재직/휴직/퇴사 상태, 성별, 근무지, 부서 조건
  - 근속연수 조건 ("18년 이상 근무", "15년차 이상")
  - 조직/표준부서 검색 ("가나다 표준조직 2026 생산 조직")
  - 직원 이력 조회 ("STEEL-00001 이력을 보여줘")
  - 부서 변경 이력, 평가, 급여 다중 테이블 질의
  - "몇 명" 카운트 질의
"""

import re

from . import db

# 자연어 기본 검색은 public.employee_information 만 대상으로 한다.
# Ontology value_map 을 SQL 조건으로 붙일 때 이 테이블의 실제 컬럼만 허용해
# (1) 다른 테이블 필드(예: employees.marital_status)가 잘못 섞이는 것과
# (2) 사용자 정의 필드명이 그대로 SQL 식별자로 삽입되는 것을 함께 막는다.
_EMP_INFO_COLUMNS = frozenset(
    c for c, _ in db.CATALOG["public.employee_information"]["columns"])

STATUS_WORDS = {
    "재직": "active", "재직중": "active", "근무중": "active", "근무 중": "active",
    "휴직": "on_leave", "휴직중": "on_leave",
    "퇴사": "resigned", "퇴직": "resigned",
}

GENDER_WORDS = {
    "여성": "female", "여자": "female",
    "남성": "male", "남자": "male",
}

# 순서 중요: 긴 표현 먼저 매칭해 team_lead 가 manager 로 오인되지 않게 한다.
LEVEL_WORDS = [
    ("individual_contributor", ["individual_contributor", "실무자", "일반 직원", "일반직원", "비관리자"]),
    ("team_lead", ["team_lead", "team lead", "팀리드", "팀 리드", "파트장", "리더"]),
    ("executive", ["executive", "임원"]),
    ("manager", ["manager", "매니저", "관리자"]),
]

LOCATION_KEYWORDS = ["서울", "포항", "광양", "송도"]

NEGATION_SUFFIX = re.compile(r"(?:가|이)?\s*아닌|제외|빼고|말고|이\s*아니")

EMPLOYEE_NO_RE = re.compile(r"(STEEL-\d{3,6}|E\d{5})", re.IGNORECASE)

YEARS_RE = re.compile(r"(\d{1,2})\s*년\s*(?:차|이상)?\s*(이상|넘는|초과)?\s*(?:근무|근속|일한|재직)?")


def _load_ontology_maps(project="default"):
    """Ontology 값 매핑/동의어를 질의 해석용 사전으로 변환.

    value_map 은 배열 형식([{value, synonyms}])과 구형 dict 형식 모두 지원한다.
    """
    value_maps = {}    # field -> [(value, [words])]
    try:
        for d in db.ontology_list(project):
            if not d.get("use_in_sql", True):
                continue
            field = d.get("field_name") or ""
            vm = d.get("value_map") or []
            if not field or not vm:
                continue
            entries = value_maps.setdefault(field, [])
            if isinstance(vm, list):
                for item in vm:
                    if isinstance(item, dict) and "value" in item:
                        words = item.get("synonyms") or []
                        if isinstance(words, str):
                            words = [words]
                        entries.append((item["value"], words))
            elif isinstance(vm, dict):
                for value, words in vm.items():
                    entries.append((value, words if isinstance(words, list) else [words]))
    except Exception:
        pass
    return value_maps


def _find_negated(question, phrase_span):
    tail = question[phrase_span[1]:phrase_span[1] + 12]
    return bool(NEGATION_SUFFIX.match(tail.strip()))


def _match_level(question):
    found = []
    used_spans = []
    for level, words in LEVEL_WORDS:
        for w in words:
            for m in re.finditer(re.escape(w), question, re.IGNORECASE):
                span = m.span()
                if any(s[0] <= span[0] < s[1] for s in used_spans):
                    continue
                used_spans.append(span)
                found.append((level, _find_negated(question, span)))
    return found


def build_sql(question, project="default"):
    q = question.strip()
    value_maps = _load_ontology_maps(project)

    used_ontology = []
    conds = []
    params = []

    # --- 직원 이력 조회 (STEEL-00001 이력을 보여줘) ---
    no_m = EMPLOYEE_NO_RE.search(q)
    if no_m and any(k in q for k in ["이력", "타임라인", "히스토리", "history"]):
        emp_no = no_m.group(1).upper()
        sql = ("SELECT h.employee_id, e.name, h.changed_at, h.change_type, "
               "h.before_value, h.after_value "
               "FROM public__employee_change_history h "
               "JOIN public__employee_information e ON e.employee_id = h.employee_id "
               "WHERE e.employee_no = ? OR e.employee_id = ? "
               "ORDER BY h.changed_at LIMIT 100")
        return sql, [emp_no, emp_no], {
            "tables": ["public.employee_change_history", "public.employee_information"],
            "ontology": [{"field": "employee_no", "value": emp_no}],
            "kind": "timeline", "employee_no": emp_no}

    # --- 표준조직 검색 (가나다 표준조직 2026 생산 조직) ---
    if any(k in q for k in ["표준조직", "org_structure", "표준부서", "조직 구조", "조직구조"]):
        where, p = [], []
        ym = re.search(r"(20\d{2})", q)
        if ym:
            where.append('"년도구분" = ?')
            p.append(ym.group(1))
        for kw in ["생산", "품질", "영업", "경영지원", "R&D", "인사", "재무", "압연", "제선", "제강"]:
            if kw in q:
                where.append('("조직직무분류" LIKE ? OR "조직직무세부분류" LIKE ? OR "부서명" LIKE ?)')
                p += ["%" + kw + "%"] * 3
                break
        sql = 'SELECT * FROM ganada__org_structure'
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " LIMIT 100"
        return sql, p, {"tables": ["ganada.org_structure"],
                        "ontology": [{"field": "org_structure", "value": "표준조직 검색"}],
                        "kind": "org"}

    # --- 부서 변경 이력 질의 ---
    if any(k in q for k in ["부서 변경", "부서변경", "이동 이력", "전보", "부서 이력"]):
        emp_name = _extract_name(q)
        sql = ("SELECT h.employee_id, e.name, h.changed_at, h.previous_department_name AS 변경이전부서, "
               "h.department_name AS 변경후부서, h.change_reason "
               "FROM public__employee_department_change_history h "
               "JOIN public__employee_information e ON e.employee_id = h.employee_id ")
        where, p = [], []
        if no_m:
            where.append("e.employee_no = ?")
            p.append(no_m.group(1).upper())
        elif emp_name:
            where.append("e.name LIKE ?")
            p.append("%" + emp_name + "%")
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY h.changed_at DESC LIMIT 50"
        return sql, p, {"tables": ["public.employee_department_change_history",
                                   "public.employee_information"],
                        "ontology": used_ontology, "kind": "history"}

    # --- 평가 질의 ---
    if any(k in q for k in ["평가", "등급", "고과"]):
        sql = ("SELECT ev.employee_no, e.name, e.department_name, ev.evaluation_year, "
               "ev.evaluation_cycle, ev.grade, ev.total_score "
               "FROM employee_evaluation_db__evaluation_scores ev "
               "JOIN public__employee_information e ON e.employee_no = ev.employee_no ")
        where, p = [], []
        m = re.search(r"(20\d{2})\s*년", q)
        if m:
            where.append("ev.evaluation_year = ?")
            p.append(int(m.group(1)))
        gm = re.search(r"\b([SABC])\s*등급", q)
        if gm:
            where.append("ev.grade = ?")
            p.append(gm.group(1))
        emp_name = _extract_name(q)
        if no_m:
            where.append("ev.employee_no = ?")
            p.append(no_m.group(1).upper())
        elif emp_name:
            where.append("e.name LIKE ?")
            p.append("%" + emp_name + "%")
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY ev.evaluation_year DESC, ev.total_score DESC LIMIT 50"
        return sql, p, {"tables": ["employee_evaluation_db.evaluation_scores",
                                   "public.employee_information"],
                        "ontology": used_ontology, "kind": "evaluation"}

    # --- 급여 질의 ---
    if any(k in q for k in ["월급", "급여", "연봉", "보상"]):
        sql = ("SELECT s.employee_no, e.name, e.department_name, s.pay_month, "
               "s.base_salary, s.bonus, s.net_pay "
               "FROM employee_salary_db__salary_payments s "
               "JOIN public__employee_information e ON e.employee_no = s.employee_no ")
        where, p = [], []
        emp_name = _extract_name(q)
        if no_m:
            where.append("s.employee_no = ?")
            p.append(no_m.group(1).upper())
        elif emp_name:
            where.append("e.name LIKE ?")
            p.append("%" + emp_name + "%")
        ym = re.search(r"(20\d{2})\s*년", q)
        if ym:
            where.append("s.pay_month LIKE ?")
            p.append(ym.group(1) + "-%")
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY s.pay_month DESC LIMIT 50"
        return sql, p, {"tables": ["employee_salary_db.salary_payments",
                                   "public.employee_information"],
                        "ontology": used_ontology, "kind": "salary"}

    # --- 기본: 임직원 검색 ---
    # 사번 단독 조회
    if no_m:
        conds.append("(employee_no = ? OR employee_id = ?)")
        params += [no_m.group(1).upper()] * 2
        used_ontology.append({"field": "employee_no", "value": no_m.group(1).upper()})

    # 상태 (긴 표현 우선: '재직중이 아닌' 이 '재직' 으로 오인돼 부정 꼬리를 놓치지 않게 한다)
    for word, code in sorted(STATUS_WORDS.items(), key=lambda kv: -len(kv[0])):
        m = re.search(re.escape(word), q)
        if m:
            neg = _find_negated(q, m.span())
            conds.append("status %s ?" % ("!=" if neg else "="))
            params.append(code)
            used_ontology.append({"field": "status", "word": word, "value": code, "negated": neg})
            break

    # 성별
    for word, code in GENDER_WORDS.items():
        if word in q:
            conds.append("gender = ?")
            params.append(code)
            used_ontology.append({"field": "gender", "word": word, "value": code})
            break

    # 관리 레벨 (부정 포함 정확 매칭)
    for level, negated in _match_level(q):
        conds.append("management_level %s ?" % ("!=" if negated else "="))
        params.append(level)
        used_ontology.append({"field": "management_level", "value": level, "negated": negated})

    # 근속연수 ("18년 이상 근무", "15년차 이상")
    ym = YEARS_RE.search(q)
    if ym and any(k in q for k in ["근무", "근속", "년차", "연차", "재직"]):
        years = int(ym.group(1))
        conds.append("years_of_service >= ?")
        params.append(years)
        used_ontology.append({"field": "years_of_service", "value": ">= %d" % years,
                              "source": "ontology_query_pattern"})

    # 근무지 (서울 본사 / 포항 제철소 / 광양 제철소 / 송도 R&D 캠퍼스)
    for kw in LOCATION_KEYWORDS:
        m = re.search(re.escape(kw), q)
        if m:
            # 부서명(예: 포항압연공장)과 함께 쓰인 경우도 근무지 조건으로 안전하게 해석
            conds.append("work_location LIKE ?")
            params.append("%" + kw + "%")
            used_ontology.append({"field": "work_location", "value": kw})
            break

    # 부서명
    _, dept_rows = db.query(
        "SELECT department_code, department_name FROM public__department_management_information")
    for code, dname in dept_rows:
        if dname and dname in q:
            m = re.search(re.escape(dname), q)
            neg = _find_negated(q, m.span()) if m else False
            conds.append("department_name %s ?" % ("!=" if neg else "="))
            params.append(dname)
            used_ontology.append({"field": "department_name", "value": dname, "negated": neg})
            break

    # 입사 년도
    m = re.search(r"(19\d{2}|20\d{2})\s*년\s*(이후|이전|부터)?\s*입사", q)
    if not m:
        m = re.search(r"입사.{0,6}?(19\d{2}|20\d{2})", q)
    if m:
        year = m.group(1)
        mode = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        if mode in ("이후", "부터"):
            conds.append("hire_date >= ?")
            params.append(year + "-01-01")
        elif mode == "이전":
            conds.append("hire_date < ?")
            params.append(year + "-01-01")
        else:
            conds.append("hire_date LIKE ?")
            params.append(year + "-%")
        used_ontology.append({"field": "hire_date", "value": year})

    # Ontology 값 매핑 (사용자 정의 확장)
    for field, entries in value_maps.items():
        # 기본 검색 대상 테이블의 실제 컬럼만 SQL 조건으로 사용 (식별자 화이트리스트)
        if field not in _EMP_INFO_COLUMNS:
            continue
        if any(u.get("field") == field for u in used_ontology):
            continue
        matched = False
        for value, words in entries:
            for w in words:
                if isinstance(w, str) and len(w) > 1 and w in q:
                    conds.append("%s = ?" % field)
                    params.append(value)
                    used_ontology.append({"field": field, "word": w, "value": value,
                                          "source": "ontology_value_map"})
                    matched = True
                    break
            if matched:
                break

    # 이름
    emp_name = _extract_name(q)
    if emp_name and not conds:
        conds.append("name LIKE ?")
        params.append("%" + emp_name + "%")
        used_ontology.append({"field": "name", "value": emp_name})

    is_count = any(k in q for k in ["몇 명", "몇명", "인원", "수는", "count", "명이"])
    select = ("SELECT COUNT(*) AS 인원수" if is_count else
              "SELECT employee_no, name, gender, status, department_name, job_title, "
              "management_level, work_location, hire_date, years_of_service")
    sql = select + " FROM public__employee_information"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    if not is_count:
        sql += " ORDER BY years_of_service DESC LIMIT 50"
    return sql, params, {"tables": ["public.employee_information"],
                         "ontology": used_ontology,
                         "kind": "count" if is_count else "employee"}


_NAME_RE = re.compile(
    r"([가-힣]{2,4})\s*(?:님|씨|사원|대리|과장|차장|부장)?\s*(?:의|이|가)?\s*(?:부서|평가|월급|급여|연봉|이력|정보)")

_NAME_STOP = {"직원", "임직원", "부서", "관리자", "매니저", "여성", "남성",
              "재직", "휴직", "퇴사", "서울", "포항", "광양", "송도", "전체", "우리",
              "변경", "이력", "이동", "전보", "히스토리", "데이터", "등급",
              "평가", "월급", "급여", "연봉", "보상", "사람", "받은", "근무",
              "표준", "조직", "생산", "품질"}


def _extract_name(q):
    m = _NAME_RE.search(q)
    if m and m.group(1) not in _NAME_STOP:
        return m.group(1)
    return None


def answer(question, project="default"):
    sql, params, meta = build_sql(question, project)
    display_sql = sql
    for p in params:
        display_sql = display_sql.replace("?", "'%s'" % p, 1)
    for qname in db.CATALOG:
        display_sql = display_sql.replace(db.physical_name(qname), qname)
    try:
        cols, rows = db.query(sql, params)
        error = None
    except Exception as exc:  # pragma: no cover
        cols, rows, error = [], [], str(exc)
    summary = _summarize(question, cols, rows, meta)
    return {
        "question": question,
        "sql": display_sql,
        "columns": cols,
        "rows": rows[:50],
        "row_count": len(rows),
        "used_tables": meta["tables"],
        "used_ontology": meta["ontology"],
        "kind": meta["kind"],
        "summary": summary,
        "error": error,
    }


def _summarize(question, cols, rows, meta):
    if meta["kind"] == "count" and rows:
        return "조건에 해당하는 인원은 %s명입니다." % rows[0][0]
    if not rows:
        return "조건에 맞는 결과가 없습니다. 조건을 바꿔 다시 질문해 보세요."
    kind_label = {"employee": "임직원", "history": "부서 변경 이력",
                  "evaluation": "평가", "salary": "급여",
                  "org": "표준조직", "timeline": "변경 이력"}.get(meta["kind"], "결과")
    return "%s %d건을 찾았습니다. (최대 표시 제한 적용)" % (kind_label, len(rows))
