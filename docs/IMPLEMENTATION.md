# OAFC 구현 현황

작성일: 2026-08-28
버전: `oafc 1.0.0`
저장소: https://github.com/randykwon/oafc

이 문서는 저장소에 실제로 구현되어 있는 코드 기준의 현황 정리다. 과거 `empsearch`
샘플 인사 검색 앱 구조는 제거되었고, 현재는 **DB 메타데이터를 탐색·저장·선택하고,
컬럼 의미(온톨로지)·관계·Semantic Model 까지 조립한 뒤 자연어로 조회**하는
로컬 웹 도구(OAFC DB Integrator)로 재구성되어 있다.

초기에는 "DB 연결 → 테이블 선택 → 온톨로지 적용"까지의 4단계 도구였고, 이후
`enterprise_ai_business_foundation.md` 비전 문서에 맞춰 **Data Knowledge →
Relationship Discovery → Semantic Model → Natural Language Query → Analytical
Knowledge** 로 이어지는 Enterprise AI 기반 계층이 얹혔다.

## 1. 개요

OAFC 는 표준 라이브러리 기반의 경량 HTTP 서버와 Vanilla JS 프런트엔드로 동작하는
로컬 솔루션이다. 사용자는 4단계 워크플로우로 DB 를 연결하고, Agent 가 사용할
테이블을 선택하고, 컬럼 의미(온톨로지)를 적용한 뒤, 별도의 **데이터 분석 도구**에서
관계를 발견·승인하고 Semantic Model 을 조립하며 자연어로 읽기 전용 쿼리 초안을
생성·저장한다.

핵심 흐름:

```text
1. DB 탐색         → 로컬 SQLite 탐색 또는 MySQL 서버 등록
2. 정보 저장        → 연결 프로필 저장, 연결 테스트
3. 테이블 선택      → DB 인벤토리 조회, 업무 테이블 지정 (검색·필터·실시간 카운트)
4. 온톨로지 적용     → 컬럼 의미 초안 생성, 동의어(한국어 포함) 검토 후 적용

데이터 분석 도구 (읽기 전용):
  · 관계 발견/승인   → 다중 신호 관계 추론 + Provenance
  · Semantic Model  → 엔티티·속성·승인 관계를 하나의 모델로 조립/내보내기
  · 자연어 조회      → Semantic Model 근거로 SELECT 초안 + Evidence (JOIN 포함)
  · 저장된 분석      → 질문·SQL·Evidence 를 재사용 가능한 지식으로 저장
  · SQL 실행         → 읽기 전용 쿼리 실행/미리보기
```

핵심 설계 원칙은 **Human-in-the-loop + Evidence**다: 시스템은 LLM 없이 규칙 기반으로
관계·쿼리 초안과 근거(Evidence)를 만들고, 실제 승인·실행은 항상 사용자가 검토한 뒤
수행한다. 생성된 모든 SQL 은 실행 전에 읽기 전용 검증기를 통과한다.

## 2. 기술 스택

| 영역 | 구현 |
| --- | --- |
| Backend | Python 3.10+, `http.server.ThreadingHTTPServer` (표준 라이브러리) |
| Frontend | HTML, CSS, Vanilla JavaScript (빌드 도구 없음) |
| 메타데이터 저장 | 로컬 SQLite 메타데이터 DB |
| 데이터 소스 | SQLite(내장), MySQL/MariaDB(`pymysql`, 선택 설치) |
| 자격증명 | 환경변수 alias 해석 — 원시 비밀번호 미저장 |
| 테스트 | `pytest` (69 케이스) |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |

의존성은 실행용 `pymysql` 하나(`requirements.txt`), 개발용은 여기에 `pytest`를
더한다(`requirements-dev.txt`). 자연어 조회를 포함한 모든 추론은 외부 API·LLM 없이
로컬 규칙으로 동작한다.

## 3. 파일 구조

```text
oafc/
  __init__.py     버전 정보 (1.0.0)
  server.py       HTTP 서버, API 라우팅, 인증/보안 (352 lines)
  metadata.py     IntegratorStore: 메타데이터 저장, DB 연결, 온톨로지·관계·
                  Semantic Model·자연어 조회 (1740 lines)
  web/
    index.html    4단계 워크플로우 + 분석 도구 UI (214 lines)
    app.js        상태 관리, API 호출, 렌더링 (1212 lines)
    app.css       스타일 (266 lines)

tests/
  fakes.py, conftest.py            테스트 픽스처/페이크 (commerce.sqlite)
  test_http.py                     서버·인증·라우팅
  test_metadata.py                 저장/연결/관계/Semantic Model/자연어 조회
  test_analysis.py                 쿼리 분석
  test_frontend.py                 정적 자산 서빙
  test_regressions.py              회귀 방지

docs/
  IMPLEMENTATION.md   본 문서
```

