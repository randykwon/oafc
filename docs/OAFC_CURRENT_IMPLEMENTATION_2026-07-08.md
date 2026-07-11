# O-A-F-C 현재 구현 통합 정리

작성일: 2026-07-08  
프로젝트 경로: `/Users/yongsunk/Documents/EmpSearch`  
실행 URL: `http://127.0.0.1:8765`  
솔루션 이름: `O-A-F-C: Ontology Agent Factory Creator`

이 문서는 현재까지 구현된 O-A-F-C 솔루션을 한 번에 이해하고 다시 만들 수 있도록 기능, 설계, 데이터 구조, 화면, 저장소, 테스트 하네스, 남은 과제를 정리한 최신 통합본이다.

## 1. 솔루션 목적

O-A-F-C는 정형 데이터, 비정형 데이터, 멀티모달 데이터, Ontology, 의미 관계 정보를 통합해 업무 Agent를 만들고 테스트하는 로컬 웹 솔루션이다.

초기 목표는 임직원/부서/이력 데이터를 자연어로 조회하는 챗봇이었고, 현재는 다음 범위까지 확장되었다.

- RDB, Cloud Storage, 파일/URL, 이미지/음성/영상 데이터 수집
- Apache Iceberg 개념의 Data Catalog, Snapshot, Dataset, Pipeline 관리
- 정형/비정형 데이터를 통합한 Ontology 자동 생성, 리뷰, 편집, 버전 관리
- 정형/비정형 간 의미 관계 자동 분석, 승인/제외, 그래프 검토
- Ontology와 관계 정보를 기반으로 Agent를 설계, 테스트, 생성
- 생성된 Agent를 Agent Shop에서 관리하고 실행

## 2. 주요 웹 경로

| 경로 | 화면 | 역할 |
| --- | --- | --- |
| `/` | 홈 | O-A-F-C 메인 메뉴 |
| `/data-manager` | Data Integrator | 데이터 연결, 수집, 파일 분석, Cloud Storage, Lakehouse Pipeline |
| `/ontology` | Ontology Definer | 의미 Ontology, 관계 Ontology, 자동화, 버전/관리 |
| `/agent-builder` | Agent Builder | Agent 설계, 테스트, 생성 |
| `/agent-shop` | Agent Shop | 생성된 Agent 카탈로그, 실행, 삭제, 백업, 복원 |
| `/schema` | Schema Graph | DB 테이블/필드/관계 그래프 |
| `/chatbots` 또는 기존 호환 경로 | 챗봇 | 임직원 검색 챗봇 호환 기능 |
| `/unstructured`, `/information-center`, `/data-integration` | 호환 경로 | Data Integrator로 라우팅 |

## 3. 기술 스택

- Backend: Python 3, `http.server.ThreadingHTTPServer`
- Database: PostgreSQL, MySQL 외부 스키마 조회 일부 지원
- Frontend: HTML, CSS, Vanilla JavaScript
- Storage: 브라우저 `localStorage` 기반 프로젝트별 상태 저장
- Optional LLM: `OPENAI_API_KEY`가 있을 때 OpenAI 기반 요약 가능
- 실행 진입점: `python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765`

## 4. 핵심 파일 구조

```text
empsearch/
  web_agent.py                 # 로컬 웹 서버, API, 정적 파일 라우팅
  web_static/
    index.html                 # 홈
    app.css / app.js           # 챗봇/공통 앱 일부
    home.css / home.js         # 홈 프로젝트 메트릭
    project.js                 # 프로젝트별 localStorage namespace
    unstructured.html          # Data Integrator
    unstructured.css
    unstructured.js
    ontology.html              # Ontology Definer
    ontology.css
    ontology.js
    schema.html                # Schema Graph
    schema.css
    schema.js
    superagent.html            # Agent Builder
    superagent.css
    superagent.js
    agent_shop.html            # Agent Shop
    agent_shop.css
    agent_shop.js

db/
  migrations/                  # PostgreSQL 테이블, View, Ontology 관련 마이그레이션
  seeds/                       # 샘플 데이터

examples/
  ganada_unstructured/         # 가나다 기업용 비정형 샘플 문서

docs/
  REBUILD_FROM_SCRATCH.md
  IMPLEMENTATION_SUMMARY_2026-07-03.md
  OAFC_CURRENT_IMPLEMENTATION_2026-07-08.md
```

