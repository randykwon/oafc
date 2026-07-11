-- 가나다 기업 표준조직 테이블 (독립 schema: ganada)
CREATE SCHEMA IF NOT EXISTS ganada;

CREATE TABLE IF NOT EXISTS ganada.org_structure (
    "표준부서코드" TEXT PRIMARY KEY,
    "표준부서_2026" TEXT,
    "운영종료제외_표준부서명" TEXT,
    "년도구분" TEXT,
    "부서명" TEXT,
    "고유코드_년도부서명" TEXT,
    "본부단위건제" TEXT,
    "본부단위" TEXT,
    "실담당단위건제" TEXT,
    "실담당단위" TEXT,
    "그룹단위건제" TEXT,
    "그룹단위" TEXT,
    "공장섹션단위건제" TEXT,
    "공장섹션단위" TEXT,
    "가공센터단위건제" TEXT,
    "가공센터단위" TEXT,
    "조직단위" TEXT,
    "조직직무분류" TEXT,
    "조직직무세부분류" TEXT
);
COMMENT ON TABLE ganada.org_structure IS '가나다 기업 표준조직 테이블';
