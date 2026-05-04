#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/LightRAG"
SERVER_BIN="${PEPTUTOR_LESSON_REGRESSION_SERVER_BIN:-${BACKEND_DIR}/.venv/bin/lightrag-server}"
PYTHON_BIN="${PEPTUTOR_LESSON_REGRESSION_PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
WAIT_SCRIPT="${PEPTUTOR_LESSON_REGRESSION_WAIT_SCRIPT:-${ROOT_DIR}/scripts/wait-for-lesson-backend.sh}"
MATRIX_SCRIPT="${PEPTUTOR_LESSON_REGRESSION_MATRIX_SCRIPT:-${ROOT_DIR}/scripts/smoke_lesson_matrix.py}"
BUDGET_GUARD_SCRIPT="${PEPTUTOR_TEST_BUDGET_GUARD_SCRIPT:-${ROOT_DIR}/scripts/test-budget-guard.sh}"
LOG_DIR="${PEPTUTOR_LESSON_REGRESSION_LOG_DIR:-${BACKEND_DIR}/temp}"
OUT_DIR="${PEPTUTOR_LESSON_REGRESSION_OUT_DIR:-${ROOT_DIR}/temp/lesson-smoke-artifacts}"
LESSON_BACKEND_HOST="${PEPTUTOR_LESSON_REGRESSION_HOST:-127.0.0.1}"
LESSON_BACKEND_PORT="${PEPTUTOR_LESSON_REGRESSION_PORT:-9625}"
BASE_URL="http://${LESSON_BACKEND_HOST}:${LESSON_BACKEND_PORT}"
TIMEOUT_SECONDS="${PEPTUTOR_LESSON_REGRESSION_TIMEOUT:-120}"
KEEP_SERVER="${PEPTUTOR_LESSON_REGRESSION_KEEP_SERVER:-0}"
FULL_STACK="${PEPTUTOR_LESSON_REGRESSION_FULL_STACK:-0}"
LOG_PATH="${LOG_DIR}/smoke_lesson_regression20_$(date +%Y%m%d_%H%M%S).log"
SERVER_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/smoke_lesson_regression_20.sh

Start a temporary route-focused LightRAG lesson backend, wait for
/lesson/catalog, run the fixed 20-page /lesson/turn regression matrix, then
stop the backend.

Environment overrides:
  PEPTUTOR_LESSON_REGRESSION_FULL_STACK=1   Keep vector/SimpleMem env.
  PEPTUTOR_LESSON_REGRESSION_KEEP_SERVER=1  Leave the backend running.
  PEPTUTOR_LESSON_REGRESSION_OUT_DIR=...    Matrix artifact directory.
  PEPTUTOR_TEST_GOAL_ID=...                  Required test budget goal id.
  PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON=...   Required for repeated L3 runs.
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
    echo "[INFO] Lesson regression backend left running at ${BASE_URL} (pid=${SERVER_PID}, log=${LOG_PATH})"
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
    tail -n 60 "${LOG_PATH}" >&2 || true
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "${BUDGET_GUARD_SCRIPT}" ]]; then
  echo "Missing test budget guard script: ${BUDGET_GUARD_SCRIPT}" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${BUDGET_GUARD_SCRIPT}"
peptutor_test_budget_guard "full_20_page" "" ""

if [[ ! -x "${SERVER_BIN}" ]]; then
  echo "Missing LightRAG server binary: ${SERVER_BIN}" >&2
  echo "Install backend/LightRAG/.venv first." >&2
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python binary: ${PYTHON_BIN}" >&2
  echo "Install backend/LightRAG/.venv first." >&2
  exit 1
fi

if [[ ! -f "${WAIT_SCRIPT}" ]]; then
  echo "Missing lesson-backend wait script: ${WAIT_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${MATRIX_SCRIPT}" ]]; then
  echo "Missing lesson matrix script: ${MATRIX_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${OUT_DIR}"
trap cleanup EXIT

export NO_PROXY="${NO_PROXY:+${NO_PROXY},}127.0.0.1,localhost,::1"
export no_proxy="${no_proxy:+${no_proxy},}127.0.0.1,localhost,::1"

server_env=(
  "NO_PROXY=${NO_PROXY}"
  "no_proxy=${no_proxy}"
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

echo "[INFO] Starting fixed 20-page regression backend at ${BASE_URL}"
echo "[INFO] Backend log: ${LOG_PATH}"
echo "[INFO] Full-stack mode: $(if is_enabled "${FULL_STACK}"; then echo on; else echo off; fi)"

(
  cd "${BACKEND_DIR}"
  exec env "${server_env[@]}" "${SERVER_BIN}" --host "${LESSON_BACKEND_HOST}" --port "${LESSON_BACKEND_PORT}"
) >"${LOG_PATH}" 2>&1 &
SERVER_PID="$!"

if ! bash "${WAIT_SCRIPT}" --url "${BASE_URL}" --timeout 120; then
  print_backend_log_tail
  exit 1
fi

echo "[INFO] Running fixed lesson regression set: lesson-core-20-v1"
if ! "${PYTHON_BIN}" "${MATRIX_SCRIPT}" --base-url "${BASE_URL}" --out-dir "${OUT_DIR}" --timeout "${TIMEOUT_SECONDS}"; then
  print_backend_log_tail
  exit 1
fi

LATEST_REPORT="$(
  find "${OUT_DIR}" -maxdepth 1 -type f -name 'lesson_smoke_matrix_*.json' -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | head -n 1 \
    | cut -d' ' -f2-
)"
peptutor_test_budget_mark_report "full_20_page" "${LATEST_REPORT}"

echo "[PASS] Fixed 20-page lesson regression completed."