## 4. 워크플로우 (프런트엔드)

프런트엔드는 `index.html`의 `stage` 섹션과 `app.js`의 `showStep()`으로 단계를
전환한다. 4단계 통합 마법사와, 연결이 준비된 뒤 진입하는 읽기 전용 **데이터 분석
도구**로 구성된다.

### STEP 1 — DB 탐색
- `SQLite 탐색`: 지정된 discovery-root 아래 SQLite 파일 후보 자동 탐색
- `MySQL 서버 등록`: 원격 MySQL/MariaDB 연결 폼 열기
- API: `GET /api/discovery`

### STEP 2 — 정보 저장
- 연결 이름, Host/Username/기본 분석 DB, SSL CA 파일(선택), Credential alias 입력
- 비밀번호는 폼에 저장하지 않고 `OAFC_CREDENTIAL_<ALIAS>` 환경변수로 주입
- `연결정보 저장` / `연결 테스트`
- API: `POST /api/connections`, `POST /api/connections/{id}/test`

### STEP 3 — 테이블 선택
- 접근 가능한 DB 인벤토리 조회, 선택 DB 스키마 분석
- 테이블 검색창, 전체/선택/미선택 필터 칩, 선택 수 실시간 카운트, 보이는 테이블
  일괄 선택
- API: `GET .../inventory`, `GET .../schema`, `PUT .../tables`, `GET .../tables`

### STEP 4 — 온톨로지 적용
- 선택 테이블 기준 온톨로지 초안 생성 → label·설명·**동의어** 검토 → 적용
- 동의어(한국어 포함)는 뒤의 자연어 조회 매칭에 바로 쓰인다
- API: `POST .../ontology/suggest`, `POST .../ontology/apply`, `GET .../ontology`

### 데이터 분석 도구
- **관계 발견/승인**, **Semantic Model 조립·내보내기**, **자연어 조회(+Evidence)**,
  **저장된 분석(Analytical Knowledge)**, **읽기 전용 SQL 실행**을 한 화면에서 제공
- 상세는 5장 참조

## 5. Enterprise AI 기능

### 5.1 관계 발견 — Relationship Discovery
`metadata.discover_relationships()` 가 선택 테이블 사이의 관계 후보를 **다중 신호**로
추론한다.

- **물리적 FK**: 스키마의 외래키 → confidence `1.0`, method `physical_fk`
- **추론 관계**: 세 신호를 결합
  - 이름 유사도(`_name_similarity`): 식별자 패턴/토큰 겹침
  - 타입 정합성(`_type_category`)
  - 값 겹침(`_sqlite_value_overlap`, SQLite): 실제 값 교집합 비율
- 후보 기준 이름 점수 `>= 0.3`, 최종 confidence `>= 0.4` 인 것만 유지
- 값 겹침이 0% 면 confidence 를 `× 0.35` 로 감쇠(관계 반증)
- 각 관계는 predicate(`belongs_to`/`references`), evidence 목록,
  from/to 엔티티 라벨, 승인 상태(candidate/approved)를 가진다

### 5.2 관계 승인과 Provenance
`save_relationships()` 는 사용자의 검토 결정을 `saved_relationships` 테이블에
저장한다.

- status `approved` → 저장, `rejected` → 삭제
- Provenance 기록: `validated_by='user'`, `validated_at`
- `discover_relationships` 는 저장된 승인 상태를 병합하며, 승인된 엣지는 재발견되지
  않아도 유지

### 5.3 Semantic Model 조립
`semantic_model()` 이 선택 테이블·적용 온톨로지·승인 관계를 하나의
Enterprise Business Model 로 통합한다.

- **엔티티**: 비즈니스 라벨/설명/동의어 + 속성(컬럼 의미)
- **관계**: 승인된 엣지 + 검증 근거(Provenance)
- **요약**: entity_count, defined_entity_count, attribute_count,
  relationship_count, coverage(정의 완료율)
- 프런트엔드에서 JSON 으로 내보내 조직 자산으로 재사용 가능

### 5.4 자연어 조회 — Natural Language Query
`nl_to_sql()` 은 Semantic Model 을 근거로 자연어 질문에서 **읽기 전용 SELECT 초안**을
생성한다. LLM 없이 엔티티/속성 매칭 규칙으로 동작하며, 실행하지 않고 초안 + Evidence
만 돌려준다(사용자가 검토 후 실행).

- **엔티티 선택**: 토큰 IDF 가중(희소·변별력 있는 토큰 우대) + 테이블 핵심명 부스트
  + 큐레이션된 동의어 직접 매칭 신호
