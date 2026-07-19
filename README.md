# OAFC — Ontology Agent Factory Creator

DB 메타데이터를 수집·통합하고, 온톨로지와 업무 Agent 설계로 이어지는 흐름을
하나로 연결하는 로컬 웹 솔루션입니다. 표준 라이브러리 기반의 가벼운 HTTP 서버와
Vanilla JS 프런트엔드로 구성됩니다.

## 요구 사항

- Python 3.10+
- (선택) MySQL/MariaDB 연결 시 `pymysql`

## 설치

```bash
pip install -r requirements.txt        # 실행용
pip install -r requirements-dev.txt    # 개발/테스트 포함
```

## 실행

```bash
python3 -m oafc.server --host 127.0.0.1 --port 8765
```

브라우저에서 `http://127.0.0.1:8765` 접속.

### 환경 변수

| 변수 | 설명 |
| --- | --- |
| `OAFC_API_TOKEN` | 설정 시 변경(mutating) API에 Bearer 토큰 인증을 요구 |
| `OAFC_ALLOWED_HOSTS` | 허용 Host 헤더 목록 (쉼표 구분) |
| `OAFC_PUBLIC_ORIGIN` | 공개 배포 시 사용할 origin |
| `OAFC_CREDENTIAL_<ALIAS>` | DB 자격증명 alias 해석용. 원시 비밀번호는 저장하지 않습니다 |

## 테스트

```bash
python3 -m pytest -q
```

## 프로젝트 구조

```text
oafc/
  server.py      # HTTP 서버, API 라우팅, 인증
  metadata.py    # 메타데이터 수집, DB 연결, 온톨로지 추론
  web/           # index.html, app.css, app.js
tests/           # pytest 기반 테스트
```
