"""OAFC 로컬 웹 서버.

실행:
    python3 -m empsearch.web_agent --host 127.0.0.1 --port 8765

라우팅:
    /               홈
    /data-manager   Data Integrator (구 Data Manager)
    /ontology       Ontology Definer
    /agent-builder  Agent Builder
    /agent-shop     Agent Shop
    /schema         Schema Graph
    /chatbots       챗봇 (임직원 검색 호환)
    /unstructured, /information-center, /data-integration -> Data Integrator
"""

import argparse
import io
import json
import mimetypes
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db, nlq, ontology_ai

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_static")

# 업로드/요청 본문 상한 (메모리 보호). 필요시 환경변수로 조정.
MAX_REQUEST_BYTES = int(os.environ.get("OAFC_MAX_REQUEST_BYTES", str(50 * 1024 * 1024)))

PAGE_ROUTES = {
    "/": "index.html",
    "/data-manager": "unstructured.html",
    "/unstructured": "unstructured.html",
    "/information-center": "unstructured.html",
    "/data-integration": "unstructured.html",
    "/ontology": "ontology.html",
    "/agent-builder": "agent_builder.html",
    "/agent-shop": "agent_shop.html",
    "/schema": "schema.html",
    "/chatbots": "app.html",
    "/chatbot": "app.html",
}

TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".html", ".htm", ".rtf"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".odt", ".xlsx", ".pptx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

MULTIMODAL_HINTS = {
    "image": ["OCR", "객체/장면 태깅", "이미지 설명 생성"],
    "audio": ["음성 전사", "화자/키워드 추출", "요약"],
    "video": ["장면 분할", "음성 전사", "프레임 OCR", "객체 태깅"],
}

_STOPWORDS = set("""the a an and or of to in is are was were be been for on with as at by
it this that from 그리고 그러나 하지만 또한 있는 있다 없는 없다 하는 한다 및 등 수 것 되어 된다
위한 대한 통해 하며 이 그 저 를 을 은 는 가 의 에 로 으로""".split())


# ---------------------------------------------------------------------------
# unstructured analysis helpers
# ---------------------------------------------------------------------------

def classify_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image", "이미지"
    if ext in AUDIO_EXTS:
        return "audio", "음성"
    if ext in VIDEO_EXTS:
        return "video", "영상"
    if ext in TEXT_EXTS:
        return "text", "텍스트 문서"
    if ext in DOC_EXTS:
        return "document", "오피스/PDF 문서"
    return "other", "기타"


def extract_keywords(text, top=12):
    words = re.findall(r"[A-Za-z가-힣0-9_]{2,}", text)
    counter = Counter(w for w in words if w.lower() not in _STOPWORDS and not w.isdigit())
    return [w for w, _ in counter.most_common(top)]


