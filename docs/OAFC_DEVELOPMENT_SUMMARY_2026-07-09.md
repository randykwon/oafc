# OAFC 개발 현황 통합 정리

작성일: 2026-07-09  
프로젝트 경로: `/Users/yongsunk/Documents/EmpSearch`  
실행 URL: `http://127.0.0.1:8765`  
솔루션 이름: `OAFC: Ontology Agent Factory Creator`

이 문서는 오늘까지 구현된 OAFC의 전체 기능, 데이터 구조, 화면, API, 저장 방식, 테스트 방법, 최근 수정사항을 한 파일로 정리한 최신 개발 현황 문서이다.

## 1. 솔루션 개요

OAFC는 정형 데이터, 비정형 데이터, 온톨로지, 의미 관계, Agent 설계를 하나의 흐름으로 연결하는 로컬 웹 솔루션이다.

핵심 흐름은 다음과 같다.

```text
Data Integrator
  -> 정형/비정형 데이터 수집 및 선택
Ontology Definer
  -> 데이터 의미 자동 생성, 수동 편집, 관계 분석, 버전 관리
Agent Builder
  -> 데이터/Ontology/관계 기반 Agent 설계와 테스트
Agent Shop
  -> 생성된 Agent 실행, 관리, 백업, 복원
```

초기에는 임직원 검색 챗봇과 직원 이력 조회 기능에서 시작했으며, 현재는 OAFC라는 이름으로 데이터 통합, 온톨로지 정의, Agent 생성/운영까지 포함하는 구조로 확장되었다.

## 2. 현재 실행 상태 기준 수치

2026-07-09 기준 로컬 서버 API로 확인한 현재 상태이다.

| 항목 | 값 |
| --- | ---: |
| 직원 수 | 10,000 |
| 직원 기본정보 row | 10,000 |
| 부서 수 | 19 |
| 근무지 수 | 4 |
| 변경 이력 row | 92,612 |
| Schema Graph 테이블 수 | 18 |
| Schema Graph 컬럼 수 | 227 |
| Schema Graph 관계 수 | 25 |
| Ontology 정의 수 | 245 |
| 테이블 단위 Ontology | 18 |
| 필드 단위 Ontology | 227 |

현재 직원 분포 예시:

| 구분 | 주요 값 |
| --- | --- |
| 상태 | active 9,656명, on_leave 243명, resigned 101명 |
| 근무지 | 서울 본사 4,455명, 포항 제철소 2,674명, 광양 제철소 2,375명 |
| 주요 부서 | 포항압연공장, 포항생산본부, 포항설비정비섹션, 광양품질섹션, 광양압연공장 등 |

## 3. 주요 메뉴와 웹 경로

| 경로 | 화면 | 역할 |
| --- | --- | --- |
| `/` | 홈 | OAFC 전체 기능 진입점 |
| `/data-manager` | Data Integrator | RDB, 파일, URL, Cloud Storage, Pipeline, Schema Graph 관리 |
| `/ontology` | Ontology Definer | 온톨로지 생성, 편집, 의미 관계 분석, 버전 관리 |
| `/agent-builder` | Agent Builder | Agent 설계, 테스트, 생성 |
| `/agent-shop` | Agent Shop | 생성 Agent 실행, 관리, 백업, 복원 |
| `/schema` | Schema Graph | DB/schema/table/field 관계도와 테이블 데이터 조회 |
| `/unstructured` | 호환 경로 | Data Integrator로 연결 |
| `/information-center` | 호환 경로 | Data Integrator로 연결 |
| `/data-integration` | 호환 경로 | Data Integrator로 연결 |

레거시 `/superagent`, `/speragent` 경로와 관련 정적 파일은 제거했다. 현재 Agent 생성 기능은 `/agent-builder`, Agent 실행/관리는 `/agent-shop` 기준이다.

## 4. 명칭 정리

현재 사용자에게 노출되는 명칭은 다음 기준으로 정리되어 있다.

