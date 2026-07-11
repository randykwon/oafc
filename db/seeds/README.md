# Seeds

임베디드 모드에서는 서버 첫 실행 시 `empsearch/db.py` 의 `seed()` 가
`data/empsearch.db` 에 샘플 데이터를 자동 생성한다.

- 기본 직원 수: 500명 (`OAFC_SEED_EMPLOYEES` 환경 변수로 변경, 예: 10000)
- 가나다 기업 / 한국 철강회사 콘셉트: 서울 · 포항 · 광양 근무지
- 부서 변경 이력, 임직원 변경 이력, 평가(최근 5년), 월급(10년치 분기 대표월)
- `ganada.org_structure` 표준조직 10행

시드를 다시 만들려면 서버를 멈추고 `data/empsearch.db` 를 삭제한 뒤 재시작한다.

```bash
rm data/empsearch.db
OAFC_SEED_EMPLOYEES=10000 python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765
```

PostgreSQL / MySQL 에 실제 시드를 넣을 때는 `db/migrations/*.sql` 로 스키마를 만들고
동일한 생성 로직을 커넥터에 맞게 이식한다.
