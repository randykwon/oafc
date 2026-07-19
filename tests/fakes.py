from oafc.metadata import IntegratorStore


class FakeMySQLCursor:
    def __init__(self):
        self.rows = []
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        targets = set(params)
        self.description = None
        if normalized.startswith("SET SESSION MAX_EXECUTION_TIME="):
            self.rows = []
        elif normalized == "START TRANSACTION READ ONLY":
            self.rows = []
        elif normalized == "SELECT event_id,product_id FROM events ORDER BY event_id":
            self.description = [("event_id",), ("product_id",)]
            self.rows = [
                {"event_id": 1, "product_id": 101},
                {"event_id": 2, "product_id": 102},
                {"event_id": 3, "product_id": 103},
            ]
        elif "@@version AS version" in normalized:
            self.rows = [{
                "version": "8.0.40", "version_comment": "MySQL Community Server",
                "hostname": "warehouse", "port": 3306, "character_set": "utf8mb4",
                "collation": "utf8mb4_0900_ai_ci", "sql_mode": "STRICT_TRANS_TABLES",
                "lower_case_table_names": 0, "max_connections": 250,
            }]
        elif "FROM information_schema.SCHEMATA" in normalized:
            self.rows = [
                {"name": "analytics", "default_character_set": "utf8mb4",
                 "default_collation": "utf8mb4_0900_ai_ci", "table_count": 1,
                 "view_count": 0, "estimated_rows": 1200, "data_bytes": 8192,
                 "index_bytes": 2048},
                {"name": "catalog", "default_character_set": "utf8mb4",
                 "default_collation": "utf8mb4_0900_ai_ci", "table_count": 1,
                 "view_count": 1, "estimated_rows": 300, "data_bytes": 4096,
                 "index_bytes": 1024},
                {"name": "mysql", "default_character_set": "utf8mb4",
                 "default_collation": "utf8mb4_0900_ai_ci", "table_count": 10,
                 "view_count": 0, "estimated_rows": 10, "data_bytes": 100,
                 "index_bytes": 100},
            ]
        elif "information_schema.ROUTINES" in normalized:
            self.rows = [{"name": "analytics", "count": 2}]
        elif "information_schema.TRIGGERS" in normalized:
            self.rows = [{"name": "catalog", "count": 1}]
        elif "FROM information_schema.TABLES WHERE" in normalized:
            candidates = [
                {"database_name": "analytics", "name": "events", "kind": "BASE TABLE",
                 "engine": "InnoDB", "estimated_rows": 1200, "data_bytes": 8192,
                 "index_bytes": 2048, "comment": "event facts"},
                {"database_name": "catalog", "name": "products", "kind": "BASE TABLE",
                 "engine": "InnoDB", "estimated_rows": 300, "data_bytes": 4096,
                 "index_bytes": 1024, "comment": "product master"},
            ]
            self.rows = [row for row in candidates if row["database_name"] in targets]
        elif "FROM information_schema.COLUMNS" in normalized:
            candidates = [
                {"database_name": "analytics", "table_name": "events", "name": "event_id",
                 "position": 1, "default_value": None, "is_nullable": "NO",
                 "data_type": "bigint", "column_type": "bigint unsigned", "column_key": "PRI",
                 "extra": "auto_increment", "comment": "event identifier"},
                {"database_name": "analytics", "table_name": "events", "name": "product_id",
                 "position": 2, "default_value": None, "is_nullable": "NO",
                 "data_type": "bigint", "column_type": "bigint", "column_key": "MUL",
                 "extra": "", "comment": ""},
                {"database_name": "catalog", "table_name": "products", "name": "product_id",
                 "position": 1, "default_value": None, "is_nullable": "NO",
                 "data_type": "bigint", "column_type": "bigint", "column_key": "PRI",
                 "extra": "", "comment": "identifier"},
                {"database_name": "catalog", "table_name": "products", "name": "title",
                 "position": 2, "default_value": None, "is_nullable": "YES",
                 "data_type": "varchar", "column_type": "varchar(200)", "column_key": "",
                 "extra": "", "comment": "display title"},
            ]
            self.rows = [row for row in candidates if row["database_name"] in targets]
        elif "FROM information_schema.STATISTICS" in normalized:
            candidates = [
                {"database_name": "analytics", "table_name": "events", "index_count": 2},
                {"database_name": "catalog", "table_name": "products", "index_count": 1},
            ]
            self.rows = [row for row in candidates if row["database_name"] in targets]
        elif "FROM information_schema.KEY_COLUMN_USAGE" in normalized:
            self.rows = ([{
                "from_database": "analytics", "from_name": "events", "from_column": "product_id",
                "to_database": "catalog", "to_name": "products", "to_column": "product_id",
            }] if {"analytics", "catalog"}.issubset(targets) else [])
        else:
            raise AssertionError("unexpected SQL: " + normalized)

    def fetchall(self):
        return self.rows

    def fetchmany(self, size):
        return self.rows[:size]


class FakeMySQLConnection:
    def cursor(self):
        return FakeMySQLCursor()

    def rollback(self):
        pass

    def close(self):
        pass


class FakeMySQLStore(IntegratorStore):
    def _mysql_connection(self, profile, database=None):
        return FakeMySQLConnection()
