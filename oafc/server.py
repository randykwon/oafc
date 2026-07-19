"""Secure standard-library HTTP server for OAFC DB Integrator."""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .metadata import IntegratorError, IntegratorStore, NotFoundError


PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
DEFAULT_DATA_DIR = PACKAGE_DIR.parent / "data"
MAX_BODY_BYTES = int(os.environ.get("OAFC_MAX_BODY_BYTES", str(2 * 1024 * 1024)))


class RequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def is_loopback(host: str) -> bool:
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_store(metadata_path: str | None = None,
                discovery_roots: list[str] | None = None) -> IntegratorStore:
    metadata = Path(metadata_path or os.environ.get(
        "OAFC_METADATA_DB", str(DEFAULT_DATA_DIR / "oafc-integrator.db")))
    if discovery_roots is None:
        configured = os.environ.get("OAFC_DISCOVERY_ROOTS")
        discovery_roots = configured.split(os.pathsep) if configured else [str(DEFAULT_DATA_DIR)]
    return IntegratorStore(metadata, discovery_roots)


class IntegratorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: IntegratorStore,
                 api_token: str = "", allowed_hosts: set[str] | None = None,
                 public_origin: str = ""):
        super().__init__(address, IntegratorHandler)
        self.store = store
        self.api_token = api_token
        self.allowed_hosts = {host.lower().rstrip(".") for host in (allowed_hosts or set())}
        self.public_origin = public_origin.rstrip("/")
        if is_loopback(address[0]):
            self.allowed_hosts.update({"localhost", "127.0.0.1", "::1", address[0]})


def create_server(host: str, port: int, store: IntegratorStore,
                  api_token: str = "", allowed_hosts: set[str] | None = None,
                  public_origin: str = "") -> IntegratorHTTPServer:
    if not is_loopback(host):
        if not api_token:
            raise ValueError("OAFC_API_TOKEN is required for a non-loopback bind")
        if not allowed_hosts:
            raise ValueError("OAFC_ALLOWED_HOSTS is required for a non-loopback bind")
    return IntegratorHTTPServer((host, port), store, api_token, allowed_hosts, public_origin)


