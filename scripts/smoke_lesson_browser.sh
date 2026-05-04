#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/LightRAG"
FRONTEND_DIR="${ROOT_DIR}/frontend/airi"
SERVER_BIN="${PEPTUTOR_LESSON_SMOKE_SERVER_BIN:-${BACKEND_DIR}/.venv/bin/lightrag-server}"
WAIT_SCRIPT="${PEPTUTOR_LESSON_SMOKE_WAIT_SCRIPT:-${ROOT_DIR}/scripts/wait-for-lesson-backend.sh}"
BUDGET_GUARD_SCRIPT="${PEPTUTOR_TEST_BUDGET_GUARD_SCRIPT:-${ROOT_DIR}/scripts/test-budget-guard.sh}"
LOG_DIR="${PEPTUTOR_LESSON_SMOKE_LOG_DIR:-${BACKEND_DIR}/temp}"
ARTIFACT_DIR="${PEPTUTOR_LESSON_SMOKE_ARTIFACT_DIR:-${ROOT_DIR}/temp/lesson-smoke-artifacts}"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_PATH="${LOG_DIR}/smoke_lesson_browser_${RUN_STAMP}.log"
BROWSER_LOG_PATH="${LOG_DIR}/lesson_browser_vitest_${RUN_STAMP}.log"
BROWSER_REPORT_JSON_PATH="${ARTIFACT_DIR}/lesson_browser_smoke_${RUN_STAMP}.json"
BROWSER_REPORT_MD_PATH="${ARTIFACT_DIR}/lesson_browser_smoke_${RUN_STAMP}.md"
LESSON_BACKEND_HOST="${PEPTUTOR_LESSON_SMOKE_BACKEND_HOST:-127.0.0.1}"
DEFAULT_LESSON_BACKEND_PORT="${PEPTUTOR_LESSON_SMOKE_DEFAULT_BACKEND_PORT:-9625}"
LESSON_BACKEND_PORT=""
LESSON_BACKEND_URL=""
KEEP_SERVER="${PEPTUTOR_LESSON_SMOKE_KEEP_SERVER:-0}"
FULL_STACK="${PEPTUTOR_LESSON_SMOKE_FULL_STACK:-0}"
BROWSER_TIMEOUT_SECONDS="${PEPTUTOR_LESSON_SMOKE_BROWSER_TIMEOUT_SECONDS:-600}"
SERVER_PID=""