| 과거 명칭 | 현재 명칭 |
| --- | --- |
| EmpSearch | OAFC |
| EmpSearch 홈 | OAFC 홈 |
| Data Manager | Data Integrator |
| Ontology Manager | Ontology Definer |
| Super Agent / SuperAgent Builder | Agent Builder |
| AgentFactory | Agent Shop |
| 직원 이력 챗봇 | Agent Shop의 임직원 검색 Agent |

저장소 폴더명 `/Users/yongsunk/Documents/EmpSearch`와 macOS 앱 번들에는 초기 이름이 일부 남아 있다. 이는 파일 경로 호환을 위한 잔존명이며, 제품/UI 명칭은 OAFC 기준으로 정리했다.

## 5. 기술 스택

| 영역 | 구현 |
| --- | --- |
| Backend | Python 3, `http.server.ThreadingHTTPServer` |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Database | PostgreSQL, MySQL/MariaDB schema/table 조회 일부 |
| 정형 데이터 조회 | PostgreSQL `psql`, MySQL `mysql` CLI subprocess |
| 상태 저장 | 브라우저 `localStorage`, 일부 `sessionStorage` |
| Optional LLM | `OPENAI_API_KEY`가 있을 때 OpenAI Chat Completions 호출 |
| 테스트 | `pytest`, Python compile check, `node --check` |

## 6. 핵심 파일 구조

```text
empsearch/
  web_agent.py
    로컬 웹 서버, API 라우팅, PostgreSQL/MySQL 조회, 자연어 질의 처리

  web_static/
    index.html / home.css / home.js
      OAFC 홈

    unstructured.html / unstructured.css / unstructured.js
      Data Integrator

    ontology.html / ontology.css / ontology.js
      Ontology Definer

    schema.html / schema.css / schema.js
      Schema Graph

    agent_builder.html / agent_builder.css / agent_builder.js
      Agent Builder

    agent_shop.html / agent_shop.css / agent_shop.js
      Agent Shop

    project.js
      프로젝트별 localStorage namespace 관리

db/
  migrations/
    PostgreSQL 테이블, View, Ontology, Query Planner 관련 SQL

  seeds/
    한국 철강회사 가나다 기준 임직원/조직/평가/급여 샘플 데이터

examples/
  ganada_unstructured/
    비정형 인사 문서 샘플 16종

docs/
  REBUILD_FROM_SCRATCH.md
  IMPLEMENTATION_SUMMARY_2026-07-03.md
  OAFC_CURRENT_IMPLEMENTATION_2026-07-08.md
  OAFC_DEVELOPMENT_SUMMARY_2026-07-09.md
```

## 7. Data Integrator 구현 내용

Data Integrator는 데이터 소스를 연결, 수집, 선택하고 Ontology Definer와 Agent Builder가 사용할 수 있도록 관리하는 영역이다.

### 7.1 정형 데이터

정형 데이터 영역은 다음 하위 기능으로 구성되어 있다.

- 연결 및 테스트
- 연결된 데이터 소스 관리
- 테이블 관리
- Data Catalog
- Cloud Storage
- Lakehouse Pipeline
- 스키마 그래프

### 7.2 연결 및 테스트

지원 UI:

- PostgreSQL
- MySQL
- MariaDB
- Oracle DB
- SQL Server
- SQLite

현재 실제 스키마 수집과 테이블 조회는 PostgreSQL, MySQL, MariaDB 중심으로 구현되어 있다. Oracle, SQL Server, SQLite는 연결 프로필 UI와 확장 구조를 제공한다.

구현 기능:

- DB 종류별 연결 폼 라벨/placeholder 자동 변경
- 연결 이름 자동 추천
- 연결 테스트
- DB 정보 보기
- 프로필 저장
- 저장된 DB 연결 관리
- 연결 히스토리 관리
- 연결된 DB 클릭 시 하단 테이블 정보 표시
- MySQL/MariaDB에서 테이블이 지정 DB에 없지만 같은 인스턴스의 다른 DB에서 유일하게 발견되면 자동 보정

관련 API:

