#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/LightRAG"
FRONTEND_DIR="${ROOT_DIR}/frontend/airi"
SERVER_BIN="${PEPTUTOR_LESSON_DEEP_SERVER_BIN:-${BACKEND_DIR}/.venv/bin/lightrag-server}"
PYTHON_BIN="${PEPTUTOR_LESSON_DEEP_PYTHON:-${BACKEND_DIR}/.venv/bin/python}"
WAIT_SCRIPT="${PEPTUTOR_LESSON_DEEP_WAIT_SCRIPT:-${ROOT_DIR}/scripts/wait-for-lesson-backend.sh}"
DEEP_SMOKE_SCRIPT="${PEPTUTOR_LESSON_DEEP_SCRIPT:-${ROOT_DIR}/temp/lesson_deep_smoke.py}"
LOG_DIR="${PEPTUTOR_LESSON_DEEP_LOG_DIR:-${BACKEND_DIR}/temp}"
ARTIFACT_DIR="${PEPTUTOR_LESSON_DEEP_ARTIFACT_DIR:-${ROOT_DIR}/temp/lesson-smoke-artifacts}"
HISTORY_ROOT="${PEPTUTOR_LESSON_DEEP_HISTORY_ROOT:-${ROOT_DIR}/frontend/airi/apps/stage-web/chat_history}"
BACKEND_HOST="${PEPTUTOR_LESSON_DEEP_BACKEND_HOST:-127.0.0.1}"
DEFAULT_BACKEND_PORT="${PEPTUTOR_LESSON_DEEP_DEFAULT_BACKEND_PORT:-9625}"
BACKEND_PORT=""
FRONTEND_HOST="${PEPTUTOR_LESSON_DEEP_FRONTEND_HOST:-127.0.0.1}"
DEFAULT_FRONTEND_PORT="${PEPTUTOR_LESSON_DEEP_DEFAULT_FRONTEND_PORT:-5173}"
FRONTEND_PORT=""
PAGE_TIMEOUT_SECONDS="${PEPTUTOR_LESSON_DEEP_PAGE_TIMEOUT_SECONDS:-180}"
OBSERVER_TIMEOUT_SECONDS="${PEPTUTOR_LESSON_DEEP_OBSERVER_TIMEOUT_SECONDS:-1500}"
KEEP_SERVERS="${PEPTUTOR_LESSON_DEEP_KEEP_SERVERS:-0}"
FULL_STACK="${PEPTUTOR_LESSON_DEEP_FULL_STACK:-0}"
BACKEND_URL=""
FRONTEND_URL=""
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
BACKEND_LOG_PATH="${LOG_DIR}/smoke_lesson_deep_backend_${RUN_STAMP}.log"
FRONTEND_LOG_PATH="${LOG_DIR}/smoke_lesson_deep_frontend_${RUN_STAMP}.log"
OBSERVER_LOG_PATH="${LOG_DIR}/lesson_deep_observer_${RUN_STAMP}.log"
BACKEND_PID=""
FRONTEND_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/smoke_lesson_deep_browser.sh

Start route-focused backend + AIRI stage-web, run the deep Playwright browser
observer, and write screenshots, network/console events, history JSON audit,
TTS HTTP statuses, audio-start probes, mouth-open probes, and Live2D
motion/expression observations into temp/lesson-smoke-artifacts.

Environment overrides:
  PEPTUTOR_LESSON_DEEP_FULL_STACK=1       Keep vector/SimpleMem env.
  PEPTUTOR_LESSON_DEEP_KEEP_SERVERS=1    Leave backend/frontend running.
  PEPTUTOR_LESSON_DEEP_BACKEND_PORT=...  Use an exact backend port.
  PEPTUTOR_LESSON_DEEP_FRONTEND_PORT=... Use another Vite port.
  PEPTUTOR_LESSON_DEEP_OBSERVER_TIMEOUT_SECONDS=... Kill a hung observer.
EOF
}

append_loopback_no_proxy() {
  local targets="127.0.0.1,localhost,::1"
  export NO_PROXY="${NO_PROXY:+${NO_PROXY},}${targets}"
  export no_proxy="${no_proxy:+${no_proxy},}${targets}"
}

is_enabled() {
  local value="${1:-}"
  case "${value,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

port_available() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sys.exit(1)
PY
}

find_free_port() {
  local host="$1"
  python3 - "$host" <<'PY'
import socket
import sys

host = sys.argv[1]
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind((host, 0))
    print(sock.getsockname()[1])
PY
}

select_port() {
  local label="$1"
  local host="$2"
  local explicit_port="$3"
  local default_port="$4"

  if [[ -n "${explicit_port}" ]]; then
    if ! port_available "${host}" "${explicit_port}"; then
      echo "Requested ${label} port is already in use: ${host}:${explicit_port}" >&2
      exit 1
    fi
    echo "${explicit_port}"
    return
  fi

  if port_available "${host}" "${default_port}"; then
    echo "${default_port}"
    return
  fi

  find_free_port "${host}"
}

