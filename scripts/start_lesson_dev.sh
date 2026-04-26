#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/LightRAG"
FRONTEND_DIR="${ROOT_DIR}/frontend/airi"
SERVER_BIN="${PEPTUTOR_LESSON_SERVER_BIN:-${BACKEND_DIR}/.venv/bin/lightrag-server}"
WAIT_SCRIPT="${ROOT_DIR}/scripts/wait-for-lesson-backend.sh"
LOG_DIR="${PEPTUTOR_LESSON_LOG_DIR:-${BACKEND_DIR}/temp}"
BACKEND_HOST="${PEPTUTOR_LESSON_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${PEPTUTOR_LESSON_BACKEND_PORT:-9625}"
FRONTEND_HOST="${PEPTUTOR_LESSON_FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${PEPTUTOR_LESSON_FRONTEND_PORT:-5173}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
LOG_PATH="${LOG_DIR}/lesson_dev_backend_$(date +%Y%m%d_%H%M%S).log"
BACKEND_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/start_lesson_dev.sh [--full-stack]

Start the PepTutor lesson backend and AIRI stage-web frontend for local use.

Default:
  Backend:  http://127.0.0.1:9625
  Frontend: http://127.0.0.1:5173/lesson

Environment overrides:
  PEPTUTOR_LESSON_BACKEND_HOST=127.0.0.1
  PEPTUTOR_LESSON_BACKEND_PORT=9625
  PEPTUTOR_LESSON_FRONTEND_HOST=0.0.0.0
  PEPTUTOR_LESSON_FRONTEND_PORT=5173
  PEPTUTOR_LESSON_SERVER_BIN=/path/to/lightrag-server
  PEPTUTOR_LESSON_LOG_DIR=/path/to/log-dir

Use --full-stack to keep vector retrieval and SimpleMem features enabled by
the surrounding environment. Without it, those features are disabled so the
local demo starts with fewer external dependencies.
EOF
}

is_enabled() {
  local value="${1:-}"
  case "${value,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

FULL_STACK="${PEPTUTOR_LESSON_FULL_STACK:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --full-stack)
      FULL_STACK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}

print_backend_log_tail() {
  if [[ -f "${LOG_PATH}" ]]; then
    echo "[INFO] Backend log tail (${LOG_PATH}):" >&2
    tail -n 60 "${LOG_PATH}" >&2 || true
  fi
}

if [[ ! -x "${SERVER_BIN}" ]]; then
  echo "Missing LightRAG server binary: ${SERVER_BIN}" >&2
  echo "Install backend dependencies first: cd backend/LightRAG && python -m venv .venv && .venv/bin/python -m pip install --no-build-isolation -e .[test]" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "Missing pnpm. Install frontend dependencies first in frontend/airi." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"
trap cleanup EXIT INT TERM

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

echo "[INFO] Starting PepTutor lesson backend: ${BACKEND_URL}"
echo "[INFO] Backend log: ${LOG_PATH}"
(
  cd "${BACKEND_DIR}"
  exec env "${server_env[@]}" "${SERVER_BIN}" --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
) >"${LOG_PATH}" 2>&1 &
BACKEND_PID="$!"

if ! bash "${WAIT_SCRIPT}" --url "${BACKEND_URL}" --timeout 120; then
  print_backend_log_tail
  exit 1
fi

if [[ -z "${VITE_PEPTUTOR_TTS_PROVIDER:-}" && -n "${PEPTUTOR_LESSON_TTS_PROVIDER:-}" ]]; then
  export VITE_PEPTUTOR_TTS_PROVIDER="${PEPTUTOR_LESSON_TTS_PROVIDER}"
fi
if [[ -z "${VITE_PEPTUTOR_TTS_MODEL:-}" && -n "${PEPTUTOR_LESSON_TTS_MODEL:-}" ]]; then
  export VITE_PEPTUTOR_TTS_MODEL="${PEPTUTOR_LESSON_TTS_MODEL}"
fi
if [[ -z "${VITE_PEPTUTOR_TTS_VOICE:-}" && -n "${PEPTUTOR_LESSON_TTS_VOICE:-}" ]]; then
  export VITE_PEPTUTOR_TTS_VOICE="${PEPTUTOR_LESSON_TTS_VOICE}"
fi

echo "[INFO] Starting AIRI stage-web frontend: http://127.0.0.1:${FRONTEND_PORT}/lesson"
echo "[INFO] Press Ctrl+C here to stop both frontend and backend."
(
  cd "${FRONTEND_DIR}"
  exec env \
    "NO_PROXY=${NO_PROXY}" \
    "no_proxy=${no_proxy}" \
    "VITE_PEPTUTOR_LESSON_API_URL=${BACKEND_URL}" \
    "VITE_PEPTUTOR_DEV_PROXY_TARGET=${BACKEND_URL}" \
    "VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=true" \
    pnpm -F @proj-airi/stage-web dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
)