class IntegratorHandler(BaseHTTPRequestHandler):
    server: IntegratorHTTPServer
    server_version = "OAFC-DB-Integrator/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("OAFC_HTTP_LOG") == "1":
            super().log_message(format, *args)

    def _json(self, payload: Any, status: int = 200,
              extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int) -> None:
        self._json({"error": message}, status)

    def _host_authority(self) -> tuple[str, int | None]:
        value = (self.headers.get("Host") or "").strip()
        try:
            parsed = urllib.parse.urlsplit("//" + value)
            return (parsed.hostname or "").lower().rstrip("."), parsed.port or 80
        except ValueError:
            return "", None

    def _authorize(self, mutating: bool = False, require_token: bool = True) -> bool:
        host, port = self._host_authority()
        if not host or host not in self.server.allowed_hosts:
            self._error("Host is not allowed", 421)
            return False
        if require_token and self.server.api_token:
            auth = self.headers.get("Authorization") or ""
            supplied = self.headers.get("X-OAFC-Token") or ""
            if auth.lower().startswith("bearer "):
                supplied = auth[7:].strip()
            if not supplied or not hmac.compare_digest(supplied, self.server.api_token):
                self._json({"error": "API authentication required"}, 401,
                           {"WWW-Authenticate": 'Bearer realm="OAFC"'})
                return False
        if mutating:
            origin = self.headers.get("Origin")
            if origin:
                if self.server.public_origin:
                    valid_origin = origin.rstrip("/") == self.server.public_origin
                else:
                    try:
                        parsed = urllib.parse.urlsplit(origin)
                        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
                        valid_origin = parsed.scheme == "http" and (
                            parsed.hostname or "").lower().rstrip(".") == host and origin_port == port
                    except ValueError:
                        valid_origin = False
                if not valid_origin:
                    self._error("Cross-origin mutation is not allowed", 403)
                    return False
            if (self.headers.get("Sec-Fetch-Site") or "").lower() in {"same-site", "cross-site"}:
                self._error("Cross-site mutation is not allowed", 403)
                return False
            if self.command in {"POST", "PUT"}:
                content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                if content_type != "application/json":
                    self._error("Content-Type must be application/json", 415)
                    return False
        return True

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise RequestError("invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise RequestError("request body is too large", 413)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError("invalid JSON body") from exc
        if not isinstance(body, dict):
            raise RequestError("JSON body must be an object")
        return body

    @staticmethod
    def _route(path: str) -> tuple[str | None, str | None]:
        match = re.fullmatch(r"/api/connections/([0-9a-fA-F-]+)(?:/(test|inventory|schema|tables|ontology|ontology/suggest|ontology/apply|analysis/query))?", path)
        return match.groups() if match else (None, None)

    def _dispatch(self, callback) -> None:
        try:
            callback()
        except RequestError as exc:
            self._error(str(exc), exc.status)
        except NotFoundError as exc:
            self._error(str(exc), 404)
        except IntegratorError as exc:
            self._error(str(exc), 400)
        except Exception:
            self._error("internal server error", 500)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.startswith("/api/"):
            if not self._authorize():
                return
            self._dispatch(lambda: self._api_get(parsed.path, urllib.parse.parse_qs(parsed.query)))
            return
        if not self._authorize(require_token=False):
            return
        self._serve_static(parsed.path)

    def _api_get(self, path: str, query: dict[str, list[str]]) -> None:
        store = self.server.store
        if path == "/api/workflow":
            self._json(store.workflow())
            return
        if path == "/api/discovery":
            self._json({"databases": store.discover()})
            return
        if path == "/api/connections":
            self._json({"connections": store.list_connections()})
            return
        connection_id, action = self._route(path)
        if connection_id:
            if action is None:
                self._json(store.get_connection(connection_id))
            elif action == "inventory":
                self._json(store.inventory(connection_id))
            elif action == "schema":
                databases = query.get("database") or None
                self._json(store.schema(connection_id, databases))
            elif action == "tables":
                self._json({"tables": store.selected_table_details(connection_id)})
            elif action == "ontology":
                self._json({"definitions": store.ontology(connection_id)})
            else:
                raise NotFoundError("route not found")
            return
        raise NotFoundError("route not found")

    def do_POST(self) -> None:
        if not self._authorize(mutating=True):
            return
        parsed = urllib.parse.urlsplit(self.path)
        self._dispatch(lambda: self._api_post(parsed.path))

    def _api_post(self, path: str) -> None:
        store = self.server.store
        body = self._body()
        if path == "/api/connections":
            self._json(store.save_connection(body), 201)
            return
        connection_id, action = self._route(path)
        if not connection_id:
            raise NotFoundError("route not found")
        if action == "test":
            self._json(store.test_connection(connection_id))
        elif action == "analysis/query":
            self._json(store.analyze_query(
                connection_id, body.get("query"), body.get("database"),
                body.get("max_rows", 100), body.get("timeout_ms", 5_000)))
        elif action == "ontology/suggest":
            self._json({"suggestions": store.ontology_suggestions(connection_id)})
        elif action == "ontology/apply":
            self._json({"definitions": store.apply_ontology(
                connection_id, body.get("definitions") or [])})
        else:
            raise NotFoundError("route not found")

    def do_PUT(self) -> None:
        if not self._authorize(mutating=True):
            return
        parsed = urllib.parse.urlsplit(self.path)
        self._dispatch(lambda: self._api_put(parsed.path))

    def _api_put(self, path: str) -> None:
        connection_id, action = self._route(path)
        if not connection_id or action != "tables":
            raise NotFoundError("route not found")
        body = self._body()
        self._json({"tables": self.server.store.select_tables(
            connection_id, body.get("tables"), body.get("databases"))})

    def do_DELETE(self) -> None:
        if not self._authorize(mutating=True):
            return
        parsed = urllib.parse.urlsplit(self.path)
        self._dispatch(lambda: self._api_delete(parsed.path))

    def _api_delete(self, path: str) -> None:
        connection_id, action = self._route(path)
        if not connection_id or action is not None:
            raise NotFoundError("route not found")
        self.server.store.delete_connection(connection_id)
        self._json({"deleted": True})

    def _serve_static(self, path: str) -> None:
        mapping = {"/": "index.html", "/index.html": "index.html",
                   "/app.js": "app.js", "/app.css": "app.css"}
        filename = mapping.get(path)
        if not filename:
            self.send_error(404)
            return
        target = (WEB_DIR / filename).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + (
            "; charset=utf-8" if content_type.startswith("text/") or "javascript" in content_type else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="OAFC DB Integrator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--metadata-db", default=None)
    parser.add_argument("--discovery-root", action="append", default=None)
    args = parser.parse_args()

    token = os.environ.get("OAFC_API_TOKEN", "")
    allowed = {item.strip() for item in os.environ.get("OAFC_ALLOWED_HOSTS", "").split(",") if item.strip()}
    public_origin = os.environ.get("OAFC_PUBLIC_ORIGIN", "")
    store = build_store(args.metadata_db, args.discovery_root)
    server = create_server(args.host, args.port, store, token, allowed, public_origin)
    print("OAFC DB Integrator: http://%s:%d" % server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close_thread_connection()


if __name__ == "__main__":
    main()