| API | 역할 |
| --- | --- |
| `POST /api/database-info` | PostgreSQL/MySQL/MariaDB DB 정보 조회 |
| `POST /api/external-schema` | MySQL/MariaDB 외부 스키마 수집 |
| `GET /api/schema` | 기본 PostgreSQL 스키마 수집 |
| `GET /api/table-data` | 선택 테이블 row 조회 |

### 7.3 테이블 관리

구현 기능:

- 연결된 DB별 테이블 리스트 표시
- 연결 DB 체크 필터
- 체크된 DB의 모든 테이블을 상세 패널에서 확인
- Schema 옆에 Table 이름 표시
- 선택 테이블 상세 정보 표시
- fields, rows, relations, key fields 표시
- 작업 대상 테이블 선택
- Data Catalog와 Agent 사용 대상 연결
- Schema Graph를 Data Integrator 하부 메뉴로 포함

### 7.4 Data Catalog

Apache Iceberg 스타일 개념을 UI에 반영했다.

구현 기능:

- Snapshot Timeline
- Snapshot diff 개념
- Dataset Builder
- 선택 테이블 기반 Agent용 논리 Dataset 생성
- Snapshot, Dataset, Agent 사용 자산 표시

현재는 브라우저 localStorage 기반의 시뮬레이션 수준이며, 실제 Iceberg catalog, metadata file, manifest 연동은 다음 단계 과제이다.

### 7.5 Cloud Storage

지원 개념:

- AWS S3, EBS, FSx
- GCP Cloud Storage, Persistent Disk
- Azure Blob, Data Lake, Managed Disk
- S3 호환 Object Storage

구현 기능:

- Storage Provider 선택
- Object/Block/Filesystem 유형 선택
- Bucket, Container, Volume, Prefix, Region 입력
- Credential Alias 입력
- 연결 시뮬레이션
- Storage 프로필 저장/삭제
- Pipeline source로 지정

보안 원칙:

- 실제 secret/access key는 저장하지 않는다.
- UI에는 credential alias만 저장한다.
- 향후 Secret Manager, IAM Role, Workload Identity와 연결하는 구조로 확장한다.

### 7.6 Lakehouse Pipeline

Apache Iceberg 개념을 Data Integrator에 도입해 수집 기능을 Pipeline 관리 기능까지 확장했다.

지원 흐름:

- Source Discovery
- Extract / Transcribe / OCR
- Profile & Quality Check
- Iceberg Snapshot Commit
- Ontology Sync
- Agent Dataset Publish

지원 계층:

- Bronze Raw
- Silver Curated
- Gold Agent Dataset

Pipeline Source:

- RDB Tables
- Object Storage
- Block Storage
- 멀티모달 파일
- 정형 + 비정형 Hybrid

Schedule:

- Manual
- Hourly
- Daily
- Event Trigger

## 8. 비정형 데이터 통합

Data Integrator의 비정형 데이터 영역은 파일, URL, 음성, 영상, YouTube Transcript 등을 지식 정보로 변환하기 위한 기능이다.

지원 파일/데이터 유형:

- PDF
- CSV, TSV
- DOCX
- PPTX
- XLSX
- TXT
- Markdown
- HTML
- JSON
- RTF
- 로그 파일
- 음성 transcript
- YouTube transcript
- 영상/음성 파일의 text extraction placeholder

구현 기능:

- 여러 파일 동시 업로드
- 업로드 파일 분석
- 문서 내용 추출
- 문서 프로파일 생성
- 비정형 파일 목록 관리
- 선택 문서를 Ontology Definer에서 활용
- URL 분석
- YouTube URL transcript 분석 시도
- 비정형 문서 기반 의미 관계 후보 생성

가나다 기업 비정형 샘플:

```text
examples/ganada_unstructured/
  01_hr_terms_policy.md
  02_department_change_rules.txt
  03_org_alias_mapping.csv
  04_manager_role_guideline.md
  05_leave_and_status_notice.txt
  06_promotion_review_memo.md
  07_location_business_area_mapping.csv
  08_employee_data_dictionary.json
  09_hr_meeting_minutes.md
  10_email_thread_transfer_request.txt
  11_audio_transcript_manager_training.txt
  12_youtube_transcript_hr_onboarding.txt
  13_status_glossary.tsv
  14_hr_policy_notice.html
  15_transfer_announcement.rtf
  16_hr_helpdesk_chat.log
```