## 5. 이름 변경 이력과 현재 명칭

초기 명칭과 현재 명칭이 다르므로 코드/문서/경로를 볼 때 주의한다.

| 과거 명칭 | 현재 명칭 |
| --- | --- |
| EmpSearch | O-A-F-C |
| Data Manager | Data Integrator |
| Ontology Manager | Ontology Definer |
| SuperAgent Builder | Agent Builder |
| AgentFactory | Agent Shop |
| 직원 이력 챗봇 | 챗봇 |

현재 상단 메뉴와 타이틀에서는 EmpSearch를 제거하고 O-A-F-C 중심으로 정리했다. 일부 README와 오래된 문서에는 초기 이름이 남아 있다.

## 6. Data Integrator

Data Integrator는 모든 데이터 소스를 수집하고 Agent/Ontology가 사용할 수 있게 관리하는 영역이다.

### 6.1 정형 데이터 기능

정형 데이터 영역은 다음 하위 메뉴로 구성된다.

- 연결 및 테스트
- 연결된 데이터 소스 관리
- 테이블 관리
- Data Catalog
- Cloud Storage
- Lakehouse Pipeline
- 스키마 그래프

### 6.2 RDB 연결 및 테스트

지원 UI:

- PostgreSQL
- Oracle DB
- MySQL
- MariaDB
- SQL Server
- SQLite

현재 실제 스키마 수집은 PostgreSQL과 MySQL/MariaDB 중심으로 구현되어 있다. 그 외 DB는 연결 프로필 UX와 향후 서버 드라이버 연동을 위한 입력 구조를 제공한다.

주요 기능:

- DB 종류별 기본 포트/라벨/placeholder 자동 변경
- 연결 테스트
- DB 정보 보기
- 프로필 저장
- 저장된 연결 리스트
- 연결 히스토리
- 연결된 DB를 클릭해 테이블 정보 가져오기

관련 localStorage key:

```text
empsearch.dataManager.dbProfiles.v1
empsearch.dataManager.dbConnectionHistory.v1
empsearch.dataManager.schemaSnapshots.v1
empsearch.dataManager.tableUsage.v1
```

### 6.3 테이블 관리

기능:

- 연결된 DB/schema별 테이블 리스트 표시
- DB 체크 필터
- 테이블 사용/비사용 관리
- 선택 테이블 상세 표시
- 필드, PK, FK, 관계, rows 추정치 표시
- 선택 테이블을 작업 대상으로 지정
- 스키마 그래프 하위 메뉴와 연동

테이블 상세 패널은 체크된 DB의 전체 테이블 목록과 선택 테이블의 필드/관계 정보를 함께 보여준다.

### 6.4 Data Catalog

Iceberg 스타일의 카탈로그 개념을 도입했다.

구현된 기능:

- Snapshot Timeline
- Snapshot diff
- Dataset Builder
- Agent가 사용할 Gold Dataset 생성
- Catalog Metrics
- Storage/Pipeline 지표 연결

현재는 브라우저 localStorage에 저장되는 시뮬레이션 레벨이며, 실제 Iceberg metadata file, manifest, catalog DB 연동은 다음 단계 과제다.

관련 localStorage key:

```text
empsearch.dataManager.datasets.v1
```

### 6.5 Cloud Storage

2026-07-08에 추가된 기능이다.

지원 UI:

- AWS: S3, EBS, FSx
- GCP: Cloud Storage, Persistent Disk
- Azure: Blob, Data Lake, Managed Disk
- S3 호환: MinIO, Ceph 등

지원 개념:

- Object Storage
- Block Storage
- Filesystem / Mount

입력 필드:

- 연결 이름
- Storage 유형
- Bucket / Container / Volume
- Prefix / Path
- Region / Location
- Credential Alias

보안 원칙:

- 실제 access key/secret key는 저장하지 않는다.
- credential alias만 저장한다.
- 향후 backend connector에서 alias를 실제 secret manager, IAM role, workload identity와 연결한다.

기능:

- 연결 시뮬레이션
- Storage 프로필 저장
- Storage 프로필 삭제
- Storage 프로필을 Pipeline 소스로 지정

관련 localStorage key:

```text
empsearch.dataManager.storageProfiles.v1
```

### 6.6 Lakehouse Pipeline

2026-07-08에 추가된 기능이다.

