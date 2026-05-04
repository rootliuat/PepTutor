#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WAIT_SCRIPT="${ROOT_DIR}/scripts/wait-for-lesson-backend.sh"
BACKEND_URL="${PEPTUTOR_LESSON_REAL_BACKEND_URL:-http://127.0.0.1:9625}"
WAIT_TIMEOUT="${PEPTUTOR_LESSON_REAL_BACKEND_WAIT_TIMEOUT:-120}"
EXPECT_DEBUG_SIGNALS="${VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS:-1}"
LESSON_API_URL="${VITE_PEPTUTOR_LESSON_API_URL:-${BACKEND_URL}}"
SMOKE_WAIT_TIMEOUT_MS="${VITE_PEPTUTOR_LESSON_SMOKE_WAIT_TIMEOUT_MS:-30000}"
SMOKE_TEST_TIMEOUT_MS="${VITE_PEPTUTOR_LESSON_SMOKE_TEST_TIMEOUT_MS:-90000}"

append_loopback_no_proxy() {
  local targets="127.0.0.1,localhost,::1"
  export NO_PROXY="${NO_PROXY:+${NO_PROXY},}${targets}"
  export no_proxy="${no_proxy:+${no_proxy},}${targets}"
}

if [[ ! -f "${WAIT_SCRIPT}" ]]; then
  echo "Missing lesson-backend wait script: ${WAIT_SCRIPT}" >&2
  exit 1
fi

append_loopback_no_proxy
bash "${WAIT_SCRIPT}" --url "${BACKEND_URL}" --timeout "${WAIT_TIMEOUT}"

(
  cd "${ROOT_DIR}/apps/stage-web"
  VITE_PEPTUTOR_LESSON_REAL_BACKEND_SMOKE=1 \
  VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL="${BACKEND_URL}" \
  VITE_PEPTUTOR_LESSON_API_URL="${LESSON_API_URL}" \
  VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS="${EXPECT_DEBUG_SIGNALS}" \
  VITE_PEPTUTOR_LESSON_SMOKE_WAIT_TIMEOUT_MS="${SMOKE_WAIT_TIMEOUT_MS}" \
  VITE_PEPTUTOR_LESSON_SMOKE_TEST_TIMEOUT_MS="${SMOKE_TEST_TIMEOUT_MS}" \
  pnpm exec vitest run -c vitest.browser.config.ts src/pages/lesson/index.browser.test.ts --reporter verbose
)