## 9. Ontology Definer 구현 내용

Ontology Definer는 Data Integrator에서 수집한 정형/비정형 데이터를 온톨로지화하고, 사람이 검토/수정/버전관리할 수 있는 영역이다.

최근 UX는 크게 세 단계로 단순화했다.

1. 온톨로지 생성
2. 온톨로지 편집
3. 온톨로지 버전관리

### 9.1 온톨로지 생성

구현 기능:

- 전체 자동 실행
- 선택 자동 실행
- 정형 테이블 선택
- 비정형 문서 선택
- 전체 선택/개별 선택
- 선택한 데이터 범위만 자동 생성
- 실행 진행 팝업 표시
- DB/schema/table/field 분석
- 필드 의미 자동 부여
- 값 매핑 자동 생성
- 관계 Ontology 자동 생성

관련 API:

| API | 역할 |
| --- | --- |
| `POST /api/ontology/automate` | 전체 자동 온톨로지 생성 |
| `POST /api/ontology/infer` | 특정 table 또는 전체 schema 기반 ontology infer |
| `GET /api/schema` | 자동 생성 대상 schema 조회 |
| `GET /api/table-data` | 샘플 값 분석 |

### 9.2 온톨로지 편집

구현 기능:

- 테이블/필드 선택
- 기존 정의 자동 로딩
- 정의가 없으면 폼 초기화
- 표시명 입력
- 설명 입력
- 동의어 입력
- 값 매핑 JSON 입력
- 리뷰 메모 입력
- 저장
- 삭제
- 자연어 SQL 생성에 적용

2026-07-09 점검 및 수정 내용:

- 테이블/필드 선택 변경 시 이전 필드의 값이 폼에 남아 있는 문제를 수정했다.
- 선택한 테이블/필드의 기존 온톨로지가 있으면 자동으로 불러오고, 없으면 새 입력 상태로 초기화한다.
- 리뷰 메모가 저장 후 설명 필드에 중복 누적되거나 편집 폼에서 사라지는 문제를 수정했다.
- 저장 시 `[리뷰 메모]` 블록을 분리해 설명과 리뷰 메모를 다시 각각의 입력 필드에 표시한다.
- 값 매핑 JSON 검증을 강화했다.
- 값 매핑은 배열 JSON이어야 하며, 각 항목은 객체이고 `value`를 가져야 한다.
- `synonyms`는 배열 또는 문자열만 허용한다.
- 잘못된 JSON 입력 시 저장 전 명확한 오류 메시지를 표시한다.

관련 주요 함수:

```text
empsearch/web_static/ontology.js
  splitDescriptionReviewNotes()
  descriptionWithReviewNotes()
  parseValueMappingsInput()
  currentOntologyFormPayload()
  fillForm()
  loadDefinitionForCurrentSelection()
```

### 9.3 의미 관계 분석

구현 기능:

- 정형 데이터와 비정형 문서 간 관계 후보 생성
- 관계 후보 리스트
- 의미 관계 그래프 패널
- 후보 클릭 시 그래프 중심 이동
- 오른쪽 상세 패널에서 근거 확인
- 승인/제외/선택 적용
- 승인된 관계를 초록색 edge로 표시
- 승인 대기/승인/제외 상태 필터
- 관계 유형 필터
- 데이터 소스별 그래프 보기
  - 정형 데이터 소스
  - DB 테이블
  - 비정형 데이터
- 그래프 확대 단계 버튼
- 관계선 클릭 시 상세 정보 표시
- 특정 신뢰도 이상 후보 자동 승인

관계 유형 예시:

- `value_of`
- `structured_fk`
- `maps_to_column`
- `alias_of`
- `policy_of`
- `evidence_for`

### 9.4 온톨로지 버전관리

구현 기능:

- Ontology 파일 내보내기
- Ontology 파일 불러오기
- Snapshot 형태 버전 저장
- 버전 목록
- 버전 복원
- 전체 삭제
- 테이블 단위 삭제
- 필드 단위 삭제
- git tree 스타일의 버전 목록 UX

