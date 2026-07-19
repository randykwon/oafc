"""Persistent metadata plus read-only SQLite and MySQL analysis services."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import ssl
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable


class IntegratorError(ValueError):
    """A user-visible validation or integration error."""


class NotFoundError(IntegratorError):
    """Requested metadata does not exist."""


class EnvironmentCredentialResolver:
    """Resolves an alias from OAFC_CREDENTIAL_<ALIAS>; secrets are never stored."""

    PREFIX = "OAFC_CREDENTIAL_"

    def __call__(self, alias: str) -> str:
        if not alias:
            return ""
        normalized = re.sub(r"[^A-Za-z0-9]", "_", alias).upper()
        value = os.environ.get(self.PREFIX + normalized)
        if value is None:
            raise IntegratorError(
                "credential alias is not configured; set %s%s" % (self.PREFIX, normalized))
        return value


class IntegratorStore:
    """Stores integration metadata and analyzes sources without modifying them."""

    SOURCE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
    FORBIDDEN_SECRET_FIELDS = {"password", "secret", "token", "api_key", "private_key"}
    MYSQL_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}
    ANALYSIS_MAX_ROWS = 500
    ANALYSIS_MAX_QUERY_BYTES = 50_000
    ANALYSIS_MAX_TIMEOUT_MS = 10_000
    ANALYSIS_FORBIDDEN_WORDS = {
        "INSERT", "UPDATE", "DELETE", "REPLACE", "MERGE", "UPSERT", "CREATE",
        "ALTER", "DROP", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
        "ANALYZE", "REINDEX", "GRANT", "REVOKE", "CALL", "EXECUTE", "DO",
        "HANDLER", "LOAD", "LOCK", "UNLOCK", "SET", "USE", "BEGIN", "START",
        "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "INTO", "OUTFILE", "DUMPFILE",
        "PROCEDURE",
    }
    ANALYSIS_ALLOWED_FUNCTIONS = {
        "ABS", "AVG", "COUNT", "MAX", "MIN", "SUM", "TOTAL", "ROUND", "CEIL",
        "CEILING", "FLOOR", "POWER", "SQRT", "MOD", "COALESCE", "IFNULL", "NULLIF",
        "IIF", "IF", "GREATEST", "LEAST", "LOWER", "UPPER", "LENGTH", "CHAR_LENGTH",
        "OCTET_LENGTH", "TRIM", "LTRIM", "RTRIM", "SUBSTR", "SUBSTRING", "CONCAT",
        "CONCAT_WS", "HEX", "UNHEX", "QUOTE", "CAST", "DATE", "TIME", "DATETIME",
        "JULIANDAY", "UNIXEPOCH", "STRFTIME", "YEAR", "MONTH", "DAY", "DAYOFMONTH",
        "NOW", "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATE_FORMAT",
        "JSON_EXTRACT", "JSON_TYPE", "JSON_VALID", "JSON_ARRAY_LENGTH", "JSON_UNQUOTE",
        "ROW_NUMBER", "RANK", "DENSE_RANK", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
        "VERSION", "SQLITE_VERSION",
    }
    ANALYSIS_PAREN_KEYWORDS = {
        "AS", "IN", "EXISTS", "OVER", "VALUES", "FROM", "WHERE", "WHEN", "THEN",
        "ELSE", "ON", "HAVING", "AND", "OR", "NOT", "SELECT", "JOIN", "LEFT",
        "RIGHT", "INNER", "OUTER", "CROSS", "BY", "ORDER", "GROUP", "LIMIT",
        "OFFSET", "UNION", "ALL", "DISTINCT", "CASE", "FILTER", "WITH", "RECURSIVE",
    }
    ANALYSIS_FORBIDDEN_FUNCTIONS = {
        "SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "IS_FREE_LOCK",
        "LOAD_FILE", "LOAD_EXTENSION", "READFILE", "WRITEFILE", "SYS_EXEC", "SYS_EVAL",
        "RELEASE_ALL_LOCKS",
    }

    def __init__(self, metadata_path: os.PathLike[str] | str,
                 discovery_roots: Iterable[os.PathLike[str] | str],
                 credential_resolver: Callable[[str], str] | None = None):
        self.metadata_path = Path(metadata_path).expanduser().resolve()
        self.discovery_roots = tuple(Path(root).expanduser().resolve() for root in discovery_roots)
        if not self.discovery_roots:
            raise ValueError("at least one discovery root is required")
        self.credential_resolver = credential_resolver or EnvironmentCredentialResolver()
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _now() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self.metadata_path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=15000")
            self._local.connection = conn
        return conn

    def close_thread_connection(self) -> None:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            del self._local.connection

    def _initialize(self) -> None:
        conn = sqlite3.connect(self.metadata_path)
        try:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    host TEXT NOT NULL DEFAULT '',
                    port INTEGER NOT NULL DEFAULT 0,
                    username TEXT NOT NULL DEFAULT '',
                    database_name TEXT NOT NULL DEFAULT '',
                    credential_alias TEXT NOT NULL DEFAULT '',
                    tls_mode TEXT NOT NULL DEFAULT '',
                    ssl_ca TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'saved',
                    last_error TEXT NOT NULL DEFAULT '',
                    discovered_at TEXT,
                    last_tested_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS selected_tables (
                    connection_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    business_domain TEXT NOT NULL DEFAULT '',
                    usage_purpose TEXT NOT NULL DEFAULT '',
                    selected_at TEXT NOT NULL,
                    PRIMARY KEY (connection_id, table_name),
                    FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS ontology_definitions (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    column_name TEXT NOT NULL DEFAULT '',
                    target_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    synonyms TEXT NOT NULL DEFAULT '[]',
                    semantic_type TEXT NOT NULL DEFAULT 'attribute',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'applied',
                    updated_at TEXT NOT NULL,
                    UNIQUE(connection_id, table_name, column_name, target_type),
                    FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
                );
            """)
            self._ensure_columns(conn, "connections", {
                "host": "TEXT NOT NULL DEFAULT ''", "port": "INTEGER NOT NULL DEFAULT 0",
                "username": "TEXT NOT NULL DEFAULT ''", "database_name": "TEXT NOT NULL DEFAULT ''",
                "tls_mode": "TEXT NOT NULL DEFAULT ''", "ssl_ca": "TEXT NOT NULL DEFAULT ''",
            })
            self._ensure_columns(conn, "selected_tables", {
                "business_domain": "TEXT NOT NULL DEFAULT ''",
                "usage_purpose": "TEXT NOT NULL DEFAULT ''",
            })
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, declaration))

    def _write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._write_lock:
            conn = self._connection()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount

    def _allowed_source(self, value: os.PathLike[str] | str) -> Path:
        path = Path(value).expanduser().resolve()
        if path == self.metadata_path:
            raise IntegratorError("Integrator metadata database cannot be used as a source")
        if not any(path == root or root in path.parents for root in self.discovery_roots):
            raise IntegratorError("database path is outside configured discovery roots")
        if not path.is_file() or path.suffix.lower() not in self.SOURCE_SUFFIXES:
            raise IntegratorError("SQLite database file does not exist or has an unsupported extension")
        return path

    @staticmethod
    def _source_connection(path: Path, timeout: float = 5.0) -> sqlite3.Connection:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _sqlite_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def discover(self, max_depth: int = 4) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for root in self.discovery_roots:
            if not root.exists():
                continue
            for current, dirs, files in os.walk(root):
                current_path = Path(current).resolve()
                if len(current_path.relative_to(root).parts) >= max_depth:
                    dirs[:] = []
                dirs[:] = [name for name in dirs if not name.startswith(".")]
                for filename in files:
                    unresolved = current_path / filename
                    if unresolved.suffix.lower() not in self.SOURCE_SUFFIXES:
                        continue
                    try:
                        candidate = self._allowed_source(unresolved)
                    except (IntegratorError, OSError):
                        # Broken links and links escaping an allowed root are not sources.
                        continue
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    results.append(self._probe_source(candidate))
        results.sort(key=lambda item: (not item["available"], item["name"].lower()))
        return results

    def _probe_source(self, path: Path) -> dict[str, Any]:
        try:
            path = self._allowed_source(path)
            item: dict[str, Any] = {
                "discovery_id": hashlib.sha256(str(path).encode()).hexdigest()[:16],
                "name": path.name, "engine": "sqlite", "location": str(path),
                "size_bytes": path.stat().st_size, "available": False,
                "database_count": 1, "table_count": 0, "error": "",
            }
            with self._source_connection(path) as conn:
                item["table_count"] = int(conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view') "
                    "AND name NOT LIKE 'sqlite_%'").fetchone()[0])
                item["available"] = True
        except (IntegratorError, OSError, sqlite3.Error) as exc:
            item = {
                "discovery_id": hashlib.sha256(str(path).encode()).hexdigest()[:16],
                "name": path.name, "engine": "sqlite", "location": str(path),
                "size_bytes": 0, "available": False, "database_count": 1,
                "table_count": 0, "error": "SQLite inspection failed: %s" % exc,
            }
        return item

    def save_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.FORBIDDEN_SECRET_FIELDS.intersection(payload):
            raise IntegratorError("raw secrets are not accepted; use credential_alias")
        engine = str(payload.get("engine") or "sqlite").lower()
        if engine not in {"sqlite", "mysql"}:
            raise IntegratorError("engine must be sqlite or mysql")
        location = ""
        host = ""
        port = 0
        username = ""
        database_name = ""
        tls_mode = ""
        ssl_ca = ""
        if engine == "sqlite":
            location = str(self._allowed_source(str(payload.get("location") or "")))
            default_name = Path(location).stem
        else:
            host = str(payload.get("host") or "").strip()
            username = str(payload.get("username") or "").strip()
            database_name = str(payload.get("database_name") or "").strip()
            if not host or not username:
                raise IntegratorError("MySQL host and username are required")
            try:
                port = int(payload.get("port") or 3306)
            except (TypeError, ValueError) as exc:
                raise IntegratorError("MySQL port must be an integer") from exc
            if port < 1 or port > 65535:
                raise IntegratorError("MySQL port must be between 1 and 65535")
            location = "mysql://%s:%d" % (host, port)
            default_name = "%s@%s" % (username, host)
            tls_mode = str(payload.get("tls_mode") or "verify_identity").strip().lower()
            if tls_mode not in {"verify_identity", "verify_ca", "required", "disabled"}:
                raise IntegratorError(
                    "tls_mode must be verify_identity, verify_ca, required, or disabled")
            ssl_ca = str(payload.get("ssl_ca") or "").strip()
            if ssl_ca:
                ca_path = Path(ssl_ca).expanduser().resolve()
                if not ca_path.is_file():
                    raise IntegratorError("MySQL SSL CA file does not exist")
                ssl_ca = str(ca_path)
        name = str(payload.get("name") or default_name).strip()
        if not name or len(name) > 120:
            raise IntegratorError("connection name must contain 1-120 characters")
        alias = str(payload.get("credential_alias") or "").strip()
        if len(alias) > 160:
            raise IntegratorError("credential_alias is too long")
        connection_id = str(payload.get("id") or uuid.uuid4())
        now = self._now()
        with self._write_lock:
            conn = self._connection()
            existing = conn.execute(
                "SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
            created_at = existing["created_at"] if existing else now
            old_identity = None if not existing else tuple(existing[key] for key in (
                "engine", "location", "host", "port", "username", "database_name",
                "credential_alias", "tls_mode", "ssl_ca"))
            new_identity = (engine, location, host, port, username, database_name,
                            alias, tls_mode, ssl_ca)
            conn.execute("""
                INSERT INTO connections
                    (id,name,engine,location,host,port,username,database_name,credential_alias,
                     tls_mode,ssl_ca,status,last_error,discovered_at,last_tested_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'saved','',?,NULL,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,engine=excluded.engine,location=excluded.location,
                    host=excluded.host,port=excluded.port,username=excluded.username,
                    database_name=excluded.database_name,credential_alias=excluded.credential_alias,
                    tls_mode=excluded.tls_mode,ssl_ca=excluded.ssl_ca,
                    status='saved',last_error='',last_tested_at=NULL,updated_at=excluded.updated_at
            """, (connection_id, name, engine, location, host, port, username, database_name,
                  alias, tls_mode, ssl_ca, payload.get("discovered_at") or now, created_at, now))
            if old_identity is not None and old_identity != new_identity:
                conn.execute("DELETE FROM ontology_definitions WHERE connection_id=?", (connection_id,))
                conn.execute("DELETE FROM selected_tables WHERE connection_id=?", (connection_id,))
            conn.commit()
        return self.get_connection(connection_id)

    @staticmethod
    def _connection_summary_sql(where: str = "") -> str:
        return """
            SELECT c.*,
                   (SELECT COUNT(*) FROM selected_tables s WHERE s.connection_id=c.id)
                       AS selected_table_count,
                   (SELECT COUNT(*) FROM ontology_definitions o WHERE o.connection_id=c.id)
                       AS ontology_count
            FROM connections c %s
        """ % where

    def list_connections(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection().execute(
            self._connection_summary_sql("ORDER BY c.updated_at DESC,c.name")).fetchall()]

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        row = self._connection().execute(
            self._connection_summary_sql("WHERE c.id=?"), (connection_id,)).fetchone()
        if not row:
            raise NotFoundError("connection not found")
        return dict(row)

    def delete_connection(self, connection_id: str) -> None:
        if self._write("DELETE FROM connections WHERE id=?", (connection_id,)) == 0:
            raise NotFoundError("connection not found")

    @staticmethod
    def _mysql_driver():
        try:
            import pymysql
            return pymysql
        except ImportError as exc:
            raise IntegratorError("MySQL support requires pymysql; install requirements.txt") from exc

    def _mysql_connection(self, profile: dict[str, Any], database: str | None = None):
        pymysql = self._mysql_driver()
        password = self.credential_resolver(profile.get("credential_alias") or "")
        tls_mode = profile.get("tls_mode") or "verify_identity"
        tls_options: dict[str, Any] = {}
        if tls_mode != "disabled":
            context = ssl.create_default_context(cafile=profile.get("ssl_ca") or None)
            context.check_hostname = tls_mode == "verify_identity"
            context.verify_mode = (ssl.CERT_REQUIRED
                                   if tls_mode in {"verify_ca", "verify_identity"}
                                   else ssl.CERT_NONE)
            tls_options["ssl"] = context
        return pymysql.connect(
            host=profile["host"], port=int(profile["port"]), user=profile["username"],
            password=password, database=database or None, charset="utf8mb4", autocommit=True,
            connect_timeout=5, read_timeout=20, write_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
            **tls_options,
        )

    @staticmethod
    def _mysql_rows(cursor, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor.execute(sql, params)
        return list(cursor.fetchall())

    def test_connection(self, connection_id: str) -> dict[str, Any]:
        profile = self.get_connection(connection_id)
        now = self._now()
        try:
            if profile["engine"] == "sqlite":
                with self._source_connection(self._allowed_source(profile["location"])) as conn:
                    version = conn.execute("SELECT sqlite_version()").fetchone()[0]
                    table_count = conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view') "
                        "AND name NOT LIKE 'sqlite_%'").fetchone()[0]
                result = {"connected": True, "engine": "sqlite", "version": version,
                          "database_count": 1, "table_count": int(table_count), "tested_at": now}
            else:
                inventory = self.inventory(connection_id)
                result = {"connected": True, "engine": "mysql",
                          "version": inventory["server"]["version"],
                          "database_count": inventory["totals"]["database_count"],
                          "table_count": inventory["totals"]["table_count"], "tested_at": now}
            self._write("UPDATE connections SET status='connected',last_error='',last_tested_at=?,updated_at=? WHERE id=?",
                        (now, now, connection_id))
            return result
        except (IntegratorError, sqlite3.Error, OSError, Exception) as exc:
            # Driver exceptions intentionally become a sanitized profile status.
            message = str(exc)[:500]
            self._write("UPDATE connections SET status='error',last_error=?,last_tested_at=?,updated_at=? WHERE id=?",
                        (message, now, now, connection_id))
            return {"connected": False, "engine": profile["engine"], "error": message, "tested_at": now}

    @classmethod
    def _validated_analysis_sql(cls, query: Any) -> str:
        if not isinstance(query, str) or not query.strip():
            raise IntegratorError("analysis query is required")
        statement = query.strip()
        if len(statement.encode("utf-8")) > cls.ANALYSIS_MAX_QUERY_BYTES:
            raise IntegratorError("analysis query is too large")
        # SQLite and MySQL SQL modes disagree on backslash escaping. Reject it so the
        # conservative lexer cannot interpret a different statement than the database.
        if "\\" in statement:
            raise IntegratorError("backslash escapes are not allowed in analysis queries")
        code: list[str] = []
        index = 0
        while index < len(statement):
            char = statement[index]
            if char in {"'", '"', "`"}:
                quote = char
                code.append(" ")
                index += 1
                while index < len(statement):
                    current = statement[index]
                    if current == quote:
                        if index + 1 < len(statement) and statement[index + 1] == quote:
                            index += 2
                            continue
                        index += 1
                        lookahead = index
                        while lookahead < len(statement) and statement[lookahead].isspace():
                            lookahead += 1
                        if lookahead < len(statement) and statement[lookahead] == "(":
                            raise IntegratorError("quoted SQL function names are not allowed")
                        break
                    index += 1
                else:
                    raise IntegratorError("analysis query contains an unterminated quote")
                continue
            if statement.startswith("--", index) or statement.startswith("/*", index) or char == "#":
                raise IntegratorError("SQL comments are not allowed in analysis queries")
            code.append(char)
            index += 1
        visible = "".join(code).strip()
        if ";" in visible:
            if not visible.endswith(";") or visible.count(";") != 1:
                raise IntegratorError("only one SQL statement is allowed")
            statement = statement[:-1].rstrip()
            visible = visible[:-1].rstrip()
        normalized = " ".join(visible.upper().split())
        first = re.match(r"[A-Z]+", normalized)
        if not first or first.group(0) not in {"SELECT", "WITH"}:
            raise IntegratorError("only SELECT or WITH queries are allowed")
        words = set(re.findall(r"[A-Z_]+", normalized))
        blocked = sorted(words.intersection(cls.ANALYSIS_FORBIDDEN_WORDS))
        if blocked:
            raise IntegratorError("read-only analysis rejected SQL keyword: %s" % blocked[0])
        if re.search(r"\bFOR\s+(?:UPDATE|SHARE)\b|\bLOCK\s+IN\s+SHARE\s+MODE\b", normalized):
            raise IntegratorError("locking reads are not allowed in analysis queries")
        function_names = set(re.findall(r"\b([A-Z_][A-Z0-9_$]*)\s*\(", normalized))
        cte_names = set(re.findall(
            r"(?:\bWITH(?:\s+RECURSIVE)?|,)\s+([A-Z_][A-Z0-9_$]*)\s*"
            r"\([^)]*\)\s+AS\s*\(", normalized))
        function_names.difference_update(cls.ANALYSIS_PAREN_KEYWORDS)
        function_names.difference_update(cte_names)
        unsafe_functions = function_names.intersection(cls.ANALYSIS_FORBIDDEN_FUNCTIONS)
        unknown_functions = function_names.difference(cls.ANALYSIS_ALLOWED_FUNCTIONS)
        if unsafe_functions or unknown_functions or ":=" in visible:
            rejected = sorted(unsafe_functions or unknown_functions)
            suffix = ": %s" % rejected[0] if rejected else ""
            raise IntegratorError("unsafe or unsupported SQL function or assignment%s" % suffix)
        return statement

    @staticmethod
    def _analysis_bound(value: Any, default: int, minimum: int, maximum: int, name: str) -> int:
        if value is None:
            return default
        if isinstance(value, bool):
            raise IntegratorError("%s must be an integer" % name)
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise IntegratorError("%s must be an integer" % name) from exc
        if parsed < minimum or parsed > maximum:
            raise IntegratorError("%s must be between %d and %d" % (name, minimum, maximum))
        return parsed

    @staticmethod
    def _analysis_value(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        if isinstance(value, bytes):
            return "0x" + value.hex()
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        return str(value)

    @classmethod
    def _analysis_result(cls, cursor: Any, max_rows: int, started: float,
                         engine: str, database: str) -> dict[str, Any]:
        if not cursor.description:
            raise IntegratorError("analysis query did not return a result set")
        columns = [str(item[0]) for item in cursor.description]
        fetched = list(cursor.fetchmany(max_rows + 1))
        truncated = len(fetched) > max_rows
        rows = []
        for row in fetched[:max_rows]:
            values = [row.get(column) for column in columns] if isinstance(row, dict) else list(row)
            rows.append([cls._analysis_value(value) for value in values])
        return {
            "engine": engine, "database": database, "columns": columns, "rows": rows,
            "row_count": len(rows), "truncated": truncated, "max_rows": max_rows,
            "elapsed_ms": max(0, round((time.monotonic() - started) * 1000, 2)),
        }

    def analyze_query(self, connection_id: str, query: Any, database: Any = None,
                      max_rows: Any = 100, timeout_ms: Any = 5_000) -> dict[str, Any]:
        profile = self.get_connection(connection_id)
        if profile["status"] != "connected":
            raise IntegratorError("test the connection successfully before running analysis")
        statement = self._validated_analysis_sql(query)
        row_limit = self._analysis_bound(max_rows, 100, 1, self.ANALYSIS_MAX_ROWS, "max_rows")
        timeout = self._analysis_bound(
            timeout_ms, 5_000, 100, self.ANALYSIS_MAX_TIMEOUT_MS, "timeout_ms")
        started = time.monotonic()
        if profile["engine"] == "sqlite":
            path = self._allowed_source(profile["location"])
            deadline = started + timeout / 1000
            try:
                with self._source_connection(path, timeout=timeout / 1000) as conn:
                    conn.execute("PRAGMA busy_timeout=%d" % timeout)
                    conn.set_progress_handler(
                        lambda: 1 if time.monotonic() >= deadline else 0, 1_000)
                    cursor = conn.execute(statement)
                    return self._analysis_result(
                        cursor, row_limit, started, "sqlite", path.name)
            except sqlite3.Error as exc:
                lowered = str(exc).lower()
                message = ("analysis query timed out" if
                           ("interrupted" in lowered or "locked" in lowered)
                           else "analysis query failed: %s" % str(exc)[:300])
                raise IntegratorError(message) from exc

        selected_database = str(database or "").strip()
        if selected_database:
            if (len(selected_database) > 64 or
                    not re.fullmatch(r"[A-Za-z0-9_$-]+", selected_database)):
                raise IntegratorError("invalid MySQL analysis database")
            inventory = self.inventory(connection_id)
            allowed = {item["name"] for item in inventory["databases"] if not item["system"]}
            if selected_database not in allowed:
                raise IntegratorError("MySQL analysis database is not accessible")
        else:
            defaults = [name.strip() for name in profile.get("database_name", "").split(",")
                        if name.strip()]
            if len(defaults) == 1:
                selected_database = defaults[0]
        conn = self._mysql_connection(profile, selected_database or None)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (timeout,))
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute(statement)
                return self._analysis_result(
                    cursor, row_limit, started, "mysql", selected_database)
        except IntegratorError:
            raise
        except Exception as exc:
            raise IntegratorError("analysis query failed: %s" % str(exc)[:300]) from exc
        finally:
            try:
                conn.rollback()
            finally:
                conn.close()

    def inventory(self, connection_id: str) -> dict[str, Any]:
        profile = self.get_connection(connection_id)
        if profile["engine"] == "sqlite":
            return self._sqlite_inventory(profile)
        return self._mysql_inventory(profile)

    def _sqlite_inventory(self, profile: dict[str, Any]) -> dict[str, Any]:
        path = self._allowed_source(profile["location"])
        with self._source_connection(path) as conn:
            version = conn.execute("SELECT sqlite_version()").fetchone()[0]
            rows = conn.execute(
                "SELECT type,COUNT(*) AS count FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' GROUP BY type").fetchall()
        counts = {row["type"]: int(row["count"]) for row in rows}
        database = {
            "name": path.name, "system": False, "default_character_set": "UTF-8",
            "default_collation": "", "table_count": counts.get("table", 0),
            "view_count": counts.get("view", 0), "estimated_rows": None,
            "data_bytes": path.stat().st_size, "index_bytes": 0,
            "routine_count": 0, "trigger_count": 0,
        }
        return {
            "engine": "sqlite",
            "server": {"version": version, "host": "local", "port": None,
                       "character_set": "UTF-8", "collation": "", "sql_mode": ""},
            "databases": [database],
            "totals": {"database_count": 1, "table_count": database["table_count"],
                       "view_count": database["view_count"], "estimated_rows": None,
                       "data_bytes": database["data_bytes"], "index_bytes": 0},
        }

    def _mysql_inventory(self, profile: dict[str, Any]) -> dict[str, Any]:
        conn = self._mysql_connection(profile)
        try:
            with conn.cursor() as cursor:
                server_row = self._mysql_rows(cursor, """
                    SELECT @@version AS version,@@version_comment AS version_comment,
                           @@hostname AS hostname,@@port AS port,
                           @@character_set_server AS character_set,
                           @@collation_server AS collation,@@sql_mode AS sql_mode,
                           @@lower_case_table_names AS lower_case_table_names,
                           @@max_connections AS max_connections
                """)[0]
                schemas = self._mysql_rows(cursor, """
                    SELECT s.SCHEMA_NAME AS name,s.DEFAULT_CHARACTER_SET_NAME AS default_character_set,
                           s.DEFAULT_COLLATION_NAME AS default_collation,
                           SUM(CASE WHEN t.TABLE_TYPE='BASE TABLE' THEN 1 ELSE 0 END) AS table_count,
                           SUM(CASE WHEN t.TABLE_TYPE='VIEW' THEN 1 ELSE 0 END) AS view_count,
                           COALESCE(SUM(CASE WHEN t.TABLE_TYPE='BASE TABLE' THEN t.TABLE_ROWS ELSE 0 END),0) AS estimated_rows,
                           COALESCE(SUM(t.DATA_LENGTH),0) AS data_bytes,
                           COALESCE(SUM(t.INDEX_LENGTH),0) AS index_bytes
                    FROM information_schema.SCHEMATA s
                    LEFT JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=s.SCHEMA_NAME
                    GROUP BY s.SCHEMA_NAME,s.DEFAULT_CHARACTER_SET_NAME,s.DEFAULT_COLLATION_NAME
                    ORDER BY s.SCHEMA_NAME
                """)
                routines = self._mysql_rows(cursor,
                    "SELECT ROUTINE_SCHEMA AS name,COUNT(*) AS count FROM information_schema.ROUTINES GROUP BY ROUTINE_SCHEMA")
                triggers = self._mysql_rows(cursor,
                    "SELECT TRIGGER_SCHEMA AS name,COUNT(*) AS count FROM information_schema.TRIGGERS GROUP BY TRIGGER_SCHEMA")
        finally:
            conn.close()
        routine_map = {row["name"]: int(row["count"]) for row in routines}
        trigger_map = {row["name"]: int(row["count"]) for row in triggers}
        databases = []
        for row in schemas:
            databases.append({
                "name": row["name"], "system": row["name"] in self.MYSQL_SYSTEM_DATABASES,
                "default_character_set": row["default_character_set"],
                "default_collation": row["default_collation"],
                "table_count": int(row["table_count"] or 0), "view_count": int(row["view_count"] or 0),
                "estimated_rows": int(row["estimated_rows"] or 0),
                "data_bytes": int(row["data_bytes"] or 0), "index_bytes": int(row["index_bytes"] or 0),
                "routine_count": routine_map.get(row["name"], 0),
                "trigger_count": trigger_map.get(row["name"], 0),
            })
        return {
            "engine": "mysql",
            "server": {
                "version": str(server_row.get("version", "")),
                "version_comment": str(server_row.get("version_comment", "")),
                "host": str(server_row.get("hostname", profile["host"])),
                "port": int(server_row.get("port") or profile["port"]),
                "character_set": str(server_row.get("character_set", "")),
                "collation": str(server_row.get("collation", "")),
                "sql_mode": str(server_row.get("sql_mode", "")),
                "lower_case_table_names": int(server_row.get("lower_case_table_names") or 0),
                "max_connections": int(server_row.get("max_connections") or 0),
            },
            "databases": databases,
            "totals": {
                "database_count": len(databases),
                "table_count": sum(item["table_count"] for item in databases),
                "view_count": sum(item["view_count"] for item in databases),
                "estimated_rows": sum(item["estimated_rows"] for item in databases),
                "data_bytes": sum(item["data_bytes"] for item in databases),
                "index_bytes": sum(item["index_bytes"] for item in databases),
            },
        }

    def schema(self, connection_id: str, databases: list[str] | None = None) -> dict[str, Any]:
        profile = self.get_connection(connection_id)
        if profile["engine"] == "sqlite":
            return self._sqlite_schema(profile)
        return self._mysql_schema(profile, databases)

    def _sqlite_schema(self, profile: dict[str, Any]) -> dict[str, Any]:
        path = self._allowed_source(profile["location"])
        tables: list[dict[str, Any]] = []
        relationships: list[dict[str, str]] = []
        with self._source_connection(path) as conn:
            rows = conn.execute(
                "SELECT name,type FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for row in rows:
                name = row["name"]
                quoted = self._sqlite_identifier(name)
                columns = [{
                    "name": col["name"], "type": col["type"] or "", "column_type": col["type"] or "",
                    "nullable": not bool(col["notnull"]), "default": col["dflt_value"],
                    "primary_key": bool(col["pk"]), "extra": "", "comment": "", "hidden": bool(col["hidden"]),
                } for col in conn.execute("PRAGMA table_xinfo(%s)" % quoted).fetchall()]
                indexes = conn.execute("PRAGMA index_list(%s)" % quoted).fetchall() if row["type"] == "table" else []
                tables.append({
                    "name": name, "qualified_name": name, "database": path.name, "kind": row["type"],
                    "engine": "SQLite", "estimated_rows": None, "data_bytes": None, "index_bytes": None,
                    "comment": "", "index_count": len(indexes), "columns": columns, "system": False,
                })
                if row["type"] == "table":
                    for fk in conn.execute("PRAGMA foreign_key_list(%s)" % quoted).fetchall():
                        relationships.append({"from_table": name, "from_column": fk["from"],
                                              "to_table": fk["table"], "to_column": fk["to"]})
        return self._schema_result(profile, tables, relationships)

    def _mysql_target_databases(self, profile: dict[str, Any], requested: list[str] | None) -> list[str]:
        if requested:
            return list(dict.fromkeys(requested))
        if profile.get("database_name"):
            return [part.strip() for part in profile["database_name"].split(",") if part.strip()]
        inventory = self._mysql_inventory(profile)
        return [item["name"] for item in inventory["databases"] if not item["system"]]

    def _mysql_schema(self, profile: dict[str, Any], requested: list[str] | None) -> dict[str, Any]:
        targets = self._mysql_target_databases(profile, requested)
        if not targets:
            return self._schema_result(profile, [], [])
        placeholders = ",".join(["%s"] * len(targets))
        conn = self._mysql_connection(profile)
        try:
            with conn.cursor() as cursor:
                tables_raw = self._mysql_rows(cursor, """
                    SELECT TABLE_SCHEMA AS database_name,TABLE_NAME AS name,TABLE_TYPE AS kind,
                           ENGINE AS engine,TABLE_ROWS AS estimated_rows,DATA_LENGTH AS data_bytes,
                           INDEX_LENGTH AS index_bytes,TABLE_COMMENT AS comment
                    FROM information_schema.TABLES WHERE TABLE_SCHEMA IN (%s)
                    ORDER BY TABLE_SCHEMA,TABLE_NAME
                """ % placeholders, tuple(targets))
                columns_raw = self._mysql_rows(cursor, """
                    SELECT TABLE_SCHEMA AS database_name,TABLE_NAME AS table_name,COLUMN_NAME AS name,
                           ORDINAL_POSITION AS position,COLUMN_DEFAULT AS default_value,
                           IS_NULLABLE AS is_nullable,DATA_TYPE AS data_type,COLUMN_TYPE AS column_type,
                           COLUMN_KEY AS column_key,EXTRA AS extra,COLUMN_COMMENT AS comment
                    FROM information_schema.COLUMNS WHERE TABLE_SCHEMA IN (%s)
                    ORDER BY TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION
                """ % placeholders, tuple(targets))
                index_raw = self._mysql_rows(cursor, """
                    SELECT TABLE_SCHEMA AS database_name,TABLE_NAME AS table_name,
                           COUNT(DISTINCT INDEX_NAME) AS index_count
                    FROM information_schema.STATISTICS WHERE TABLE_SCHEMA IN (%s)
                    GROUP BY TABLE_SCHEMA,TABLE_NAME
                """ % placeholders, tuple(targets))
                relationships = self._mysql_rows(cursor, """
                    SELECT TABLE_SCHEMA AS from_database,TABLE_NAME AS from_name,COLUMN_NAME AS from_column,
                           REFERENCED_TABLE_SCHEMA AS to_database,REFERENCED_TABLE_NAME AS to_name,
                           REFERENCED_COLUMN_NAME AS to_column
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA IN (%s) AND REFERENCED_TABLE_NAME IS NOT NULL
                    ORDER BY TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME
                """ % placeholders, tuple(targets))
        finally:
            conn.close()
        columns: dict[str, list[dict[str, Any]]] = {}
        for col in columns_raw:
            key = "%s.%s" % (col["database_name"], col["table_name"])
            columns.setdefault(key, []).append({
                "name": col["name"], "type": col["data_type"] or "", "column_type": col["column_type"] or "",
                "nullable": col["is_nullable"] == "YES", "default": col["default_value"],
                "primary_key": col["column_key"] == "PRI", "extra": col["extra"] or "",
                "comment": col["comment"] or "", "hidden": False,
            })
        index_map = {"%s.%s" % (row["database_name"], row["table_name"]): int(row["index_count"] or 0)
                     for row in index_raw}
        tables = []
        for row in tables_raw:
            qualified = "%s.%s" % (row["database_name"], row["name"])
            tables.append({
                "name": row["name"], "qualified_name": qualified, "database": row["database_name"],
                "kind": "view" if row["kind"] == "VIEW" else "table", "engine": row["engine"] or "",
                "estimated_rows": int(row["estimated_rows"] or 0), "data_bytes": int(row["data_bytes"] or 0),
                "index_bytes": int(row["index_bytes"] or 0), "comment": row["comment"] or "",
                "index_count": index_map.get(qualified, 0), "columns": columns.get(qualified, []), "system": False,
            })
        normalized_relations = [{
            "from_table": "%s.%s" % (row["from_database"], row["from_name"]),
            "from_column": row["from_column"],
            "to_table": "%s.%s" % (row["to_database"], row["to_name"]),
            "to_column": row["to_column"],
        } for row in relationships]
        return self._schema_result(profile, tables, normalized_relations)

    def _schema_result(self, profile: dict[str, Any], tables: list[dict[str, Any]],
                       relationships: list[dict[str, str]]) -> dict[str, Any]:
        selected = {item["table_name"]: item for item in self.selected_table_details(profile["id"])}
        for table in tables:
            detail = selected.get(table["qualified_name"])
            table["selected"] = detail is not None
            table["business_domain"] = detail["business_domain"] if detail else ""
            table["usage_purpose"] = detail["usage_purpose"] if detail else ""
        return {"connection": profile, "tables": tables, "relationships": relationships,
                "totals": {"table_count": sum(t["kind"] == "table" for t in tables),
                           "view_count": sum(t["kind"] == "view" for t in tables),
                           "column_count": sum(len(t["columns"]) for t in tables),
                           "relationship_count": len(relationships)}}

    def selected_tables(self, connection_id: str) -> list[str]:
        return [item["table_name"] for item in self.selected_table_details(connection_id)]

    def selected_table_details(self, connection_id: str) -> list[dict[str, Any]]:
        self.get_connection(connection_id)
        return [dict(row) for row in self._connection().execute(
            "SELECT table_name,business_domain,usage_purpose,selected_at FROM selected_tables "
            "WHERE connection_id=? ORDER BY table_name", (connection_id,)).fetchall()]

    def select_tables(self, connection_id: str, selections: list[Any],
                      databases: list[str] | None = None) -> list[dict[str, Any]]:
        if not isinstance(selections, list):
            raise IntegratorError("tables must be an array")
        profile = self.get_connection(connection_id)
        if databases is not None and (not isinstance(databases, list) or
                                      not all(isinstance(item, str) and item for item in databases)):
            raise IntegratorError("databases must be an array of names")
        if profile["engine"] == "mysql" and not databases:
            databases = list(dict.fromkeys(
                str(entry.get("table_name") if isinstance(entry, dict) else entry).split(".", 1)[0]
                for entry in selections if "." in str(
                    entry.get("table_name") if isinstance(entry, dict) else entry))) or None
        available = {table["qualified_name"]
                     for table in self.schema(connection_id, databases)["tables"]}
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in selections:
            if isinstance(entry, str):
                item = {"table_name": entry, "business_domain": "", "usage_purpose": ""}
            elif isinstance(entry, dict):
                item = {"table_name": str(entry.get("table_name") or ""),
                        "business_domain": str(entry.get("business_domain") or "").strip(),
                        "usage_purpose": str(entry.get("usage_purpose") or "").strip()}
            else:
                raise IntegratorError("each table selection must be text or an object")
            if item["table_name"] not in available:
                raise IntegratorError("unknown table: %s" % item["table_name"])
            if item["table_name"] not in seen:
                seen.add(item["table_name"])
                normalized.append(item)
        now = self._now()
        with self._write_lock:
            conn = self._connection()
            conn.execute("DELETE FROM selected_tables WHERE connection_id=?", (connection_id,))
            conn.executemany("""
                INSERT INTO selected_tables
                    (connection_id,table_name,business_domain,usage_purpose,selected_at)
                VALUES (?,?,?,?,?)
            """, [(connection_id, item["table_name"], item["business_domain"],
                    item["usage_purpose"], now) for item in normalized])
            if normalized:
                placeholders = ",".join("?" for _item in normalized)
                conn.execute(
                    "DELETE FROM ontology_definitions WHERE connection_id=? "
                    "AND table_name NOT IN (%s)" % placeholders,
                    (connection_id, *(item["table_name"] for item in normalized)))
            else:
                conn.execute("DELETE FROM ontology_definitions WHERE connection_id=?", (connection_id,))
            conn.commit()
        return self.selected_table_details(connection_id)

    @staticmethod
    def _words(value: str) -> list[str]:
        return [part.lower() for part in re.findall(r"[A-Za-z0-9]+", value.replace("_", " "))]

    @classmethod
    def _column_semantics(cls, name: str, data_type: str) -> tuple[str, float]:
        words = set(cls._words(name))
        upper_type = data_type.upper()
        if words.intersection({"id", "key", "uuid", "code"}): return "identifier", 0.9
        if words.intersection({"created", "updated", "date", "time", "timestamp", "year", "month"}): return "temporal", 0.86
        if words.intersection({"status", "type", "category", "kind", "state"}): return "classification", 0.82
        if words.intersection({"amount", "price", "total", "count", "quantity", "rate", "score"}): return "measure", 0.84
        if words.intersection({"name", "title", "description", "label", "summary"}): return "descriptive", 0.8
        if any(token in upper_type for token in ("INT", "REAL", "NUM", "DEC", "FLOAT")): return "measure", 0.68
        if any(token in upper_type for token in ("DATE", "TIME")): return "temporal", 0.72
        return "attribute", 0.62

    @classmethod
    def _label(cls, value: str) -> str:
        words = cls._words(value.split(".")[-1])
        return " ".join(word.capitalize() for word in words) or value

    def ontology_suggestions(self, connection_id: str) -> list[dict[str, Any]]:
        selection_details = {item["table_name"]: item for item in self.selected_table_details(connection_id)}
        if not selection_details:
            raise IntegratorError("select at least one business table before generating ontology suggestions")
        profile = self.get_connection(connection_id)
        databases = (list(dict.fromkeys(name.split(".", 1)[0] for name in selection_details
                                        if "." in name)) or None
                     if profile["engine"] == "mysql" else None)
        schema = self.schema(connection_id, databases)
        suggestions: list[dict[str, Any]] = []
        for table in schema["tables"]:
            qualified = table["qualified_name"]
            if qualified not in selection_details:
                continue
            selection = selection_details[qualified]
            description = selection["usage_purpose"] or "Business meaning of source table %s" % qualified
            suggestions.append({
                "target_type": "table", "table_name": qualified, "column_name": "",
                "label": self._label(qualified), "description": description, "synonyms": [],
                "semantic_type": selection["business_domain"] or "entity", "confidence": 0.75,
            })
            for column in table["columns"]:
                semantic_type, confidence = self._column_semantics(column["name"], column["type"])
                words = self._words(column["name"])
                suggestions.append({
                    "target_type": "column", "table_name": qualified, "column_name": column["name"],
                    "label": self._label(column["name"]),
                    "description": column.get("comment") or "%s field from %s" % (semantic_type.capitalize(), qualified),
                    "synonyms": [" ".join(words)] if words else [],
                    "semantic_type": semantic_type, "confidence": confidence,
                })
        return suggestions

    def apply_ontology(self, connection_id: str, definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(definitions, list) or not definitions:
            raise IntegratorError("definitions must be a non-empty array")
        selected = set(self.selected_tables(connection_id))
        profile = self.get_connection(connection_id)
        databases = (list(dict.fromkeys(name.split(".", 1)[0] for name in selected
                                        if "." in name)) or None
                     if profile["engine"] == "mysql" else None)
        schema = self.schema(connection_id, databases)
        columns_by_table = {table["qualified_name"]: {col["name"] for col in table["columns"]}
                            for table in schema["tables"] if table["qualified_name"] in selected}
        now = self._now()
        rows = []
        for definition in definitions:
            if not isinstance(definition, dict):
                raise IntegratorError("each ontology definition must be an object")
            table_name = str(definition.get("table_name") or "")
            column_name = str(definition.get("column_name") or "")
            target_type = str(definition.get("target_type") or ("column" if column_name else "table"))
            if table_name not in selected:
                raise IntegratorError("ontology target is not a selected business table: %s" % table_name)
            if target_type not in {"table", "column"}:
                raise IntegratorError("ontology target_type must be table or column")
            if target_type == "table" and column_name:
                raise IntegratorError("table ontology definitions cannot specify column_name")
            if target_type == "column" and (not column_name or
                    column_name not in columns_by_table.get(table_name, set())):
                raise IntegratorError("unknown ontology column: %s.%s" % (table_name, column_name))
            label = str(definition.get("label") or "").strip()
            if not label:
                raise IntegratorError("ontology label is required")
            synonyms = definition.get("synonyms") or []
            if isinstance(synonyms, str):
                synonyms = [part.strip() for part in synonyms.split(",") if part.strip()]
            if not isinstance(synonyms, list):
                raise IntegratorError("synonyms must be an array or comma-separated text")
            if not all(isinstance(item, str) and item.strip() for item in synonyms):
                raise IntegratorError("each ontology synonym must be non-empty text")
            synonyms = [item.strip() for item in synonyms]
            raw_confidence = definition.get("confidence", 0.0)
            if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
                raise IntegratorError("ontology confidence must be a number from 0 to 1")
            confidence = float(raw_confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise IntegratorError("ontology confidence must be a number from 0 to 1")
            rows.append((str(uuid.uuid4()), connection_id, table_name, column_name, target_type,
                         label, str(definition.get("description") or ""),
                         json.dumps(synonyms, ensure_ascii=False),
                         str(definition.get("semantic_type") or "attribute"),
                         confidence, now))
        with self._write_lock:
            conn = self._connection()
            conn.execute("DELETE FROM ontology_definitions WHERE connection_id=?", (connection_id,))
            conn.executemany("""
                INSERT INTO ontology_definitions
                    (id,connection_id,table_name,column_name,target_type,label,description,
                     synonyms,semantic_type,confidence,status,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'applied',?)
                ON CONFLICT(connection_id,table_name,column_name,target_type) DO UPDATE SET
                    label=excluded.label,description=excluded.description,synonyms=excluded.synonyms,
                    semantic_type=excluded.semantic_type,confidence=excluded.confidence,
                    status='applied',updated_at=excluded.updated_at
            """, rows)
            conn.commit()
        return self.ontology(connection_id)

    def ontology(self, connection_id: str) -> list[dict[str, Any]]:
        self.get_connection(connection_id)
        result = []
        for row in self._connection().execute(
                "SELECT * FROM ontology_definitions WHERE connection_id=? "
                "ORDER BY table_name,target_type,column_name", (connection_id,)).fetchall():
            item = dict(row)
            try: item["synonyms"] = json.loads(item["synonyms"])
            except (TypeError, ValueError): item["synonyms"] = []
            result.append(item)
        return result

    def workflow(self) -> dict[str, Any]:
        conn = self._connection()
        connection_count = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
        connected_count = conn.execute("SELECT COUNT(*) FROM connections WHERE status='connected'").fetchone()[0]
        selected_count = conn.execute("SELECT COUNT(*) FROM selected_tables").fetchone()[0]
        ontology_count = conn.execute("SELECT COUNT(*) FROM ontology_definitions").fetchone()[0]
        ready_selection_count = conn.execute("""
            SELECT COUNT(*) FROM selected_tables s
            JOIN connections c ON c.id=s.connection_id AND c.status='connected'
        """).fetchone()[0]
        complete = bool(conn.execute("""
            SELECT EXISTS(
                SELECT 1 FROM connections c
                WHERE c.status='connected'
                  AND EXISTS(SELECT 1 FROM selected_tables s WHERE s.connection_id=c.id)
                  AND NOT EXISTS(
                    SELECT 1 FROM selected_tables s
                    WHERE s.connection_id=c.id AND NOT EXISTS(
                        SELECT 1 FROM ontology_definitions o
                        WHERE o.connection_id=c.id AND o.table_name=s.table_name))
            )
        """).fetchone()[0])
        step = (1 if not connection_count else 2 if not connected_count else
                3 if not ready_selection_count else 4)
        return {"current_step": step, "connection_count": int(connection_count),
                "connected_count": int(connected_count), "selected_table_count": int(selected_count),
                "ontology_count": int(ontology_count),
                "complete": complete}