- **교차 언어 매칭**: 자동 라벨은 영어라, 흔한 한국어 업무 용어를 영어 토큰으로
  확장하는 힌트 사전(`_KR_EN_HINTS`)을 둔다
- **집계/그룹 의도**: COUNT/SUM/AVG/MAX/MIN, `별`/독립 토큰 `수`·`명` 감지
- **Evidence**: entity, table, columns, intent, group_by, join 을 함께 반환
- 생성된 SQL 은 반드시 읽기 전용 검증기를 통과

### 5.5 관계 인식 JOIN
질문이 **승인된 관계로 직접 연결된** 두 엔티티에 걸치면 `_nl_join_draft()` 가
Semantic Model 의 관계를 따라 별칭(t1/t2) JOIN 초안을 만든다.

- 측정 컬럼과 그룹 차원을 두 표에 걸쳐 선택(차원은 관계 상대 표 우선)
- 승인된 관계가 없으면 단일 테이블 초안으로 폴백 — 관계를 임의로 만들지 않음
- Evidence.join 에 상대 엔티티·ON 절·predicate·confidence·Provenance 포함
- 예: `카테고리별 주문 수량 합계` →
  `SELECT t2."category", SUM(t1."quantity") ... FROM orders t1 JOIN products t2
  ON t1."product_id" = t2."product_id" GROUP BY t2."category"`

### 5.6 동의어 기반 매칭 (한국어 포함)
온톨로지에 등록한 동의어가 자연어 매칭을 직접 이끈다. 토크나이저가 `[A-Za-z0-9]`
만 남기므로 한국어 동의어는 **부분 문자열**로 직접 매칭한다.

- 엔티티 선택: 큐레이션 동의어 신호(희소할수록 강함)를 토큰 IDF 와 함께 합산
- 컬럼 매칭: 토큰이 안 맞으면 동의어 부분 문자열로 폴백
- 테이블 레벨 동의어도 Semantic Model 에 노출 → 표 동의어가 엔티티를 선택
- 힌트 사전 밖의 완전 커스텀 동의어(예: `임직원현황`)도 정확히 라우팅

### 5.7 저장된 분석 — Analytical Knowledge
`save_analysis()`/`saved_analyses()`/`delete_analysis()` 가 검토한 쿼리를 재사용
가능한 조직 지식으로 남긴다.

- 자연어 질문 + SQL 초안 + Evidence 를 `saved_analyses` 테이블에 저장
- 저장 시점에도 SQL 이 읽기 전용 검증기를 통과해야 함(항상 안전하게 재실행)
- Provenance: `created_by='user'`, `created_at`
- 프런트엔드에서 카드로 나열, 편집기로 불러오기·삭제

## 6. API 목록

| Method | 경로 | 역할 |
| --- | --- | --- |
| `GET` | `/api/workflow` | 연결/선택 테이블/온톨로지 수 요약 |
| `GET` | `/api/discovery` | SQLite DB 후보 탐색 |
| `GET` | `/api/connections` | 저장된 연결 목록 |
| `POST` | `/api/connections` | 연결 프로필 저장 |
| `GET` | `/api/connections/{id}` | 연결 상세 |
| `DELETE` | `/api/connections/{id}` | 연결 삭제 |
| `POST` | `/api/connections/{id}/test` | 연결 테스트 |
| `GET` | `/api/connections/{id}/inventory` | 접근 가능 DB 인벤토리 |
| `GET` | `/api/connections/{id}/schema` | 스키마/테이블/컬럼 조회 |
| `GET` `PUT` | `/api/connections/{id}/tables` | 선택 테이블 조회 / 저장 |
| `POST` | `/api/connections/{id}/ontology/suggest` | 온톨로지 초안 생성 |
| `POST` | `/api/connections/{id}/ontology/apply` | 온톨로지 정의 적용 |
| `GET` | `/api/connections/{id}/ontology` | 적용된 온톨로지 정의 조회 |
| `GET` `PUT` | `/api/connections/{id}/relationships` | 관계 발견 / 승인·제외 저장 |
| `GET` | `/api/connections/{id}/semantic-model` | Semantic Model 조립 결과 |
| `POST` | `/api/connections/{id}/analysis/query` | 읽기 전용 쿼리 분석 |
| `POST` | `/api/connections/{id}/analysis/nl-to-sql` | 자연어 → SELECT 초안 |
| `GET` `POST` | `/api/connections/{id}/analysis/saved` | 저장된 분석 목록 / 저장 |
| `DELETE` | `/api/connections/{id}/analysis/saved/{analysis_id}` | 저장된 분석 삭제 |

라우팅은 `server.py`의 정규식 `_route()`(+ 저장 분석용 `_route_saved_analysis()`)로
`connection_id`와 액션을 파싱한다.