관련 API:

| API | 역할 |
| --- | --- |
| `GET /api/ontology` | Ontology 조회 |
| `POST /api/ontology` | Ontology 저장 |
| `DELETE /api/ontology` | 단건/범위 삭제 |
| `POST /api/ontology/import` | Ontology JSON import |
| `POST /api/ontology/bulk-delete` | 전체/테이블/필드 bulk delete |

## 10. Schema Graph 구현 내용

Schema Graph는 DB/schema/table/field 관계를 시각적으로 확인하고 테이블 데이터를 조회하는 화면이다.

구현 기능:

- 테이블 관계도 표시
- FK 관계 edge 표시
- 테이블 카드 내 field 목록 표시
- DB/schema별 색상 구분
- `ganada` schema 구분
- zoom in/out/reset
- 그래프 크게 3단계 조정
- 관계 정렬
- star layout
- 테이블 드래그 이동
- 위치 저장
- 위치 초기화
- 심플 보기
- 테이블 더블클릭 시 필드 숨김/표시
- 좌우 패널 접기/펼치기
- 패널 크기 조정
- 하단 테이블 데이터 조회 패널
- 하단 패널 세로 크기 조정
- 테이블 선택 시 중심 이동 및 하이라이트
- 관계선이 잘 보이도록 정렬 기능
- Ontology Definer로 선택 테이블 범위 전달

현재 `/schema`는 독립 경로로도 열 수 있고, Data Integrator의 하위 메뉴 iframe으로도 볼 수 있다.

## 11. Agent Builder 구현 내용

Agent Builder는 Ontology Definer에서 작성한 정보와 관계를 활용해 Agent를 설계하고 테스트하고 Agent Shop에 등록하는 영역이다.

### 11.1 Agent 생성 시나리오

Agent Builder는 다음 세 가지 생성 시나리오를 지원한다.

| 방식 | UI 이름 | 설명 |
| --- | --- | --- |
| 대화 기반 | Chat Studio | 사용자가 만들고 싶은 Agent를 자연어로 설명하면 데이터/Ontology 자산을 추천 |
| 시나리오 기반 | Scenario Studio | 연결된 데이터와 Ontology를 분석해 가능한 Agent 아이디어를 제안 |
| 수동 구성 | Manual Studio | 정형/비정형/생성 데이터/Ontology/관계를 직접 선택해 Agent 생성 |

추가로 다음 고급 설계 기능이 구현되어 있다.

- Flow Studio
- Production Agent Factory
- Discover
- Design Canvas
- Runtime Configure
- Quality Gates
- Deployment Pipeline
- Operations
- Governance

### 11.2 Agent 설계 기능

구현 기능:

- Agent Catalog
- 새 Agent 생성
- 자동 구성
- Chat Studio 아이디어 분석
- 추천 자산 표시
- Capability Map
- Agent Critic
- Agent Canvas
- 데이터 소스 선택
- 사용 도구 선택
- 운영 규칙 입력
- System Prompt 생성
- Prompt / Test Harness
- 테스트 샘플 문구 선택
- 테스트 결과 표시
- JSON 내보내기
- 생성완료 클릭 시 Agent Shop에 등록

지원 Agent System 유형:

- Simple Agent
- Tool-Using Agent
- Multi-Agent System
- Workflow Agent

지원 도구 예시:

- 자연어 SQL 생성
- Ontology Query Planner
- 테이블 리포트
- 근거 그래프
- 데이터 구조 탐색

### 11.3 Agent Flow Builder

Airflow DAG 스타일의 Agent Flow Builder 개념을 추가했다.

구현된 개념:

- 노드 팔레트
- Agent Flow Canvas
- Flow 속성
- Flow로 Agent 초안 만들기
- 단계 기반 Agent 설계
- 멀티 Agent workflow 설계 방향

## 12. Agent Shop 구현 내용

Agent Shop은 Agent Builder에서 생성한 Agent를 실행하고 관리하는 영역이다.

구현 기능:

