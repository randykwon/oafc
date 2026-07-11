# OAFC: Ontology Agent Factory Creator

정형 데이터, 비정형 데이터, 온톨로지, 의미 관계, Agent 설계를
하나의 흐름으로 연결하는 로컬 웹 솔루션.

```text
Data Integrator   -> 정형/비정형 데이터 수집 및 선택
Ontology Definer  -> 데이터 의미 자동 생성, 수동 편집, 관계 분석, 버전 관리
Agent Builder     -> 데이터/Ontology/관계 기반 Agent 설계와 테스트
Agent Shop        -> 생성된 Agent 실행, 관리, 백업, 복원
```

## 실행

```bash
python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765
# 또는
scripts/run_oafc_server.sh
```

브라우저: http://127.0.0.1:8765

런타임 외부 의존성 없음 — Python 3 표준 라이브러리만 사용한다.
첫 실행 시 `data/empsearch.db` 에 가나다 철강회사 샘플이 자동 시드된다.

- 직원 10,000명 (사번 STEEL-xxxxx), 부서 19개, 근무지 4곳(서울 본사/포항 제철소/광양 제철소/송도 R&D 캠퍼스)
- 변경 이력 약 9만 건, 평가 5년치, 월급 10년치
- Schema Graph 기준 테이블 18개 / 컬럼 227개 / 관계 25개
- 직원 수 변경: `data/empsearch.db` 삭제 후 `OAFC_SEED_EMPLOYEES=<N>` 로 재시작

## 화면

| 경로 | 화면 | 역할 |
| --- | --- | --- |
| `/` | 홈 | OAFC 전체 기능 진입점 |
| `/data-manager` | Data Integrator | RDB, 파일, URL, Cloud Storage, Pipeline, Schema Graph 관리 |
| `/ontology` | Ontology Definer | 온톨로지 생성, 편집, 의미 관계 분석, 버전 관리 |
| `/agent-builder` | Agent Builder | Chat/Scenario/Manual/Flow Studio, Production Agent Factory |
| `/agent-shop` | Agent Shop | 생성 Agent 실행, 관리, 백업, 복원 (임직원 검색 Agent 포함) |
| `/schema` | Schema Graph | DB/schema/table/field 관계도와 테이블 데이터 조회 |

`/unstructured`, `/information-center`, `/data-integration` 은 Data Integrator 로 연결되는 호환 경로다.

## 데이터 소스 (임베디드 모드)

PostgreSQL/MySQL 미설치 환경을 위해 SQLite 하나로 4개 논리 소스를 시뮬레이션한다.

- `public` — 직원관리 DB 15개 테이블 (employees, employee_information, departments,
  department_management_information, employee_assignments, employee_department_change_history,
  employee_change_history, employee_work_location_history, work_locations, job_positions,
  ontology_concepts, ontology_concept_columns, ontology_relationships,
  ontology_query_patterns, ontology_definitions)
- `ganada` — 표준조직 `org_structure` (한국어 컬럼)
- `employee_salary_db` — 급여 `salary_payments` (MySQL 시뮬레이션)
- `employee_evaluation_db` — 평가 `evaluation_scores` (MySQL 시뮬레이션)

MySQL DB 자동 보정: `employee_salary_db.evaluation_scores` 처럼 잘못된 DB 를 지정해도
테이블명이 유일하면 실제 DB 로 자동 보정한다.

실서버 전환용 DDL 은 `db/migrations/` 참조.

## 주요 API

| Method | Path | 역할 |
| --- | --- | --- |
| GET | `/api/summary` | 직원/부서/근무지/스키마 요약 |
| GET | `/api/schema` | schema/table/field/relation 조회 |
| GET | `/api/table-data` | 테이블 데이터 조회 (DB 자동 보정 포함) |
| GET | `/api/employees` | 직원 검색 |
| GET | `/api/timeline/{employee_no}` | 직원 이력 조회 |
| POST | `/api/agent` | 자연어 Agent 질의 (SQL/근거 반환) |
| POST | `/api/unstructured/upload` | 비정형 파일 업로드/분석 |
| POST | `/api/unstructured/url` | URL/YouTube 분석 |
| GET/POST/DELETE | `/api/ontology` | Ontology 조회/저장/삭제 |
| POST | `/api/ontology/infer` | Ontology 자동 유추 |
| POST | `/api/ontology/automate` | 전체/선택 범위 자동 실행 |
| POST | `/api/ontology/import` | Ontology JSON import |
| POST | `/api/ontology/bulk-delete` | 전체/테이블/필드 bulk delete |
| POST | `/api/generated-metadata/reset` | 생성 메타데이터 초기화 |
| GET/POST | `/api/database-info` | DB 정보 조회 |
| GET/POST | `/api/external-schema` | 외부 schema 수집 (드라이버 필요) |

## 자연어 질의 예시

```text
광양 근무자 중 여성 18년 이상 근무하고 manager인 사람만 뽑아줘
광양 근무자 중 여성 18년 이상 근무하고 manager가 아닌 사람만 뽑아줘
포항에 근무하는 15년차 이상 여성 관리자를 찾아줘
가나다 표준조직 2026 생산 조직을 보여줘
STEEL-00001 이력을 보여줘
```

## 테스트

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q                                   # 7 passed
for f in empsearch/web_static/*.js; do node --check "$f"; done
```

## 문서

- [docs/OAFC_DEVELOPMENT_SUMMARY_2026-07-09.md](docs/OAFC_DEVELOPMENT_SUMMARY_2026-07-09.md) — 최신 통합 현황 (스펙)
- [docs/OAFC_CURRENT_IMPLEMENTATION_2026-07-08.md](docs/OAFC_CURRENT_IMPLEMENTATION_2026-07-08.md)
- [docs/REBUILD_FROM_SCRATCH.md](docs/REBUILD_FROM_SCRATCH.md)
- `examples/ganada_unstructured/` — 비정형 인사 문서 샘플 16종

## 현재 한계

Cloud Storage / Iceberg / Pipeline 실행 / 멀티모달 처리(OCR·STT·비전)는
UI·메타데이터·시뮬레이션 레벨이다. localStorage 상태 저장의 서버 이전,
실제 SDK/Catalog/Orchestrator 연동은 다음 단계 과제다
(상세: 스펙 문서 20장).