Apache Iceberg 개념을 Data Integrator에 도입해 데이터 수집 기능을 Data Pipeline 관리 기능으로 확장했다.

Pipeline 구성:

- Source Type
  - RDB Tables
  - Object Storage
  - Block Storage
  - 멀티모달 파일
  - 정형 + 비정형 Hybrid
- Iceberg Layer
  - Bronze Raw
  - Silver Curated
  - Gold Agent Dataset
- Schedule
  - Manual
  - Hourly
  - Daily
  - Event Trigger
- Steps
  - Source Discovery
  - Extract / Transcribe / OCR
  - Profile & Quality Check
  - Iceberg Snapshot Commit
  - Ontology Sync
  - Agent Dataset Publish

기능:

- Pipeline 생성
- Pipeline 삭제
- Pipeline 실행 시뮬레이션
- Iceberg snapshot id 생성
- 실행 로그 표시
- Data Catalog, Storage, 멀티모달 자산 카운트 연결

관련 localStorage key:

```text
empsearch.dataManager.pipelines.v1
```

현재 구현은 UI/메타데이터/시뮬레이션 레벨이다. 실제 Production 구현에서는 Spark, Flink, Airflow, Dagster, Iceberg REST Catalog, Nessie, Hive Metastore, Glue Catalog 등의 연동이 필요하다.

### 6.7 비정형 데이터 통합

기능:

- 파일 다중 업로드
- URL 분석
- YouTube 또는 웹 URL 입력
- 파일 분석
- 파일분류
- 전체 결합 사용
- 선택 문서 사용
- 분석 내용/파일 내용 표시

지원 확장자:

```text
.pdf, .csv, .tsv, .doc, .docx, .rtf, .odt, .txt, .md, .json,
.html, .htm, .xlsx, .pptx,
.png, .jpg, .jpeg, .gif, .webp, .bmp, .tiff, .heic,
.mp3, .m4a, .wav, .aac, .flac, .ogg,
.mp4, .mov, .mkv, .webm, .m4v
```

### 6.8 멀티모달 분석

2026-07-08에 추가된 기능이다.

대상:

- 이미지
- 음성
- 영상

표시 정보:

- 자산 수
- 파일 유형
- 파일 크기
- 추출 텍스트 길이
- 주요 용어
- Pipeline 후보

멀티모달 처리 힌트:

- 이미지: OCR, 객체/장면 태깅, 이미지 설명 생성
- 음성: 음성 전사, 화자/키워드 추출, 요약
- 영상: 장면 분할, 음성 전사, 프레임 OCR, 객체 태깅

현재 실제 OCR/STT/비전 모델 호출은 구현되지 않았고, Data Integrator에서 관리 가능한 자산/파이프라인 후보로 정보화하는 구조를 구현했다.

## 7. Ontology Definer

Ontology Definer는 Data Integrator에서 모은 정형/비정형 데이터를 Ontology화하고, 필요시 사람이 검토/수정/승인하는 영역이다.

### 7.1 현재 메뉴 구조

상단 탭:

- Dashboard
- 의미 Ontology
- 관계 Ontology
- 버전/관리

기능을 크게 두 축으로 분리했다.

- 의미 Ontology: 테이블/필드/값 의미 정의
- 관계 Ontology: 정형/비정형 데이터 간 의미 관계 정의

### 7.2 의미 Ontology

구성:

- 테이블 / 필드 탐색
- 정의 목록
- Ontology 초안 / 편집
- 비정형 데이터 온톨로지 작성
- AI 의미 리뷰

주요 기능:

- 테이블/필드 선택
- 자동 작성
- 선택 자동 유추
- 전체 자동 유추 / 저장
- 전체 자동 작성 / 저장
- 동의어 입력
- 값 매핑 JSON 입력
- 자연어 SQL 생성 적용 여부
- 리뷰 메모 / 추가 정보 입력

### 7.3 AI 의미 리뷰

2026-07-08에 강화한 기능이다.

목적:

- 각 테이블과 필드의 의미를 자동으로 부여한다.
- 신뢰도와 근거를 표시한다.
- 사람이 리뷰하면서 재정의하고 추가 정보를 쉽게 입력한다.

자동 제안 근거:

- 테이블명
- 필드명
- 데이터 타입
- PK/FK 여부
- 테이블/컬럼 comment
- 기존 Ontology 정의
- 업무 도메인 키워드
- 기본 값 매핑 후보

