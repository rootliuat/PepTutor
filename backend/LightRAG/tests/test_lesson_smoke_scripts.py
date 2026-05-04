from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

REPO_ROOT = Path(__file__).resolve().parents[3]
WAIT_SCRIPT = REPO_ROOT / "scripts" / "wait-for-lesson-backend.sh"
SMOKE_BROWSER_SCRIPT = REPO_ROOT / "scripts" / "smoke_lesson_browser.sh"
REGRESSION20_SCRIPT = REPO_ROOT / "scripts" / "smoke_lesson_regression_20.sh"
DEEP_BROWSER_SCRIPT = REPO_ROOT / "scripts" / "smoke_lesson_deep_browser.sh"
START_DEV_SCRIPT = REPO_ROOT / "scripts" / "start_lesson_dev.sh"
SMOKE_MATRIX_SCRIPT = REPO_ROOT / "scripts" / "smoke_lesson_matrix.py"
STRUCTURE_AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_lesson_structure.py"
TEMPLATE_TONE_AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_lesson_template_tone.py"
TEACHING_MOVE_AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_teaching_moves.py"
CLASSROOM_QUALITY_AUDIT_SCRIPT = (
    REPO_ROOT / "scripts" / "audit_classroom_quality_from_teaching_moves.py"
)
REDIRECT_EXPERIENCE_AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_redirect_experience.py"
LLM_TOKEN_USAGE_AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_llm_token_usage.py"
LLM_CONTEXT_BREAKDOWN_AUDIT_SCRIPT = (
    REPO_ROOT / "scripts" / "audit_llm_context_breakdown.py"
)
UNKNOWN_CONTEXT_ATTRIBUTION_AUDIT_SCRIPT = (
    REPO_ROOT / "scripts" / "audit_unknown_context_attribution.py"
)
RUNTIME_STATE_SHADOW_AUDIT_SCRIPT = (
    REPO_ROOT / "scripts" / "audit_runtime_state_minimal_view_shadow.py"
)
MILI_PERSONA_CONSISTENCY_AUDIT_SCRIPT = (
    REPO_ROOT / "scripts" / "audit_mili_persona_consistency.py"
)
DEEP_SMOKE_SCRIPT = REPO_ROOT / "temp" / "lesson_deep_smoke.py"