## 7. 온톨로지 추론

`metadata.py`의 `_column_semantics()`가 컬럼명/타입을 규칙 기반으로 분류해 초안을
만든다.

| semantic_type | 판별 근거 (예) | confidence |
| --- | --- | --- |
| `identifier` | `id`, `key`, `uuid`, `code` | 0.90 |
| `temporal` | `created`, `updated`, `date`, `time`, `DATE/TIME` 타입 | 0.72–0.86 |
| `measure` | `amount`, `price`, `total`, `count`, 숫자형 타입 | 0.68–0.84 |
| `classification` | `status`, `type`, `category`, `kind`, `state` | 0.82 |
| `attribute`/`entity` | 기본값 | ~0.75 |

각 정의는 `label`, `description`, `synonyms`, `semantic_type`, `confidence`를
가지며 SQLite 메타데이터 테이블에 저장된다. 적용 시 synonyms 는 배열 또는 쉼표 구분
문자열을 허용하고 비어 있지 않은 문자열인지 검증한다. semantic_type 은 자연어 조회의
측정 컬럼·그룹 차원 선택에 직접 활용된다.

## 8. 보안 설계

`server.py`는 로컬 도구지만 방어적으로 구성되어 있다.

- **토큰 인증**: `OAFC_API_TOKEN` 설정 시 변경(mutating) API 에 `Bearer` 토큰을
  요구하고, `hmac.compare_digest`로 상수 시간 비교
- **Host 허용목록**: `Host` 헤더를 `allowed_hosts`와 대조, 불일치 시 421 응답
  (기본으로 `localhost`, `127.0.0.1`, `::1`, 바인딩 주소 허용)
- **Origin/Sec-Fetch 검사**: 변경 요청의 Origin·교차 사이트 요청 차단
- **정적 서빙 경로 제한**: `web/` 밖 경로 접근 차단(경로 탈출 방지)
- **응답 헤더**: `X-Content-Type-Options: nosniff`, 엄격한
  `Content-Security-Policy`(`default-src 'self'`, `style-src 'self'`,
  `object-src 'none'`, `frame-ancestors 'none'` 등)
  - CSP 가 인라인 스타일을 막으므로 프런트엔드의 모든 동적 스타일은 클래스 기반
- **자격증명 비저장**: 원시 비밀번호를 받지 않고 `OAFC_CREDENTIAL_<ALIAS>`
  환경변수로만 해석(`EnvironmentCredentialResolver`)

### 읽기 전용 SQL 검증기
분석·자연어 조회·저장된 분석에서 실행/저장되는 모든 SQL 은
`_validated_analysis_sql()` 를 통과해야 한다.

- `SELECT`/`WITH` 로 시작하는 단일 문장만 허용
- 주석(`--`, `/* */`, `#`)·백슬래시 이스케이프·잠금 읽기(`FOR UPDATE` 등) 거부
- 금지 키워드/함수 목록 대조, 따옴표로 감싼 함수명 차단
- 행 수·타임아웃 제한으로 실행

## 9. 실행

```bash
pip install -r requirements.txt
python3 -m oafc.server --host 127.0.0.1 --port 8765
```

| 인자/환경변수 | 설명 |
| --- | --- |
| `--host` / `--port` | 바인딩 주소 (기본 127.0.0.1:8765) |
| `--metadata-db` | 메타데이터 SQLite 경로 |
| `--discovery-root` | SQLite 탐색 루트 (반복 지정 가능) |
| `OAFC_API_TOKEN` | 변경 API Bearer 토큰 |
| `OAFC_ALLOWED_HOSTS` | 허용 Host 목록(쉼표 구분) |
| `OAFC_PUBLIC_ORIGIN` | 공개 배포 origin |
| `OAFC_CREDENTIAL_<ALIAS>` | DB 자격증명 alias |

비-loopback 바인딩에는 `OAFC_API_TOKEN` 과 `OAFC_ALLOWED_HOSTS` 가 필수다.

## 10. 테스트

```bash
python3 -m pytest -q
```

현재 **69개 테스트 전부 통과**. HTTP/인증/라우팅, 메타데이터 저장, 관계 발견·승인,
Semantic Model 조립, 자연어 조회(집계·JOIN·동의어), 저장된 분석, 쿼리 분석,
정적 자산 서빙, 회귀 방지를 커버한다.

## 11. 남은 개선 후보

- 저장된 분석 실행 이력(run_count / 마지막 결과 요약)
- 2-hop 이상 관계 경로를 따르는 JOIN
- Semantic Model 문서/그래프 시각화 및 공유
- PostgreSQL 등 추가 커넥터 지원
- 사용자/프로젝트/권한 모델