def strip_html(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def analyze_text_content(filename, text):
    kind, kind_label = classify_file(filename)
    keywords = extract_keywords(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    summary = " ".join(lines[:3])[:400] if lines else ""
    return {
        "filename": filename,
        "kind": kind,
        "kind_label": kind_label,
        "size": len(text.encode("utf-8", "ignore")),
        "text_length": len(text),
        "keywords": keywords,
        "summary": summary,
        "content_preview": text[:4000],
    }


def analyze_binary(filename, data):
    kind, kind_label = classify_file(filename)
    result = {
        "filename": filename,
        "kind": kind,
        "kind_label": kind_label,
        "size": len(data),
        "text_length": 0,
        "keywords": [],
        "summary": "",
        "content_preview": "",
    }
    if kind in MULTIMODAL_HINTS:
        result["multimodal_hints"] = MULTIMODAL_HINTS[kind]
        result["pipeline_candidate"] = {
            "image": "Extract / OCR 단계 포함 Bronze 수집 Pipeline",
            "audio": "Transcribe(STT) 단계 포함 Bronze 수집 Pipeline",
            "video": "장면 분할 + Transcribe + 프레임 OCR Pipeline",
        }[kind]
        result["summary"] = ("%s 자산. 실제 OCR/STT/비전 모델 호출은 미구현이며 "
                             "Pipeline 후보로 정보화되었다." % kind_label)
    else:
        result["summary"] = "%s (%d bytes). 텍스트 추출 미지원 형식." % (kind_label, len(data))
    return result


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class RequestTooLarge(Exception):
    """요청 본문이 MAX_REQUEST_BYTES 를 초과했을 때."""


class Handler(BaseHTTPRequestHandler):
    server_version = "OAFC/0.8"

    # -- helpers ------------------------------------------------------------

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg, status=400):
        self._json({"error": msg}, status)

    def _file(self, name):
        path = os.path.normpath(os.path.join(STATIC_DIR, name))
        # STATIC_DIR 하위 파일만 허용 (형제 디렉터리 'web_static_x' 나 '../' 탈출 차단)
        if not path.startswith(STATIC_DIR + os.sep) or not os.path.isfile(path):
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _content_length(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_REQUEST_BYTES:
            raise RequestTooLarge(
                "요청 본문 %d bytes 가 상한 %d bytes 를 초과했습니다." % (length, MAX_REQUEST_BYTES))
        return length

    def _read_json_body(self):
        length = self._content_length()
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt, *args):
        pass  # quiet

    # -- GET ----------------------------------------------------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in PAGE_ROUTES:
            return self._file(PAGE_ROUTES[path])

        if path.startswith("/api/"):
            return self._api_get(path, qs)

        # static assets
        name = path.lstrip("/")
        if name and os.path.isfile(os.path.join(STATIC_DIR, name)):
            return self._file(name)
        self.send_error(404)

    def _api_get(self, path, qs):
        project = (qs.get("project") or ["default"])[0]
        try:
            if path == "/api/schema":
                return self._json(db.get_schema())
            if path == "/api/summary":
                return self._json(db.get_summary())
            if path == "/api/table-data":
                table = (qs.get("table") or [""])[0]
                limit = (qs.get("limit") or ["50"])[0]
                return self._json(db.get_table_data(table, limit))
            if path == "/api/employees":
                return self._json(db.search_employees(
                    q=(qs.get("q") or [None])[0],
                    department=(qs.get("department") or [None])[0],
                    status=(qs.get("status") or [None])[0],
                    location=(qs.get("location") or [None])[0],
                    limit=(qs.get("limit") or ["50"])[0]))
            if path.startswith("/api/timeline/"):
                emp_no = urllib.parse.unquote(path[len("/api/timeline/"):])
                return self._json(db.get_timeline(emp_no))
            if path == "/api/ontology":
                return self._json({"definitions": db.ontology_list(project)})
            if path == "/api/database-info":
                return self._json(self._database_info())
            if path == "/api/external-schema":
                return self._json({
                    "error": "외부 DB 드라이버(psycopg2/pymysql)가 설치되어 있지 않습니다.",
                    "simulated": True,
                    "hint": "임베디드 모드에서는 /api/schema 를 사용하세요.",
                }, 200)
        except Exception as exc:
            return self._error(str(exc), 500)
        self.send_error(404)

    def _database_info(self):
        schema = db.get_schema()
        by_schema = {}
        for t in schema["tables"]:
            s = by_schema.setdefault(t["schema"], {"tables": 0, "rows": 0})
            s["tables"] += 1
            s["rows"] += t["row_estimate"]
        return {
            "engine": "embedded-sqlite",
            "path": db.DB_PATH,
            "note": "PostgreSQL/MySQL 미설치 환경용 임베디드 모드. "
                    "public=직원관리(PG 시뮬레이션), ganada=표준조직, "
                    "employee_salary_db=급여, employee_evaluation_db=평가(MySQL 시뮬레이션)",
            "schemas": by_schema,
            "seed_employees": db.SEED_EMPLOYEES,
        }

    # -- POST ---------------------------------------------------------------

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/agent":
                body = self._read_json_body()
                q = (body.get("question") or "").strip()
                if not q:
                    return self._error("question 이 비어 있습니다.")
                return self._json(nlq.answer(q, body.get("project") or "default"))

            if path == "/api/ontology":
                body = self._read_json_body()
                project = body.get("project") or "default"
                defs = body.get("definitions") or ([body["definition"]] if body.get("definition") else [])
                for d in defs:
                    db.ontology_save(d, project)
                return self._json({"saved": len(defs)})

            if path == "/api/ontology/infer":
                body = self._read_json_body()
                schema = db.get_schema()
                suggestions = ontology_ai.infer_for_tables(
                    schema["tables"],
                    only_tables=body.get("tables") or body.get("table"),
                    only_fields=body.get("fields"))
                return self._json({"suggestions": suggestions})

            if path == "/api/ontology/automate":
                body = self._read_json_body()
                project = body.get("project") or "default"
                schema = db.get_schema()
                suggestions = ontology_ai.infer_for_tables(
                    schema["tables"], only_tables=body.get("tables"))
                saved = 0
                if body.get("save", True):
                    for s in suggestions:
                        db.ontology_save(s, project)
                        saved += 1
                return self._json({"suggestions": suggestions, "saved": saved})

            if path == "/api/ontology/import":
                body = self._read_json_body()
                saved = db.ontology_import(
                    body.get("definitions") or [], body.get("project") or "default")
                return self._json({"saved": saved})

            if path == "/api/ontology/bulk-delete":
                body = self._read_json_body()
                n = db.ontology_bulk_delete(
                    body.get("scope") or "table",
                    body.get("table"),
                    body.get("field"),
                    body.get("project") or "default")
                return self._json({"deleted": n})

            if path == "/api/database-info":
                return self._json(self._database_info())

            if path == "/api/external-schema":
                return self._json({
                    "error": "외부 DB 드라이버(psycopg2/pymysql)가 설치되어 있지 않습니다.",
                    "simulated": True,
                    "hint": "임베디드 모드에서는 /api/schema 를 사용하세요.",
                }, 200)

            if path == "/api/ontology/delete":
                body = self._read_json_body()
                n = db.ontology_delete(
                    body.get("target_type") or "field",
                    body.get("table_name"),
                    body.get("field_name"),
                    body.get("project") or "default")
                return self._json({"deleted": n})

            if path == "/api/unstructured/upload":
                return self._handle_upload()

            if path == "/api/unstructured/url":
                body = self._read_json_body()
                return self._json(self._analyze_url((body.get("url") or "").strip()))

            if path == "/api/generated-metadata/reset":
                body = self._read_json_body()
                return self._json(db.reset_generated_metadata(body.get("project") or "default"))
        except RequestTooLarge as exc:
            return self._error(str(exc), 413)
        except Exception as exc:
            return self._error(str(exc), 500)
        self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/ontology":
            n = db.ontology_delete(
                (qs.get("target_type") or ["field"])[0],
                (qs.get("table_name") or [""])[0],
                (qs.get("field_name") or [""])[0],
                (qs.get("project") or ["default"])[0])
            return self._json({"deleted": n})
        self.send_error(404)

    # -- upload / url -------------------------------------------------------

    def _handle_upload(self):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            # JSON body: {files: [{name, content_base64 | text}]}
            body = self._read_json_body()
            results = []
            for f in body.get("files", []):
                name = f.get("name", "unnamed")
                if "text" in f:
                    results.append(analyze_text_content(name, f["text"]))
                else:
                    import base64
                    data = base64.b64decode(f.get("content_base64", ""))
                    results.append(self._analyze_bytes(name, data))
            return self._json({"results": results})

        boundary = ctype.split("boundary=")[-1].strip().encode()
        length = self._content_length()
        raw = self.rfile.read(length)
        results = []
        for part in raw.split(b"--" + boundary):
            part = part.strip()
            if not part or part == b"--":
                continue
            if b"\r\n\r\n" not in part:
                continue
            headers, content = part.split(b"\r\n\r\n", 1)
            content = content.rstrip(b"\r\n")
            m = re.search(rb'filename="([^"]*)"', headers)
            if not m or not m.group(1):
                continue
            filename = m.group(1).decode("utf-8", "ignore")
            results.append(self._analyze_bytes(filename, content))
        return self._json({"results": results})

    def _analyze_bytes(self, filename, data):
        ext = os.path.splitext(filename)[1].lower()
        if ext in TEXT_EXTS:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("cp949", "ignore")
            if ext in (".html", ".htm"):
                text = strip_html(text)
            return analyze_text_content(filename, text)
        return analyze_binary(filename, data)

    def _analyze_url(self, url):
        if not url:
            return {"error": "url 이 비어 있습니다."}
        yt = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{6,})", url)
        if yt:
            return {
                "url": url, "kind": "video", "kind_label": "YouTube 영상",
                "video_id": yt.group(1),
                "multimodal_hints": MULTIMODAL_HINTS["video"],
                "summary": "YouTube 영상 링크. 전사/장면 분석은 Pipeline 후보로 등록해 처리한다.",
                "keywords": [],
            }
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OAFC/0.8"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read(1_000_000)
            html = raw.decode("utf-8", "ignore")
        except Exception as exc:
            return {"url": url, "error": "URL 요청 실패: %s" % exc}
        title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        text = strip_html(html)
        return {
            "url": url,
            "kind": "web",
            "kind_label": "웹 문서",
            "title": (title_m.group(1).strip() if title_m else url)[:200],
            "text_length": len(text),
            "keywords": extract_keywords(text),
            "summary": text[:400],
            "content_preview": text[:4000],
        }


def main():
    parser = argparse.ArgumentParser(description="OAFC local web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    db.get_conn()  # ensure seeded before serving
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("OAFC: Ontology Agent Factory Creator")
    print("Serving on http://%s:%d" % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