def _write_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_wait_script(tmp_path: Path, *, url: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    return subprocess.run(
        ["bash", str(WAIT_SCRIPT), "--url", url, "--timeout", str(timeout_seconds)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@dataclass(frozen=True)
class SmokeBrowserStubs:
    server_bin: Path
    wait_script: Path
    log_dir: Path
    server_pid_file: Path
    server_env_log: Path
    server_argv_log: Path
    server_events_log: Path
    wait_args_log: Path
    pnpm_args_log: Path
    pnpm_env_log: Path


def _prepare_smoke_browser_stubs(tmp_path: Path) -> SmokeBrowserStubs:
    bin_dir = tmp_path / "bin"
    log_dir = tmp_path / "logs"
    server_pid_file = tmp_path / "server.pid"
    server_env_log = tmp_path / "server-env.log"
    server_argv_log = tmp_path / "server-argv.log"
    server_events_log = tmp_path / "server-events.log"
    wait_args_log = tmp_path / "wait-args.log"
    pnpm_args_log = tmp_path / "pnpm-args.log"
    pnpm_env_log = tmp_path / "pnpm-env.log"

    server_bin = _write_executable(
        bin_dir / "lightrag-server",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        printf '%s\\n' "$$" > "{server_pid_file}"
        printf '%s\\n' "$*" > "{server_argv_log}"
        : > "{server_env_log}"
        printf 'PEPTUTOR_LESSON_LIVE_PROMPTS=%s\\n' "${{PEPTUTOR_LESSON_LIVE_PROMPTS-__unset__}}" >> "{server_env_log}"
        printf 'PEPTUTOR_DEBUG_SIGNALS=%s\\n' "${{PEPTUTOR_DEBUG_SIGNALS-__unset__}}" >> "{server_env_log}"
        printf 'PEPTUTOR_LESSON_VECTOR_RETRIEVAL=%s\\n' "${{PEPTUTOR_LESSON_VECTOR_RETRIEVAL-__unset__}}" >> "{server_env_log}"
        printf 'PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=%s\\n' "${{PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION-__unset__}}" >> "{server_env_log}"
        printf 'PEPTUTOR_SIMPLEMEM_WRITEBACK=%s\\n' "${{PEPTUTOR_SIMPLEMEM_WRITEBACK-__unset__}}" >> "{server_env_log}"
        printf 'PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=%s\\n' "${{PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL-__unset__}}" >> "{server_env_log}"

        trap 'printf "TERM\\n" >> "{server_events_log}"; exit 0' TERM INT
        trap 'printf "HUP\\n" >> "{server_events_log}"' HUP

        printf 'stub-server-ready\\n'
        printf 'STARTED\\n' > "{server_events_log}"
        while true; do
          /bin/sleep 1
        done
        """,
    )
    wait_script = _write_executable(
        tmp_path / "wait-for-lesson-backend.sh",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{wait_args_log}"
        /bin/sleep "${{PEPTUTOR_TEST_WAIT_SLEEP_SECONDS:-0}}"
        exit "${{PEPTUTOR_TEST_WAIT_EXIT_CODE:-0}}"
        """,
    )
    _write_executable(
        bin_dir / "pnpm",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{pnpm_args_log}"
        printf 'NO_PROXY=%s\\n' "${{NO_PROXY-__unset__}}" > "{pnpm_env_log}"
        printf 'no_proxy=%s\\n' "${{no_proxy-__unset__}}" >> "{pnpm_env_log}"
        printf 'PEPTUTOR_LESSON_REAL_BACKEND_URL=%s\\n' "${{PEPTUTOR_LESSON_REAL_BACKEND_URL-__unset__}}" >> "{pnpm_env_log}"
        printf 'VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL=%s\\n' "${{VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL-__unset__}}" >> "{pnpm_env_log}"
        printf 'VITE_PEPTUTOR_LESSON_API_URL=%s\\n' "${{VITE_PEPTUTOR_LESSON_API_URL-__unset__}}" >> "{pnpm_env_log}"
        printf 'VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS=%s\\n' "${{VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS-__unset__}}" >> "{pnpm_env_log}"
        if [[ -n "${{PEPTUTOR_TEST_PNPM_STDOUT:-}}" ]]; then
          printf '%b\\n' "${{PEPTUTOR_TEST_PNPM_STDOUT}}"
        fi
        /bin/sleep "${{PEPTUTOR_TEST_PNPM_SLEEP_SECONDS:-0}}"
        exit "${{PEPTUTOR_TEST_PNPM_EXIT_CODE:-0}}"
        """,
    )

    return SmokeBrowserStubs(
        server_bin=server_bin,
        wait_script=wait_script,
        log_dir=log_dir,
        server_pid_file=server_pid_file,
        server_env_log=server_env_log,
        server_argv_log=server_argv_log,
        server_events_log=server_events_log,
        wait_args_log=wait_args_log,
        pnpm_args_log=pnpm_args_log,
        pnpm_env_log=pnpm_env_log,
    )


def _run_smoke_browser_script(
    tmp_path: Path,
    *,
    stubs: SmokeBrowserStubs,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs.server_bin.parent}:{env['PATH']}"
    env["PEPTUTOR_LESSON_SMOKE_SERVER_BIN"] = str(stubs.server_bin)
    env["PEPTUTOR_LESSON_SMOKE_WAIT_SCRIPT"] = str(stubs.wait_script)
    env["PEPTUTOR_LESSON_SMOKE_LOG_DIR"] = str(stubs.log_dir)
    env["PEPTUTOR_LESSON_SMOKE_ARTIFACT_DIR"] = str(tmp_path / "browser-artifacts")
    env["PEPTUTOR_TEST_GOAL_ID"] = f"pytest-{tmp_path.name}"
    env["PEPTUTOR_TEST_GOAL_TYPE"] = "frontend"
    env["PEPTUTOR_TEST_BUDGET_DIR"] = str(tmp_path / "test-budget")

    for key in (
        "PEPTUTOR_LESSON_LIVE_PROMPTS",
        "PEPTUTOR_DEBUG_SIGNALS",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        "PEPTUTOR_LESSON_SMOKE_FULL_STACK",
        "PEPTUTOR_LESSON_SMOKE_KEEP_SERVER",
        "PEPTUTOR_LESSON_SMOKE_BACKEND_PORT",
        "PEPTUTOR_LESSON_SMOKE_BROWSER_TIMEOUT_SECONDS",
        "PEPTUTOR_TEST_PNPM_STDOUT",
        "PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON",
    ):
        env.pop(key, None)

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(SMOKE_BROWSER_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_regression20_script(
    tmp_path: Path,
    *,
    stubs: SmokeBrowserStubs,
    matrix_script: Path,
    matrix_args_log: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs.server_bin.parent}:{env['PATH']}"
    env["PEPTUTOR_LESSON_REGRESSION_SERVER_BIN"] = str(stubs.server_bin)
    env["PEPTUTOR_LESSON_REGRESSION_WAIT_SCRIPT"] = str(stubs.wait_script)
    env["PEPTUTOR_LESSON_REGRESSION_LOG_DIR"] = str(stubs.log_dir)
    env["PEPTUTOR_LESSON_REGRESSION_PYTHON"] = "/bin/bash"
    env["PEPTUTOR_LESSON_REGRESSION_MATRIX_SCRIPT"] = str(matrix_script)
    env["PEPTUTOR_LESSON_REGRESSION_OUT_DIR"] = str(tmp_path / "matrix-artifacts")
    env["PEPTUTOR_TEST_MATRIX_ARGS_LOG"] = str(matrix_args_log)
    env["PEPTUTOR_TEST_GOAL_ID"] = f"pytest-{tmp_path.name}"
    env["PEPTUTOR_TEST_GOAL_TYPE"] = "backend"
    env["PEPTUTOR_TEST_BUDGET_DIR"] = str(tmp_path / "test-budget")

    for key in (
        "PEPTUTOR_LESSON_LIVE_PROMPTS",
        "PEPTUTOR_DEBUG_SIGNALS",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        "PEPTUTOR_LESSON_REGRESSION_FULL_STACK",
        "PEPTUTOR_LESSON_REGRESSION_KEEP_SERVER",
        "PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON",
    ):
        env.pop(key, None)

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(REGRESSION20_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_deep_browser_script(
    tmp_path: Path,
    *,
    stubs: SmokeBrowserStubs,
    deep_script: Path,
    deep_args_log: Path,
    frontend_port: int,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs.server_bin.parent}:{env['PATH']}"
    env["PEPTUTOR_LESSON_DEEP_SERVER_BIN"] = str(stubs.server_bin)
    env["PEPTUTOR_LESSON_DEEP_WAIT_SCRIPT"] = str(stubs.wait_script)
    env["PEPTUTOR_LESSON_DEEP_LOG_DIR"] = str(stubs.log_dir)
    env["PEPTUTOR_LESSON_DEEP_PYTHON"] = "/bin/bash"
    env["PEPTUTOR_LESSON_DEEP_SCRIPT"] = str(deep_script)
    env["PEPTUTOR_LESSON_DEEP_ARTIFACT_DIR"] = str(tmp_path / "deep-artifacts")
    env["PEPTUTOR_LESSON_DEEP_HISTORY_ROOT"] = str(tmp_path / "history")
    env["PEPTUTOR_LESSON_DEEP_FRONTEND_PORT"] = str(frontend_port)
    env["PEPTUTOR_TEST_DEEP_ARGS_LOG"] = str(deep_args_log)
    env["PEPTUTOR_TEST_GOAL_ID"] = f"pytest-{tmp_path.name}"
    env["PEPTUTOR_TEST_GOAL_TYPE"] = "deep-s4"
    env["PEPTUTOR_TEST_BUDGET_DIR"] = str(tmp_path / "test-budget")

    for key in (
        "PEPTUTOR_LESSON_LIVE_PROMPTS",
        "PEPTUTOR_DEBUG_SIGNALS",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        "PEPTUTOR_LESSON_DEEP_FULL_STACK",
        "PEPTUTOR_LESSON_DEEP_KEEP_SERVERS",
        "PEPTUTOR_LESSON_DEEP_OBSERVER_TIMEOUT_SECONDS",
        "PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON",
    ):
        env.pop(key, None)

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(DEEP_BROWSER_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _read_budget_metadata(tmp_path: Path, goal_id: str) -> dict[str, object]:
    path = tmp_path / "test-budget" / f"{goal_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _load_deep_smoke_module():
    spec = importlib.util.spec_from_file_location("lesson_deep_smoke", DEEP_SMOKE_SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_smoke_matrix_module():
    spec = importlib.util.spec_from_file_location("smoke_lesson_matrix", SMOKE_MATRIX_SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_structure_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_lesson_structure",
        STRUCTURE_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_template_tone_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_lesson_template_tone",
        TEMPLATE_TONE_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_teaching_move_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_teaching_moves",
        TEACHING_MOVE_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_classroom_quality_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_classroom_quality_from_teaching_moves",
        CLASSROOM_QUALITY_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_redirect_experience_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_redirect_experience",
        REDIRECT_EXPERIENCE_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_llm_token_usage_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_llm_token_usage",
        LLM_TOKEN_USAGE_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_llm_context_breakdown_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_llm_context_breakdown",
        LLM_CONTEXT_BREAKDOWN_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_unknown_context_attribution_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_unknown_context_attribution",
        UNKNOWN_CONTEXT_ATTRIBUTION_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_runtime_state_shadow_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_runtime_state_minimal_view_shadow",
        RUNTIME_STATE_SHADOW_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_mili_persona_consistency_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_mili_persona_consistency",
        MILI_PERSONA_CONSISTENCY_AUDIT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_fake_structure_smoke_report(tmp_path: Path) -> Path:
    matrix = _load_smoke_matrix_module()
    audit = _load_structure_audit_module()
    catalog = audit.PilotLessonCatalog(
        manifest_path=audit._resolve_path(audit.DEFAULT_MANIFEST),
    )

    turns = []
    for page in matrix.PAGES:
        page_record = catalog.get_page(page.page_uid)
        state_block_uid = page_record.priority_blocks[0]
        for index in range(8):
            turns.append(
                {
                    "book": page.book,
                    "page_uid": page.page_uid,
                    "page_label": page.label,
                    "page_risk": page.risk,
                    "block_count": page.block_count,
                    "step": "page_entry" if index == 0 else f"turn_{index}",
                    "learner_input": None,
                    "http_status": 200,
                    "error": None,
                    "teacher_response": "继续练这一页。",
                    "teacherresponsesource": "llm",
                    "fallbackused": False,
                    "state_page_uid": page.page_uid,
                    "state_block_uid": state_block_uid,
                    "quality_flags": [],
                    "elapsed_ms": 1,
                    "latencyms": 1,
                }
            )

    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": matrix.REGRESSION_SET_ID,
                "pages": [
                    {
                        "book": page.book,
                        "page_uid": page.page_uid,
                        "label": page.label,
                        "block_count": page.block_count,
                        "risk": page.risk,
                    }
                    for page in matrix.PAGES
                ],
                "turns": turns,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return smoke_path


def _wait_for_process_exit(pid: int, *, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.05)
    return not _is_process_alive(pid)


def test_lesson_deep_smoke_writes_partial_report_for_incomplete_page(tmp_path: Path) -> None:
    deep_smoke = _load_deep_smoke_module()
    report = {
        "started_at": "2026-05-01T00:00:00",
        "frontend_url": "http://127.0.0.1:5173",
        "student_prefix": "deep-smoke-test",
        "pages": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "label": "P24",
                "student_id": "deep-smoke-test-p24",
                "initial": {},
                "turns": [],
                "refresh": {},
                "fatal_error": "SmokeTimeoutError('TB-G5S1U3-P24 timed out')",
                "tts_statuses": [],
                "websockets": [],
                "history_detail_fetches": [],
                "runtime_observation": {},
            }
        ],
        "server_history_detail_fetches": [],
        "history_files": [],
        "issues": [],
    }

    path = deep_smoke.write_report(
        report,
        tmp_path,
        history_root=tmp_path / "history",
        student_prefix="deep-smoke-test",
        status="partial",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "partial"
    assert payload["report_path"] == str(path)
    assert payload["summary"]["fatal_page_count"] == 1
    assert payload["summary"]["tts_request_count"] == 0
    assert any(issue["id"] == "S6" for issue in payload["issues"])
    assert any("TTS provider" in issue["title"] for issue in payload["issues"])


def test_smoke_matrix_copies_llm_token_usage_from_response_audit() -> None:
    matrix = _load_smoke_matrix_module()
    page = matrix.PagePlan(
        "G5S1",
        "TB-FIXTURE-P1",
        "fixture",
        1,
        "token usage",
        (),
    )
    token_usage = {
        "llm_call_count": 1,
        "prompt_bytes": 160,
        "prompt_token_estimate": 40,
        "completion_bytes": 24,
        "completion_token_estimate": 6,
        "total_token_estimate": 46,
        "token_count_source": "byte_estimate",
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-FIXTURE-P1",
        "block_uid": "TB-FIXTURE-P1-D1",
        "llm_provider": "test",
        "llm_model": "test-model",
        "rag_context_bytes": 0,
        "history_bytes": 2,
        "system_prompt_bytes": 32,
        "lesson_context_bytes": 126,
        "persona_prompt_bytes": 24,
        "persona_capsule_bytes": 24,
        "textbook_block_bytes": 48,
        "page_overview_bytes": 20,
        "runtime_state_bytes": 16,
        "runtime_state_minimal_view_bytes": 9,
        "runtime_state_legacy_frame_bytes": 20,
        "runtime_state_savings_candidate_bytes": 11,
        "teaching_move_bytes": 0,
        "policy_instruction_bytes": 30,
        "quality_revision_prompt_bytes": 0,
        "learner_input_bytes": 4,
        "prompt_frame_overhead_bytes": 3,
        "json_serialization_overhead_bytes": 2,
        "output_schema_bytes": 1,
        "planner_prompt_overhead_bytes": 0,
        "responder_prompt_overhead_bytes": 1,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 1,
        "other_bytes": 8,
        "unknown_context_bytes": 1,
        "calls": [],
    }
    turn = matrix.compact_turn(
        page=page,
        step="page_entry",
        learner_input=None,
        status=200,
        elapsed_ms=10,
        payload={
            "teacher_response": "我们开始。",
            "turn_label": "page_entry",
            "state": {
                "current_page_uid": "TB-FIXTURE-P1",
                "current_block_uid": "TB-FIXTURE-P1-D1",
            },
            "debug_signals": {
                "response_audit": {
                    "source": "llm",
                    "fallback_used": False,
                    "latency_ms": 10,
                    "route": "answer_turn_policy",
                    "llm_called": True,
                    "llm_token_usage": token_usage,
                },
                "persona": {
                    "persona_source": "mili_persona_capsule",
                    "persona_version": "v1",
                    "full_soul_injected": False,
                    "answer_turn_policy_persona_capsule_enabled": True,
                    "current_llm_call_persona_capsule_injected": True,
                    "persona_capsule_bytes_configured": 12,
                    "persona_capsule_bytes_metered": 24,
                    "airi_performance": {
                        "motion": "Explain",
                        "expression": "thinking",
                        "emotion": "thinking",
                        "speech_style": "normal",
                        "interrupt_policy": "finish_current_sentence",
                        "mouth_intensity": 0.7,
                    },
                },
            },
        },
    )

    assert turn["llm_token_usage"] == token_usage
    assert turn["persona_source"] == "mili_persona_capsule"
    assert turn["persona_version"] == "v1"
    assert turn["full_soul_injected"] is False
    assert turn["answer_turn_policy_persona_capsule_enabled"] is True
    assert turn["current_llm_call_persona_capsule_injected"] is True
    assert turn["persona_capsule_bytes_configured"] == 12
    assert turn["persona_capsule_bytes_metered"] == 24
    assert turn["live2d_motion"] == "Explain"
    assert turn["speech_style"] == "normal"
    assert turn["interrupt_policy"] == "finish_current_sentence"
    summary = matrix.summarize([turn], [])
    assert summary["llm_call_count"] == 1
    assert summary["llm_prompt_token_estimate"] == 40
    assert summary["llm_completion_token_estimate"] == 6
    assert summary["interrupt_policy_counts"] == {"finish_current_sentence": 1}
    assert turn["llm_token_usage"]["textbook_block_bytes"] == 48
    assert turn["llm_token_usage"]["persona_capsule_bytes"] == 24
    assert turn["llm_token_usage"]["other_bytes"] == 8
    assert turn["llm_token_usage"]["unknown_context_bytes"] == 1
    assert turn["llm_token_usage"]["prompt_frame_overhead_bytes"] == 3
    assert turn["llm_token_usage"]["runtime_state_minimal_view_bytes"] == 9
    assert turn["llm_token_usage"]["runtime_state_legacy_frame_bytes"] == 20
    assert turn["llm_token_usage"]["runtime_state_savings_candidate_bytes"] == 11


def test_smoke_matrix_persona_semantics_distinguish_call_injection() -> None:
    matrix = _load_smoke_matrix_module()
    page = matrix.PAGES[0]
    llm_only_turn = matrix.compact_turn(
        page=page,
        step="page_entry",
        learner_input=None,
        status=200,
        elapsed_ms=10,
        payload={
            "teacher_response": "我们开始。",
            "turn_label": "page_entry",
            "state": {
                "current_page_uid": page.page_uid,
                "current_block_uid": f"{page.page_uid}-D1",
            },
            "debug_signals": {
                "response_audit": {
                    "source": "llm",
                    "fallback_used": False,
                    "latency_ms": 10,
                    "route": "llm_only",
                    "llm_called": True,
                    "llm_token_usage": {
                        "llm_call_count": 1,
                        "prompt_token_estimate": 10,
                        "completion_token_estimate": 2,
                        "calls": [{"route": "llm_only", "persona_capsule_bytes": 0}],
                    },
                },
                "persona": {
                    "persona_source": "mili_persona_capsule",
                    "persona_version": "v1",
                    "full_soul_injected": False,
                    "answer_turn_policy_persona_capsule_enabled": True,
                    "current_llm_call_persona_capsule_injected": False,
                    "persona_capsule_bytes_configured": 269,
                    "persona_capsule_bytes_metered": 0,
                },
            },
        },
    )
    deterministic_turn = matrix.compact_turn(
        page=page,
        step="page_entry",
        learner_input=None,
        status=200,
        elapsed_ms=5,
        payload={
            "teacher_response": "我们开始。",
            "turn_label": "page_entry",
            "state": {
                "current_page_uid": page.page_uid,
                "current_block_uid": f"{page.page_uid}-D1",
            },
            "debug_signals": {
                "response_audit": {
                    "source": "deterministic",
                    "fallback_used": False,
                    "latency_ms": 0,
                    "route": "deterministic_only",
                    "llm_called": False,
                },
                "persona": {
                    "persona_source": "mili_persona_capsule",
                    "persona_version": "v1",
                    "full_soul_injected": False,
                    "answer_turn_policy_persona_capsule_enabled": True,
                    "current_llm_call_persona_capsule_injected": False,
                    "persona_capsule_bytes_configured": 269,
                    "persona_capsule_bytes_metered": 0,
                },
            },
        },
    )

    assert llm_only_turn["answer_turn_policy_persona_capsule_enabled"] is True
    assert llm_only_turn["current_llm_call_persona_capsule_injected"] is False
    assert llm_only_turn["persona_capsule_bytes_metered"] == 0
    assert deterministic_turn["llm_token_usage"] is None
    assert deterministic_turn["current_llm_call_persona_capsule_injected"] is False
    assert deterministic_turn["persona_capsule_bytes_metered"] == 0


def test_lesson_deep_smoke_flags_any_non_2xx_tts_status() -> None:
    deep_smoke = _load_deep_smoke_module()
    report = {
        "started_at": "2026-05-02T00:00:00",
        "frontend_url": "http://127.0.0.1:5173",
        "student_prefix": "deep-smoke-test",
        "pages": [
            {
                "page_uid": "TB-G5S1U3-P26",
                "label": "P26",
                "student_id": "deep-smoke-test-p26",
                "initial": {
                    "result": {
                        "airi_performance": {},
                        "ui": {"tts": "HTTP 502 Bad Gateway"},
                    }
                },
                "turns": [],
                "refresh": {"after_refresh_turn_ok": True},
                "tts_statuses": [
                    {"url": "http://127.0.0.1/api/peptutor/edge-tts", "status": 200},
                    {"url": "http://127.0.0.1/api/peptutor/edge-tts", "status": 502},
                ],
                "websockets": [],
                "history_detail_fetches": [],
                "runtime_observations": [
                    {
                        "tts_synthesis_state": "http_error",
                        "tts_playback_state": "skipped",
                        "mouth_open_observed": False,
                        "tts_overlap_detected": False,
                    }
                ],
                "runtime_observation": {
                    "tts_synthesis_state": "http_error",
                    "tts_playback_state": "skipped",
                    "mouth_open_observed": False,
                    "tts_overlap_detected": False,
                },
            }
        ],
        "server_history_detail_fetches": [],
        "history_files": [],
        "issues": [],
    }

    issues = deep_smoke.analyze(report)

    assert any(
        issue["id"] == "S4"
        and issue["severity"] == "major"
        and issue["title"] == "TTS HTTP request returned non-2xx"
        and "502" in issue["evidence"]
        for issue in issues
    )


def test_lesson_deep_smoke_summarizes_interrupt_stop_type_observations() -> None:
    deep_smoke = _load_deep_smoke_module()
    report = {
        "pages": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "initial": {"result": {"turn_label": "page_entry"}},
                "turns": [],
                "refresh": {},
                "runtime_observations": [
                    {
                        "tts_playback_state": "interrupted",
                        "tts_stop_reason": "lesson-learner-transcription",
                        "tts_stop_type": "final_transcript_interrupt",
                        "tts_overlap_detected": False,
                        "facts": {
                            "lesson-airi-visible-fact-interrupt_policy": "barge_in_allowed",
                        },
                    },
                    {
                        "tts_playback_state": "playing",
                        "tts_stop_reason": "none",
                        "tts_stop_type": "none",
                        "tts_overlap_detected": False,
                        "facts": {
                            "lesson-airi-visible-fact-interrupt_policy": "finish_current_sentence",
                        },
                    },
                    {
                        "tts_playback_state": "playing",
                        "tts_stop_reason": "none",
                        "tts_stop_type": "none",
                        "tts_overlap_detected": True,
                        "facts": {
                            "lesson-airi-visible-fact-interrupt_policy": "no_interrupt",
                        },
                    },
                ],
            }
        ],
        "issues": [],
    }

    summary = deep_smoke.summarize_report(report)

    assert summary["tts_stop_type_counts"] == {"final_transcript_interrupt": 1}
    assert summary["tts_playback_stop_reason_counts"] == {"lesson-learner-transcription": 1}
    assert summary["final_transcript_interrupt_count"] == 1
    assert summary["finish_current_sentence_defer_count"] == 1
    assert summary["no_interrupt_count"] == 1
    assert summary["playback_overlap_count"] == 1


def test_lesson_deep_smoke_waits_for_http_ok_idle_playback_to_resolve() -> None:
    deep_smoke = _load_deep_smoke_module()

    assert deep_smoke.should_wait_for_tts_runtime_progress({
        "tts_synthesis_state": "http_ok",
        "tts_playback_state": "idle",
        "tts_stop_reason": "none",
        "mouth_open_observed": False,
    })
    assert not deep_smoke.should_wait_for_tts_runtime_progress({
        "tts_synthesis_state": "http_ok",
        "tts_playback_state": "playing",
        "tts_stop_reason": "none",
        "mouth_open_observed": False,
    })
    assert not deep_smoke.should_wait_for_tts_runtime_progress({
        "tts_synthesis_state": "http_ok",
        "tts_playback_state": "idle",
        "tts_stop_reason": "lesson-learner-send",
        "mouth_open_observed": False,
    })


def test_lesson_deep_smoke_flags_short_answer_object_praise_without_grounding() -> None:
    deep_smoke = _load_deep_smoke_module()
    summary = deep_smoke.result_summary(
        {"teacher_response": "你说的是pizza，那个很好吃。"},
        1,
        {},
        learner_input="pizza",
    )
    grounded = deep_smoke.result_summary(
        {"teacher_response": "pizza 可以算 food，不过这页图上我们先找本页词，比如 cake。"},
        1,
        {},
        learner_input="pizza",
    )

    assert summary["generic_praise_for_short_answer"] is True
    assert grounded["generic_praise_for_short_answer"] is False


def test_lesson_matrix_p49_includes_pizza_short_answer_regression() -> None:
    matrix = _load_smoke_matrix_module()
    p49 = next(page for page in matrix.PAGES if page.page_uid == "TB-G6S2Recycle2-P49")

    assert p49.inputs == ("第一块", "pizza", "news", "我不知道", "我想学第二块")


def test_lesson_matrix_summary_enforces_fixed_20_page_regression_acceptance() -> None:
    matrix = _load_smoke_matrix_module()
    turns = []
    for page in matrix.PAGES:
        for index in range(8):
            turns.append({
                "page_uid": page.page_uid,
                "step": f"turn_{index}",
                "learner_input": None,
                "http_status": 200,
                "error": None,
                "teacher_response": "继续练这一页。",
                "teacherresponsesource": "llm",
                "fallbackused": False,
                "state_page_uid": page.page_uid,
                "elapsed_ms": 1,
                "latencyms": 1,
            })

    summary = matrix.summarize(turns, [])

    assert summary["regression_set_id"] == "lesson-core-20-v1"
    assert summary["page_count"] == 20
    assert summary["turn_count"] == 160
    assert summary["acceptance_passed"] is True

    turns[0]["fallbackused"] = True
    rejected = matrix.summarize(turns, [])
    assert rejected["fallback_count"] == 1
    assert rejected["acceptance_passed"] is False


def test_lesson_matrix_flags_phonics_tautology_as_s3_issue() -> None:
    matrix = _load_smoke_matrix_module()
    flags = matrix.quality_flags("cow uses the cow sound。先读 cow。")

    assert "phonics_tautology" in flags

    turn = {
        "page_uid": "TB-G5S1U3-P26",
        "step": "turn_3",
        "learner_input": "What does cow mean?",
        "http_status": 200,
        "error": None,
        "teacher_response": "cow uses the cow sound。先读 cow。",
        "teacherresponsesource": "llm",
        "fallbackused": False,
        "state_page_uid": "TB-G5S1U3-P26",
        "quality_flags": flags,
        "block_count": 4,
        "elapsed_ms": 1,
        "latencyms": 1,
    }

    issues = matrix.analyze([turn])

    assert any(issue["title"] == "phonics reply uses tautological sound label" for issue in issues)


def test_lesson_matrix_flags_short_answer_object_praise_without_task_grounding() -> None:
    matrix = _load_smoke_matrix_module()
    flags = matrix.quality_flags(
        "你说的是pizza，那个很好吃。",
        learner_input="pizza",
    )
    grounded_flags = matrix.quality_flags(
        "pizza 可以算 food，不过这页图上我们先找本页词，比如 cake。",
        learner_input="pizza",
    )

    assert "generic_praise_for_short_answer" in flags
    assert "generic_praise_for_short_answer" not in grounded_flags

    turn = {
        "page_uid": "TB-G6S2Recycle2-P49",
        "step": "turn_2",
        "learner_input": "pizza",
        "http_status": 200,
        "error": None,
        "teacher_response": "你说的是pizza，那个很好吃。",
        "teacherresponsesource": "llm",
        "fallbackused": False,
        "state_page_uid": "TB-G6S2Recycle2-P49",
        "quality_flags": flags,
        "block_count": 4,
        "elapsed_ms": 1,
        "latencyms": 1,
    }

    issues = matrix.analyze([turn])

    assert any(
        issue["title"] == "generic praise for short answer lacks task grounding"
        for issue in issues
    )


def test_lesson_matrix_allows_page_entry_vocabulary_glosses() -> None:
    matrix = _load_smoke_matrix_module()
    page_entry = (
        "第一块：先认识5个餐厅里的词，比如 sandwich 三明治、"
        "hamburger 汉堡、salad 沙拉。第二块：练怎么用 I'd like 点餐。"
    )

    assert "broken_mixed_english" not in matrix.quality_flags(page_entry)
    assert "broken_mixed_english" not in matrix.quality_flags(
        "你刚才说的是 turn left.\n我们先说这个：Where is the museum shop."
    )
    assert "broken_mixed_english" not in matrix.quality_flags(
        "clock 是“钟”。回到刚才的小任务：你听我说 'cl' 开头的 clean，能试一试吗？"
    )
    assert "broken_mixed_english" in matrix.quality_flags("用 I'd like. 开头回答。")


def test_lesson_matrix_flags_incomplete_sentence_tail_as_s3_issue() -> None:
    matrix = _load_smoke_matrix_module()
    flags = matrix.quality_flags("请你试着用 Usually, I come... 来回答，")

    assert "incomplete_sentence_tail" in flags
    assert "incomplete_sentence_tail" not in matrix.quality_flags(
        "请你试着用 Usually, I come ... 来回答。"
    )

    turn = {
        "page_uid": "TB-G6S1U2-P14",
        "step": "turn_2",
        "learner_input": "How do you come to school?",
        "http_status": 200,
        "error": None,
        "teacher_response": "请你试着用 Usually, I come... 来回答，",
        "teacherresponsesource": "policy_repaired",
        "fallbackused": False,
        "state_page_uid": "TB-G6S1U2-P14",
        "quality_flags": flags,
        "block_count": 4,
        "elapsed_ms": 1,
        "latencyms": 1,
    }

    issues = matrix.analyze([turn])

    assert any(
        issue["title"] == "teacher response ends with incomplete punctuation"
        for issue in issues
    )


def test_lesson_matrix_does_not_fail_on_sub_10s_latency_jitter() -> None:
    matrix = _load_smoke_matrix_module()
    turn = {
        "page_uid": "TB-G5S2U2-P19",
        "step": "turn_3",
        "learner_input": "我不知道",
        "http_status": 200,
        "error": None,
        "teacher_response": "继续这一页。",
        "teacherresponsesource": "policy",
        "fallbackused": False,
        "state_page_uid": "TB-G5S2U2-P19",
        "quality_flags": [],
        "block_count": 3,
        "elapsed_ms": 8465,
        "latencyms": 8056,
        "live2d_motion": "idle",
        "live2d_expression": "known_capability_gap",
    }

    assert matrix.analyze([turn]) == []


def test_lesson_template_tone_audit_counts_guardrails_and_watch_phrases(
    tmp_path: Path,
) -> None:
    audit = _load_template_tone_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G5S1U3-P24",
                        "page_label": "P24",
                        "step": "page_entry",
                        "learner_input": None,
                        "teacher_response": (
                            "这一页练点餐，先选入口：第一块。"
                            "你想先学哪一块？可以说 第一块。"
                        ),
                        "teacherresponsesource": "llm_repaired",
                        "repair_reason": "classroom_pacing",
                    },
                    {
                        "page_uid": "TB-G5S1U3-P22",
                        "page_label": "P22",
                        "step": "turn_1",
                        "learner_input": "I like sandwiches.",
                        "teacher_response": (
                            "你刚才说的是 I like sandwiches.\n"
                            "这一步先抓住 favourite food.\n"
                            "跟我读：favourite food."
                        ),
                        "teacherresponsesource": "policy_repaired",
                        "repair_reason": "reply_quality_revision;classroom_phrasing",
                    },
                    {
                        "page_uid": "TB-G5S2U1-P4",
                        "page_label": "P4",
                        "step": "turn_4",
                        "learner_input": "start class",
                        "teacher_response": "先定一个入口：Let's talk 或 Let's try。你想从哪块开始？",
                        "teacherresponsesource": "llm_repaired",
                        "repair_reason": "classroom_pacing",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_template_tone(smoke_report_path=smoke_path)
    patterns = {item["pattern_id"]: item for item in report["pattern_summaries"]}

    assert report["kind"] == "lesson_template_tone_audit"
    assert report["summary"]["page_count"] == 3
    assert report["summary"]["turn_count"] == 3
    assert report["summary"]["hit_count"] == 5
    assert "pattern-turn hits" in report["summary"]["hit_count_definition"]
    assert patterns["module_choice_entry"]["verdict"] == "necessary_guardrail"
    assert patterns["learner_echo"]["verdict"] == "necessary_guardrail"
    assert patterns["now_step_practice"]["verdict"] == "tone_watch"
    assert patterns["learning_entry_choice"]["verdict"] == "tone_watch"
    assert patterns["repeat_after_me"]["verdict"] == "tone_watch"
    assert "tone_revision_candidate" not in report["summary"]["verdict_counts"]
    assert any("tone_watch" in note for note in report["interpretation"])

    json_path, md_path = audit.write_report(report, tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Lesson Template Tone Audit" in md_text
    assert "pattern-turn hits" in md_text


def test_teaching_move_audit_aligns_runtime_moves_to_smoke_turns(
    tmp_path: Path,
) -> None:
    audit = _load_teaching_move_audit_module()
    single_payload = {
        "schema_version": "peptutor-teaching-move-v1",
        "detected_signal": "module_navigation_unavailable",
        "move": "single_block_guard",
        "teaching_action": "redirect",
        "rationale": "The learner requested another page module.",
        "evidence_fields_used": [
            "module_choice_skill.navigation_request",
            "page_overview.modules",
        ],
        "expected_next_learner_action": "Continue with the current single-block prompt.",
    }
    vocab_payload = {
        "schema_version": "peptutor-teaching-move-v1",
        "detected_signal": "vocabulary_question",
        "move": "vocab_answer_return",
        "teaching_action": "explain",
        "rationale": "Answer the word narrowly and return to the active task.",
        "evidence_fields_used": [
            "learner_input",
            "planner.retrieval_mode",
            "retrieval_selection.block_uids",
            "support_hits",
            "runtime_state.last_teacher_question",
            "return_anchor",
        ],
        "expected_next_learner_action": "Continue with the current task prompt.",
        "payload_fields": {
            "query_term": "thirsty",
            "retrieval_mode": "unit",
            "return_anchor": "What would Zoom like to eat?",
            "active_prompt": "What would Zoom like to eat?",
            "return_to_current_task": True,
            "retrieval_evidence_count": 1,
            "support_evidence_count": 1,
        },
        "constraints": [
            "Do not change the current page or block.",
            "Ground the word meaning in retrieval or support evidence.",
        ],
    }
    gentle_payload = {
        "schema_version": "peptutor-teaching-move-v1",
        "detected_signal": "off_topic",
        "move": "gentle_redirect",
        "teaching_action": "redirect",
        "rationale": "Preserve the current target after a learner detour.",
        "evidence_fields_used": [
            "learner_input",
            "runtime_state.current_page_uid",
            "runtime_state.current_block_uid",
            "runtime_state.last_teacher_question",
        ],
        "expected_next_learner_action": "Return to the active prompt.",
        "payload_fields": {
            "learner_input": "I want to play basketball.",
            "interpreted_intent": "off_topic",
            "current_target": "Talk about favourite food.",
            "target_phrase": "What's your favourite food?",
            "active_prompt": "What's your favourite food?",
            "return_anchor": "What's your favourite food?",
            "next_action": "return_to_active_task",
            "correction_kind": "incorrect",
            "route": "answer_turn_policy",
            "turn_label": "answer_question",
            "preserve_page_uid": "TB-G5S1U3-P22",
            "preserve_block_uid": "TB-G5S1U3-P22-D1",
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": "What's your favourite food?",
            "answer_target": "",
            "answer_frame": "My favourite food is ...",
            "action_source": "active_prompt",
        },
        "constraints": [
            "Do not change the current page or block.",
            "Do not change the runtime route.",
        ],
    }
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G5S1U3-P22",
                        "step": "turn_5",
                        "learner_input": "我想学第二块",
                        "route": "single_module_navigation_guard",
                        "turn_label": "navigation",
                        "teacherresponsesource": "deterministic",
                        "repair_reason": "none",
                    },
                    {
                        "page_uid": "TB-G6S1U1-P2",
                        "step": "turn_4",
                        "learner_input": "museum",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "teacherresponsesource": "llm_repaired",
                        "repair_reason": "generic_praise_stripped",
                    },
                    {
                        "page_uid": "TB-G5S1U3-P31",
                        "step": "turn_2",
                        "learner_input": "What does thirsty mean?",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "teacherresponsesource": "llm_repaired",
                        "repair_reason": "classroom_pacing",
                        "state_block_uid": "TB-G5S1U3-P31-D1",
                    },
                    {
                        "page_uid": "TB-G5S1U3-P22",
                        "step": "rapid_b_same_state",
                        "learner_input": "I want to play basketball.",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "teacherresponsesource": "policy_repaired",
                        "repair_reason": "reply_quality_revision",
                        "state_block_uid": "TB-G5S1U3-P22-D1",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "smoke_lesson_regression20.log"
    log_path.write_text(
        "\n".join(
            [
                (
                    "INFO: Lesson teaching move planned "
                    f"route=single_module_navigation_guard payload={json.dumps(single_payload, sort_keys=True)}"
                ),
                (
                    "INFO: Lesson teacher response audit turn_label=navigation "
                    "llmcalled=false llmprovider=openai latencyms=0 "
                    "fallbackused=false fallbackreason=none "
                    "teacherresponse_source=deterministic response_chars=71 "
                    "route=single_module_navigation_guard"
                ),
                (
                    "INFO: Lesson teaching move planned "
                    f"route=vocab_answer_return payload={json.dumps(vocab_payload, sort_keys=True)}"
                ),
                (
                    "INFO: Lesson turn audit path=rag_plus_llm turn_label=ask_knowledge "
                    "page_uid=TB-G5S1U3-P31 block_uid=TB-G5S1U3-P31-D1 "
                    "teaching_action=explain retrieval_mode=unit retrieval_evidence=1 "
                    "support_evidence=1 responder_llm=True stream=False fallback_chars=30"
                ),
                (
                    "INFO: Lesson teaching move planned "
                    f"route=gentle_redirect payload={json.dumps(gentle_payload, sort_keys=True)}"
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = audit.audit_teaching_moves(
        smoke_report_path=smoke_path,
        runtime_log_path=log_path,
    )

    assert report["kind"] == "lesson_teaching_move_audit"
    assert report["summary"]["audit_passed"] is True
    assert report["summary"]["move_count"] == 3
    assert report["summary"]["move_type_counts"] == {
        "gentle_redirect": 1,
        "single_block_guard": 1,
        "vocab_answer_return": 1,
    }
    assert report["summary"]["route_counts"] == {
        "answer_turn_policy": 1,
        "rag_plus_llm": 1,
        "single_module_navigation_guard": 1,
    }
    assert report["summary"]["turn_label_counts"] == {
        "ask_knowledge": 1,
        "answer_question": 1,
        "navigation": 1,
    }
    assert report["summary"]["teaching_action_field_missing_count"] == 0
    assert report["summary"]["teaching_action_field_warning_count"] == 0
    assert report["summary"]["teaching_action_semantic_warning_count"] == 0
    assert report["summary"]["teaching_action_type_counts"] == {"question": 1}
    assert report["summary"]["expected_student_action_counts"] == {"answer": 1}
    assert report["missing_payload_fields"] == []
    assert report["teaching_action_field_missing"] == []
    assert report["teaching_action_field_warnings"] == []
    assert report["teaching_action_semantic_warnings"] == []
    assert report["unknown_move_types"] == []
    assert report["route_turn_label_mismatches"] == []
    assert report["examples_by_move_type"]["vocab_answer_return"][0]["page_uid"] == (
        "TB-G5S1U3-P31"
    )
    assert report["moves"][1]["payload"]["payload_fields"]["query_term"] == "thirsty"
    assert report["moves"][2]["payload"]["payload_fields"]["next_action"] == (
        "return_to_active_task"
    )

    json_path, md_path = audit.write_report(report, tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Lesson Teaching Move Audit" in md_text
    assert "gentle_redirect" in md_text
    assert "vocab_answer_return" in md_text


def test_teaching_move_audit_flags_missing_payload_and_route_mismatch(
    tmp_path: Path,
) -> None:
    audit = _load_teaching_move_audit_module()
    bad_payload = {
        "schema_version": "peptutor-teaching-move-v1",
        "detected_signal": "vocabulary_question",
        "move": "vocab_answer_return",
        "teaching_action": "explain",
        "rationale": "Answer the word narrowly.",
        "evidence_fields_used": ["learner_input"],
        "expected_next_learner_action": "Continue.",
        "payload_fields": {
            "query_term": "museum",
            "retrieval_mode": "block",
            "return_to_current_task": True,
            "retrieval_evidence_count": 1,
            "support_evidence_count": 0,
        },
    }
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "turns": [
                    {
                        "page_uid": "TB-G6S1U1-P2",
                        "step": "turn_4",
                        "learner_input": "museum",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "smoke_lesson_regression20.log"
    log_path.write_text(
        "\n".join(
            [
                (
                    "INFO: Lesson teaching move planned "
                    f"route=vocab_answer_return payload={json.dumps(bad_payload, sort_keys=True)}"
                ),
                (
                    "INFO: Lesson turn audit path=rag_plus_llm turn_label=ask_knowledge "
                    "page_uid=TB-G6S1U1-P2 block_uid=TB-G6S1U1-P2-D1 "
                    "teaching_action=explain retrieval_mode=block retrieval_evidence=1 "
                    "support_evidence=0 responder_llm=True stream=False fallback_chars=30"
                ),
            ]
        ),
        encoding="utf-8",
    )

    report = audit.audit_teaching_moves(
        smoke_report_path=smoke_path,
        runtime_log_path=log_path,
    )

    assert report["summary"]["audit_passed"] is False
    assert report["summary"]["missing_payload_field_count"] == 1
    assert report["missing_payload_fields"][0]["missing_fields"] == [
        "payload_fields.return_anchor",
        "payload_fields.active_prompt",
    ]
    assert report["summary"]["route_turn_label_mismatch_count"] == 1
    assert "no matching smoke turn" in report["route_turn_label_mismatches"][0]["reasons"]


def test_teaching_move_audit_checks_gentle_redirect_action_fields(
    tmp_path: Path,
) -> None:
    audit = _load_teaching_move_audit_module()
    payload = {
        "schema_version": "peptutor-teaching-move-v1",
        "detected_signal": "off_topic",
        "move": "gentle_redirect",
        "teaching_action": "redirect",
        "rationale": "Preserve the current target after a learner detour.",
        "evidence_fields_used": ["learner_input"],
        "expected_next_learner_action": "Return to the active prompt.",
        "payload_fields": {
            "learner_input": "water",
            "interpreted_intent": "off_topic",
            "current_target": "Talk about the museum shop.",
            "target_phrase": "Where is the museum shop?",
            "active_prompt": "Where is the museum shop?",
            "return_anchor": "Where is the museum shop?",
            "next_action": "return_to_active_task",
            "correction_kind": "incorrect",
            "route": "answer_turn_policy",
            "turn_label": "answer_question",
            "preserve_page_uid": "TB-G6S1U1-P4",
            "preserve_block_uid": "TB-G6S1U1-P4-D2",
            "target_role": "mystery",
            "expected_student_action": "answer",
            "question_target": "Where is the museum shop?",
            "answer_target": "",
            "answer_frame": "",
            "action_source": "block_core_pattern",
        },
    }
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G6S1U1-P4",
                        "step": "turn_2",
                        "learner_input": "water",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G6S1U1-P4-D2",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "smoke_lesson_regression20.log"
    log_path.write_text(
        "\n".join(
            [
                (
                    "INFO: Lesson teaching move planned "
                    f"route=gentle_redirect payload={json.dumps(payload, sort_keys=True)}"
                )
            ]
        ),
        encoding="utf-8",
    )

    report = audit.audit_teaching_moves(
        smoke_report_path=smoke_path,
        runtime_log_path=log_path,
    )

    assert report["summary"]["audit_passed"] is False
    assert report["summary"]["teaching_action_field_missing_count"] == 1
    assert report["teaching_action_field_missing"][0]["issues"] == [
        "target_role:unknown"
    ]


def test_teaching_move_audit_reports_action_semantic_warnings(
    tmp_path: Path,
) -> None:
    audit = _load_teaching_move_audit_module()

    def payload(
        *,
        page_uid: str,
        block_uid: str,
        learner_input: str,
        target_phrase: str,
        active_prompt: str,
        target_role: str,
        expected_student_action: str,
        question_target: str,
        answer_target: str,
        answer_frame: str,
        action_source: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "peptutor-teaching-move-v1",
            "detected_signal": "off_topic",
            "move": "gentle_redirect",
            "teaching_action": "redirect",
            "rationale": "Preserve the current target after a learner detour.",
            "evidence_fields_used": ["learner_input"],
            "expected_next_learner_action": "Return to the active prompt.",
            "payload_fields": {
                "learner_input": learner_input,
                "interpreted_intent": "off_topic",
                "current_target": "Keep the current classroom target.",
                "target_phrase": target_phrase,
                "active_prompt": active_prompt,
                "return_anchor": target_phrase,
                "next_action": "return_to_active_task",
                "correction_kind": "incorrect",
                "route": "answer_turn_policy",
                "turn_label": "answer_question",
                "preserve_page_uid": page_uid,
                "preserve_block_uid": block_uid,
                "target_role": target_role,
                "expected_student_action": expected_student_action,
                "question_target": question_target,
                "answer_target": answer_target,
                "answer_frame": answer_frame,
                "action_source": action_source,
            },
        }

    cases = [
        (
            "TB-G6S2U1-P2",
            "TB-G6S2U1-P2-D1",
            "water",
            payload(
                page_uid="TB-G6S2U1-P2",
                block_uid="TB-G6S2U1-P2-D1",
                learner_input="water",
                target_phrase="I'm 1.6 metres tall?",
                active_prompt="I'm 1.6 metres tall.",
                target_role="question",
                expected_student_action="answer",
                question_target="I'm 1.6 metres tall?",
                answer_target="I'm 1.6 metres tall.",
                answer_frame="",
                action_source="block_core_pattern",
            ),
            "question_role_uses_declarative_sentence",
        ),
        (
            "TB-G6S2U1-P4",
            "TB-G6S2U1-P4-D2",
            "How tall are you?",
            payload(
                page_uid="TB-G6S2U1-P4",
                block_uid="TB-G6S2U1-P4-D2",
                learner_input="How tall are you?",
                target_phrase="How tall are you",
                active_prompt="How tall is it?",
                target_role="question",
                expected_student_action="answer",
                question_target="How tall are you",
                answer_target="",
                answer_frame="",
                action_source="block_core_pattern",
            ),
            "height_object_question_overridden_by_personal_question",
        ),
        (
            "TB-G5S1U3-P31",
            "TB-G5S1U3-P31-D1",
            "Zip",
            payload(
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="Zip",
                target_phrase="What would Zoom like to eat?",
                active_prompt="What would Zoom like to eat?",
                target_role="story",
                expected_student_action="answer",
                question_target="What would Zoom like to eat?",
                answer_target="Zoom would like a salad.",
                answer_frame="",
                action_source="story_context",
            ),
            "story_role_without_answer_frame",
        ),
        (
            "TB-G5S2U1-P6",
            "TB-G5S2U1-P6-D1",
            "water",
            payload(
                page_uid="TB-G5S2U1-P6",
                block_uid="TB-G5S2U1-P6-D1",
                learner_input="water",
                target_phrase="cl' as in",
                active_prompt="Learn the consonant blend 'cl' as in 'clean'.",
                target_role="phonics",
                expected_student_action="repeat",
                question_target="Do you know the word clean?",
                answer_target="cl' as in",
                answer_frame="",
                action_source="phonics_context",
            ),
            "phonics_role_has_question_target",
        ),
    ]
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": page_uid,
                        "step": f"turn_{index}",
                        "learner_input": learner_input,
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": block_uid,
                    }
                    for index, (page_uid, block_uid, learner_input, _, _) in enumerate(
                        cases,
                        start=1,
                    )
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "smoke_lesson_regression20.log"
    log_path.write_text(
        "\n".join(
            "INFO: Lesson teaching move planned "
            f"route=gentle_redirect payload={json.dumps(case_payload, sort_keys=True)}"
            for _, _, _, case_payload, _ in cases
        ),
        encoding="utf-8",
    )

    report = audit.audit_teaching_moves(
        smoke_report_path=smoke_path,
        runtime_log_path=log_path,
    )

    assert report["summary"]["audit_passed"] is False
    assert report["summary"]["teaching_action_semantic_warning_count"] == 4
    all_issues = [
        issue
        for warning in report["teaching_action_semantic_warnings"]
        for issue in warning["issues"]
    ]
    for _, _, _, _, expected_issue in cases:
        assert expected_issue in all_issues
    assert "height_object_target_phrase_overridden_by_personal_question" in all_issues
    assert "story_role_without_answer_frame" in all_issues
    assert "phonics_role_uses_fragment_target" in all_issues


def test_classroom_quality_audit_reports_gentle_redirect_hotspots_and_candidates(
    tmp_path: Path,
) -> None:
    audit = _load_classroom_quality_audit_module()

    def gentle_move(
        *,
        page_uid: str,
        step: str,
        learner_input: str,
        block_uid: str,
        target_phrase: str,
        active_prompt: str,
        return_anchor: str,
    ) -> dict[str, object]:
        return {
            "line_no": 10,
            "move_type": "gentle_redirect",
            "page_uid": page_uid,
            "step": step,
            "learner_input": learner_input,
            "route": "answer_turn_policy",
            "turn_label": "answer_question",
            "planned_route": "gentle_redirect",
            "runtime_route": "",
            "runtime_turn_label": "",
            "payload": {
                "schema_version": "peptutor-teaching-move-v1",
                "detected_signal": "off_topic",
                "move": "gentle_redirect",
                "teaching_action": "redirect",
                "rationale": "Preserve the current target.",
                "evidence_fields_used": ["learner_input"],
                "expected_next_learner_action": "Return to the active prompt.",
                "payload_fields": {
                    "learner_input": learner_input,
                    "interpreted_intent": "off_topic",
                    "current_target": "Keep the current classroom target.",
                    "target_phrase": target_phrase,
                    "active_prompt": active_prompt,
                    "return_anchor": return_anchor,
                    "next_action": "return_to_active_task",
                    "correction_kind": "incorrect",
                    "route": "answer_turn_policy",
                    "turn_label": "answer_question",
                    "preserve_page_uid": page_uid,
                    "preserve_block_uid": block_uid,
                },
            },
        }

    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {
                    "page_count": 5,
                    "turn_count": 8,
                    "fallback_count": 0,
                    "http_error_count": 0,
                    "state_drift_count": 0,
                    "issue_count": 0,
                    "acceptance_passed": True,
                },
                "pages": [
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P22",
                        "label": "P22 Let's talk",
                        "block_count": 2,
                        "risk": "fixture",
                    },
                    {
                        "book": "G6S1",
                        "page_uid": "TB-G6S1U1-P2",
                        "label": "P2 Let's learn",
                        "block_count": 1,
                        "risk": "fixture",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P25",
                        "label": "P25 words",
                        "block_count": 3,
                        "risk": "module choice and role play",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P26",
                        "label": "P26 phonics",
                        "block_count": 4,
                        "risk": "phonics boundary",
                    },
                    {
                        "book": "G5S2",
                        "page_uid": "TB-G5S2U1-P6",
                        "label": "P6 phonics practice",
                        "block_count": 3,
                        "risk": "phonics branch and task page",
                    },
                ],
                "turns": [
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P22",
                        "page_label": "P22 Let's talk",
                        "page_risk": "fixture",
                        "block_count": 2,
                        "step": "turn_1",
                        "learner_input": "pizza",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P22-D1",
                        "teacher_response": "我们先回到这一句。",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P22",
                        "page_label": "P22 Let's talk",
                        "page_risk": "fixture",
                        "block_count": 2,
                        "step": "turn_2",
                        "learner_input": "news",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P22-D1",
                        "teacher_response": "我们先说这个：Can you try.",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P22",
                        "page_label": "P22 Let's talk",
                        "page_risk": "fixture",
                        "block_count": 2,
                        "step": "turn_3",
                        "learner_input": "book",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P22-D2",
                        "teacher_response": "我们先看这块。",
                    },
                    {
                        "book": "G6S1",
                        "page_uid": "TB-G6S1U1-P2",
                        "page_label": "P2 Let's learn",
                        "page_risk": "fixture",
                        "block_count": 1,
                        "step": "turn_1",
                        "learner_input": "what",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G6S1U1-P2-D1",
                        "teacher_response": "继续这一页。",
                    },
                    {
                        "book": "G6S1",
                        "page_uid": "TB-G6S1U1-P2",
                        "page_label": "P2 Let's learn",
                        "page_risk": "fixture",
                        "block_count": 1,
                        "step": "turn_2",
                        "learner_input": "hello",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G6S1U1-P2-D1",
                        "teacher_response": "我们先说这个：Zip.",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P25",
                        "page_label": "P25 words",
                        "page_risk": "module choice and role play",
                        "block_count": 3,
                        "step": "turn_1",
                        "learner_input": "water",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P25-D1",
                        "teacher_response": "跟我读：salad.",
                    },
                    {
                        "book": "G5S1",
                        "page_uid": "TB-G5S1U3-P26",
                        "page_label": "P26 phonics",
                        "page_risk": "phonics boundary",
                        "block_count": 4,
                        "step": "turn_1",
                        "learner_input": "water",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P26-D1",
                        "teacher_response": "老师刚才问的是 cow 怎么读，你试试看：cow。",
                    },
                    {
                        "book": "G5S2",
                        "page_uid": "TB-G5S2U1-P6",
                        "page_label": "P6 phonics practice",
                        "page_risk": "phonics branch and task page",
                        "block_count": 3,
                        "step": "turn_1",
                        "learner_input": "please",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S2U1-P6-D1",
                        "teacher_response": "Read after me: clean。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    teaching_path = tmp_path / "teaching_move_audit.json"
    teaching_path.write_text(
        json.dumps(
            {
                "kind": "lesson_teaching_move_audit",
                "summary": {
                    "smoke_report_path": str(smoke_path),
                    "move_count": 10,
                    "move_type_counts": {
                        "gentle_redirect": 8,
                        "vocab_answer_return": 1,
                        "single_block_guard": 1,
                    },
                    "missing_payload_field_count": 0,
                    "unknown_move_type_count": 0,
                    "route_turn_label_mismatch_count": 0,
                    "unmatched_move_count": 0,
                    "audit_passed": True,
                },
                "moves": [
                    gentle_move(
                        page_uid="TB-G5S1U3-P22",
                        step="turn_1",
                        learner_input="pizza",
                        block_uid="TB-G5S1U3-P22-D1",
                        target_phrase="Can you try",
                        active_prompt="What is your favourite food?",
                        return_anchor="What is your favourite food?",
                    ),
                    gentle_move(
                        page_uid="TB-G5S1U3-P22",
                        step="turn_2",
                        learner_input="news",
                        block_uid="TB-G5S1U3-P22-D1",
                        target_phrase="I'm.",
                        active_prompt="Let's talk.",
                        return_anchor="Where are you going?",
                    ),
                    gentle_move(
                        page_uid="TB-G5S1U3-P22",
                        step="turn_3",
                        learner_input="book",
                        block_uid="TB-G5S1U3-P22-D2",
                        target_phrase="Let's talk.",
                        active_prompt="Comprehension ques",
                        return_anchor="A table showing tr",
                    ),
                    gentle_move(
                        page_uid="TB-G6S1U1-P2",
                        step="turn_1",
                        learner_input="what",
                        block_uid="TB-G6S1U1-P2-D1",
                        target_phrase="suggestion.",
                        active_prompt="Zoom.",
                        return_anchor="Where are you going?",
                    ),
                    gentle_move(
                        page_uid="TB-G6S1U1-P2",
                        step="turn_2",
                        learner_input="hello",
                        block_uid="TB-G6S1U1-P2-D1",
                        target_phrase="Zip",
                        active_prompt="John.",
                        return_anchor="Robin.",
                    ),
                    gentle_move(
                        page_uid="TB-G5S1U3-P25",
                        step="turn_1",
                        learner_input="water",
                        block_uid="TB-G5S1U3-P25-D1",
                        target_phrase="salad",
                        active_prompt="I'd like ...",
                        return_anchor="I'd like ...",
                    ),
                    gentle_move(
                        page_uid="TB-G5S1U3-P26",
                        step="turn_1",
                        learner_input="water",
                        block_uid="TB-G5S1U3-P26-D1",
                        target_phrase="cow?",
                        active_prompt="cow: ow -> /aʊ/",
                        return_anchor="cow: ow -> /aʊ/",
                    ),
                    gentle_move(
                        page_uid="TB-G5S2U1-P6",
                        step="turn_1",
                        learner_input="please",
                        block_uid="TB-G5S2U1-P6-D1",
                        target_phrase="clean",
                        active_prompt="Learn the consonant blend 'cl' as in 'clean'.",
                        return_anchor="Learn the consonant blend 'cl' as in 'clean'.",
                    ),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_classroom_quality(
        smoke_report_path=smoke_path,
        teaching_move_audit_path=teaching_path,
    )

    assert report["kind"] == "lesson_classroom_quality_audit"
    assert report["summary"]["page_count"] == 5
    assert report["summary"]["turn_count"] == 8
    assert report["summary"]["total_move_count"] == 10
    assert report["summary"]["gentle_redirect_count"] == 8
    assert report["summary"]["vocab_answer_return_count"] == 1
    assert report["summary"]["single_block_guard_count"] == 1
    assert report["summary"]["audit_passed"] is True
    assert report["summary"]["smoke_acceptance_passed"] is True
    assert report["summary"]["bad_anchor_candidate_count"] >= 5
    assert report["summary"]["legitimate_short_vocab_target_count"] == 2
    assert report["summary"]["legitimate_phonics_target_count"] == 3

    pages = {page["page_uid"]: page for page in report["gentle_redirect_by_page"]}
    assert pages["TB-G5S1U3-P22"]["gentle_redirect_count"] == 3
    assert pages["TB-G5S1U3-P22"]["answer_turn_count"] == 3
    assert pages["TB-G5S1U3-P22"]["redirect_rate"] == 1.0
    assert pages["TB-G5S1U3-P22"]["book"] == "G5S1"

    blocks = {
        (block["page_uid"], block["block_uid"]): block
        for block in report["gentle_redirect_by_block"]
    }
    assert blocks[("TB-G5S1U3-P22", "TB-G5S1U3-P22-D1")]["gentle_redirect_count"] == 2
    assert blocks[("TB-G5S1U3-P22", "TB-G5S1U3-P22-D1")]["answer_turn_count"] == 2
    assert blocks[("TB-G5S1U3-P22", "TB-G5S1U3-P22-D1")]["redirect_rate"] == 1.0
    assert blocks[("TB-G5S1U3-P22", "TB-G5S1U3-P22-D1")][
        "sample_teacher_response_excerpt"
    ]

    top_page = report["top_redirect_pages"][0]
    assert top_page["page_uid"] == "TB-G5S1U3-P22"
    assert top_page["why_flagged"].startswith("redirect_hotspot")

    candidate_phrases = {
        item["phrase"] for item in report["target_phrase_revision_candidates"]
    }
    assert {
        "Can you try",
        "I'm.",
        "suggestion.",
        "Comprehension ques",
        "A table showing tr",
        "Let's talk.",
        "Robin.",
        "Zoom.",
        "Zip",
        "John.",
    } <= candidate_phrases
    assert "salad" not in candidate_phrases
    assert "clean" not in candidate_phrases
    assert "cow?" not in candidate_phrases
    assert any(
        item["phrase"] == "Can you try"
        and item["classification"] == "bad_anchor_candidate"
        and item["severity"] == "major_candidate"
        for item in report["target_phrase_revision_candidates"]
    )
    assert all(
        item["classification"] in {"bad_anchor_candidate", "review_target_phrase"}
        for item in report["target_phrase_revision_candidates"]
    )
    legitimate_vocab_phrases = {
        item["phrase"] for item in report["legitimate_short_vocab_targets"]
    }
    legitimate_phonics_phrases = {
        item["phrase"] for item in report["legitimate_phonics_targets"]
    }
    assert {"salad", "salad."} <= legitimate_vocab_phrases
    assert {"cow?", "clean"} <= legitimate_phonics_phrases
    assert {"salad", "salad."}.isdisjoint(legitimate_phonics_phrases)
    assert {"Zip", "John.", "Robin.", "Zoom."}.isdisjoint(
        legitimate_vocab_phrases | legitimate_phonics_phrases
    )
    assert any(
        item["phrase"] == "Zip"
        and item["classification"] == "bad_anchor_candidate"
        for item in report["target_phrase_revision_candidates"]
    )
    bad_candidate_count = len(report["target_phrase_revision_candidates"])

    repaired_smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    repaired_smoke["turns"][1]["teacher_response"] = (
        "我们先说这个：Where is the museum shop?"
    )
    repaired_smoke_path = tmp_path / "lesson_smoke_matrix_repaired.json"
    repaired_smoke_path.write_text(
        json.dumps(repaired_smoke, ensure_ascii=False),
        encoding="utf-8",
    )
    repaired_teaching = json.loads(teaching_path.read_text(encoding="utf-8"))
    repaired_teaching["summary"]["smoke_report_path"] = str(repaired_smoke_path)
    replacement_phrases = [
        "Where is the museum shop?",
        "I'm 1.6 metres tall.",
        "What does the story tell us?",
        "What suggestions will you give to your friends? Make a poster.",
        "Where are you going?",
        "salad",
        "cow?",
        "clean",
    ]
    for move, phrase in zip(
        repaired_teaching["moves"],
        replacement_phrases,
        strict=True,
    ):
        fields = move["payload"]["payload_fields"]
        fields["target_phrase"] = phrase
        fields["active_prompt"] = phrase
        fields["return_anchor"] = phrase
    repaired_teaching_path = tmp_path / "teaching_move_audit_repaired.json"
    repaired_teaching_path.write_text(
        json.dumps(repaired_teaching, ensure_ascii=False),
        encoding="utf-8",
    )
    repaired_report = audit.audit_classroom_quality(
        smoke_report_path=repaired_smoke_path,
        teaching_move_audit_path=repaired_teaching_path,
    )
    assert (
        len(repaired_report["target_phrase_revision_candidates"])
        < bad_candidate_count
    )
    assert repaired_report["summary"]["audit_passed"] is True

    serialized = json.dumps(report, ensure_ascii=False)
    assert "robotic_smell" not in serialized
    assert "机器人老师" not in serialized

    json_path, md_path = audit.write_report(report, tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Classroom Quality Audit" in md_text
    assert "Bad / Review Target Phrase Candidates" in md_text
    assert "Legitimate Short Targets" in md_text
    assert "robotic_smell" not in md_text
    assert "机器人老师" not in md_text


def test_classroom_quality_audit_uses_action_payload_for_vocab_context(
    tmp_path: Path,
) -> None:
    audit = _load_classroom_quality_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {"page_count": 1, "turn_count": 1, "acceptance_passed": True},
                "pages": [
                    {
                        "book": "G6S2",
                        "page_uid": "TB-G6S2U1-P4",
                        "label": "P4 listening",
                        "block_count": 4,
                        "risk": "fixture",
                    }
                ],
                "turns": [
                    {
                        "book": "G6S2",
                        "page_uid": "TB-G6S2U1-P4",
                        "page_label": "P4 listening",
                        "page_risk": "fixture",
                        "block_count": 4,
                        "step": "turn_4",
                        "learner_input": "heavier",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G6S2U1-P4-D1",
                        "teacher_response": "把这句读出来：dinosaur.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    teaching_path = tmp_path / "teaching_move_audit.json"
    teaching_path.write_text(
        json.dumps(
            {
                "kind": "lesson_teaching_move_audit",
                "summary": {
                    "smoke_report_path": str(smoke_path),
                    "move_count": 1,
                    "move_type_counts": {"gentle_redirect": 1},
                    "missing_payload_field_count": 0,
                    "teaching_action_field_missing_count": 0,
                    "unknown_move_type_count": 0,
                    "route_turn_label_mismatch_count": 0,
                    "unmatched_move_count": 0,
                    "audit_passed": True,
                },
                "moves": [
                    {
                        "line_no": 10,
                        "move_type": "gentle_redirect",
                        "page_uid": "TB-G6S2U1-P4",
                        "step": "turn_4",
                        "learner_input": "heavier",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "payload": {
                            "payload_fields": {
                                "learner_input": "heavier",
                                "target_phrase": "The children are in the museum. Listen and circle.",
                                "active_prompt": "The children are in the museum. Listen and circle.",
                                "return_anchor": "The children are in the museum. Listen and circle.",
                                "current_target": "Catch the key information from the listening task.",
                                "question_target": "Do you know the word dinosaur?",
                                "answer_target": "",
                                "answer_frame": "",
                                "target_role": "phrase",
                                "expected_student_action": "read",
                                "action_source": "block_core_pattern",
                                "preserve_block_uid": "TB-G6S2U1-P4-D1",
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_classroom_quality(
        smoke_report_path=smoke_path,
        teaching_move_audit_path=teaching_path,
    )

    assert report["summary"]["target_phrase_revision_candidate_count"] == 0
    assert report["summary"]["legitimate_short_vocab_target_count"] == 1
    assert report["legitimate_short_vocab_targets"][0]["phrase"] == "dinosaur."


def test_redirect_experience_audit_classifies_hotspot_experience_candidates(
    tmp_path: Path,
) -> None:
    audit = _load_redirect_experience_audit_module()

    page_specs = {
        "TB-FIXTURE-NORMAL": {
            "label": "normal smoke artifact",
            "responses": [
                "你说 water（水），我听到了。water 是“水”。这页先看地点：science museum。跟我读：science museum。",
                "你说 I want to play basketball，我听到了。这页先看地点：science museum。跟我读：science museum。",
                "你说 water（水），我听到了。water 是“水”。这页先看地点：science museum。跟我读：science museum。",
            ],
            "inputs": ["water", "I want to play basketball.", "water"],
            "target": "science museum",
            "intent": "off_topic",
        },
        "TB-FIXTURE-MECHANICAL": {
            "label": "mechanical wording",
            "responses": [
                "你刚才说的是 I want to play basketball.\n我们先说这个：science museum.\n你来读：science museum.",
                "你刚才说的是 Yesterday I played football.\n我们先说这个：science museum.\n你来读：science museum.",
                "你刚才说的是 I want to play basketball.\n这一步先听清这个问题：Where is the science museum?",
            ],
            "inputs": [
                "I want to play basketball.",
                "Yesterday I played football.",
                "I want to play basketball.",
            ],
            "target": "science museum",
            "intent": "off_topic",
        },
        "TB-FIXTURE-MISSING": {
            "label": "missing scaffold",
            "responses": [
                "你说 water，我听到了。这页先看 science museum。跟我读：science museum。",
                "你说 tea，我听到了。这页先看 science museum。跟我读：science museum。",
                "你说 museum，我听到了。这页先看 science museum。跟我读：science museum。",
            ],
            "inputs": ["water", "tea", "museum"],
            "target": "science museum",
            "intent": "short_answer_pullback",
        },
        "TB-FIXTURE-OVERLOADED": {
            "label": "overloaded redirect",
            "responses": [
                (
                    "你说了water（水），水和饮料有关，不过老师问的是Zoom想吃什么，不是想喝什么。"
                    "我们再看故事，Zoom说“I'd like a salad.”，salad是沙拉。"
                    "你先找答案，再用I'd like回答老师：What would Zoom like to eat?"
                ),
                (
                    "你说了Zip，Zip是故事角色，不过老师问的是Zoom想吃什么。"
                    "先看故事，再找Zoom说的话，然后用英文回答：What would Zoom like to eat?"
                ),
                (
                    "你说 I want to play basketball，我听到了。现在先回到故事问题，"
                    "再看Zoom的话，然后回答：What would Zoom like to eat?"
                ),
            ],
            "inputs": ["water", "Zip", "I want to play basketball."],
            "target": "What would Zoom like to eat?",
            "intent": "short_answer_pullback",
        },
        "TB-FIXTURE-TARGET": {
            "label": "target issue",
            "responses": [
                "你说 water（水），我听到了。跟我读：cl' as in.",
                "你说 please，我听到了。跟我读：cl' as in.",
                "你说 basketball，我听到了。跟我读：cl' as in.",
            ],
            "inputs": ["water", "please", "I want to play basketball."],
            "target": "Learn the consonant blend 'cl' as in 'clean'.",
            "intent": "short_answer_pullback",
        },
        "TB-FIXTURE-SCOPE": {
            "label": "answer scope issue",
            "responses": [
                "老师刚才问的是你想先学哪一块。What did you do last weekend? 你先回答第一块还是第二块。",
                "老师刚才问的是你想先学哪一块。What did you do last weekend? 你先回答第一块还是第二块。",
                "老师刚才问的是你想先学哪一块。What did you do last weekend? 你先回答第一块还是第二块。",
            ],
            "inputs": ["I stayed at home.", "had a cold", "water"],
            "target": "What did you do last weekend?",
            "intent": "short_answer_pullback",
        },
    }

    turns: list[dict[str, object]] = []
    moves: list[dict[str, object]] = []
    top_pages: list[dict[str, object]] = []
    for page_index, (page_uid, spec) in enumerate(page_specs.items(), start=1):
        top_pages.append(
            {
                "rank": page_index,
                "page_uid": page_uid,
                "page_label": spec["label"],
                "gentle_redirect_count": 3,
                "redirect_rate": 1.0,
                "why_flagged": "redirect_hotspot: fixture",
            }
        )
        for turn_index, (learner_input, response) in enumerate(
            zip(spec["inputs"], spec["responses"], strict=True),
            start=1,
        ):
            step = f"turn_{turn_index}"
            block_uid = f"{page_uid}-D1"
            turns.append(
                {
                    "book": "G5S1",
                    "page_uid": page_uid,
                    "page_label": spec["label"],
                    "page_risk": "fixture",
                    "block_count": 1,
                    "step": step,
                    "learner_input": learner_input,
                    "route": "answer_turn_policy",
                    "turn_label": "answer_question",
                    "state_block_uid": block_uid,
                    "teacher_response": response,
                }
            )
            moves.append(
                {
                    "line_no": len(moves) + 1,
                    "move_type": "gentle_redirect",
                    "page_uid": page_uid,
                    "step": step,
                    "learner_input": learner_input,
                    "route": "answer_turn_policy",
                    "turn_label": "answer_question",
                    "planned_route": "gentle_redirect",
                    "runtime_route": "",
                    "runtime_turn_label": "",
                    "payload": {
                        "schema_version": "peptutor-teaching-move-v1",
                        "detected_signal": spec["intent"],
                        "move": "gentle_redirect",
                        "teaching_action": "redirect",
                        "rationale": "fixture",
                        "evidence_fields_used": ["learner_input"],
                        "expected_next_learner_action": "Return to active task.",
                        "payload_fields": {
                            "learner_input": learner_input,
                            "interpreted_intent": spec["intent"],
                            "current_target": spec["target"],
                            "target_phrase": spec["target"],
                            "active_prompt": spec["target"],
                            "return_anchor": spec["target"],
                            "next_action": "return_to_active_task",
                            "correction_kind": "incorrect",
                            "route": "answer_turn_policy",
                            "turn_label": "answer_question",
                            "preserve_page_uid": page_uid,
                            "preserve_block_uid": block_uid,
                        },
                    },
                }
            )

    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    smoke_path.write_text(
        json.dumps(
            {
                "regression_set_id": "lesson-core-20-v1",
                "summary": {
                    "page_count": len(page_specs),
                    "turn_count": len(turns),
                    "fallback_count": 0,
                    "http_error_count": 0,
                    "state_drift_count": 0,
                    "issue_count": 0,
                    "acceptance_passed": True,
                },
                "pages": [
                    {
                        "book": "G5S1",
                        "page_uid": page_uid,
                        "label": spec["label"],
                        "block_count": 1,
                        "risk": "fixture",
                    }
                    for page_uid, spec in page_specs.items()
                ],
                "turns": turns,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    teaching_path = tmp_path / "teaching_move_audit.json"
    teaching_path.write_text(
        json.dumps(
            {
                "kind": "lesson_teaching_move_audit",
                "summary": {
                    "smoke_report_path": str(smoke_path),
                    "move_count": len(moves),
                    "move_type_counts": {"gentle_redirect": len(moves)},
                    "missing_payload_field_count": 0,
                    "unknown_move_type_count": 0,
                    "route_turn_label_mismatch_count": 0,
                    "unmatched_move_count": 0,
                    "audit_passed": True,
                },
                "moves": moves,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    classroom_path = tmp_path / "classroom_quality_audit.json"
    classroom_path.write_text(
        json.dumps(
            {
                "kind": "lesson_classroom_quality_audit",
                "top_redirect_pages": top_pages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_redirect_experience(
        smoke_report_path=smoke_path,
        teaching_move_audit_path=teaching_path,
        classroom_quality_audit_path=classroom_path,
    )
    pages = {page["page_uid"]: page for page in report["hotspot_pages"]}

    assert report["kind"] == "lesson_redirect_experience_audit"
    assert report["summary"]["audit_passed"] is True
    assert report["summary"]["hotspot_page_count"] == len(page_specs)
    assert pages["TB-FIXTURE-NORMAL"]["experience_classification"] == "normal_test_artifact"
    assert pages["TB-FIXTURE-MECHANICAL"]["experience_classification"] == "wording_too_mechanical"
    assert pages["TB-FIXTURE-MISSING"]["experience_classification"] == "missing_scaffold_translation"
    assert pages["TB-FIXTURE-OVERLOADED"]["experience_classification"] == "overloaded_redirect"
    assert pages["TB-FIXTURE-TARGET"]["experience_classification"] == "target_selection_issue"
    assert pages["TB-FIXTURE-SCOPE"]["experience_classification"] == "answer_scope_issue"
    assert pages["TB-FIXTURE-NORMAL"]["student_input_relevance"] == "mostly_deliberate_smoke_probe"
    assert pages["TB-FIXTURE-MECHANICAL"]["mechanical_phrase_hits"]
    assert pages["TB-FIXTURE-MISSING"]["issue_counts"]["missing_scaffold_translation_count"] == 3
    assert pages["TB-FIXTURE-TARGET"]["issue_counts"]["target_selection_issue_count"] == 3

    json_path, md_path = audit.write_report(report, tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "Redirect Experience Audit" in md_text
    assert "normal_test_artifact" in md_text
    assert "wording_too_mechanical" in md_text
    assert "missing_scaffold_translation" in md_text
    assert "target_selection_issue" in md_text


def test_redirect_experience_audit_does_not_flag_full_phonics_anchor_as_fragment():
    audit = _load_redirect_experience_audit_module()

    assert (
        audit._target_selection_issues(
            response="这一步练 cl 的发音，例词是 clean. 跟我读：clean.",
            target_phrase="Learn the consonant blend 'cl' as in 'clean'.",
        )
        == []
    )
    assert audit._target_selection_issues(
        response="你说 water（水），我听到了。跟我读：cl' as in.",
        target_phrase="Learn the consonant blend 'cl' as in 'clean'.",
    ) == ["bad_target_fragment"]


def test_lesson_structure_audit_generates_page_verdicts_from_fixed_smoke_report(
    tmp_path: Path,
) -> None:
    audit = _load_structure_audit_module()
    smoke_path = _write_fake_structure_smoke_report(tmp_path)

    report = audit.audit_structure(
        manifest_path=audit.DEFAULT_MANIFEST,
        smoke_report_path=smoke_path,
    )

    assert report["kind"] == audit.REPORT_KIND
    assert report["smoke_regression_set_id"] == "lesson-core-20-v1"
    assert report["summary"]["page_count"] == 20
    assert report["summary"]["coverage_complete"] is True
    assert len(report["pages"]) == 20
    assert all(
        page["verdict"] in {"pass", "suspicious", "broken"}
        for page in report["pages"]
    )
    assert all(page["recommended_fix_scope"] for page in report["pages"])

    json_path, md_path = audit.write_report(report, tmp_path)

    assert json_path.exists()
    assert md_path.exists()
    assert "Lesson Structure Audit" in md_path.read_text(encoding="utf-8")


def test_lesson_structure_audit_recognizes_p9_structure_repairs(
    tmp_path: Path,
) -> None:
    audit = _load_structure_audit_module()
    smoke_path = _write_fake_structure_smoke_report(tmp_path)

    report = audit.audit_structure(
        manifest_path=audit.DEFAULT_MANIFEST,
        smoke_report_path=smoke_path,
    )
    pages = {page["page_uid"]: page for page in report["pages"]}

    p14_edge_ids = {finding["id"] for finding in pages["TB-G5S2U2-P14"]["edge_findings"]}
    p24_edge_ids = {finding["id"] for finding in pages["TB-G5S1U3-P24"]["edge_findings"]}
    p24_block_ids = {finding["id"] for finding in pages["TB-G5S1U3-P24"]["block_findings"]}
    p25_block_ids = {finding["id"] for finding in pages["TB-G5S1U3-P25"]["block_findings"]}

    assert "priority_order_differs_from_block_numbering" not in p24_edge_ids
    assert "page_overview_omits_priority_blocks" not in p14_edge_ids
    assert "priority_order_differs_from_block_numbering" not in p14_edge_ids
    assert "block_mixes_food_and_drink_targets" not in p24_block_ids
    assert "open_slot_has_narrow_examples" not in p24_block_ids
    assert "block_mixes_food_and_drink_targets" not in p25_block_ids
    assert "open_slot_has_narrow_examples" not in p25_block_ids


def test_lesson_structure_audit_recognizes_p1_structure_repairs(
    tmp_path: Path,
) -> None:
    audit = _load_structure_audit_module()
    smoke_path = _write_fake_structure_smoke_report(tmp_path)

    report = audit.audit_structure(
        manifest_path=audit.DEFAULT_MANIFEST,
        smoke_report_path=smoke_path,
    )
    pages = {page["page_uid"]: page for page in report["pages"]}

    p16_block_ids = {finding["id"] for finding in pages["TB-G6S2U2-P16"]["block_findings"]}
    p49_block_ids = {
        finding["id"] for finding in pages["TB-G6S2Recycle2-P49"]["block_findings"]
    }
    p31_block_ids = {finding["id"] for finding in pages["TB-G5S1U3-P31"]["block_findings"]}
    p4_block_ids = {finding["id"] for finding in pages["TB-G5S2U1-P4"]["block_findings"]}
    p19_block_ids = {finding["id"] for finding in pages["TB-G6S1U2-P19"]["block_findings"]}
    g6_p4_block_ids = {finding["id"] for finding in pages["TB-G6S2U1-P4"]["block_findings"]}

    assert "open_slot_has_narrow_examples" not in p16_block_ids
    assert "block_has_many_core_patterns" not in p16_block_ids
    assert "block_has_many_core_patterns" not in p31_block_ids
    assert "block_has_many_core_patterns" not in p4_block_ids
    assert "block_has_many_core_patterns" not in p19_block_ids
    assert "block_has_many_core_patterns" not in g6_p4_block_ids
    assert "block_mixes_food_and_drink_targets" not in p49_block_ids
    assert pages["TB-G6S2Recycle2-P49"]["verdict"] == "pass"


def test_lesson_structure_audit_marks_runtime_block_drift_as_broken(
    tmp_path: Path,
) -> None:
    audit = _load_structure_audit_module()
    smoke_path = _write_fake_structure_smoke_report(tmp_path)
    payload = json.loads(smoke_path.read_text(encoding="utf-8"))
    payload["turns"][0]["state_block_uid"] = "TB-OTHER-P1-D1"
    smoke_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = audit.audit_structure(
        manifest_path=audit.DEFAULT_MANIFEST,
        smoke_report_path=smoke_path,
    )
    page = next(
        item for item in report["pages"] if item["page_uid"] == payload["turns"][0]["page_uid"]
    )

    assert page["verdict"] == "broken"
    assert "adjust_priority_blocks" in page["recommended_fix_scope"]
    assert any(
        item["id"] == "runtime_state_block_outside_priority"
        for item in page["runtime_evidence"]
    )


@pytest.mark.parametrize(
    ("url", "expected_suffix"),
    [
        ("http://127.0.0.1:9625", "http://127.0.0.1:9625/lesson/catalog"),
        ("http://localhost:9625", "http://localhost:9625/lesson/catalog"),
        ("http://[::1]:9625", "http://[::1]:9625/lesson/catalog"),
    ],
)
def test_wait_for_lesson_backend_bypasses_proxy_for_loopback(
    tmp_path: Path,
    *,
    url: str,
    expected_suffix: str,
) -> None:
    args_log = tmp_path / "curl-args.log"
    _write_executable(
        tmp_path / "bin" / "curl",
        f"""\
        #!/usr/bin/env bash
        printf '%s\n' "$*" >> "{args_log}"
        exit 0
        """,
    )

    result = _run_wait_script(
        tmp_path,
        url=url,
        timeout_seconds=5,
    )

    assert result.returncode == 0, result.stderr
    assert "Lesson backend ready after" in result.stdout

    curl_args = args_log.read_text(encoding="utf-8").strip()
    assert "--noproxy *" in curl_args
    assert curl_args.endswith(expected_suffix)


def test_wait_for_lesson_backend_keeps_proxy_path_for_non_loopback(tmp_path: Path) -> None:
    args_log = tmp_path / "curl-args.log"
    date_counter = tmp_path / "date-count.txt"

    _write_executable(
        tmp_path / "bin" / "curl",
        f"""\
        #!/usr/bin/env bash
        printf '%s\n' "$*" >> "{args_log}"
        exit 1
        """,
    )
    _write_executable(
        tmp_path / "bin" / "sleep",
        """\
        #!/usr/bin/env bash
        exit 0
        """,
    )
    _write_executable(
        tmp_path / "bin" / "date",
        f"""\
        #!/usr/bin/env bash
        counter_file="{date_counter}"
        count=0
        if [[ -f "$counter_file" ]]; then
          count="$(cat "$counter_file")"
        fi

        if [[ "${{1:-}}" == "+%s" ]]; then
          if [[ "$count" == "0" ]]; then
            printf '100\n'
          else
            printf '101\n'
          fi
          printf '%s' "$((count + 1))" > "$counter_file"
          exit 0
        fi

        exec /bin/date "$@"
        """,
    )

    result = _run_wait_script(
        tmp_path,
        url="http://lesson-backend.example.test:9625",
        timeout_seconds=1,
    )

    assert result.returncode == 1
    assert "Timed out after 1s waiting for lesson backend" in result.stderr

    curl_args = args_log.read_text(encoding="utf-8").strip()
    assert "--noproxy" not in curl_args
    assert curl_args.endswith("http://lesson-backend.example.test:9625/lesson/catalog")


def test_smoke_lesson_browser_runs_route_focused_defaults(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    browser_artifact_dir = tmp_path / "browser-artifacts"
    browser_artifact_dir.mkdir(parents=True)
    (browser_artifact_dir / "lesson_browser_smoke_20000101_000000.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "browser_test_counts": {
                    "passed": 8,
                    "failed": 1,
                    "skipped": 22,
                },
                "failure_attribution": {"reason": "browser_test_failure"},
                "evidence_events": {"s4_interrupt": [{}]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={
            "PEPTUTOR_LESSON_LIVE_PROMPTS": "keep-live",
            "PEPTUTOR_DEBUG_SIGNALS": "keep-debug",
            "PEPTUTOR_LESSON_VECTOR_RETRIEVAL": "keep-vector",
            "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION": "keep-injection",
            "PEPTUTOR_SIMPLEMEM_WRITEBACK": "keep-writeback",
            "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL": "keep-recall",
            "PEPTUTOR_TEST_PNPM_STDOUT": (
                " ↓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke > skipped fixture-only input test\\n"
                " ↓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke (real backend) > real backend opt-in skipped test\\n"
                " ✓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke (real backend) > real backend route test 123ms\\n"
                " [lesson-real-smoke] {\"test\":\"real backend route test\",\"duration_ms\":123,\"teacher_response\":\"ok\"}\\n"
                " [lesson-s4-interrupt-evidence] {\"test\":\"barge_in_allowed\",\"interrupt_policy\":\"barge_in_allowed\",\"tts_playback_stop_reason_normalized\":\"final_transcript_interrupt\"}\\n"
                " [lesson-real-debug-signals] {\"test\":\"debug signals\",\"debug_signals\":{\"response_audit\":{\"route\":\"llm_only\"}}}\\n"
                " [lesson-real-artifacts] {\"test\":\"real backend route test\",\"network_entries\":[{\"name\":\"http://127.0.0.1:9625/lesson/turn\",\"initiator_type\":\"fetch\",\"duration_ms\":12,\"transfer_size\":456}],\"history_debug\":{\"active_session_id\":\"session-1\",\"active_lesson_tab_writable\":true,\"active_history_read_only\":false,\"history_safety_session_count\":1},\"dom_snapshot\":{\"text_chars\":123,\"has_lesson_sidebar\":true},\"screenshot\":{\"format\":\"png\",\"data_url\":\"data:image/png;base64,iVBORw0KGgo=\",\"error\":\"\"}}\\n"
                " Test Files  1 passed (1)\\n"
                " Tests  10 passed | 22 skipped (32)\\n"
            ),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "[PASS] Lesson browser smoke completed." in result.stdout
    assert "[INFO] Full-stack mode: off" in result.stdout
    assert stubs.wait_args_log.read_text(encoding="utf-8").strip() == "--url http://127.0.0.1:9625 --timeout 120"
    assert stubs.pnpm_args_log.read_text(encoding="utf-8").strip() == "-F @proj-airi/stage-web test:run:browser:real"
    assert stubs.server_argv_log.read_text(encoding="utf-8").strip() == "--host 127.0.0.1 --port 9625"
    pnpm_env = _read_assignments(stubs.pnpm_env_log)
    assert "127.0.0.1" in pnpm_env["NO_PROXY"]
    assert "localhost" in pnpm_env["NO_PROXY"]
    assert "::1" in pnpm_env["no_proxy"]
    assert pnpm_env["PEPTUTOR_LESSON_REAL_BACKEND_URL"] == "http://127.0.0.1:9625"
    assert pnpm_env["VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL"] == "http://127.0.0.1:9625"
    assert pnpm_env["VITE_PEPTUTOR_LESSON_API_URL"] == "http://127.0.0.1:9625"
    assert pnpm_env["VITE_PEPTUTOR_LESSON_EXPECT_DEBUG_SIGNALS"] == "1"

    server_env = _read_assignments(stubs.server_env_log)
    assert server_env == {
        "PEPTUTOR_LESSON_LIVE_PROMPTS": "1",
        "PEPTUTOR_DEBUG_SIGNALS": "1",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL": "0",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION": "0",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK": "0",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL": "0",
    }

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")
    assert len(list(stubs.log_dir.glob("smoke_lesson_browser_*.log"))) == 1
    assert len(list(stubs.log_dir.glob("lesson_browser_vitest_*.log"))) == 1
    reports = sorted((tmp_path / "browser-artifacts").glob("lesson_browser_smoke_*.json"))
    assert len(reports) == 2
    report_path = reports[-1]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["acceptance_passed"] is True
    assert report["browser_test_counts"] == {
        "passed": 10,
        "failed": 0,
        "skipped": 22,
    }
    assert report["browser_test_file_counts"] == {
        "passed": 1,
        "failed": 0,
        "skipped": 0,
    }
    assert report["failure_attribution"] == {
        "reason": "passed_with_skips",
        "timed_out": False,
        "browser_exit_code": 0,
        "failed_test_count": 0,
        "skipped_test_count": 22,
    }
    assert report["browser_suite_summary"] == {
        "real_backend_passed": 1,
        "real_backend_failed": 0,
        "real_backend_skipped": 1,
        "mock_suite_passed": 0,
        "mock_suite_failed": 0,
        "mock_suite_skipped": 1,
        "skipped_due_real_backend_mode": 1,
    }
    assert report["skipped_tests"] == [
        "skipped fixture-only input test",
        "real backend opt-in skipped test",
    ]
    assert report["skipped_test_entries"] == [
        {
            "name": "skipped fixture-only input test",
            "suite_name": "/lesson browser smoke",
            "suite_kind": "mock_suite",
            "raw": "↓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke > skipped fixture-only input test",
            "skip_reason": "mock_skipped_due_real_backend_mode",
        },
        {
            "name": "real backend opt-in skipped test",
            "suite_name": "/lesson browser smoke (real backend)",
            "suite_kind": "real_backend_suite",
            "raw": "↓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke (real backend) > real backend opt-in skipped test",
            "skip_reason": "real_backend_conditional_skip",
        },
    ]
    assert report["passed_test_entries"] == [
        {
            "name": "real backend route test",
            "suite_name": "/lesson browser smoke (real backend)",
            "suite_kind": "real_backend_suite",
            "raw": "✓ |stage-web-browser (chromium)| src/pages/lesson/index.browser.test.ts > /lesson browser smoke (real backend) > real backend route test 123ms",
        }
    ]
    assert report["passed_tests"] == ["real backend route test"]
    assert report["failed_tests"] == []
    assert report["evidence_events"]["lesson_real_smoke"] == [
        {
            "test": "real backend route test",
            "duration_ms": 123,
            "teacher_response": "ok",
        }
    ]
    assert report["evidence_events"]["s4_interrupt"] == [
        {
            "test": "barge_in_allowed",
            "interrupt_policy": "barge_in_allowed",
            "tts_playback_stop_reason_normalized": "final_transcript_interrupt",
        }
    ]
    assert report["evidence_events"]["debug_signals"][0]["test"] == "debug signals"
    assert report["evidence_events"]["lesson_real_artifacts"][0]["test"] == "real backend route test"
    assert report["artifact_manifest"]["json_report"] == str(report_path)
    assert report["partial_report"] is False
    assert report["artifact_inventory"]["backend_log"]["collected"] is True
    assert report["artifact_inventory"]["browser_console_log"]["collected"] is True
    assert report["evidence_events"]["lesson_real_artifacts"][0]["screenshot"] == {
        "format": "png",
        "data_url_bytes": len("data:image/png;base64,iVBORw0KGgo=".encode("utf-8")),
        "error": "",
        "captured": True,
    }
    assert report["artifact_inventory"]["screenshots"]["status"] == "collected"
    assert report["artifact_inventory"]["screenshots"]["count"] == 1
    assert report["artifact_inventory"]["network_logs"]["status"] == "collected"
    assert report["artifact_inventory"]["network_logs"]["count"] == 1
    assert report["artifact_inventory"]["history_json"]["status"] == "collected"
    assert report["artifact_inventory"]["history_json"]["count"] == 1
    assert report["artifact_inventory"]["dom_snapshots"]["status"] == "collected"
    assert report["artifact_inventory"]["dom_snapshots"]["count"] == 1
    collected_artifact_paths = [
        *report["artifact_inventory"]["network_logs"]["paths"],
        *report["artifact_inventory"]["history_json"]["paths"],
        *report["artifact_inventory"]["dom_snapshots"]["paths"],
        *report["artifact_inventory"]["screenshots"]["paths"],
    ]
    assert collected_artifact_paths
    for artifact_path in collected_artifact_paths:
        assert Path(artifact_path).exists()
    assert report["trend_comparison"]["status"] == "compared"
    assert report["trend_comparison"]["passed_delta"] == 2
    assert report["trend_comparison"]["failed_delta"] == -1
    assert report["trend_comparison"]["skipped_delta"] == 0
    assert report["trend_comparison"]["s4_interrupt_event_delta"] == 0
    assert report["trend_comparison"]["failure_reason_changed"] is True
    assert report["log_excerpt"]["browser_tail"]
    assert Path(report["backend_log_path"]).name.startswith("smoke_lesson_browser_")
    assert Path(report["browser_log_path"]).name.startswith("lesson_browser_vitest_")
    markdown = Path(report["artifact_manifest"]["markdown_report"]).read_text(encoding="utf-8")
    assert "## Suite Breakdown" in markdown
    assert "- real_backend_passed: `1`" in markdown
    assert "- mock_suite_skipped: `1`" in markdown
    assert "- skipped_due_real_backend_mode: `1`" in markdown
    assert (
        "- skipped fixture-only input test (`mock_suite`, `mock_skipped_due_real_backend_mode`)"
        in markdown
    )


def test_smoke_lesson_browser_passes_selected_backend_port_to_real_browser_runner(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    backend_port = _free_loopback_port()

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={"PEPTUTOR_LESSON_SMOKE_BACKEND_PORT": str(backend_port)},
    )

    assert result.returncode == 0, result.stderr
    assert stubs.wait_args_log.read_text(encoding="utf-8").strip() == (
        f"--url http://127.0.0.1:{backend_port} --timeout 120"
    )
    assert stubs.server_argv_log.read_text(encoding="utf-8").strip() == f"--host 127.0.0.1 --port {backend_port}"
    pnpm_env = _read_assignments(stubs.pnpm_env_log)
    assert pnpm_env["PEPTUTOR_LESSON_REAL_BACKEND_URL"] == f"http://127.0.0.1:{backend_port}"
    assert pnpm_env["VITE_PEPTUTOR_LESSON_REAL_BACKEND_URL"] == f"http://127.0.0.1:{backend_port}"
    assert pnpm_env["VITE_PEPTUTOR_LESSON_API_URL"] == f"http://127.0.0.1:{backend_port}"

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)


def test_smoke_lesson_regression20_runs_fixed_matrix_and_cleans_up(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    matrix_args_log = tmp_path / "matrix-args.log"
    matrix_script = _write_executable(
        tmp_path / "smoke_lesson_matrix_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "${PEPTUTOR_TEST_MATRIX_ARGS_LOG}"
        exit "${PEPTUTOR_TEST_MATRIX_EXIT_CODE:-0}"
        """,
    )

    result = _run_regression20_script(
        tmp_path,
        stubs=stubs,
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
    )

    assert result.returncode == 0, result.stderr
    assert "[PASS] Fixed 20-page lesson regression completed." in result.stdout
    assert "[INFO] Full-stack mode: off" in result.stdout
    assert stubs.wait_args_log.read_text(encoding="utf-8").strip() == "--url http://127.0.0.1:9625 --timeout 120"
    assert stubs.server_argv_log.read_text(encoding="utf-8").strip() == "--host 127.0.0.1 --port 9625"
    assert matrix_args_log.read_text(encoding="utf-8").strip() == (
        f"--base-url http://127.0.0.1:9625 --out-dir {tmp_path / 'matrix-artifacts'} --timeout 120"
    )

    server_env = _read_assignments(stubs.server_env_log)
    assert server_env == {
        "PEPTUTOR_LESSON_LIVE_PROMPTS": "1",
        "PEPTUTOR_DEBUG_SIGNALS": "1",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL": "0",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION": "0",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK": "0",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL": "0",
    }

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")
    assert len(list(stubs.log_dir.glob("smoke_lesson_regression20_*.log"))) == 1


def test_smoke_lesson_regression20_tails_log_when_matrix_fails(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    matrix_args_log = tmp_path / "matrix-args.log"
    matrix_script = _write_executable(
        tmp_path / "smoke_lesson_matrix_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "${PEPTUTOR_TEST_MATRIX_ARGS_LOG}"
        exit "${PEPTUTOR_TEST_MATRIX_EXIT_CODE:-0}"
        """,
    )

    result = _run_regression20_script(
        tmp_path,
        stubs=stubs,
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={"PEPTUTOR_TEST_MATRIX_EXIT_CODE": "8"},
    )

    assert result.returncode == 1
    assert "[INFO] Running fixed lesson regression set: lesson-core-20-v1" in result.stdout
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr
    assert "stub-server-ready" in result.stderr

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")


def test_test_budget_guard_allows_first_full_smoke_and_records_metadata(tmp_path: Path) -> None:
    goal_id = "pytest-budget-full-first"
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    matrix_args_log = tmp_path / "matrix-args.log"
    matrix_script = _write_executable(
        tmp_path / "smoke_lesson_matrix_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\n' "$*" > "${PEPTUTOR_TEST_MATRIX_ARGS_LOG}"
        out_dir=""
        args=("$@")
        for ((i = 0; i < ${#args[@]}; i++)); do
          if [[ "${args[$i]}" == "--out-dir" && $((i + 1)) -lt ${#args[@]} ]]; then
            out_dir="${args[$((i + 1))]}"
          fi
        done
        mkdir -p "${out_dir}"
        printf '{"summary":{"acceptance_passed":true}}\n' > "${out_dir}/lesson_smoke_matrix_20000101_000000.json"
        """,
    )

    result = _run_regression20_script(
        tmp_path,
        stubs=stubs,
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={"PEPTUTOR_TEST_GOAL_ID": goal_id},
    )

    assert result.returncode == 0, result.stderr
    assert "Test budget accepted" in result.stdout
    metadata = _read_budget_metadata(tmp_path, goal_id)
    assert metadata["goal_id"] == goal_id
    assert metadata["smoke_type"] == "full_20_page"
    assert metadata["run_count"] == 1
    assert metadata["override_reason"] == ""
    assert metadata["runs_by_type"] == {"full_20_page": 1}
    assert metadata["report_path"].endswith("lesson_smoke_matrix_20000101_000000.json")
    assert metadata["runs"][0]["status"] == "completed"


def test_test_budget_guard_rejects_second_full_smoke_without_override(tmp_path: Path) -> None:
    goal_id = "pytest-budget-full-repeat"
    matrix_args_log = tmp_path / "matrix-args.log"
    matrix_script = _write_executable(
        tmp_path / "smoke_lesson_matrix_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\n' "$*" > "${PEPTUTOR_TEST_MATRIX_ARGS_LOG}"
        exit 0
        """,
    )

    first = _run_regression20_script(
        tmp_path,
        stubs=_prepare_smoke_browser_stubs(tmp_path / "first"),
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": goal_id,
            "PEPTUTOR_TEST_BUDGET_DIR": str(tmp_path / "test-budget"),
        },
    )
    assert first.returncode == 0, first.stderr

    second_stubs = _prepare_smoke_browser_stubs(tmp_path / "second")
    second = _run_regression20_script(
        tmp_path / "second",
        stubs=second_stubs,
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": goal_id,
            "PEPTUTOR_TEST_BUDGET_DIR": str(tmp_path / "test-budget"),
        },
    )

    assert second.returncode == 3
    assert "Test budget exceeded" in second.stderr
    assert not second_stubs.server_pid_file.exists()
    metadata = _read_budget_metadata(tmp_path, goal_id)
    assert metadata["run_count"] == 1
    assert len(metadata["runs"]) == 1


def test_test_budget_guard_allows_repeat_full_smoke_with_override(tmp_path: Path) -> None:
    goal_id = "pytest-budget-full-override"
    matrix_args_log = tmp_path / "matrix-args.log"
    matrix_script = _write_executable(
        tmp_path / "smoke_lesson_matrix_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\n' "$*" > "${PEPTUTOR_TEST_MATRIX_ARGS_LOG}"
        exit 0
        """,
    )

    first = _run_regression20_script(
        tmp_path,
        stubs=_prepare_smoke_browser_stubs(tmp_path / "first"),
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": goal_id,
            "PEPTUTOR_TEST_BUDGET_DIR": str(tmp_path / "test-budget"),
        },
    )
    assert first.returncode == 0, first.stderr

    second = _run_regression20_script(
        tmp_path / "second",
        stubs=_prepare_smoke_browser_stubs(tmp_path / "second"),
        matrix_script=matrix_script,
        matrix_args_log=matrix_args_log,
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": goal_id,
            "PEPTUTOR_TEST_BUDGET_DIR": str(tmp_path / "test-budget"),
            "PEPTUTOR_TEST_BUDGET_OVERRIDE_REASON": "rerun after isolated L2 fix",
        },
    )

    assert second.returncode == 0, second.stderr
    metadata = _read_budget_metadata(tmp_path, goal_id)
    assert metadata["run_count"] == 2
    assert metadata["runs_by_type"] == {"full_20_page": 2}
    assert metadata["runs"][1]["override_reason"] == "rerun after isolated L2 fix"


def test_test_budget_guard_rejects_browser_smoke_for_backend_goal(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": "pytest-budget-browser-denied",
            "PEPTUTOR_TEST_GOAL_TYPE": "backend",
        },
    )

    assert result.returncode == 2
    assert "browser smoke is not allowed" in result.stderr
    assert not stubs.server_pid_file.exists()


def test_test_budget_guard_rejects_deep_smoke_without_deep_s4_tts_or_live2d_goal(
    tmp_path: Path,
) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    deep_args_log = tmp_path / "deep-args.log"
    deep_script = _write_executable(
        tmp_path / "lesson_deep_smoke_stub.sh",
        """\
        #!/usr/bin/env bash
        exit 0
        """,
    )

    result = _run_deep_browser_script(
        tmp_path,
        stubs=stubs,
        deep_script=deep_script,
        deep_args_log=deep_args_log,
        frontend_port=_free_loopback_port(),
        extra_env={
            "PEPTUTOR_TEST_GOAL_ID": "pytest-budget-deep-denied",
            "PEPTUTOR_TEST_GOAL_TYPE": "frontend",
        },
    )

    assert result.returncode == 2
    assert "deep smoke is not allowed" in result.stderr
    assert not stubs.server_pid_file.exists()
    assert not deep_args_log.exists()


def test_smoke_lesson_deep_browser_runs_observer_with_frontend_and_backend(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    deep_args_log = tmp_path / "deep-args.log"
    frontend_args_log = tmp_path / "frontend-args.log"
    frontend_port = _free_loopback_port()
    deep_script = _write_executable(
        tmp_path / "lesson_deep_smoke_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "${PEPTUTOR_TEST_DEEP_ARGS_LOG}"
        /bin/sleep "${PEPTUTOR_TEST_DEEP_SLEEP_SECONDS:-0}"
        exit 0
        """,
    )
    _write_executable(
        stubs.server_bin.parent / "pnpm",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{frontend_args_log}"
        host="127.0.0.1"
        port="0"
        args=("$@")
        for ((i = 0; i < ${{#args[@]}}; i++)); do
          if [[ "${{args[$i]}}" == "--host" && $((i + 1)) -lt ${{#args[@]}} ]]; then
            host="${{args[$((i + 1))]}}"
          fi
          if [[ "${{args[$i]}}" == "--port" && $((i + 1)) -lt ${{#args[@]}} ]]; then
            port="${{args[$((i + 1))]}}"
          fi
        done
        exec python3 - "$host" "$port" <<'PY'
        import http.server
        import socketserver
        import sys

        host = sys.argv[1]
        port = int(sys.argv[2])

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = b"lesson-ready"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                return

        with socketserver.TCPServer((host, port), Handler) as httpd:
            httpd.serve_forever()
        PY
        """,
    )

    result = _run_deep_browser_script(
        tmp_path,
        stubs=stubs,
        deep_script=deep_script,
        deep_args_log=deep_args_log,
        frontend_port=frontend_port,
    )

    assert result.returncode == 0, result.stderr
    assert "[PASS] Deep lesson browser observation completed." in result.stdout
    assert stubs.wait_args_log.read_text(encoding="utf-8").strip() == "--url http://127.0.0.1:9625 --timeout 120"
    assert stubs.server_argv_log.read_text(encoding="utf-8").strip() == "--host 127.0.0.1 --port 9625"
    assert frontend_args_log.read_text(encoding="utf-8").strip() == (
        f"-F @proj-airi/stage-web exec vite --host 127.0.0.1 --port {frontend_port} --strictPort"
    )
    assert deep_args_log.read_text(encoding="utf-8").strip() == (
        f"--frontend-url http://127.0.0.1:{frontend_port} "
        f"--history-root {tmp_path / 'history'} "
        f"--artifact-dir {tmp_path / 'deep-artifacts'} "
        "--page-timeout-seconds 180"
    )

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")
    assert len(list(stubs.log_dir.glob("lesson_deep_observer_*.log"))) == 1


def test_smoke_lesson_deep_browser_times_out_hung_observer_and_cleans_up(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    deep_args_log = tmp_path / "deep-args.log"
    frontend_args_log = tmp_path / "frontend-args.log"
    frontend_port = _free_loopback_port()
    deep_script = _write_executable(
        tmp_path / "lesson_deep_smoke_stub.sh",
        """\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "${PEPTUTOR_TEST_DEEP_ARGS_LOG}"
        /bin/sleep "${PEPTUTOR_TEST_DEEP_SLEEP_SECONDS:-0}"
        exit 0
        """,
    )
    _write_executable(
        stubs.server_bin.parent / "pnpm",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{frontend_args_log}"
        host="127.0.0.1"
        port="0"
        args=("$@")
        for ((i = 0; i < ${{#args[@]}}; i++)); do
          if [[ "${{args[$i]}}" == "--host" && $((i + 1)) -lt ${{#args[@]}} ]]; then
            host="${{args[$((i + 1))]}}"
          fi
          if [[ "${{args[$i]}}" == "--port" && $((i + 1)) -lt ${{#args[@]}} ]]; then
            port="${{args[$((i + 1))]}}"
          fi
        done
        exec python3 - "$host" "$port" <<'PY'
        import http.server
        import socketserver
        import sys

        host = sys.argv[1]
        port = int(sys.argv[2])

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = b"lesson-ready"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                return

        with socketserver.TCPServer((host, port), Handler) as httpd:
            httpd.serve_forever()
        PY
        """,
    )

    result = _run_deep_browser_script(
        tmp_path,
        stubs=stubs,
        deep_script=deep_script,
        deep_args_log=deep_args_log,
        frontend_port=frontend_port,
        extra_env={
            "PEPTUTOR_LESSON_DEEP_OBSERVER_TIMEOUT_SECONDS": "1",
            "PEPTUTOR_TEST_DEEP_SLEEP_SECONDS": "3",
        },
    )

    assert result.returncode == 1
    assert "[ERROR] Deep browser observer timed out after 1s" in result.stderr
    assert f"[INFO] Observer log tail ({stubs.log_dir}" in result.stderr
    assert f"[INFO] Frontend log tail ({stubs.log_dir}" in result.stderr
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")


def test_smoke_lesson_browser_preserves_full_stack_env_and_keep_server(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={
            "PEPTUTOR_LESSON_SMOKE_FULL_STACK": "1",
            "PEPTUTOR_LESSON_SMOKE_KEEP_SERVER": "1",
            "PEPTUTOR_LESSON_LIVE_PROMPTS": "keep-live",
            "PEPTUTOR_DEBUG_SIGNALS": "keep-debug",
            "PEPTUTOR_LESSON_VECTOR_RETRIEVAL": "keep-vector",
            "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION": "keep-injection",
            "PEPTUTOR_SIMPLEMEM_WRITEBACK": "keep-writeback",
            "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL": "keep-recall",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "[INFO] Full-stack mode: on" in result.stdout
    assert "Lesson browser backend left running" in result.stdout

    server_env = _read_assignments(stubs.server_env_log)
    assert server_env == {
        "PEPTUTOR_LESSON_LIVE_PROMPTS": "1",
        "PEPTUTOR_DEBUG_SIGNALS": "1",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL": "keep-vector",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION": "keep-injection",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK": "keep-writeback",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL": "keep-recall",
    }

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    try:
        assert _is_process_alive(pid)
    finally:
        if _is_process_alive(pid):
            os.kill(pid, signal.SIGTERM)
            assert _wait_for_process_exit(pid)


def test_smoke_lesson_browser_fails_fast_when_server_bin_missing(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    missing_server_bin = tmp_path / "missing-lightrag-server"

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={"PEPTUTOR_LESSON_SMOKE_SERVER_BIN": str(missing_server_bin)},
    )

    assert result.returncode == 1
    assert f"Missing LightRAG server binary: {missing_server_bin}" in result.stderr
    assert "Install backend/LightRAG/.venv first." in result.stderr
    assert not stubs.server_pid_file.exists()
    assert not stubs.wait_args_log.exists()
    assert not stubs.pnpm_args_log.exists()
    assert not stubs.log_dir.exists()


def test_smoke_lesson_browser_fails_fast_when_wait_script_missing(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)
    missing_wait_script = tmp_path / "missing-wait-for-lesson-backend.sh"

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={"PEPTUTOR_LESSON_SMOKE_WAIT_SCRIPT": str(missing_wait_script)},
    )

    assert result.returncode == 1
    assert f"Missing lesson-backend wait script: {missing_wait_script}" in result.stderr
    assert not stubs.server_pid_file.exists()
    assert not stubs.wait_args_log.exists()
    assert not stubs.pnpm_args_log.exists()
    assert not stubs.log_dir.exists()


def test_smoke_lesson_browser_prints_log_tail_and_cleans_up_when_wait_fails(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={
            "PEPTUTOR_TEST_WAIT_EXIT_CODE": "7",
            "PEPTUTOR_TEST_WAIT_SLEEP_SECONDS": "0.1",
        },
    )

    assert result.returncode == 1
    assert "[INFO] Running checked-in /lesson real-browser suite" not in result.stdout
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr
    assert "stub-server-ready" in result.stderr
    assert not stubs.pnpm_args_log.exists()

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")


def test_smoke_lesson_browser_prints_log_tail_and_cleans_up_when_browser_suite_fails(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={"PEPTUTOR_TEST_PNPM_EXIT_CODE": "9"},
    )

    assert result.returncode == 1
    assert "[INFO] Running checked-in /lesson real-browser suite" in result.stdout
    assert stubs.pnpm_args_log.read_text(encoding="utf-8").strip() == "-F @proj-airi/stage-web test:run:browser:real"
    assert f"[INFO] Browser suite log tail ({stubs.log_dir}" in result.stderr
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr
    assert "stub-server-ready" in result.stderr

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")
    reports = list((tmp_path / "browser-artifacts").glob("lesson_browser_smoke_*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["acceptance_passed"] is False
    assert report["browser_exit_code"] == 9


def test_smoke_lesson_browser_times_out_hung_browser_suite_and_cleans_up(tmp_path: Path) -> None:
    stubs = _prepare_smoke_browser_stubs(tmp_path)

    result = _run_smoke_browser_script(
        tmp_path,
        stubs=stubs,
        extra_env={
            "PEPTUTOR_LESSON_SMOKE_BROWSER_TIMEOUT_SECONDS": "1",
            "PEPTUTOR_TEST_PNPM_SLEEP_SECONDS": "3",
        },
    )

    assert result.returncode == 1
    assert "[ERROR] Lesson browser suite timed out after 1s" in result.stderr
    assert f"[INFO] Browser suite log tail ({stubs.log_dir}" in result.stderr
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr
    reports = list((tmp_path / "browser-artifacts").glob("lesson_browser_smoke_*.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["status"] == "timeout"
    assert report["timed_out"] is True
    assert report["browser_exit_code"] == 124

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")


def test_start_lesson_dev_runs_vite_on_the_requested_strict_port(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    server_argv_log = tmp_path / "server-argv.log"
    pnpm_args_log = tmp_path / "pnpm-args.log"
    log_dir = tmp_path / "logs"

    server_bin = _write_executable(
        bin_dir / "lightrag-server",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{server_argv_log}"
        exec python3 - "$@" <<'PY'
        import http.server
        import json
        import socketserver
        import sys

        host = "127.0.0.1"
        port = 0
        args = sys.argv[1:]
        for index, value in enumerate(args):
            if value == "--host" and index + 1 < len(args):
                host = args[index + 1]
            if value == "--port" and index + 1 < len(args):
                port = int(args[index + 1])

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/lesson/catalog":
                    payload = json.dumps({{"pages": []}}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_args):
                return

        with socketserver.TCPServer((host, port), Handler) as httpd:
            httpd.serve_forever()
        PY
        """,
    )
    _write_executable(
        bin_dir / "pnpm",
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" > "{pnpm_args_log}"
        exit 0
        """,
    )

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PEPTUTOR_LESSON_SERVER_BIN"] = str(server_bin)
    env["PEPTUTOR_LESSON_LOG_DIR"] = str(log_dir)
    env["PEPTUTOR_LESSON_BACKEND_HOST"] = "127.0.0.1"
    env["PEPTUTOR_LESSON_BACKEND_PUBLIC_HOST"] = "127.0.0.1"
    backend_port = _free_loopback_port()
    frontend_port = _free_loopback_port()
    env["PEPTUTOR_LESSON_BACKEND_PORT"] = str(backend_port)
    env["PEPTUTOR_LESSON_FRONTEND_HOST"] = "127.0.0.1"
    env["PEPTUTOR_LESSON_FRONTEND_PORT"] = str(frontend_port)

    result = subprocess.run(
        ["bash", str(START_DEV_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert server_argv_log.read_text(encoding="utf-8").strip() == f"--host 127.0.0.1 --port {backend_port}"
    assert pnpm_args_log.read_text(encoding="utf-8").strip() == (
        f"-F @proj-airi/stage-web exec vite --host 127.0.0.1 --port {frontend_port} --strictPort"
    )
    assert "dev -- --host" not in pnpm_args_log.read_text(encoding="utf-8")
    assert f"http://127.0.0.1:{frontend_port}/lesson" in result.stdout


def test_llm_token_usage_audit_summarizes_pages_routes_and_rag(tmp_path: Path) -> None:
    audit = _load_llm_token_usage_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    calls = [
        {
            "call_id": "c1",
            "audit_tag": "planner.classify_open_turn",
            "mode": "complete",
            "status": "success",
            "prompt_bytes": 400,
            "prompt_token_estimate": 100,
            "completion_bytes": 40,
            "completion_token_estimate": 10,
            "total_token_estimate": 110,
            "token_count_source": "byte_estimate",
            "route": "llm_only",
            "turn_label": "page_entry",
            "page_uid": "TB-FIXTURE-P1",
            "block_uid": "TB-FIXTURE-P1-D1",
            "llm_provider": "test",
            "llm_model": "test-model",
            "rag_context_bytes": 0,
            "history_bytes": 2,
            "system_prompt_bytes": 80,
            "lesson_context_bytes": 318,
            "persona_prompt_bytes": 0,
            "textbook_block_bytes": 120,
            "page_overview_bytes": 24,
            "runtime_state_bytes": 32,
            "teaching_move_bytes": 0,
            "policy_instruction_bytes": 110,
            "quality_revision_prompt_bytes": 0,
            "learner_input_bytes": 10,
            "other_bytes": 22,
            "unknown_context_bytes": 22,
        },
        {
            "call_id": "c2",
            "audit_tag": "responder.render_teacher_turn.ask_knowledge",
            "mode": "complete",
            "status": "success",
            "prompt_bytes": 800,
            "prompt_token_estimate": 200,
            "completion_bytes": 80,
            "completion_token_estimate": 20,
            "total_token_estimate": 220,
            "token_count_source": "byte_estimate",
            "route": "rag_plus_llm",
            "turn_label": "ask_knowledge",
            "page_uid": "TB-FIXTURE-P2",
            "block_uid": "TB-FIXTURE-P2-D1",
            "llm_provider": "test",
            "llm_model": "test-model",
            "rag_context_bytes": 120,
            "history_bytes": 2,
            "system_prompt_bytes": 100,
            "lesson_context_bytes": 578,
            "persona_prompt_bytes": 12,
            "textbook_block_bytes": 180,
            "page_overview_bytes": 40,
            "runtime_state_bytes": 54,
            "teaching_move_bytes": 16,
            "policy_instruction_bytes": 160,
            "quality_revision_prompt_bytes": 0,
            "learner_input_bytes": 14,
            "other_bytes": 114,
            "unknown_context_bytes": 114,
        },
    ]
    smoke_path.write_text(
        json.dumps(
            {
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-FIXTURE-P1",
                        "page_label": "Fixture 1",
                        "step": "page_entry",
                        "route": "llm_only",
                        "turn_label": "page_entry",
                        "state_block_uid": "TB-FIXTURE-P1-D1",
                        "llm_token_usage": {
                            "llm_call_count": 1,
                            "prompt_token_estimate": 100,
                            "completion_token_estimate": 10,
                            "calls": [calls[0]],
                        },
                    },
                    {
                        "page_uid": "TB-FIXTURE-P2",
                        "page_label": "Fixture 2",
                        "step": "turn_1",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "state_block_uid": "TB-FIXTURE-P2-D1",
                        "llm_token_usage": {
                            "llm_call_count": 1,
                            "prompt_token_estimate": 200,
                            "completion_token_estimate": 20,
                            "calls": [calls[1]],
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_llm_token_usage(
        smoke_report_path=smoke_path,
        out_dir=tmp_path,
        timestamp="20260503_000000",
    )

    assert report["kind"] == "lesson_llm_token_usage_audit"
    assert report["summary"]["total_llm_calls"] == 2
    assert report["summary"]["total_prompt_token_estimate"] == 300
    assert report["summary"]["avg_prompt_tokens"] == 150
    assert report["summary"]["p95_prompt_tokens"] == 200
    assert report["summary"]["max_prompt_tokens"] == 200
    assert report["summary"]["token_count_sources"] == ["byte_estimate"]
    assert report["top_pages_by_prompt_tokens"][0]["page_uid"] == "TB-FIXTURE-P2"
    assert report["top_routes_by_prompt_tokens"][0]["route"] == "rag_plus_llm"
    rag_bucket = {
        item["bucket"]: item for item in report["rag_vs_non_rag_avg_tokens"]
    }
    assert rag_bucket["rag"]["avg_prompt_tokens"] == 200
    assert rag_bucket["non_rag"]["avg_prompt_tokens"] == 100
    assert report["largest_context_breakdown"]["call_id"] == "c2"
    assert Path(report["json_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_llm_context_breakdown_audit_attributes_prompt_components(
    tmp_path: Path,
) -> None:
    audit = _load_llm_context_breakdown_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    answer_call = {
        "call_id": "answer-p24",
        "audit_tag": "teacher_turn_policy.answer_question",
        "mode": "complete",
        "status": "success",
        "prompt_bytes": 1200,
        "prompt_token_estimate": 300,
        "completion_bytes": 80,
        "completion_token_estimate": 20,
        "total_token_estimate": 320,
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-G5S1U3-P24",
        "block_uid": "TB-G5S1U3-P24-D2",
        "lesson_context_bytes": 1198,
        "system_prompt_bytes": 0,
        "persona_prompt_bytes": 120,
        "persona_capsule_bytes": 120,
        "textbook_block_bytes": 520,
        "page_overview_bytes": 90,
        "runtime_state_bytes": 160,
        "teaching_move_bytes": 20,
        "policy_instruction_bytes": 320,
        "quality_revision_prompt_bytes": 0,
        "rag_context_bytes": 0,
        "history_bytes": 2,
        "learner_input_bytes": 8,
        "prompt_frame_overhead_bytes": 30,
        "json_serialization_overhead_bytes": 20,
        "output_schema_bytes": 15,
        "planner_prompt_overhead_bytes": 0,
        "responder_prompt_overhead_bytes": 5,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 10,
        "other_bytes": 80,
        "unknown_context_bytes": 10,
    }
    revision_call = {
        "call_id": "revision-p24",
        "audit_tag": "teacher_turn_policy.reply_quality_revision",
        "mode": "complete",
        "status": "success",
        "prompt_bytes": 700,
        "prompt_token_estimate": 175,
        "completion_bytes": 60,
        "completion_token_estimate": 15,
        "total_token_estimate": 190,
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-G5S1U3-P24",
        "block_uid": "TB-G5S1U3-P24-D2",
        "lesson_context_bytes": 698,
        "system_prompt_bytes": 0,
        "persona_prompt_bytes": 0,
        "persona_capsule_bytes": 0,
        "textbook_block_bytes": 140,
        "page_overview_bytes": 30,
        "runtime_state_bytes": 80,
        "teaching_move_bytes": 0,
        "policy_instruction_bytes": 90,
        "quality_revision_prompt_bytes": 220,
        "rag_context_bytes": 0,
        "history_bytes": 2,
        "learner_input_bytes": 8,
        "prompt_frame_overhead_bytes": 14,
        "json_serialization_overhead_bytes": 10,
        "output_schema_bytes": 4,
        "planner_prompt_overhead_bytes": 0,
        "responder_prompt_overhead_bytes": 0,
        "revision_notes_bytes": 72,
        "unclassified_context_bytes": 0,
        "other_bytes": 100,
        "unknown_context_bytes": 0,
    }
    rag_call = {
        "call_id": "rag-p6",
        "audit_tag": "responder.render_teacher_turn.ask_knowledge",
        "mode": "complete",
        "status": "success",
        "prompt_bytes": 400,
        "prompt_token_estimate": 100,
        "completion_bytes": 40,
        "completion_token_estimate": 10,
        "total_token_estimate": 110,
        "route": "rag_plus_llm",
        "turn_label": "ask_knowledge",
        "page_uid": "TB-G5S2U1-P6",
        "block_uid": "TB-G5S2U1-P6-D1",
        "lesson_context_bytes": 300,
        "system_prompt_bytes": 80,
        "persona_prompt_bytes": 10,
        "persona_capsule_bytes": 0,
        "textbook_block_bytes": 70,
        "page_overview_bytes": 20,
        "runtime_state_bytes": 30,
        "teaching_move_bytes": 10,
        "policy_instruction_bytes": 40,
        "quality_revision_prompt_bytes": 0,
        "rag_context_bytes": 100,
        "history_bytes": 2,
        "learner_input_bytes": 6,
        "prompt_frame_overhead_bytes": 24,
        "json_serialization_overhead_bytes": 20,
        "output_schema_bytes": 30,
        "planner_prompt_overhead_bytes": 40,
        "responder_prompt_overhead_bytes": 0,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 0,
        "other_bytes": 114,
        "unknown_context_bytes": 0,
    }
    smoke_path.write_text(
        json.dumps(
            {
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G5S1U3-P24",
                        "page_label": "P24",
                        "step": "turn_1",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P24-D2",
                        "llm_token_usage": {
                            "llm_call_count": 2,
                            "prompt_token_estimate": 475,
                            "completion_token_estimate": 35,
                            "calls": [answer_call, revision_call],
                        },
                    },
                    {
                        "page_uid": "TB-G5S2U1-P6",
                        "page_label": "P6",
                        "step": "turn_2",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "state_block_uid": "TB-G5S2U1-P6-D1",
                        "llm_token_usage": {
                            "llm_call_count": 1,
                            "prompt_token_estimate": 100,
                            "completion_token_estimate": 10,
                            "calls": [rag_call],
                        },
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_llm_context_breakdown(
        smoke_report_path=smoke_path,
        out_dir=tmp_path,
        timestamp="20260503_000001",
    )

    assert report["kind"] == "lesson_llm_context_breakdown_audit"
    assert report["summary"]["total_llm_calls"] == 3
    assert report["summary"]["component_totals"]["other_bytes"] == 294
    assert report["summary"]["component_totals"]["unknown_context_bytes"] == 10
    assert report["summary"]["component_totals"]["unclassified_context_bytes"] == 10
    assert report["summary"]["component_totals"]["output_schema_bytes"] == 49
    assert report["summary"]["component_totals"]["revision_notes_bytes"] == 72
    assert report["summary"]["component_totals"]["persona_capsule_bytes"] == 120
    assert report["top_calls_by_lesson_context_bytes"][0]["call_id"] == "answer-p24"
    assert report["top_pages_by_lesson_context_bytes"][0]["page_uid"] == "TB-G5S1U3-P24"
    assert report["top_routes_by_lesson_context_bytes"][0]["route"] == "answer_turn_policy"
    assert (
        report["top_audit_tags_by_lesson_context_bytes"][0]["audit_tag"]
        == "teacher_turn_policy.answer_question"
    )
    assert report["answer_turn_policy_breakdown"]["top_component"] == (
        "textbook_block_bytes"
    )
    assert report["reply_quality_revision_breakdown"]["top_component"] == (
        "quality_revision_prompt_bytes"
    )
    buckets = {item["bucket"]: item for item in report["rag_vs_non_rag_breakdown"]}
    assert buckets["rag"]["call_count"] == 1
    assert buckets["non_rag"]["call_count"] == 2


def test_unknown_context_attribution_audit_splits_overhead_fields(
    tmp_path: Path,
) -> None:
    audit = _load_unknown_context_attribution_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    first_call = {
        "call_id": "answer-p24",
        "audit_tag": "teacher_turn_policy.answer_question",
        "prompt_bytes": 1200,
        "prompt_token_estimate": 300,
        "completion_bytes": 80,
        "completion_token_estimate": 20,
        "total_token_estimate": 320,
        "route": "answer_turn_policy",
        "page_uid": "TB-G5S1U3-P24",
        "lesson_context_bytes": 1198,
        "prompt_frame_overhead_bytes": 30,
        "json_serialization_overhead_bytes": 20,
        "output_schema_bytes": 15,
        "planner_prompt_overhead_bytes": 0,
        "responder_prompt_overhead_bytes": 5,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 10,
        "other_bytes": 80,
        "unknown_context_bytes": 10,
    }
    second_call = {
        "call_id": "planner-p6",
        "audit_tag": "planner.plan_turn.ask_knowledge",
        "prompt_bytes": 900,
        "prompt_token_estimate": 225,
        "completion_bytes": 60,
        "completion_token_estimate": 15,
        "total_token_estimate": 240,
        "route": "rag_plus_llm",
        "page_uid": "TB-G5S2U1-P6",
        "lesson_context_bytes": 798,
        "prompt_frame_overhead_bytes": 24,
        "json_serialization_overhead_bytes": 20,
        "output_schema_bytes": 30,
        "planner_prompt_overhead_bytes": 40,
        "responder_prompt_overhead_bytes": 0,
        "revision_notes_bytes": 0,
        "unclassified_context_bytes": 0,
        "other_bytes": 114,
        "unknown_context_bytes": 0,
    }
    smoke_path.write_text(
        json.dumps(
            {
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G5S1U3-P24",
                        "page_label": "P24",
                        "step": "turn_1",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P24-D2",
                        "llm_token_usage": {"calls": [first_call]},
                    },
                    {
                        "page_uid": "TB-G5S2U1-P6",
                        "page_label": "P6",
                        "step": "turn_2",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "state_block_uid": "TB-G5S2U1-P6-D1",
                        "llm_token_usage": {"calls": [second_call]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_unknown_context_attribution(
        smoke_report_path=smoke_path,
        out_dir=tmp_path,
        timestamp="20260504_000001",
    )

    assert report["kind"] == "lesson_unknown_context_attribution_audit"
    assert report["summary"]["previously_unknown_context_bytes"] == 194
    assert report["summary"]["attributed_unknown_context_bytes"] == 184
    assert report["summary"]["unclassified_context_bytes"] == 10
    assert report["summary"]["attribution_totals"]["planner_prompt_overhead_bytes"] == 40
    assert report["top_pages_by_previously_unknown_bytes"][0]["page_uid"] == (
        "TB-G5S2U1-P6"
    )
    assert report["top_routes_by_previously_unknown_bytes"][0]["route"] == (
        "rag_plus_llm"
    )
    assert Path(report["json_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_runtime_state_minimal_view_shadow_audit_reports_candidate_savings(
    tmp_path: Path,
) -> None:
    audit = _load_runtime_state_shadow_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    p24_call = {
        "call_id": "answer-p24",
        "audit_tag": "teacher_turn_policy.answer_question",
        "prompt_token_estimate": 300,
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-G5S1U3-P24",
        "block_uid": "TB-G5S1U3-P24-D2",
        "runtime_state_bytes": 400,
        "runtime_state_legacy_frame_bytes": 2862,
        "runtime_state_minimal_view_bytes": 958,
        "runtime_state_savings_candidate_bytes": 1904,
    }
    p13_call = {
        "call_id": "answer-p13",
        "audit_tag": "teacher_turn_policy.answer_question",
        "prompt_token_estimate": 260,
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-G6S2U2-P13",
        "block_uid": "TB-G6S2U2-P13-D2",
        "runtime_state_bytes": 240,
        "runtime_state_legacy_frame_bytes": 1298,
        "runtime_state_minimal_view_bytes": 599,
        "runtime_state_savings_candidate_bytes": 699,
    }
    rag_call = {
        "call_id": "rag-p6",
        "audit_tag": "responder.render_teacher_turn.ask_knowledge",
        "prompt_token_estimate": 120,
        "route": "rag_plus_llm",
        "turn_label": "ask_knowledge",
        "page_uid": "TB-G5S2U1-P6",
        "block_uid": "TB-G5S2U1-P6-D1",
        "runtime_state_bytes": 30,
        "runtime_state_legacy_frame_bytes": 0,
        "runtime_state_minimal_view_bytes": 0,
        "runtime_state_savings_candidate_bytes": 0,
    }
    smoke_path.write_text(
        json.dumps(
            {
                "summary": {"acceptance_passed": True},
                "turns": [
                    {
                        "page_uid": "TB-G5S1U3-P24",
                        "page_label": "P24",
                        "step": "turn_1",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G5S1U3-P24-D2",
                        "llm_token_usage": {"calls": [p24_call]},
                    },
                    {
                        "page_uid": "TB-G6S2U2-P13",
                        "page_label": "P13",
                        "step": "turn_2",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "state_block_uid": "TB-G6S2U2-P13-D2",
                        "llm_token_usage": {"calls": [p13_call]},
                    },
                    {
                        "page_uid": "TB-G5S2U1-P6",
                        "page_label": "P6",
                        "step": "turn_3",
                        "route": "rag_plus_llm",
                        "turn_label": "ask_knowledge",
                        "state_block_uid": "TB-G5S2U1-P6-D1",
                        "llm_token_usage": {"calls": [rag_call]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_runtime_state_minimal_view_shadow(
        smoke_report_path=smoke_path,
        out_dir=tmp_path,
        timestamp="20260504_000001",
    )

    assert report["kind"] == "lesson_runtime_state_minimal_view_shadow_audit"
    assert report["shadow_only"] is True
    assert report["live_prompt_switched"] is False
    assert report["summary"]["metered_runtime_state_call_count"] == 2
    assert report["summary"]["total_runtime_state_legacy_frame_bytes"] == 4160
    assert report["summary"]["total_runtime_state_minimal_view_bytes"] == 1557
    assert report["summary"]["total_runtime_state_savings_candidate_bytes"] == 2603
    assert report["summary"]["minimal_view_missing_count"] == 0
    assert report["top_pages_by_savings_candidate_bytes"][0]["page_uid"] == (
        "TB-G5S1U3-P24"
    )
    route_rows = {
        row["route"]: row for row in report["top_routes_by_savings_candidate_bytes"]
    }
    assert route_rows["answer_turn_policy"][
        "runtime_state_savings_candidate_bytes"
    ] == 2603
    watchlist = {row["page_uid"]: row for row in report["boundary_watchlist"]}
    assert watchlist["TB-G5S1U3-P24"]["seen_in_sample"] is True
    assert watchlist["TB-G6S2U2-P13"]["seen_in_sample"] is True
    assert watchlist["TB-G6S1U1-P4"]["seen_in_sample"] is False
    assert Path(report["json_path"]).exists()
    assert Path(report["markdown_path"]).exists()


def test_mili_persona_consistency_audit_reports_wiring_and_token_impact(
    tmp_path: Path,
) -> None:
    audit = _load_mili_persona_consistency_audit_module()
    smoke_path = tmp_path / "lesson_smoke_matrix.json"
    token_path = tmp_path / "llm_token_usage_audit.json"
    context_path = tmp_path / "llm_context_breakdown_audit.json"
    redirect_path = tmp_path / "redirect_experience_audit.json"
    answer_call = {
        "call_id": "answer-1",
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "page_uid": "TB-FIXTURE-P1",
        "prompt_token_estimate": 120,
        "persona_capsule_bytes": 499,
    }
    llm_only_call = {
        "call_id": "entry-1",
        "route": "llm_only",
        "turn_label": "page_entry",
        "page_uid": "TB-FIXTURE-P1",
        "prompt_token_estimate": 80,
        "persona_capsule_bytes": 0,
    }
    smoke_path.write_text(
        json.dumps(
            {
                "summary": {
                    "page_count": 1,
                    "turn_count": 3,
                    "issue_count": 0,
                    "state_drift_count": 0,
                    "acceptance_passed": True,
                },
                "turns": [
                    {
                        "page_uid": "TB-FIXTURE-P1",
                        "step": "turn_1",
                        "route": "answer_turn_policy",
                        "turn_label": "answer_question",
                        "llm_called": True,
                        "teacher_response": (
                            "你说 water，我听到了。这页的问题是："
                            "What's your favourite food? 你先说一个食物。"
                        ),
                        "full_soul_injected": False,
                        "answer_turn_policy_persona_capsule_enabled": True,
                        "current_llm_call_persona_capsule_injected": True,
                        "persona_capsule_bytes_configured": 269,
                        "persona_capsule_bytes_metered": 499,
                        "llm_token_usage": {
                            "llm_call_count": 1,
                            "calls": [answer_call],
                        },
                    },
                    {
                        "page_uid": "TB-FIXTURE-P1",
                        "step": "page_entry",
                        "route": "llm_only",
                        "turn_label": "page_entry",
                        "llm_called": True,
                        "teacher_response": "我们开始。",
                        "full_soul_injected": False,
                        "answer_turn_policy_persona_capsule_enabled": True,
                        "current_llm_call_persona_capsule_injected": False,
                        "persona_capsule_bytes_configured": 269,
                        "persona_capsule_bytes_metered": 0,
                        "llm_token_usage": {
                            "llm_call_count": 1,
                            "calls": [llm_only_call],
                        },
                    },
                    {
                        "page_uid": "TB-FIXTURE-P1",
                        "step": "page_entry",
                        "route": "deterministic_only",
                        "turn_label": "page_entry",
                        "llm_called": False,
                        "teacher_response": "我们开始。",
                        "full_soul_injected": False,
                        "answer_turn_policy_persona_capsule_enabled": True,
                        "current_llm_call_persona_capsule_injected": False,
                        "persona_capsule_bytes_configured": 269,
                        "persona_capsule_bytes_metered": 0,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    token_path.write_text(
        json.dumps(
            {
                "summary": {
                    "avg_prompt_tokens": 100,
                    "p95_prompt_tokens": 120,
                    "max_prompt_tokens": 120,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    context_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_lesson_context_bytes": 10000,
                    "component_totals": {"persona_capsule_bytes": 499},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    redirect_path.write_text(
        json.dumps(
            {
                "summary": {
                    "experience_classification_counts": {"normal_test_artifact": 1}
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit.audit_mili_persona_consistency(
        smoke_report_path=smoke_path,
        token_audit_path=token_path,
        context_audit_path=context_path,
        redirect_audit_path=redirect_path,
        out_dir=tmp_path,
        timestamp="20260503_000002",
    )

    assert report["kind"] == "mili_persona_consistency_audit"
    assert report["audit_passed"] is True
    assert report["interpretation"] == "wiring success != visible personality success"
    wiring = report["persona_wiring"]
    assert wiring["full_soul_leak_count"] == 0
    assert wiring["interest_leak_count"] == 0
    assert wiring["sample_line_copy_count"] == 0
    assert wiring["answer_turn_policy_injected_call_count"] == 1
    assert wiring["llm_only_injected_call_count"] == 0
    assert wiring["deterministic_injected_turn_count"] == 0
    assert wiring["miswired_turn_count"] == 0
    assert report["token_impact"]["persona_capsule_bytes_total"] == 499
    assert report["token_impact"]["persona_capsule_share"] == 0.0499
    assert Path(report["json_path"]).exists()
    assert Path(report["markdown_path"]).exists()
    assert "wiring success != visible personality success" in Path(
        report["markdown_path"]
    ).read_text(encoding="utf-8")


def test_mili_persona_audit_does_not_add_smoke_input_or_page_special_cases() -> None:
    source = MILI_PERSONA_CONSISTENCY_AUDIT_SCRIPT.read_text(encoding="utf-8")
    forbidden_fragments = (
        "page_uid ==",
        "page_uid==",
        "I want to play basketball",
        "我不知道",
        "我想学第二块",
        "How tall are you?",
        "teacher_response =",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_post_p7_visible_micro_slice_has_no_runtime_page_or_smoke_input_special_cases() -> None:
    production_sources = [
        REPO_ROOT / "backend/LightRAG/lightrag/pedagogy/redirect_reply_policy.py",
        REPO_ROOT / "backend/LightRAG/lightrag/orchestrator/lesson_runtime.py",
        REPO_ROOT / "backend/LightRAG/lightrag/orchestrator/teaching_move_planner.py",
    ]
    forbidden_fragments = (
        "TB-G",
        "I want to play basketball",
        "我不知道",
        "我想学第二块",
    )
    for source_path in production_sources:
        source = source_path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in source


def test_smoke_matrix_core_inputs_are_locked() -> None:
    matrix = _load_smoke_matrix_module()
    rows = [
        (
            page.book,
            page.page_uid,
            page.label,
            page.block_count,
            page.risk,
            tuple(page.inputs),
        )
        for page in matrix.PAGES
    ]
    digest = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    assert len(rows) == 20
    assert digest == (
        "fe1892d4e722a15da786c3b2f9d1543fa55eb84c7504f42b8ba45d8212fbd177"
    )