지원되는 의미 힌트 예시:

- 임직원 주체 데이터
- 조직/부서 기준 데이터
- 변경 이력 데이터
- 보상/급여 데이터
- 평가/성과 데이터
- 직원 식별자
- 부서/소속 조직
- 근무지/사업장
- 입사/퇴사 시점
- 관리자/리더 구분
- 직무/역할 정보
- 상태 분류
- 유형/분류 코드

리뷰 액션:

- 편집 폼에 반영
- 승인 저장
- 제외

리뷰 메모는 저장 시 description 하단의 `[리뷰 메모]` 섹션으로 합쳐진다.

### 7.4 값 매핑 강화

기본 코드성 필드는 샘플 데이터가 없어도 값 매핑을 제안한다.

예:

- `gender`
  - `female`: 여성, 여자, female
  - `male`: 남성, 남자, male
- `status`
  - `active`: 재직, 재직중, 근무중
  - `on_leave`: 휴직, 휴직중
  - `resigned`: 퇴사, 퇴직
- `management_level`
  - `manager`: manager, 매니저, 관리자
  - `team_lead`: 팀리드, 파트장, 리더
  - `executive`: 임원
  - `individual_contributor`: 실무자, 일반 직원, 비관리자
- boolean
  - `true`: 예, 해당, true, Y
  - `false`: 아니오, 미해당, false, N

### 7.5 관계 Ontology

구성:

- 의미 관계 분석기
- 관계 후보 리스트
- 관계 그래프
- 관계 상세
- 필터와 자동 승인

기능:

- 정형 DB와 비정형 문서 사이의 관계 후보 자동 생성
- 정형 컬럼 간 semantic relationship 후보 생성
- 관계 유형 필터
- 상태 필터
  - 전체
  - 승인
  - 승인대기
  - 제외
- 검색 필터
- 신뢰도 기준 자동 승인
- 후보 클릭 시 관계 그래프 중심 이동
- edge 클릭 시 상세 표시
- 승인 관계는 초록색 edge로 표시

그래프 보기:

- 관계 중심
- 정형데이터소스
- DB 테이블
- 비정형데이터

그래프 크기:

- 그래프 1단계
- 그래프 2단계
- 그래프 3단계

현재 한 개 버튼으로 단계 순환한다.

### 7.6 버전/관리

기능:

- Ontology 파일 export
- Ontology 파일 import
- 버전 생성
- 버전 복원
- 버전 삭제
- 선택 정의 삭제
- 선택 범위 삭제
- 테이블 Ontology 삭제
- 전체 Ontology 삭제

관련 localStorage key:

```text
empsearch.ontology.versions.v1
empsearch.ontology.semanticRelations.v1
```

## 8. Schema Graph

Schema Graph는 DB 테이블, 필드, 관계를 그래픽으로 탐색하는 화면이다.

기능:

- 테이블 관계도 표시
- 확대/축소
- 관계 정렬
- star 형태 정렬
- 양옆 패널 접기/펼치기
- 패널 가로 크기 조정
- 하단 테이블 데이터 패널
- 하단 패널 상하 크기 조정
- 테이블 드래그 이동
- 위치 저장
- 심플 보기
- 더블클릭으로 테이블 필드 접기/펼치기
- 심플 버튼으로 테이블 이름과 관계만 표시
- 테이블 목록에서 클릭 시 그래프의 해당 테이블 하이라이트 및 중심 이동
- Ontology Definer 연결 링크

Data Integrator의 하위 메뉴에서도 iframe으로 표시된다.

## 9. Agent Builder

Agent Builder는 Ontology Definer에서 만든 의미 정의와 관계 정보를 이용해 Agent를 설계, 테스트, 생성하는 영역이다.

### 9.1 주요 설계 방향

기존 단순 Agent 생성에서 다음 수준으로 확장했다.

- 단순 Agent부터 복잡한 workflow/multi-agent 설계까지 지원
- Ontology 기반 추천
- LLM Chatbot 형태 설계
- 데이터/온톨로지 선택 기반 수동 설계
- Production Agent Factory 관점의 품질/배포/운영 설계

### 9.2 Agent 생성 시나리오

세 가지 생성 모드:

1. Chat Studio
   - LLM Chatbot과 대화로 Agent 아이디어와 설계 생성
