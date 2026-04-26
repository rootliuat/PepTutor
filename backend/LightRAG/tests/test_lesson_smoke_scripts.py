from __future__ import annotations

import os
import signal
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

REPO_ROOT = Path(__file__).resolve().parents[3]
WAIT_SCRIPT = REPO_ROOT / "scripts" / "wait-for-lesson-backend.sh"
SMOKE_BROWSER_SCRIPT = REPO_ROOT / "scripts" / "smoke_lesson_browser.sh"


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


def _prepare_smoke_browser_stubs(tmp_path: Path) -> SmokeBrowserStubs:
    bin_dir = tmp_path / "bin"
    log_dir = tmp_path / "logs"
    server_pid_file = tmp_path / "server.pid"
    server_env_log = tmp_path / "server-env.log"
    server_argv_log = tmp_path / "server-argv.log"
    server_events_log = tmp_path / "server-events.log"
    wait_args_log = tmp_path / "wait-args.log"
    pnpm_args_log = tmp_path / "pnpm-args.log"

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

    for key in (
        "PEPTUTOR_LESSON_LIVE_PROMPTS",
        "PEPTUTOR_DEBUG_SIGNALS",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        "PEPTUTOR_LESSON_SMOKE_FULL_STACK",
        "PEPTUTOR_LESSON_SMOKE_KEEP_SERVER",
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


def _read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_exit(pid: int, *, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.05)
    return not _is_process_alive(pid)


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
        },
    )

    assert result.returncode == 0, result.stderr
    assert "[PASS] Lesson browser smoke completed." in result.stdout
    assert "[INFO] Full-stack mode: off" in result.stdout
    assert stubs.wait_args_log.read_text(encoding="utf-8").strip() == "--url http://127.0.0.1:9625 --timeout 120"
    assert stubs.pnpm_args_log.read_text(encoding="utf-8").strip() == "-F @proj-airi/stage-web test:run:browser:real"
    assert stubs.server_argv_log.read_text(encoding="utf-8").strip() == "--host 127.0.0.1 --port 9625"

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
    assert f"[INFO] Backend log tail ({stubs.log_dir}" in result.stderr
    assert "stub-server-ready" in result.stderr

    pid = int(stubs.server_pid_file.read_text(encoding="utf-8").strip())
    assert _wait_for_process_exit(pid)
    assert "TERM" in stubs.server_events_log.read_text(encoding="utf-8")
