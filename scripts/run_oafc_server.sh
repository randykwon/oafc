#!/usr/bin/env bash
# OAFC 로컬 서버 실행 스크립트
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m empsearch.web_agent --host "${OAFC_HOST:-127.0.0.1}" --port "${OAFC_PORT:-8765}"
