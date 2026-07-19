# OAFC 구현 현황

작성일: 2026-07-19
버전: `oafc 1.0.0`
저장소: https://github.com/randykwon/oafc

이 문서는 저장소에 실제로 구현되어 있는 코드 기준의 현황 정리다. 과거 `empsearch`
샘플 인사 검색 앱 구조는 제거되었고, 현재는 **DB 메타데이터를 탐색·저장·선택하고
온톨로지 초안까지 연결하는 로컬 웹 도구**(OAFC DB Integrator)로 재구성되어 있다.

## 1. 개요

OAFC는 표준 라이브러리 기반의 경량 HTTP 서버와 Vanilla JS 프런트엔드로 동작하는
로컬 솔루션이다. 사용자는 4단계 워크플로우를 따라 DB를 연결하고, Agent가 사용할
테이블을 선택한 뒤, 컬럼 의미(온톨로지) 초안을 생성·적용한다.

핵심 흐름:

```text
1. DB 탐색      → 로컬 SQLite 탐색 또는 MySQL 서버 등록
2. 정보 저장    → 연결 프로필 저장, 연결 테스트
3. 테이블 선택  → DB 인벤토리 조회, 업무 테이블 지정
4. 온톨로지 적용 → 컬럼 의미 초안 생성, 검토 후 적용
   + 데이터 분석 도구 → 읽기 전용 쿼리 실행/미리보기
```

## 2. 기술 스택

| 영역 | 구현 |
| --- | --- |
| Backend | Python 3.10+, `http.server.ThreadingHTTPServer` (표준 라이브러리) |
| Frontend | HTML, CSS, Vanilla JavaScript (빌드 도구 없음) |
| 메타데이터 저장 | 로컬 SQLite 메타데이터 DB |
| 데이터 소스 | SQLite(내장), MySQL/MariaDB(`pymysql`, 선택 설치) |
| 자격증명 | 환경변수 alias 해석 — 원시 비밀번호 미저장 |
| 테스트 | `pytest` (62 케이스) |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |

의존성은 실행용 `pymysql` 하나(`requirements.txt`), 개발용은 여기에 `pytest`를
더한다(`requirements-dev.txt`).

## 3. 파일 구조

```text
oafc/
  __init__.py     버전 정보 (1.0.0)
  server.py       HTTP 서버, API 라우팅, 인증/보안 (325 lines)
  metadata.py     IntegratorStore: 메타데이터 저장, DB 연결, 온톨로지 추론 (1050 lines)
  web/
    index.html    4단계 워크플로우 UI (161 lines)
    app.js        상태 관리, API 호출, 렌더링 (876 lines)
    app.css       스타일 (187 lines)

tests/
  fakes.py, conftest.py            테스트 픽스처/페이크
  test_http.py                     서버·인증·라우팅
  test_metadata.py                 저장/연결 로직
  test_analysis.py                 쿼리 분석
  test_frontend.py                 정적 자산 서빙
  test_regressions.py              회귀 방지

docs/
  IMPLEMENTATION.md   본 문서
```

## 4. 워크플로우 (프런트엔드 4단계)

프런트엔드는 `index.html`의 4개 `stage` 섹션과 `app.js`의 `showStep()`으로
단계를 전환한다.

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
- Agent가 사용할 업무 테이블 지정(전체 선택/해제)
- API: `GET /api/connections/{id}/inventory`, `GET .../schema`,
  `PUT .../tables`, `GET .../tables`

### STEP 4 — 온톨로지 적용
- 선택 테이블 기준 온톨로지 초안 생성 → 검토 → 적용
- API: `POST /api/connections/{id}/ontology/suggest`,
  `POST .../ontology/apply`, `GET .../ontology`

### 데이터 분석 도구
- 읽기 전용 쿼리 실행, row 미리보기(기본 100행, 타임아웃 5초)
- API: `POST /api/connections/{id}/analysis/query`

## 5. API 목록

