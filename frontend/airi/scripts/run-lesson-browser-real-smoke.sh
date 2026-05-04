#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WAIT_SCRIPT="${ROOT_DIR}/scripts/wait-for-lesson-backend.sh"
NODE_BIN_RESOLVER="${ROOT_DIR}/scripts/resolve-node-bin.mjs"
STAGE_WEB_DIR="${ROOT_DIR}/apps/stage-web"
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
if [[ ! -f "${NODE_BIN_RESOLVER}" ]]; then
  echo "Missing Node bin resolver: ${NODE_BIN_RESOLVER}" >&2
  exit 1
fi

VITEST_BIN="$(
  node "${NODE_BIN_RESOLVER}" vitest vitest.mjs "${STAGE_WEB_DIR}"
)"

append_loopback_no_proxy
bash "${WAIT_SCRIPT}" --url "${BACKEND_URL}" --timeout "${WAIT_TIMEOUT}"

(
  cd "${STAGE_WEB_DIR}"
  VITE_PEPTUTOR_LESSON_REAL_BACKEND_SMOKE=1 \
  VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL="${BACKEND_URL}" \
  VITE_PEPTUTOR_LESSON_API_URL="${LESSON_API_URL}" \
  VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS="${EXPECT_DEBUG_SIGNALS}" \
  VITE_PEPTUTOR_LESSON_SMOKE_WAIT_TIMEOUT_MS="${SMOKE_WAIT_TIMEOUT_MS}" \
  VITE_PEPTUTOR_LESSON_SMOKE_TEST_TIMEOUT_MS="${SMOKE_TEST_TIMEOUT_MS}" \
  node "${VITEST_BIN}" run -c vitest.browser.config.ts src/pages/lesson/index.browser.test.ts --reporter verbose
)