2. Scenario Studio
   - 데이터와 Ontology information 기반 추천 시나리오에서 생성
3. Zero Studio
   - 데이터, 정보, Ontology 데이터를 수동 선택해 Zero부터 생성

추가 개념:

- Top-down
- Bottom-up
- Meet in the middle

### 9.3 Agent Flow Builder

Airflow 기반 workflow 개념을 도입한 Agent Flow Builder를 계획/구현했다.

구성 요소 예시:

- input_parser
- ontology_mapper
- natural_language_sql
- table_report
- document_retriever
- evidence_graph
- report_generator
- evaluator

### 9.4 Prompt / Test Harness

기능:

- 테스트 샘플 문구 선택
- 선택 샘플을 테스트 입력에 적용
- 테스트 실행
- 테스트 결과 확인
- 테스트 이력
- 생성된 SQL/프롬프트/근거 표시

### 9.5 Agent 생성 완료

Agent Builder에서 생성 완료를 클릭하면 Agent Shop에 Agent가 추가된다.

Agent는 localStorage에 저장된다.

관련 localStorage key:

```text
empsearch.agentShop.agents.v1
```

프로젝트별 key namespace는 `project.js`의 `window.EmpProjects.key(...)`를 통해 분리된다.

## 10. Agent Shop

Agent Shop은 생성된 Agent를 보고 관리하고 실행하는 화면이다.

기능:

- Agent Catalog
- Agent 실행
- Agent 삭제
- Agent 백업
- Agent 복원
- Agent 생성 화면으로 이동
- 기본 임직원 검색 Agent 표시
- 생성된 Agent 카드 UI 개선

Agent Builder에서 생성한 Agent가 Agent Catalog에 포함되지 않던 문제를 수정하고, Catalog 관리 기능을 추가했다.

## 11. 챗봇과 자연어 SQL

초기 임직원 검색 챗봇은 다음 기능을 지원한다.

- 자연어 검색
- 테이블 리포트 출력
- 검색 결과 최신 결과 상단 배치
- 생성된 SQL을 답변 하단에 표시
- SQL 생성 시 Ontology 정보 활용
- 여러 테이블을 참조한 자연어 검색 확장
- 결과로 사용된 테이블, Ontology, 지식 정보를 그래픽하게 보여주는 방향으로 확장

중요 수정:

- `manager가 아닌 사람` 질의에서 manager가 포함되는 문제 수정
- `manager인 사람` 질의에서 `team_lead`가 같이 나오는 문제 수정
- manager/team_lead/individual_contributor를 정확히 구분하도록 자연어 조건 파싱 개선

## 12. 데이터베이스와 샘플 데이터

### 12.1 PostgreSQL

초기 구현:

- 직원 관리 DB
- 직원 기본정보
- 부서 정보
- 직원 배치 이력
- 직원 변경 이력
- 부서 변경 히스토리
- 표준 부서 관리 테이블
- Ontology 정의 테이블

샘플 데이터:

- 초기 500건
- 이후 한국 철강회사 기준 샘플
- 서울, 포항, 광양 근무지 중심
- 100년 회사 이력
- 1년에 한 번 이상 변경 이력
- 직원 5만명까지 확장한 샘플
- 이후 가나다 기업 기준 1만명 재생성 요청 처리

### 12.2 직원/부서 테이블 분리

직원 기본정보와 부서변경히스토리를 분리했다.

요구사항:

- 직원정보에는 현재 부서 정보가 있어야 한다.
- 부서 변경 이력은 별도 테이블에서 조회한다.
- 부서변경히스토리 테이블은 부서이름과 변경이전 부서이름 컬럼으로 구성되어야 한다.

핵심 테이블:

- `employee_information`
- `department_management_information`
- `employee_department_change_history`

### 12.3 가나다 org_structure

사용자 제공 SQL 기반 표준조직 테이블:

```sql
CREATE TABLE ORG_STRUCTURE (
    표준부서코드 VARCHAR(10),
    표준부서_2026 VARCHAR(50),
    운영종료제외_표준부서명 VARCHAR(100),
    년도구분 VARCHAR(10),
    부서명 VARCHAR(100),
    고유코드_년도부서명 VARCHAR(50),
    본부단위건제 VARCHAR(20),
    본부단위 VARCHAR(50),
    실담당단위건제 VARCHAR(20),
    실담당단위 VARCHAR(50),
    그룹단위건제 VARCHAR(20),
    그룹단위 VARCHAR(50),
    공장섹션단위건제 VARCHAR(20),
    공장섹션단위 VARCHAR(50),
    가공센터단위건제 VARCHAR(20),
    가공센터단위 VARCHAR(50),
    조직단위 VARCHAR(100),
    조직직무분류 VARCHAR(100),
    조직직무세부분류 VARCHAR(100)
);
```