| Method | 경로 | 역할 |
| --- | --- | --- |
| `GET` | `/api/workflow` | 연결 수 / 선택 테이블 수 / 온톨로지 수 요약 |
| `GET` | `/api/discovery` | SQLite DB 후보 탐색 |
| `GET` | `/api/connections` | 저장된 연결 목록 |
| `POST` | `/api/connections` | 연결 프로필 저장 |
| `GET` | `/api/connections/{id}` | 연결 상세 |
| `DELETE` | `/api/connections/{id}` | 연결 삭제 |
| `POST` | `/api/connections/{id}/test` | 연결 테스트 |
| `GET` | `/api/connections/{id}/inventory` | 접근 가능 DB 인벤토리 |
| `GET` | `/api/connections/{id}/schema` | 스키마/테이블/컬럼 조회 |
| `GET` | `/api/connections/{id}/tables` | 선택 테이블 상세 |
| `PUT` | `/api/connections/{id}/tables` | 사용 테이블 선택 저장 |
| `POST` | `/api/connections/{id}/ontology/suggest` | 온톨로지 초안 생성 |
| `POST` | `/api/connections/{id}/ontology/apply` | 온톨로지 정의 적용 |
| `GET` | `/api/connections/{id}/ontology` | 적용된 온톨로지 정의 조회 |
| `POST` | `/api/connections/{id}/analysis/query` | 읽기 전용 쿼리 분석 |

라우팅은 `server.py`의 정규식 `_route()`로 `connection_id`와 액션을 파싱한다.

## 6. 온톨로지 추론

`metadata.py`의 `_column_semantics()`가 컬럼명/타입을 규칙 기반으로 분류해
초안을 만든다.

| semantic_type | 판별 근거 (예) | confidence |
| --- | --- | --- |
| `identifier` | `id`, `key`, `uuid`, `code` | 0.90 |
| `temporal` | `created`, `updated`, `date`, `time`, `DATE/TIME` 타입 | 0.72–0.86 |
| `measure` | `amount`, `price`, `total`, `count`, 숫자형 타입 | 0.68–0.84 |
| `attribute`/`entity` | 기본값 | ~0.75 |

각 정의는 `label`, `description`, `synonyms`, `semantic_type`, `confidence`를
가지며 SQLite 메타데이터 테이블에 저장된다. 적용 시 synonyms는 배열 또는
쉼표 구분 문자열을 허용하고 비어 있지 않은 문자열인지 검증한다.

## 7. 보안 설계

`server.py`는 로컬 도구지만 방어적으로 구성되어 있다.

- **토큰 인증**: `OAFC_API_TOKEN` 설정 시 변경(mutating) API에 `Bearer` 토큰을
  요구하고, `hmac.compare_digest`로 상수 시간 비교
- **Host 허용목록**: `Host` 헤더를 `allowed_hosts`와 대조, 불일치 시 421 응답
  (기본으로 `localhost`, `127.0.0.1`, `::1`, 바인딩 주소 허용)
- **Origin 검사**: 변경 요청의 Origin 확인
- **정적 서빙 경로 제한**: `web/` 밖 경로 접근 차단(경로 탈출 방지)
- **응답 헤더**: `X-Content-Type-Options: nosniff`,
  엄격한 `Content-Security-Policy`(`default-src 'self'`, `object-src 'none'`,
  `frame-ancestors 'none'` 등)
- **자격증명 비저장**: 원시 비밀번호를 받지 않고 `OAFC_CREDENTIAL_<ALIAS>`
  환경변수로만 해석(`EnvironmentCredentialResolver`)
- **읽기 전용 쿼리**: 분석 쿼리는 행 수·타임아웃 제한

## 8. 실행

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

## 9. 테스트

```bash
python3 -m pytest -q
```

현재 **62개 테스트 전부 통과**. HTTP/인증/라우팅, 메타데이터 저장, 쿼리 분석,
정적 자산 서빙, 회귀 방지를 커버한다.

## 10. 남은 개선 후보

- PostgreSQL 등 추가 커넥터 지원
- 온톨로지 초안의 관계(relationship) 추론
- 스키마 그래프 시각화
- Agent 설계/실행 레이어(과거 계획) 재도입 검토
- 사용자/프로젝트/권한 모델