cleanup() {
  if is_enabled "${KEEP_SERVERS}"; then
    if [[ -n "${BACKEND_PID}" ]]; then
      disown "${BACKEND_PID}" 2>/dev/null || true
    fi
    if [[ -n "${FRONTEND_PID}" ]]; then
      disown "${FRONTEND_PID}" 2>/dev/null || true
    fi
    echo "[INFO] Deep smoke servers left running: backend=${BACKEND_URL}, frontend=${FRONTEND_URL}"
    return
  fi

  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
    wait "${FRONTEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}

print_log_tail() {
  local label="$1"
  local path="$2"
  if [[ -f "${path}" ]]; then
    echo "[INFO] ${label} log tail (${path}):" >&2
    tail -n 60 "${path}" >&2 || true
  fi
}

wait_for_frontend() {
  local deadline
  deadline=$((SECONDS + 120))
  until curl --noproxy '*' -fsS "${FRONTEND_URL}/lesson" >/dev/null 2>&1; do
    if [[ -n "${FRONTEND_PID}" ]] && ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
      echo "AIRI stage-web exited before becoming ready." >&2
      return 1
    fi
    if (( SECONDS >= deadline )); then
      echo "Timed out after 120s waiting for AIRI stage-web at ${FRONTEND_URL}/lesson" >&2
      return 1
    fi
    sleep 1
  done
  echo "[INFO] AIRI stage-web ready at ${FRONTEND_URL}/lesson"
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

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python binary: ${PYTHON_BIN}" >&2
  echo "Install backend/LightRAG/.venv first." >&2
  exit 1
fi

if [[ ! -f "${WAIT_SCRIPT}" ]]; then
  echo "Missing lesson-backend wait script: ${WAIT_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${DEEP_SMOKE_SCRIPT}" ]]; then
  echo "Missing deep smoke script: ${DEEP_SMOKE_SCRIPT}" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "Missing pnpm. Install frontend dependencies first in frontend/airi." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${ARTIFACT_DIR}"
append_loopback_no_proxy
BACKEND_PORT="$(select_port "deep browser backend" "${BACKEND_HOST}" "${PEPTUTOR_LESSON_DEEP_BACKEND_PORT:-}" "${DEFAULT_BACKEND_PORT}")"
FRONTEND_PORT="$(select_port "AIRI stage-web frontend" "${FRONTEND_HOST}" "${PEPTUTOR_LESSON_DEEP_FRONTEND_PORT:-}" "${DEFAULT_FRONTEND_PORT}")"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
trap cleanup EXIT

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

if [[ -z "${PEPTUTOR_LESSON_DEEP_BACKEND_PORT:-}" && "${BACKEND_PORT}" != "${DEFAULT_BACKEND_PORT}" ]]; then
  echo "[INFO] Default backend port ${DEFAULT_BACKEND_PORT} is busy; using ${BACKEND_PORT} for this deep smoke run"
fi
if [[ -z "${PEPTUTOR_LESSON_DEEP_FRONTEND_PORT:-}" && "${FRONTEND_PORT}" != "${DEFAULT_FRONTEND_PORT}" ]]; then
  echo "[INFO] Default frontend port ${DEFAULT_FRONTEND_PORT} is busy; using ${FRONTEND_PORT} for this deep smoke run"
fi

echo "[INFO] Starting deep browser backend at ${BACKEND_URL}"
echo "[INFO] Backend log: ${BACKEND_LOG_PATH}"
(
  cd "${BACKEND_DIR}"
  exec env "${server_env[@]}" "${SERVER_BIN}" --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
) >"${BACKEND_LOG_PATH}" 2>&1 &
BACKEND_PID="$!"

if ! bash "${WAIT_SCRIPT}" --url "${BACKEND_URL}" --timeout 120; then
  print_log_tail "Backend" "${BACKEND_LOG_PATH}"
  exit 1
fi

echo "[INFO] Starting AIRI stage-web at ${FRONTEND_URL}/lesson"
echo "[INFO] Frontend log: ${FRONTEND_LOG_PATH}"
(
  cd "${FRONTEND_DIR}"
  exec env \
    "NO_PROXY=${NO_PROXY}" \
    "no_proxy=${no_proxy}" \
    "VITE_PEPTUTOR_LESSON_API_URL=${BACKEND_URL}" \
    "VITE_PEPTUTOR_DEV_PROXY_TARGET=${BACKEND_URL}" \
    "VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=true" \
    "VITE_PEPTUTOR_TTS_PROVIDER=${VITE_PEPTUTOR_TTS_PROVIDER:-edge-tts}" \
    "VITE_PEPTUTOR_TTS_MODEL=${VITE_PEPTUTOR_TTS_MODEL:-edge-tts}" \
    "VITE_PEPTUTOR_TTS_VOICE=${VITE_PEPTUTOR_TTS_VOICE:-zh-CN-XiaoxiaoNeural}" \
    pnpm -F @proj-airi/stage-web exec vite --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --strictPort
) >"${FRONTEND_LOG_PATH}" 2>&1 &
FRONTEND_PID="$!"

if ! wait_for_frontend; then
  print_log_tail "Frontend" "${FRONTEND_LOG_PATH}"
  print_log_tail "Backend" "${BACKEND_LOG_PATH}"
  exit 1
fi

echo "[INFO] Running deep browser observer"
echo "[INFO] Observer log: ${OBSERVER_LOG_PATH}"
set +e
timeout --foreground "${OBSERVER_TIMEOUT_SECONDS}s" \
  "${PYTHON_BIN}" "${DEEP_SMOKE_SCRIPT}" \
  --frontend-url "${FRONTEND_URL}" \
  --history-root "${HISTORY_ROOT}" \
  --artifact-dir "${ARTIFACT_DIR}" \
  --page-timeout-seconds "${PAGE_TIMEOUT_SECONDS}" \
  2>&1 | tee "${OBSERVER_LOG_PATH}"
observer_status="${PIPESTATUS[0]}"
set -e
if [[ "${observer_status}" -ne 0 ]]; then
  if [[ "${observer_status}" -eq 124 ]]; then
    echo "[ERROR] Deep browser observer timed out after ${OBSERVER_TIMEOUT_SECONDS}s" >&2
  fi
  print_log_tail "Observer" "${OBSERVER_LOG_PATH}"
  print_log_tail "Frontend" "${FRONTEND_LOG_PATH}"
  print_log_tail "Backend" "${BACKEND_LOG_PATH}"
  exit 1
fi

echo "[PASS] Deep lesson browser observation completed."
