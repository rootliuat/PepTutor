#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/LightRAG"
FRONTEND_DIR="${ROOT_DIR}/frontend/airi"
SERVER_BIN="${PEPTUTOR_LESSON_SMOKE_SERVER_BIN:-${BACKEND_DIR}/.venv/bin/lightrag-server}"
WAIT_SCRIPT="${PEPTUTOR_LESSON_SMOKE_WAIT_SCRIPT:-${ROOT_DIR}/scripts/wait-for-lesson-backend.sh}"
LOG_DIR="${PEPTUTOR_LESSON_SMOKE_LOG_DIR:-${BACKEND_DIR}/temp}"
LOG_PATH="${LOG_DIR}/smoke_lesson_browser_$(date +%Y%m%d_%H%M%S).log"
LESSON_BACKEND_HOST="127.0.0.1"
LESSON_BACKEND_PORT="9625"
KEEP_SERVER="${PEPTUTOR_LESSON_SMOKE_KEEP_SERVER:-0}"
FULL_STACK="${PEPTUTOR_LESSON_SMOKE_FULL_STACK:-0}"
SERVER_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/smoke_lesson_browser.sh

Start a temporary route-focused LightRAG lesson backend, wait for it to answer
GET /lesson/catalog on http://127.0.0.1:9625, run the checked-in Chromium
/lesson real-browser suite, then stop the backend.

Environment overrides:
  PEPTUTOR_LESSON_SMOKE_FULL_STACK=1   Keep the current vector/SimpleMem env.
  PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1  Leave the backend running after the suite.
EOF
}

is_enabled() {
  local value="${1:-}"
  case "${value,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

cleanup() {
  if [[ -z "${SERVER_PID}" ]]; then
    return
  fi

  if is_enabled "${KEEP_SERVER}"; then
    disown "${SERVER_PID}" 2>/dev/null || true
    echo "[INFO] Lesson browser backend left running at http://${LESSON_BACKEND_HOST}:${LESSON_BACKEND_PORT} (pid=${SERVER_PID}, log=${LOG_PATH})"
    return
  fi

  if kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}

print_backend_log_tail() {
  if [[ -f "${LOG_PATH}" ]]; then
    echo "[INFO] Backend log tail (${LOG_PATH}):" >&2
    tail -n 40 "${LOG_PATH}" >&2 || true
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "${SERVER_BIN}" ]]; then
  echo "Missing LightRAG server binary: ${SERVER_BIN}" >&2
  echo "Install backend/LightRAG/.venv first." >&2
  exit 1
fi

if [[ ! -f "${WAIT_SCRIPT}" ]]; then
  echo "Missing lesson-backend wait script: ${WAIT_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
trap cleanup EXIT

server_env=(
  "PEPTUTOR_LESSON_LIVE_PROMPTS=1"
  "PEPTUTOR_DEBUG_SIGNALS=1"
)

if ! is_enabled "${FULL_STACK}"; then
  server_env+=(
    "PEPTUTOR_LESSON_VECTOR_RETRIEVAL=0"
    "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=0"
    "PEPTUTOR_SIMPLEMEM_WRITEBACK=0"
    "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=0"
  )
fi

echo "[INFO] Starting lesson browser backend at http://${LESSON_BACKEND_HOST}:${LESSON_BACKEND_PORT}"
echo "[INFO] Backend log: ${LOG_PATH}"
echo "[INFO] Full-stack mode: $(if is_enabled "${FULL_STACK}"; then echo on; else echo off; fi)"

(
  cd "${BACKEND_DIR}"
  exec env "${server_env[@]}" "${SERVER_BIN}" --host "${LESSON_BACKEND_HOST}" --port "${LESSON_BACKEND_PORT}"
) >"${LOG_PATH}" 2>&1 &
SERVER_PID="$!"

if is_enabled "${KEEP_SERVER}"; then
  disown "${SERVER_PID}" 2>/dev/null || true
fi

if ! bash "${WAIT_SCRIPT}" --url "http://${LESSON_BACKEND_HOST}:${LESSON_BACKEND_PORT}" --timeout 120; then
  print_backend_log_tail
  exit 1
fi

echo "[INFO] Running checked-in /lesson real-browser suite"
if ! (
  cd "${FRONTEND_DIR}"
  pnpm -F @proj-airi/stage-web test:run:browser:real
); then
  print_backend_log_tail
  exit 1
fi

echo "[PASS] Lesson browser smoke completed."
