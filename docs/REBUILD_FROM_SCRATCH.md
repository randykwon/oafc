# OAFC 재구현 가이드

`docs/OAFC_DEVELOPMENT_SUMMARY_2026-07-09.md` 를 스펙으로 삼아 재구현한 버전이다.

## 이 구현의 환경 차이

스펙 문서는 PostgreSQL + MySQL 환경을 전제하지만, 이 저장소는 DB 서버가 없는
로컬 환경에서도 전체 기능이 동작하도록 **임베디드 모드(SQLite)** 를 기본으로 한다.

- `empsearch/db.py` 가 `data/empsearch.db` 에 4개 논리 소스를 시뮬레이션한다.
  - `public`                 — 직원 관리 DB 15개 테이블 (PostgreSQL 역할)
  - `ganada`                 — 표준조직 schema
  - `employee_salary_db`     — 급여 DB (MySQL 역할)
  - `employee_evaluation_db` — 평가 DB (MySQL 역할)
- Schema Graph 기준 테이블 18개 / 컬럼 227개 / 관계 25개.
- PostgreSQL / MySQL 실서버 전환 시 `db/migrations/*.sql` 로 스키마를 만들고
  `empsearch/db.py` 의 query/execute 를 해당 드라이버로 교체한다.
- sqlite3 커넥션은 스레드별로 분리되어 있다 (동시 요청 시 공유 커넥션 segfault 방지).

## 재구현 순서 (스펙 문서 21장 매핑)

1. `empsearch/db.py` — 18테이블 스키마 + 10,000명 시드 (STEEL-xxxxx)
2. `empsearch/web_agent.py` — 서버 + `/api/schema`, `/api/summary`, `/api/table-data`,
   `/api/employees`, `/api/timeline/{no}` 등
3. `empsearch/nlq.py` — 자연어 SQL (근속연수/부정 조건/표준조직/사번 이력)
4. `schema.html/css/js` — Schema Graph
5. `unstructured.html/css/js` — Data Integrator 전체
6. `ontology.html/css/js` + `empsearch/ontology_ai.py` — Ontology Definer
   (생성/편집/의미 관계/버전관리)
7. `agent_builder.html/css/js` — Agent Builder (Chat/Scenario/Manual/Flow Studio,
   Production Agent Factory)
8. `agent_shop.html/css/js` — Agent Shop
9. `project.js` — 프로젝트 namespace (`empsearch.project.{id}.*`)

## 실행

```bash
python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765
# 또는
scripts/run_oafc_server.sh
```

## 검증

```bash
python3 -m pytest -q          # 7 passed
curl -sS http://127.0.0.1:8765/api/summary
curl -sS -X POST http://127.0.0.1:8765/api/agent \
  -H 'Content-Type: application/json' \
  -d '{"question":"광양 근무자 중 여성 18년 이상 근무하고 manager가 아닌 사람만 뽑아줘"}'
for f in empsearch/web_static/*.js; do node --check "$f"; done
```