이 테이블은 독립 schema `ganada` 영역으로 이동했고, Schema Graph/Data Integrator에서 DB/schema별 색상 구분 대상으로 사용한다.

### 12.4 MySQL

MySQL 쪽에는 PostgreSQL 직원 데이터를 참고해 임직원 평가 및 연봉/월급 데이터를 생성했다.

구현된 방향:

- MySQL 연결 프로필 관리
- 연결된 DB 리스트 표시
- DB 정보 보기
- MySQL database list 조회
- MySQL 테이블 정보 가져오기
- 평가/연봉/월급 데이터 생성
- 10년간 월급 데이터 테이블 생성

## 13. 비정형 샘플 데이터

가나다 기업에서 임직원 관리를 위해 사용할 만한 가상 비정형 문서를 생성했다.

예시 위치:

```text
examples/ganada_unstructured/
```

예시 문서:

- HR 용어/정책 문서
- 관리자 역할 가이드
- 승진 리뷰 메모
- HR 회의록
- 전보 요청 이메일 스레드
- 상태 glossary

비정형 문서는 Data Integrator에서 업로드하거나 localStorage에 수집 상태로 저장하고, Ontology Definer에서 정형 데이터와 함께 의미 분석에 활용한다.

## 14. 프로젝트 분리 구조

여러 사용자가 독립적으로 여러 목적의 프로젝트를 만들어 사용할 수 있도록 `project.js` 기반의 프로젝트 namespace를 도입했다.

기능:

- 프로젝트 선택
- 새 프로젝트 생성
- 프로젝트별 localStorage key 분리
- 홈 화면 프로젝트 메트릭 표시

저장 key는 다음 형태로 래핑된다.

```javascript
window.EmpProjects.key("원래.storage.key")
```

## 15. 주요 API

`empsearch/web_agent.py`에서 제공하는 주요 API:

| API | 역할 |
| --- | --- |
| `/api/schema` | PostgreSQL schema/relationship 조회 |
| `/api/table-data` | 테이블 row 샘플 조회 |
| `/api/agent` | 자연어 질의 처리 |
| `/api/ontology` | Ontology 조회/저장/삭제 |
| `/api/ontology/infer` | Ontology 자동 유추 |
| `/api/ontology/automate` | Ontology 전체 자동화 |
| `/api/ontology/bulk-delete` | Ontology 범위 삭제 |
| `/api/unstructured/upload` | 비정형 파일 업로드 분석 |
| `/api/unstructured/url` | URL 분석 |
| `/api/database-info` | 연결 DB 정보 조회 |
| `/api/external-schema` | 외부 DB schema 조회 |
| `/api/generated-metadata/reset` | 생성 메타데이터 초기화 |

## 16. 실행 방법

서버 실행:

```bash
python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765
```

브라우저:

```text
http://127.0.0.1:8765
```

기본 검증:

```bash
curl -sS http://127.0.0.1:8765/
curl -sS http://127.0.0.1:8765/data-manager
curl -sS http://127.0.0.1:8765/ontology
curl -sS http://127.0.0.1:8765/api/schema
```

정적 JS 문법 검사:

```bash
node --check empsearch/web_static/unstructured.js
node --check empsearch/web_static/ontology.js
node --check empsearch/web_static/superagent.js
node --check empsearch/web_static/agent_shop.js
node --check empsearch/web_static/schema.js
```

## 17. 테스트 하네스

### 17.1 Data Integrator

검증 항목:

- `/data-manager` 로드
- 정형 데이터 탭 표시
- 연결 및 테스트 표시
- 연결된 데이터 소스 관리 표시
- 테이블 관리 클릭 시 테이블 목록 표시
- DB 체크 필터 변경 시 테이블 목록 갱신
- Data Catalog 클릭 시 Snapshot/Dataset 표시
- Cloud Storage 클릭 후 Storage 프로필 저장
- Storage 프로필을 Pipeline 소스로 지정
- Lakehouse Pipeline 생성
- Pipeline 실행 시뮬레이션
- 비정형 데이터 탭 클릭
- 멀티모달 분석 클릭
- 이미지/음성/영상 accept 확장자 확인

