#!/usr/bin/env bash

# Shared PepTutor smoke budget guard.
#
# Source this from smoke wrappers before starting backends, browsers, or any
# LLM-consuming smoke. It records one metadata file per goal id and rejects
# repeated L3 smoke runs unless the caller provides an explicit override reason.

peptutor_test_budget_guard() {
  local smoke_type="$1"
  local allowed_goal_types="${2:-}"
  local report_path="${3:-}"
  local goal_id="${PEPTUTOR_TEST_GOAL_ID:-}"
  local goal_type="${PEPTUTOR_TEST_GOAL_TYPE:-}"
  local override_reason="${PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON:-}"
  local root_dir="${ROOT_DIR:-$(pwd)}"
  local budget_dir="${PEPTUTOR_TEST_BUDGET_DIR:-${root_dir}/temp/lesson-smoke-artifacts/test-budget}"

  if [[ -z "${goal_id}" ]]; then
    cat >&2 <<EOF
[ERROR] PEPTUTOR_TEST_GOAL_ID is required before running ${smoke_type} smoke.
Set PEPTUTOR_TEST_GOAL_ID to a stable id for this /goal so smoke wrappers can
enforce the test budget and prevent repeated L3 runs.
EOF
    return 2
  fi

  case "${goal_id}" in
    *"/"*|*"\\"*|*".."*|"."|"")
      echo "[ERROR] Invalid PEPTUTOR_TEST_GOAL_ID: ${goal_id}" >&2
      echo "Use only a stable filename-safe id without slashes or '..'." >&2
      return 2
      ;;
  esac

  if [[ -n "${allowed_goal_types}" ]]; then
    if [[ -z "${goal_type}" ]]; then
      echo "[ERROR] PEPTUTOR_TEST_GOAL_TYPE is required before running ${smoke_type} smoke." >&2
      echo "Allowed goal types for this smoke: ${allowed_goal_types}" >&2
      return 2
    fi
    if ! peptutor_test_budget_goal_type_allowed "${goal_type}" "${allowed_goal_types}"; then
      echo "[ERROR] ${smoke_type} smoke is not allowed for PEPTUTOR_TEST_GOAL_TYPE=${goal_type}." >&2
      echo "Allowed goal types: ${allowed_goal_types}" >&2
      return 2
    fi
  fi

  mkdir -p "${budget_dir}"
  python3 - \
    "${budget_dir}/${goal_id}.json" \
    "${goal_id}" \
    "${goal_type}" \
    "${smoke_type}" \
    "${override_reason}" \
    "${report_path}" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
goal_id = sys.argv[2]
goal_type = sys.argv[3]
smoke_type = sys.argv[4]
override_reason = sys.argv[5]
report_path = sys.argv[6]

if path.exists():
    payload = json.loads(path.read_text(encoding="utf-8"))
else:
    payload = {
        "goal_id": goal_id,
        "goal_type": goal_type,
        "runs": [],
        "runs_by_type": {},
    }

runs = payload.setdefault("runs", [])
previous_count = sum(
    1 for run in runs
    if isinstance(run, dict) and run.get("smoke_type") == smoke_type
)
if previous_count >= 1 and not override_reason:
    print(
        "[ERROR] Test budget exceeded for "
        f"goal_id={goal_id} smoke_type={smoke_type}: "
        "one run is already recorded. Set "
        "PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON to run again.",
        file=sys.stderr,
    )
    sys.exit(3)

run_count = previous_count + 1
timestamp = datetime.now(timezone.utc).isoformat()
entry = {
    "goal_id": goal_id,
    "goal_type": goal_type,
    "smoke_type": smoke_type,
    "run_count": run_count,
    "timestamp": timestamp,
    "override_reason": override_reason,
    "report_path": report_path,
    "status": "started",
}
runs.append(entry)
payload.update(
    {
        "goal_id": goal_id,
        "goal_type": goal_type,
        "smoke_type": smoke_type,
        "run_count": run_count,
        "timestamp": timestamp,
        "override_reason": override_reason,
        "report_path": report_path,
        "runs_by_type": {
            key: sum(
                1 for run in runs
                if isinstance(run, dict) and run.get("smoke_type") == key
            )
            for key in sorted(
                {
                    str(run.get("smoke_type"))
                    for run in runs
                    if isinstance(run, dict) and run.get("smoke_type")
                }
            )
        },
    }
)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"[INFO] Test budget accepted: goal_id={goal_id} smoke_type={smoke_type} run_count={run_count}")
PY
}

peptutor_test_budget_mark_report() {
  local smoke_type="$1"
  local report_path="$2"
  local goal_id="${PEPTUTOR_TEST_GOAL_ID:-}"
  local root_dir="${ROOT_DIR:-$(pwd)}"
  local budget_dir="${PEPTUTOR_TEST_BUDGET_DIR:-${root_dir}/temp/lesson-smoke-artifacts/test-budget}"

  if [[ -z "${goal_id}" || -z "${report_path}" ]]; then
    return 0
  fi

  python3 - "${budget_dir}/${goal_id}.json" "${smoke_type}" "${report_path}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
smoke_type = sys.argv[2]
report_path = sys.argv[3]
if not path.exists():
    sys.exit(0)
payload = json.loads(path.read_text(encoding="utf-8"))
runs = payload.get("runs")
if not isinstance(runs, list):
    sys.exit(0)
for run in reversed(runs):
    if isinstance(run, dict) and run.get("smoke_type") == smoke_type:
        run["report_path"] = report_path
        run["status"] = "completed"
        payload["report_path"] = report_path
        break
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

peptutor_test_budget_goal_type_allowed() {
  local goal_type="$1"
  local allowed_goal_types="$2"
  python3 - "${goal_type}" "${allowed_goal_types}" <<'PY'
from __future__ import annotations

import re
import sys

goal_type = sys.argv[1].casefold()
allowed = {
    token
    for token in re.split(r"[^a-z0-9]+", sys.argv[2].casefold())
    if token
}
tokens = {
    token
    for token in re.split(r"[^a-z0-9]+", goal_type)
    if token
}
if tokens & allowed:
    sys.exit(0)
sys.exit(1)
PY
}