usage() {
  cat <<'EOF'
Usage: scripts/smoke_lesson_browser.sh

Start a temporary route-focused LightRAG lesson backend, wait for it to answer
GET /lesson/catalog, run the checked-in Chromium /lesson real-browser suite,
then stop the backend.

Environment overrides:
  PEPTUTOR_LESSON_SMOKE_FULL_STACK=1   Keep the current vector/SimpleMem env.
  PEPTUTOR_LESSON_SMOKE_KEEP_SERVER=1  Leave the backend running after the suite.
  PEPTUTOR_LESSON_SMOKE_BACKEND_PORT=... Use an exact backend port.
  PEPTUTOR_LESSON_SMOKE_BROWSER_TIMEOUT_SECONDS=... Kill a hung browser suite.
  PEPTUTOR_LESSON_SMOKE_ARTIFACT_DIR=... Write browser smoke JSON/MD reports here.
  PEPTUTOR_TEST_GOAL_ID=...              Required test budget goal id.
  PEPTUTOR_TEST_GOAL_TYPE=frontend       Required; must include frontend, s4, or browser.
  PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON=... Required for repeated browser smoke.
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

select_backend_port() {
  if [[ -n "${PEPTUTOR_LESSON_SMOKE_BACKEND_PORT:-}" ]]; then
    if ! port_available "${LESSON_BACKEND_HOST}" "${PEPTUTOR_LESSON_SMOKE_BACKEND_PORT}"; then
      echo "Requested lesson browser backend port is already in use: ${LESSON_BACKEND_HOST}:${PEPTUTOR_LESSON_SMOKE_BACKEND_PORT}" >&2
      exit 1
    fi
    echo "${PEPTUTOR_LESSON_SMOKE_BACKEND_PORT}"
    return
  fi

  if port_available "${LESSON_BACKEND_HOST}" "${DEFAULT_LESSON_BACKEND_PORT}"; then
    echo "${DEFAULT_LESSON_BACKEND_PORT}"
    return
  fi

  find_free_port "${LESSON_BACKEND_HOST}"
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

print_browser_log_tail() {
  if [[ -f "${BROWSER_LOG_PATH}" ]]; then
    echo "[INFO] Browser suite log tail (${BROWSER_LOG_PATH}):" >&2
    tail -n 80 "${BROWSER_LOG_PATH}" >&2 || true
  fi
}

write_browser_report() {
  local status="$1"
  local browser_exit_code="$2"
  local timed_out="$3"
  python3 - \
    "${BROWSER_REPORT_JSON_PATH}" \
    "${BROWSER_REPORT_MD_PATH}" \
    "${RUN_STAMP}" \
    "${LESSON_BACKEND_URL}" \
    "${LOG_PATH}" \
    "${BROWSER_LOG_PATH}" \
    "${status}" \
    "${browser_exit_code}" \
    "${timed_out}" \
    "$(if is_enabled "${FULL_STACK}"; then echo on; else echo off; fi)" <<'PY'
import base64
import binascii
import json
import re
import sys
from datetime import datetime
from pathlib import Path

json_path = Path(sys.argv[1])
md_path = Path(sys.argv[2])
run_stamp = sys.argv[3]
backend_url = sys.argv[4]
backend_log_path = sys.argv[5]
browser_log_path = Path(sys.argv[6])
status = sys.argv[7]
browser_exit_code = int(sys.argv[8])
timed_out = sys.argv[9].lower() == "true"
full_stack = sys.argv[10]

browser_log_text = ""
if browser_log_path.exists():
    browser_log_text = browser_log_path.read_text(encoding="utf-8", errors="replace")


def parse_vitest_counts(label: str) -> dict[str, int]:
    match = re.search(rf"^\s*{re.escape(label)}\s+(.+)$", browser_log_text, re.MULTILINE)
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    if not match:
        return counts
    segment = match.group(1)
    for value, kind in re.findall(r"(\d+)\s+(passed|failed|skipped)", segment):
            counts[kind] += int(value)
    return counts


def parse_vitest_test_names(marker: str) -> list[str]:
    return [entry["name"] for entry in parse_vitest_test_entries(marker)]


def classify_vitest_suite(suite_name: str) -> str:
    if suite_name == "/lesson browser smoke (real backend)":
        return "real_backend_suite"
    if suite_name == "/lesson browser smoke":
        return "mock_suite"
    return "unknown_suite"


def skip_reason_for_entry(entry: dict[str, str]) -> str:
    if entry.get("suite_kind") == "mock_suite":
        return "mock_skipped_due_real_backend_mode"
    if entry.get("suite_kind") == "real_backend_suite":
        return "real_backend_conditional_skip"
    return "unknown_skip_reason"


def parse_vitest_test_entries(marker: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in browser_log_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(marker):
            continue
        segments = [segment.strip() for segment in stripped.split(" > ")]
        if not segments:
            continue
        suite_name = segments[-2] if len(segments) >= 2 else ""
        suite_kind = classify_vitest_suite(suite_name)
        name = re.sub(r"\s+\d+(?:ms|s)$", "", segments[-1]).strip()
        if name:
            entry = {
                "name": name,
                "suite_name": suite_name,
                "suite_kind": suite_kind,
                "raw": stripped,
            }
            if marker == "↓":
                entry["skip_reason"] = skip_reason_for_entry(entry)
            entries.append(entry)
    return entries


def build_browser_suite_summary(
    *,
    passed_entries: list[dict[str, str]],
    failed_entries: list[dict[str, str]],
    skipped_entries: list[dict[str, str]],
) -> dict[str, int]:
    def count(entries: list[dict[str, str]], suite_kind: str) -> int:
        return sum(1 for entry in entries if entry.get("suite_kind") == suite_kind)

    return {
        "real_backend_passed": count(passed_entries, "real_backend_suite"),
        "real_backend_failed": count(failed_entries, "real_backend_suite"),
        "real_backend_skipped": count(skipped_entries, "real_backend_suite"),
        "mock_suite_passed": count(passed_entries, "mock_suite"),
        "mock_suite_failed": count(failed_entries, "mock_suite"),
        "mock_suite_skipped": count(skipped_entries, "mock_suite"),
        "skipped_due_real_backend_mode": sum(
            1
            for entry in skipped_entries
            if entry.get("skip_reason") == "mock_skipped_due_real_backend_mode"
        ),
    }


def parse_json_events(prefix: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    pattern = re.compile(rf"{re.escape(prefix)}\s+(\{{.*\}})")
    for match in pattern.finditer(browser_log_text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            events.append({"parse_error": True, "raw": match.group(1)[:500]})
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def write_json_artifact(
    artifact_dir: Path,
    filename: str,
    payload: object,
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "collected": True}


def build_artifact_snapshots(
    artifact_events: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    artifact_dir = json_path.parent / f"lesson_browser_artifacts_{run_stamp}"
    network_payload: list[dict[str, object]] = []
    history_payload: list[dict[str, object]] = []
    dom_payload: list[dict[str, object]] = []
    screenshot_paths: list[str] = []
    screenshot_errors: list[dict[str, str]] = []

    for index, event in enumerate(artifact_events, start=1):
        test_name = str(event.get("test") or "")
        network_entries = event.get("network_entries")
        if isinstance(network_entries, list):
            network_payload.append({"test": test_name, "network_entries": network_entries})
        history_debug = event.get("history_debug")
        if isinstance(history_debug, dict):
            history_payload.append({"test": test_name, "history_debug": history_debug})
        dom_snapshot = event.get("dom_snapshot")
        if isinstance(dom_snapshot, dict):
            dom_payload.append({"test": test_name, "dom_snapshot": dom_snapshot})
        screenshot = event.get("screenshot")
        if isinstance(screenshot, dict):
            error = str(screenshot.get("error") or "")
            data_url = str(screenshot.get("data_url") or "")
            if error:
                screenshot_errors.append({"test": test_name, "error": error[:500]})
            elif data_url.startswith("data:image/png;base64,"):
                artifact_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = artifact_dir / f"screenshot_{index:02d}.png"
                try:
                    screenshot_path.write_bytes(
                        base64.b64decode(data_url.split(",", 1)[1], validate=True)
                    )
                except (binascii.Error, OSError) as exc:
                    screenshot_errors.append({"test": test_name, "error": str(exc)[:500]})
                else:
                    screenshot_paths.append(str(screenshot_path))

    snapshots: dict[str, dict[str, object]] = {}
    if network_payload:
        total_entries = sum(
            len(item.get("network_entries", []))
            for item in network_payload
            if isinstance(item.get("network_entries"), list)
        )
        written = write_json_artifact(artifact_dir, "network_events.json", network_payload)
        snapshots["network_logs"] = {
            "paths": [written["path"]],
            "count": total_entries,
            "status": "collected",
        }
    if history_payload:
        written = write_json_artifact(artifact_dir, "history_debug.json", history_payload)
        snapshots["history_json"] = {
            "paths": [written["path"]],
            "count": len(history_payload),
            "status": "collected",
        }
    if dom_payload:
        written = write_json_artifact(artifact_dir, "dom_snapshots.json", dom_payload)
        snapshots["dom_snapshots"] = {
            "paths": [written["path"]],
            "count": len(dom_payload),
            "status": "collected",
        }
    if screenshot_paths:
        snapshots["screenshots"] = {
            "paths": screenshot_paths,
            "count": len(screenshot_paths),
            "status": "collected",
        }
    elif screenshot_errors:
        written = write_json_artifact(artifact_dir, "screenshot_errors.json", screenshot_errors)
        snapshots["screenshots"] = {
            "paths": [written["path"]],
            "count": 0,
            "status": "capture_failed",
        }
    return snapshots


def sanitized_artifact_events(
    artifact_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for event in artifact_events:
        next_event = dict(event)
        screenshot = next_event.get("screenshot")
        if isinstance(screenshot, dict):
            data_url = str(screenshot.get("data_url") or "")
            next_event["screenshot"] = {
                "format": screenshot.get("format") or "png",
                "data_url_bytes": len(data_url.encode("utf-8")),
                "error": screenshot.get("error") or "",
                "captured": bool(data_url) and not screenshot.get("error"),
            }
        sanitized.append(next_event)
    return sanitized


def tail_lines(text: str, limit: int = 80) -> list[str]:
    return text.splitlines()[-limit:]


def previous_browser_report() -> dict[str, object]:
    candidates = sorted(
        path
        for path in json_path.parent.glob("lesson_browser_smoke_*.json")
        if path.resolve() != json_path.resolve()
    )
    if not candidates:
        return {}
    previous_path = candidates[-1]
    try:
        payload = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(previous_path), "load_error": True}
    if isinstance(payload, dict):
        payload["_path"] = str(previous_path)
        return payload
    return {"path": str(previous_path), "load_error": True}


def count_delta(current: dict[str, int], previous: dict[str, int], key: str) -> int:
    return int(current.get(key, 0)) - int(previous.get(key, 0))


def build_trend_comparison(
    *,
    current_counts: dict[str, int],
    current_s4_events: list[dict[str, object]],
    current_status: str,
    current_failure_reason: str,
) -> dict[str, object]:
    previous = previous_browser_report()
    if not previous:
        return {"previous_report": "", "status": "no_previous_report"}
    previous_counts = previous.get("browser_test_counts")
    if not isinstance(previous_counts, dict):
        previous_counts = {}
    previous_events = previous.get("evidence_events")
    if not isinstance(previous_events, dict):
        previous_events = {}
    previous_s4_events = previous_events.get("s4_interrupt")
    if not isinstance(previous_s4_events, list):
        previous_s4_events = []
    previous_attribution = previous.get("failure_attribution")
    if not isinstance(previous_attribution, dict):
        previous_attribution = {}
    return {
        "previous_report": str(previous.get("_path") or previous.get("path") or ""),
        "status": "compared",
        "status_changed": current_status != str(previous.get("status") or ""),
        "failure_reason_changed": current_failure_reason
        != str(previous_attribution.get("reason") or ""),
        "passed_delta": count_delta(current_counts, previous_counts, "passed"),
        "failed_delta": count_delta(current_counts, previous_counts, "failed"),
        "skipped_delta": count_delta(current_counts, previous_counts, "skipped"),
        "s4_interrupt_event_delta": len(current_s4_events) - len(previous_s4_events),
    }


test_counts = parse_vitest_counts("Tests")
file_counts = parse_vitest_counts("Test Files")
skipped_test_entries = parse_vitest_test_entries("↓")
passed_test_entries = parse_vitest_test_entries("✓")
failed_test_entries = parse_vitest_test_entries("×") + parse_vitest_test_entries("✗")
skipped_tests = [entry["name"] for entry in skipped_test_entries]
passed_tests = [entry["name"] for entry in passed_test_entries]
failed_tests = [entry["name"] for entry in failed_test_entries]
browser_suite_summary = build_browser_suite_summary(
    passed_entries=passed_test_entries,
    failed_entries=failed_test_entries,
    skipped_entries=skipped_test_entries,
)
s4_interrupt_events = parse_json_events("[lesson-s4-interrupt-evidence]")
real_smoke_events = parse_json_events("[lesson-real-smoke]")
debug_signal_events = parse_json_events("[lesson-real-debug-signals]")
artifact_events = parse_json_events("[lesson-real-artifacts]")
artifact_events_for_report = sanitized_artifact_events(artifact_events)
if status == "passed":
    failure_reason = "passed_with_skips" if test_counts.get("skipped", 0) else "passed"
elif timed_out:
    failure_reason = "browser_timeout"
elif status == "backend_wait_failed":
    failure_reason = "backend_unavailable"
elif test_counts.get("failed", 0):
    failure_reason = "browser_test_failure"
else:
    failure_reason = "browser_process_failure"
artifact_inventory = {
    "backend_log": {"path": backend_log_path, "collected": Path(backend_log_path).exists()},
    "browser_console_log": {
        "path": str(browser_log_path),
        "collected": browser_log_path.exists(),
        "line_count": len(browser_log_text.splitlines()),
    },
    "json_report": {"path": str(json_path), "collected": True},
    "markdown_report": {"path": str(md_path), "collected": True},
    "screenshots": {
        "paths": [],
        "count": 0,
        "status": "not_collected_by_route_focused_browser_smoke",
    },
    "network_logs": {
        "paths": [],
        "count": 0,
        "status": "not_collected_by_route_focused_browser_smoke",
    },
    "history_json": {
        "paths": [],
        "count": 0,
        "status": "not_collected_by_route_focused_browser_smoke",
    },
    "dom_snapshots": {
        "paths": [],
        "count": 0,
        "status": "not_collected_by_route_focused_browser_smoke",
    },
}
artifact_inventory.update(build_artifact_snapshots(artifact_events))
trend_comparison = build_trend_comparison(
    current_counts=test_counts,
    current_s4_events=s4_interrupt_events,
    current_status=status,
    current_failure_reason=failure_reason,
)
report = {
    "kind": "lesson_browser_smoke_report",
    "run_id": run_stamp,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "status": status,
    "acceptance_passed": status == "passed",
    "partial_report": status != "passed",
    "timed_out": timed_out,
    "browser_exit_code": browser_exit_code,
    "backend_url": backend_url,
    "full_stack": full_stack,
    "backend_log_path": backend_log_path,
    "browser_log_path": str(browser_log_path),
    "browser_test_counts": test_counts,
    "browser_test_file_counts": file_counts,
    "browser_suite_summary": browser_suite_summary,
    "skipped_test_entries": skipped_test_entries,
    "passed_test_entries": passed_test_entries,
    "failed_test_entries": failed_test_entries,
    "skipped_tests": skipped_tests,
    "passed_tests": passed_tests,
    "failed_tests": failed_tests,
    "evidence_events": {
        "lesson_real_smoke": real_smoke_events,
        "s4_interrupt": s4_interrupt_events,
        "debug_signals": debug_signal_events,
        "lesson_real_artifacts": artifact_events_for_report,
    },
    "failure_attribution": {
        "reason": failure_reason,
        "timed_out": timed_out,
        "browser_exit_code": browser_exit_code,
        "failed_test_count": test_counts.get("failed", 0),
        "skipped_test_count": test_counts.get("skipped", 0),
    },
    "artifact_manifest": {
        "backend_log": backend_log_path,
        "browser_log": str(browser_log_path),
        "json_report": str(json_path),
        "markdown_report": str(md_path),
    },
    "artifact_inventory": artifact_inventory,
    "trend_comparison": trend_comparison,
    "log_excerpt": {
        "browser_tail": tail_lines(browser_log_text, limit=80),
    },
}
json_path.parent.mkdir(parents=True, exist_ok=True)
json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

md_lines = [
    "# Lesson Browser Smoke",
    "",
    f"Generated: `{report['generated_at']}`",
    f"Backend: `{backend_url}`",
    f"Status: `{status}`",
    f"Acceptance passed: `{report['acceptance_passed']}`",
    f"Timed out: `{timed_out}`",
    f"Browser exit code: `{browser_exit_code}`",
    f"Full-stack mode: `{full_stack}`",
    "",
    "## Counts",
    "",
    f"- tests: `{test_counts}`",
    f"- test_files: `{file_counts}`",
    f"- skipped_tests: `{len(skipped_tests)}`",
    f"- passed_tests: `{len(passed_tests)}`",
    f"- failed_tests: `{len(failed_tests)}`",
    "",
    "## Suite Breakdown",
    "",
    f"- real_backend_passed: `{browser_suite_summary['real_backend_passed']}`",
    f"- real_backend_failed: `{browser_suite_summary['real_backend_failed']}`",
    f"- real_backend_skipped: `{browser_suite_summary['real_backend_skipped']}`",
    f"- mock_suite_passed: `{browser_suite_summary['mock_suite_passed']}`",
    f"- mock_suite_failed: `{browser_suite_summary['mock_suite_failed']}`",
    f"- mock_suite_skipped: `{browser_suite_summary['mock_suite_skipped']}`",
    f"- skipped_due_real_backend_mode: `{browser_suite_summary['skipped_due_real_backend_mode']}`",
    "",
    "## Failure Attribution",
    "",
    f"- reason: `{failure_reason}`",
    f"- timed_out: `{timed_out}`",
    f"- browser_exit_code: `{browser_exit_code}`",
    "",
    "## Evidence Events",
    "",
    f"- lesson_real_smoke: `{len(real_smoke_events)}`",
    f"- s4_interrupt: `{len(s4_interrupt_events)}`",
    f"- debug_signals: `{len(debug_signal_events)}`",
    f"- lesson_real_artifacts: `{len(artifact_events)}`",
    "",
    "## Artifact Inventory",
    "",
    f"- backend_log: `{artifact_inventory['backend_log']['collected']}`",
    f"- browser_console_log: `{artifact_inventory['browser_console_log']['collected']}`",
    f"- screenshots: `{artifact_inventory['screenshots']['status']}`",
    f"- network_logs: `{artifact_inventory['network_logs']['status']}`",
    f"- history_json: `{artifact_inventory['history_json']['status']}`",
    f"- dom_snapshots: `{artifact_inventory['dom_snapshots']['status']}`",
    "",
    "## Trend Comparison",
    "",
    f"- status: `{trend_comparison['status']}`",
    f"- previous_report: `{trend_comparison.get('previous_report', '')}`",
    f"- passed_delta: `{trend_comparison.get('passed_delta', 0)}`",
    f"- failed_delta: `{trend_comparison.get('failed_delta', 0)}`",
    f"- skipped_delta: `{trend_comparison.get('skipped_delta', 0)}`",
]
if skipped_tests:
    md_lines.extend([
        "",
        "## Skipped Tests",
        "",
        *[
            f"- {entry['name']} "
            f"(`{entry['suite_kind']}`, `{entry.get('skip_reason', '')}`)"
            for entry in skipped_test_entries[:30]
        ],
    ])
md_lines.extend([
    "",
    "## Logs",
    "",
    f"- backend: `{backend_log_path}`",
    f"- browser: `{browser_log_path}`",
])
md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
PY
  echo "[INFO] Browser smoke report: ${BROWSER_REPORT_JSON_PATH}"
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
peptutor_test_budget_guard "browser" "frontend,s4,browser" "${BROWSER_REPORT_JSON_PATH}"

if [[ ! -x "${SERVER_BIN}" ]]; then
  echo "Missing LightRAG server binary: ${SERVER_BIN}" >&2
  echo "Install backend/LightRAG/.venv first." >&2
  exit 1
fi

if [[ ! -f "${WAIT_SCRIPT}" ]]; then
  echo "Missing lesson-backend wait script: ${WAIT_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}" "${ARTIFACT_DIR}"
append_loopback_no_proxy
LESSON_BACKEND_PORT="$(select_backend_port)"
LESSON_BACKEND_URL="http://${LESSON_BACKEND_HOST}:${LESSON_BACKEND_PORT}"
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

if [[ -z "${PEPTUTOR_LESSON_SMOKE_BACKEND_PORT:-}" && "${LESSON_BACKEND_PORT}" != "${DEFAULT_LESSON_BACKEND_PORT}" ]]; then
  echo "[INFO] Default backend port ${DEFAULT_LESSON_BACKEND_PORT} is busy; using ${LESSON_BACKEND_PORT} for this smoke run"
fi

echo "[INFO] Starting lesson browser backend at ${LESSON_BACKEND_URL}"
echo "[INFO] Backend log: ${LOG_PATH}"
echo "[INFO] Browser suite log: ${BROWSER_LOG_PATH}"
echo "[INFO] Full-stack mode: $(if is_enabled "${FULL_STACK}"; then echo on; else echo off; fi)"

(
  cd "${BACKEND_DIR}"
  exec env "${server_env[@]}" "${SERVER_BIN}" --host "${LESSON_BACKEND_HOST}" --port "${LESSON_BACKEND_PORT}"
) >"${LOG_PATH}" 2>&1 &
SERVER_PID="$!"

if ! bash "${WAIT_SCRIPT}" --url "${LESSON_BACKEND_URL}" --timeout 120; then
  write_browser_report "backend_wait_failed" "1" "false"
  peptutor_test_budget_mark_report "browser" "${BROWSER_REPORT_JSON_PATH}"
  print_backend_log_tail
  exit 1
fi

echo "[INFO] Running checked-in /lesson real-browser suite"
set +e
(
  cd "${FRONTEND_DIR}"
  exec env \
    "NO_PROXY=${NO_PROXY}" \
    "no_proxy=${no_proxy}" \
    "PEPTUTOR_LESSON_REAL_BACKEND_URL=${LESSON_BACKEND_URL}" \
    "VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL=${LESSON_BACKEND_URL}" \
    "VITE_PEPTUTOR_LESSON_API_URL=${LESSON_BACKEND_URL}" \
    "VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS=1" \
    timeout --foreground "${BROWSER_TIMEOUT_SECONDS}s" \
    pnpm -F @proj-airi/stage-web test:run:browser:real
) 2>&1 | tee "${BROWSER_LOG_PATH}"
browser_status="${PIPESTATUS[0]}"
set -e
if [[ "${browser_status}" -ne 0 ]]; then
  if [[ "${browser_status}" -eq 124 ]]; then
    echo "[ERROR] Lesson browser suite timed out after ${BROWSER_TIMEOUT_SECONDS}s" >&2
    write_browser_report "timeout" "${browser_status}" "true"
  else
    write_browser_report "failed" "${browser_status}" "false"
  fi
  peptutor_test_budget_mark_report "browser" "${BROWSER_REPORT_JSON_PATH}"
  print_browser_log_tail
  print_backend_log_tail
  exit 1
fi

write_browser_report "passed" "${browser_status}" "false"
peptutor_test_budget_mark_report "browser" "${BROWSER_REPORT_JSON_PATH}"
echo "[PASS] Lesson browser smoke completed."