최근 검증 결과:

- Cloud Storage 프로필 저장 정상
- Storage 프로필을 Pipeline 소스로 지정 정상
- Pipeline 생성 정상
- Pipeline 실행 시뮬레이션 정상
- 멀티모달 메뉴 표시 정상
- `node --check empsearch/web_static/unstructured.js` 통과

### 17.2 Ontology Definer

검증 항목:

- `/ontology` 로드
- 의미 Ontology 탭 클릭
- 테이블/필드 선택
- AI 의미 리뷰 생성
- 리뷰 카드 생성
- 편집 폼에 반영
- 리뷰 메모 입력
- 저장
- 관계 Ontology 탭 클릭
- 자동 관계 분석 실행
- 상태/유형 필터 적용
- 그래프 edge 클릭
- 승인/제외
- 신뢰도 기준 자동 승인

최근 검증 결과:

- AI 의미 리뷰 카드 22건 생성 확인
- 편집 폼 반영 정상
- `node --check empsearch/web_static/ontology.js` 통과

### 17.3 Agent Builder

검증 항목:

- Chat Studio에서 아이디어 분석
- Scenario Studio 추천
- Zero부터 만들기
- 데이터/문서/Ontology 선택
- Prompt / Test Harness 샘플 적용
- 테스트 실행 결과 표시
- 생성 완료
- Agent Shop에 추가

### 17.4 Agent Shop

검증 항목:

- Agent Catalog 표시
- Agent 삭제
- Agent 백업
- Agent 복원
- Agent 실행
- Builder로 이동

## 18. 현재 구현 한계

현재 구현은 로컬 MVP와 UX/메타데이터 시뮬레이션을 포함한다. Production 전환 시 다음 보강이 필요하다.

### 18.1 Cloud Storage

현재:

- Provider/profile UI
- credential alias 저장
- 연결 시뮬레이션

필요:

- AWS SDK, GCP SDK, Azure SDK 서버 연동
- Secret Manager 연동
- IAM role/workload identity 지원
- bucket/container listing
- object metadata scan
- incremental discovery
- block storage mount/scan agent

### 18.2 Apache Iceberg

현재:

- Iceberg 개념 UI
- snapshot id 시뮬레이션
- Bronze/Silver/Gold pipeline 정의

필요:

- Iceberg REST Catalog 또는 Glue/Hive/Nessie 연동
- 실제 metadata/manifest read/write
- Spark/Flink/Trino/DuckDB 연동
- schema evolution 검증
- partition spec 관리
- time travel query
- snapshot rollback

### 18.3 Pipeline Orchestration

현재:

- Pipeline 정의와 실행 시뮬레이션

필요:

- Airflow/Dagster/Prefect 연동
- DAG export/import
- schedule trigger
- retry/failure policy
- lineage capture
- run history DB 저장

### 18.4 멀티모달

현재:

- 이미지/음성/영상 파일 타입 분류
- 처리 힌트 표시
- Pipeline 후보 표시

필요:

- OCR
- STT
- 이미지 captioning
- object detection
- scene detection
- video frame sampling
- embedding/vector index
- RAG chunking

### 18.5 Agent 운영

현재:

- localStorage 기반 Agent Catalog

필요:

- Agent DB 저장
- 권한 관리
- Agent versioning
- audit log
- deployment channel
- evaluation set
- guardrail

## 19. 재구현 순서

처음부터 다시 만들 때 추천 순서:

1. PostgreSQL 설치 및 기본 schema 구성
2. 직원/부서/이력 테이블 생성
3. 샘플 데이터 생성
4. `web_agent.py` 서버와 `/api/schema`, `/api/table-data` 구현
5. 챗봇 자연어 검색 구현
6. Schema Graph 구현
7. Data Integrator 정형 데이터 연결/테이블 관리 구현
8. 비정형 파일 업로드/분석 구현
9. Data Catalog와 Snapshot/Dataset 구현
10. Cloud Storage profile UI 구현
11. Lakehouse Pipeline UI와 시뮬레이션 구현
12. 멀티모달 자산 분류 구현
13. Ontology Definer 의미 Ontology 구현
14. AI 의미 리뷰 구현
15. 관계 Ontology와 의미 관계 그래프 구현
16. Agent Builder 구현
17. Agent Shop 구현
18. 프로젝트별 namespace 구현
19. 통합 테스트와 UX 정리

