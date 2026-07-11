-- Ontology / Query Planner 테이블 (PostgreSQL)

CREATE TABLE IF NOT EXISTS ontology_concepts (
    concept_id INTEGER PRIMARY KEY,
    concept_name TEXT,
    concept_type TEXT,
    description TEXT,
    domain TEXT,
    synonyms TEXT,
    updated_by TEXT,
    created_at TEXT
);
COMMENT ON TABLE ontology_concepts IS 'Ontology 개념 (자연어 SQL 생성용)';

CREATE TABLE IF NOT EXISTS ontology_concept_columns (
    id INTEGER PRIMARY KEY,
    concept_id INTEGER,
    table_name TEXT,
    column_name TEXT,
    role TEXT,
    confidence NUMERIC(8,1),
    created_at TEXT
);
COMMENT ON TABLE ontology_concept_columns IS 'Ontology 개념 - 컬럼 매핑';

CREATE TABLE IF NOT EXISTS ontology_relationships (
    relationship_id INTEGER PRIMARY KEY,
    from_concept INTEGER,
    to_concept INTEGER,
    relation_type TEXT,
    confidence NUMERIC(8,1),
    approved INTEGER,
    approved_by TEXT,
    evidence TEXT,
    created_at TEXT
);
COMMENT ON TABLE ontology_relationships IS 'Ontology 개념 간 의미 관계';

CREATE TABLE IF NOT EXISTS ontology_query_patterns (
    pattern_id INTEGER PRIMARY KEY,
    concept_id INTEGER,
    pattern_text TEXT,
    intent TEXT,
    sql_template TEXT,
    priority INTEGER,
    enabled INTEGER,
    updated_at TEXT
);
COMMENT ON TABLE ontology_query_patterns IS '자연어 질의 패턴 (Query Planner)';

CREATE TABLE IF NOT EXISTS ontology_definitions (
    id INTEGER PRIMARY KEY,
    project TEXT,
    target_type TEXT,
    table_name TEXT,
    field_name TEXT,
    label TEXT,
    description TEXT,
    synonyms TEXT,
    value_map TEXT,
    use_in_sql INTEGER,
    review_note TEXT,
    updated_at TEXT
);
COMMENT ON TABLE ontology_definitions IS 'Ontology 정의 (의미/동의어/값 매핑)';