- Agent Catalog 표시
- Agent 선택
- Agent 실행
- 질문 입력
- 결과 테이블 표시
- 생성 SQL 표시
- 사용한 데이터/Ontology/지식 근거 표시
- 전체 데이터 구조 왼쪽 패널 표시
- Agent 상세
- 데이터 소스 표시
- 사용 도구 표시
- 운영 규칙 표시
- Agent 삭제
- Agent 백업
- Agent 복원
- Agent 생성 진입

Agent Builder에서 `생성완료`를 클릭하면 Agent 정의가 localStorage catalog에 저장되고 Agent Shop에서 사용할 수 있다.

## 13. 자연어 질의와 챗봇 기능

자연어 검색은 `/api/agent`가 처리한다.

지원 예시:

```text
광양 근무자 중 여성 18년 이상 근무하고 manager인 사람만 뽑아줘
광양 근무자 중 여성 18년 이상 근무하고 manager가 아닌 사람만 뽑아줘
포항에 근무하는 15년차 이상 여성 관리자를 찾아줘
가나다 표준조직 2026 생산 조직을 보여줘
STEEL-00001 이력을 보여줘
```

구현 기능:

- 근무지 조건 인식
- 성별 조건 인식
- 근속연수 조건 인식
- manager / manager가 아닌 조건 분리
- team_lead와 manager 혼동 방지
- 조직/표준부서 검색
- 직원 이력 조회
- 온톨로지 기반 값 매핑 조회
- 복합 검색 의도 탐지
- 결과 테이블 반환
- 생성 SQL 표시
- 사용한 데이터와 Ontology 근거 반환

## 14. DB와 샘플 데이터

### 14.1 PostgreSQL

주요 테이블/뷰:

- `employees`
- `employee_information`
- `departments`
- `department_management_information`
- `employee_assignments`
- `employee_department_change_history`
- `employee_change_history`
- `employee_work_location_history`
- `work_locations`
- `job_positions`
- `org_structure`
- `ontology_concepts`
- `ontology_concept_columns`
- `ontology_relationships`
- `ontology_query_patterns`
- `ontology_definitions`

주요 설계 원칙:

- 직원 기본정보와 이력성 데이터를 분리한다.
- 직원 기본정보에는 현재 부서 참조를 둔다.
- 실제 부서 이동 기간/변경 내역은 부서변경히스토리에서 조회한다.
- 부서변경히스토리는 `department_name`, `previous_department_name`을 포함한다.
- 표준조직정보 `org_structure`는 가나다 schema로 분리한다.
- 자연어 SQL 생성을 위해 Ontology 정의와 관계 테이블을 둔다.

### 14.2 MySQL

구현/생성된 데이터 영역:

- `employee_salary_db`
  - 급여
  - 월급
  - 보상 지급
  - 10년간 월급 데이터
- `employee_evaluation_db`
  - 평가 주기
  - 평가 결과
  - 평가 점수

MySQL 테이블 조회 개선:

- 사용자가 `employee_salary_db.evaluation_scores`처럼 잘못된 DB를 지정해도, 같은 MySQL 인스턴스 내에서 `evaluation_scores`가 유일하게 발견되면 실제 DB인 `employee_evaluation_db`로 자동 보정한다.

### 14.3 Seed와 Migration

주요 migration:

```text
001_employee_lifecycle.sql
002_century_employee_history.sql
003_standard_department_management_alias.sql
004_steel_company_locations.sql
005_employee_demographics_and_report_view.sql
006_employee_and_department_information_tables.sql
007_ontology_definitions.sql
008_ontology_unique_nulls_not_distinct.sql
009_employee_department_history_split.sql
010_department_history_previous_department.sql
011_ganada_org_structure.sql
012_move_org_structure_to_ganada_schema.sql
013_expand_steel_employees_to_50000.sql
014_ontology_query_planner.sql
```

주요 seed:

```text
001_sample_employees.sql
002_century_employee_history.sql
003_korean_steel_company.sql
004_rebuild_10000_from_org_structure.sql
005_rebuild_mysql_eval_salary_10000.sql
```