## 20. 핵심 프롬프트 흐름

아래 프롬프트 흐름이 현재 솔루션의 기능 발전 순서를 만든다.

1. Notion FDE 데이터를 RAG로 만들고 내부 지식 검색 App 제안
2. PostgreSQL 설치
3. 직원관리 DB table 설계
4. 입사부터 퇴사까지 유연한 이력 구조 설계
5. 설계된 테이블을 PostgreSQL에 반영
6. 샘플 데이터 생성
7. 100년 회사 이력과 연 1회 이상 변경 이력 생성
8. 표준 부서 관리 테이블 정의
9. 웹 기반 직원 이력 조회 Agent 구현
10. 철강회사 한국 본사, 서울/포항/광양 근무 기준 데이터 재생성
11. EmpSearch Agent를 챗봇 형태로 변경
12. 최신 LLM 도구 UX로 개선
13. 자연어 DB 검색 UI 구현
14. 임직원정보와 부서관리정보 테이블 분리
15. 자연어 질의 시 생성 SQL 표시
16. manager/team_lead 조건 오류 수정
17. Schema Graph 구현
18. 관계도 확대/축소, 정렬, star layout 구현
19. 패널 접기/펼치기, 리사이즈, 하단 데이터 조회 구현
20. 테이블 위치 저장, 심플 보기, 더블클릭 필드 접기 구현
21. Ontology 정의/편집/삭제 페이지 구현
22. 테이블/필드 자동 Ontology 생성
23. 비정형 데이터를 정보화해 Ontology에 활용
24. 비정형 데이터 처리 페이지 독립
25. 가나다 org_structure 반영
26. org_structure를 독립 schema로 이동
27. Data Manager를 Data Integrator로 변경
28. Ontology Manager를 Ontology Definer로 변경
29. SuperAgent Builder를 Agent Builder로 변경
30. AgentFactory를 Agent Shop으로 변경
31. O-A-F-C 솔루션 이름 확정
32. Data Integrator에 RDB 연결/테이블 관리/스키마 그래프 정리
33. MySQL 평가/연봉/월급 데이터 생성
34. Apache Iceberg 유사 기능 아이디어 및 구현
35. 프로젝트별 독립 사용 구조 구현
36. Ontology Definer 의미/관계 분리
37. 의미 관계 그래프와 승인/제외 UX 구현
38. Agent Builder Production 수준 설계 강화
39. AI 의미 리뷰와 사람 검토/재정의 UX 강화
40. Data Integrator에 Cloud Storage, Lakehouse Pipeline, 멀티모달 데이터 지원 추가

## 21. 최신 변경 요약

2026-07-08 기준 가장 최근 변경:

- Ontology Definer에 AI 의미 리뷰 패널 추가
- 테이블/필드 의미 자동 부여 로직 강화
- 신뢰도/근거 기반 리뷰 큐 구현
- 리뷰 메모/추가 정보 저장 UX 추가
- Data Integrator에 Cloud Storage 메뉴 추가
- AWS/GCP/Azure/S3 호환 Object & Block Storage profile 관리
- Data Integrator에 Lakehouse Pipeline 메뉴 추가
- Apache Iceberg 개념의 Bronze/Silver/Gold Pipeline 생성/실행 시뮬레이션
- Data Integrator에 멀티모달 분석 메뉴 추가
- 이미지 확장자 업로드 지원 추가
- 멀티모달 파일을 OCR/STT/장면 분석 후보로 분류

## 22. 다음 구현 권장 사항

우선순위 높은 다음 과제:

1. Cloud Storage 실제 backend connector
2. Iceberg Catalog 실제 연동
3. Pipeline run history를 DB 테이블로 저장
4. 멀티모달 OCR/STT/vision 모델 호출
5. Ontology와 Agent Catalog를 localStorage에서 DB 저장으로 이전
6. Agent Builder에서 Pipeline을 Agent tool로 직접 선택
7. Data Integrator와 Ontology Definer 간 lineage graph 통합
8. 사용자/프로젝트/권한 모델 도입
9. 테스트 자동화
10. README를 O-A-F-C 최신 명칭으로 갱신

