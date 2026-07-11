-- OAFC 직원 관리 핵심 테이블 (PostgreSQL, 2026-07-09 스키마)
-- 임베디드(SQLite) 모드와 동일한 논리 스키마의 PostgreSQL 버전.
-- 원 프로젝트의 001~013 마이그레이션 이력을 현재 스키마 기준으로 통합한 참고용 DDL 이다.

CREATE TABLE IF NOT EXISTS employees (
    employee_no TEXT PRIMARY KEY,
    korean_name TEXT,
    english_name TEXT,
    gender TEXT,
    birth_date TEXT,
    nationality TEXT,
    hire_date TEXT,
    resignation_date TEXT,
    employment_type TEXT,
    status TEXT,
    current_department_code TEXT,
    job_position_code TEXT,
    work_location_code TEXT,
    job_family TEXT,
    marital_status TEXT,
    military_service TEXT,
    blood_type TEXT,
    disability_flag INTEGER,
    veteran_flag INTEGER,
    bank_alias TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    created_at TEXT
);
COMMENT ON TABLE employees IS '임직원 마스터 (STEEL-xxxxx 사번)';

CREATE TABLE IF NOT EXISTS employee_information (
    employee_id TEXT PRIMARY KEY,
    employee_no TEXT,
    name TEXT,
    gender TEXT,
    birth_date TEXT,
    age INTEGER,
    hire_date TEXT,
    resignation_date TEXT,
    years_of_service INTEGER,
    status TEXT,
    department_code TEXT,
    department_name TEXT,
    job_title TEXT,
    management_level TEXT,
    work_location TEXT,
    salary_grade TEXT,
    education_level TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    postal_code TEXT,
    last_promotion_date TEXT,
    emergency_contact TEXT,
    updated_at TEXT
);
COMMENT ON TABLE employee_information IS '임직원 기본 정보 (현재 부서/근무지 포함, 자연어 검색 기본 대상)';

CREATE TABLE IF NOT EXISTS departments (
    department_code TEXT PRIMARY KEY,
    department_name TEXT,
    department_name_en TEXT,
    parent_department_code TEXT,
    location_code TEXT,
    department_level INTEGER,
    cost_center TEXT,
    established_date TEXT,
    closed_date TEXT,
    sort_order INTEGER,
    is_active INTEGER
);
COMMENT ON TABLE departments IS '부서 마스터';

CREATE TABLE IF NOT EXISTS department_management_information (
    department_code TEXT PRIMARY KEY,
    department_name TEXT,
    department_alias TEXT,
    standard_department_code TEXT,
    parent_department_code TEXT,
    department_head_no TEXT,
    org_unit_type TEXT,
    location TEXT,
    business_area TEXT,
    headcount_budget INTEGER,
    established_date TEXT,
    closed_date TEXT,
    is_active INTEGER
);
COMMENT ON TABLE department_management_information IS '부서 관리 정보 (표준 부서)';

CREATE TABLE IF NOT EXISTS employee_assignments (
    assignment_id INTEGER PRIMARY KEY,
    employee_no TEXT,
    department_code TEXT,
    job_position_code TEXT,
    assignment_type TEXT,
    assignment_reason TEXT,
    start_date TEXT,
    end_date TEXT,
    is_current INTEGER,
    approved_by TEXT,
    note TEXT
);
COMMENT ON TABLE employee_assignments IS '임직원 배치 이력';

CREATE TABLE IF NOT EXISTS employee_department_change_history (
    change_id INTEGER PRIMARY KEY,
    employee_id TEXT,
    changed_at TEXT,
    department_name TEXT,
    previous_department_name TEXT,
    change_reason TEXT,
    approved_by TEXT,
    approved_at TEXT
);
COMMENT ON TABLE employee_department_change_history IS '임직원 부서 변경 히스토리 (부서이름 / 변경이전 부서이름)';

CREATE TABLE IF NOT EXISTS employee_change_history (
    history_id INTEGER PRIMARY KEY,
    employee_id TEXT,
    changed_at TEXT,
    change_type TEXT,
    before_value TEXT,
    after_value TEXT,
    changed_by TEXT,
    change_source TEXT
);
COMMENT ON TABLE employee_change_history IS '임직원 변경 이력 (부서/직급/상태/근무지 등)';

CREATE TABLE IF NOT EXISTS employee_work_location_history (
    id INTEGER PRIMARY KEY,
    employee_no TEXT,
    work_location_code TEXT,
    work_location_name TEXT,
    start_date TEXT,
    end_date TEXT,
    change_reason TEXT,
    approved_by TEXT
);
COMMENT ON TABLE employee_work_location_history IS '임직원 근무지 변경 이력';

CREATE TABLE IF NOT EXISTS work_locations (
    location_code TEXT PRIMARY KEY,
    location_name TEXT,
    city TEXT,
    region TEXT,
    address TEXT,
    business_area TEXT,
    site_type TEXT,
    postal_code TEXT,
    timezone TEXT,
    is_active INTEGER
);
COMMENT ON TABLE work_locations IS '근무지/사업장 마스터';

CREATE TABLE IF NOT EXISTS job_positions (
    position_code TEXT PRIMARY KEY,
    position_name TEXT,
    position_level INTEGER,
    is_management INTEGER,
    job_family TEXT,
    grade_band TEXT,
    min_years INTEGER,
    max_years INTEGER,
    description TEXT
);
COMMENT ON TABLE job_positions IS '직위/직급 마스터';