현재 데이터는 org_structure를 보존하면서 나머지 데이터를 1만명 기준으로 재생성한 상태이다.

## 15. 프로젝트 분리와 localStorage 저장 구조

여러 사용 목적별로 독립 프로젝트를 만들 수 있도록 프로젝트 관리 기능을 추가했다.

핵심 키:

```text
empsearch.projects.v1
empsearch.currentProjectId.v1
empsearch.project.{projectId}.*
```

주요 project-scoped localStorage key:

```text
empsearch.dataIntegration.documents.v1
empsearch.dataIntegration.selection.v1
empsearch.dataManager.dbProfiles.v1
empsearch.dataManager.dbConnectionHistory.v1
empsearch.dataManager.tableUsage.v1
empsearch.dataManager.schemaSnapshots.v1
empsearch.dataManager.datasets.v1
empsearch.dataManager.storageProfiles.v1
empsearch.dataManager.pipelines.v1
empsearch.ontology.versions.v1
empsearch.ontology.semanticRelations.v1
empsearch.agentBuilder.catalog.v1
empsearch.schema.savedLayout.v1
```

프로젝트별 namespace를 통해 같은 브라우저에서도 목적별 Data Integrator/Ontology/Agent Catalog 상태를 분리할 수 있다.

## 16. Backend API 목록

| Method | Path | 역할 |
| --- | --- | --- |
| `GET` | `/api/summary` | 직원/부서/근무지 요약 |
| `GET` | `/api/schema` | PostgreSQL schema/table/field/relation 조회 |
| `GET` | `/api/ontology` | Ontology 정의 조회 |
| `GET` | `/api/table-data` | 테이블 데이터 조회 |
| `GET` | `/api/employees` | 직원 검색 |
| `GET` | `/api/timeline/{employee_no}` | 직원 이력 조회 |
| `POST` | `/api/agent` | 자연어 Agent 질의 |
| `POST` | `/api/unstructured/upload` | 비정형 파일 업로드/분석 |
| `POST` | `/api/unstructured/url` | URL/YouTube 등 분석 |
| `POST` | `/api/ontology` | Ontology 저장 |
| `DELETE` | `/api/ontology` | Ontology 삭제 |
| `POST` | `/api/ontology/import` | Ontology 파일 import |
| `POST` | `/api/ontology/bulk-delete` | Ontology 전체/부분 삭제 |
| `POST` | `/api/ontology/infer` | Ontology 자동 유추 |
| `POST` | `/api/ontology/automate` | Ontology 전체 자동 실행 |
| `POST` | `/api/generated-metadata/reset` | 생성 메타데이터 초기화 |
| `POST` | `/api/external-schema` | MySQL/MariaDB schema 수집 |
| `POST` | `/api/database-info` | DB 정보 조회 |

## 17. 실행 방법

기본 실행:

```bash
python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765
```

스크립트 실행:

```bash
scripts/run_oafc_server.sh
```

브라우저 접속:

```text
http://127.0.0.1:8765
```

## 18. 테스트와 검증

Python 테스트:

```bash
python3 -m pytest -q
```

현재 확인 결과:

```text
7 passed
```

프론트엔드 JavaScript 문법 검사:

```bash
for f in empsearch/web_static/*.js; do node --check "$f"; done
```

최근 개별 검증:

```bash
node --check empsearch/web_static/ontology.js
python3 -m py_compile empsearch/web_agent.py
python3 -m pytest -q
```

최근 API 검증:

- `/api/summary` 정상
- `/api/schema` 정상
- `/api/ontology` 정상
- Ontology manual save/delete 정상
- Ontology bulk delete/import 관련 기능 점검 및 수정
- Ontology edit form에서 수동 입력값 저장/복원 정상

## 19. 오늘까지의 주요 수정 사항

2026-07-09 기준 주요 변경:

- 전체 솔루션 이름을 `OAFC: Ontology Agent Factory Creator`로 정리
- 메뉴/타이틀에서 EmpSearch 노출 제거
- Data Manager를 Data Integrator로 정리
- Ontology Manager를 Ontology Definer로 정리
- Super Agent Builder를 Agent Builder로 정리
- AgentFactory를 Agent Shop으로 정리
- `/superagent`, `/speragent` 레거시 경로 제거
- Agent Builder 파일명을 `agent_builder.*`로 정리
- Agent Shop에서 Agent Catalog 관리 기능 강화
- Data Integrator의 연결 및 테스트/연결된 데이터 소스 관리 UX 분리
- 테이블 관리에서 연결 DB별 테이블 표시 개선
- Schema Graph를 Data Integrator 하부 메뉴로 포함
- Ontology Definer를 생성/편집/버전관리 중심으로 단순화
- Ontology 자동 실행 범위 선택 기능 추가
- Ontology 편집 단계 수동 입력/수정 흐름 점검 및 수정
- Ontology 값 매핑 JSON 검증 강화
- Ontology 리뷰 메모 저장/복원 개선
- MySQL 테이블 DB 자동 보정 로직 추가
- README를 현재 OAFC 기준으로 정리
- 개발 의존성 `requirements-dev.txt` 추가
- 서버 실행 스크립트 `scripts/run_oafc_server.sh` 추가

## 20. 현재 한계와 다음 단계

현재 구현은 로컬 PoC에서 Production 설계 방향으로 확장 중인 상태이다. 다음 항목은 향후 고도화 대상이다.

### 20.1 Backend와 저장소

- localStorage 중심 상태 저장을 서버 DB 기반으로 전환
- 프로젝트, Agent Catalog, Data Catalog, Pipeline, Ontology Version을 서버 persistence로 이전
- 사용자/권한/감사로그 추가
- 파일 업로드 결과를 실제 object storage 또는 local managed storage에 저장

### 20.2 Data Integrator

- Oracle, SQL Server, SQLite 실제 driver 연결
- Cloud Storage 실제 SDK 연동
- Iceberg catalog 실제 연동
- Pipeline 실행 엔진 도입
- 데이터 품질 검사 규칙 추가
- schema drift 감지와 알림

### 20.3 Ontology Definer

- LLM 기반 의미 자동 생성 정확도 향상
- Embedding 기반 필드/문서 관계 추천
- 승인된 semantic relation을 DB에 영구 저장
- 관계 변경 이력과 reviewer workflow 추가
- ontology quality score와 coverage dashboard 고도화

### 20.4 Agent Builder와 Agent Shop

- Agent 정의를 서버 DB에 저장
- Agent별 권한, 버전, 배포 상태 관리
- 실제 multi-agent runtime 연결
- Workflow 실행 로그와 재실행 기능
- BI Graph, evidence graph, data lineage를 Agent 결과와 더 강하게 연결

### 20.5 운영

- 통합 테스트 확대
- 브라우저 E2E 테스트 도입
- DB fixture 자동화
- Docker Compose 또는 launchd 기반 실행 구성
- macOS 앱 번들명을 OAFC 기준으로 정리

## 21. 재현 시 참고 순서

처음부터 다시 구성할 때는 다음 순서가 가장 안정적이다.

1. PostgreSQL과 MySQL/MariaDB 준비
2. `db/migrations` SQL 적용
3. `db/seeds` SQL 적용
4. 서버 실행
5. `/data-manager`에서 DB 연결 확인
6. 테이블 관리에서 사용할 DB/table 선택
7. `/ontology`에서 자동 실행으로 Ontology 생성
8. 온톨로지 편집에서 주요 테이블/필드 의미 검토
9. 의미 관계 분석에서 관계 후보 승인/제외
10. `/agent-builder`에서 Agent 생성
11. `/agent-shop`에서 Agent 실행과 SQL/근거 확인

## 22. 관련 문서

```text
README.md
docs/REBUILD_FROM_SCRATCH.md
docs/IMPLEMENTATION_SUMMARY_2026-07-03.md
docs/OAFC_CURRENT_IMPLEMENTATION_2026-07-08.md
docs/OAFC_DEVELOPMENT_SUMMARY_2026-07-09.md
```

이 문서가 2026-07-09 기준 최신 통합 현황 문서이다.
