#!/usr/bin/env python3
"""One-command live smoke for POST /lesson/turn via a temporary LightRAG backend."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend" / "LightRAG"
SERVER_BIN = BACKEND_DIR / ".venv" / "bin" / "lightrag-server"
SERVER_LOG_DIR = BACKEND_DIR / "temp"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PAGE_UID = "TB-G5S1U3-P24"
DEFAULT_P25_PAGE_UID = "TB-G5S1U3-P25"
DEFAULT_P26_PAGE_UID = "TB-G5S1U3-P26"
DEFAULT_G6_PAGE_UID = "TB-G6S2U2-P13"
DEFAULT_G6_P49_PAGE_UID = "TB-G6S2Recycle2-P49"
DEFAULT_TIMEOUT_SECONDS = 45.0
DEFAULT_STARTUP_TIMEOUT_SECONDS = 90.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45.0

P49_GOLD_STREAM_CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "G6 P49 reluctant learner stream",
        "learner_input": "我不想说",
        "expected_turn_label": "answer_question",
        "expected_teaching_action": "hint",
        "expected_evaluation": "unclear",
        "expected_block_uid": "TB-G6S2Recycle2-P49-D4",
    },
    {
        "name": "G6 P49 task echo stream",
        "learner_input": "Create a personal party shopping list.",
        "expected_turn_label": "answer_question",
        "expected_teaching_action": "hint",
        "expected_evaluation": "incorrect",
        "expected_block_uid": "TB-G6S2Recycle2-P49-D4",
        "forbidden_phrases": ("开头带起来",),
    },
    {
        "name": "G6 P49 rough item sentence stream",
        "learner_input": "I bring apple.",
        "expected_turn_label": "answer_question",
        "expected_teaching_action": "hint",
        "expected_evaluation": "partially_correct",
        "expected_block_uid": "TB-G6S2Recycle2-P49-D4",
    },
    {
        "name": "G6 P49 off-topic redirect stream",
        "learner_input": "I played games yesterday.",
        "expected_turn_label": "social",
        "expected_teaching_action": "redirect",
        "expected_evaluation": None,
        "expected_block_uid": "TB-G6S2Recycle2-P49-D4",
    },
    {
        "name": "G6 P49 good party-list answer stream",
        "learner_input": "I'm going to bring some fruit and drinks.",
        "expected_turn_label": "answer_question",
        "expected_teaching_action": "confirm",
        "expected_evaluation": "correct",
        "expected_block_uid": "TB-G6S2Recycle2-P49-D2",
    },
)

P49_FORBIDDEN_TEACHER_META_PHRASES = (
    "Theme:",
    "Key patterns:",
    "teaching_goal",
    "retrieval",
    "planner",
    "persona",
    "AIRI",
    "block_uid",
    "page_uid",
    "TB-",
    "开放性的活动",
    "鼓励学生",
    "要求学生",
    "引导学生",
)

ASCII_TOKEN_RE = re.compile(r"^[a-z0-9_]+$", re.IGNORECASE)


class SmokeFailure(RuntimeError):
    """A smoke check failed."""


@dataclass(slots=True)
class StartedBackend:
    process: asyncio.subprocess.Process
    base_url: str
    log_path: Path
    port: int


@dataclass(slots=True)
class LessonTurnResult:
    name: str
    elapsed_ms: int
    payload: dict[str, Any]

    @property
    def teacher_response(self) -> str:
        return str(self.payload.get("teacher_response") or "")

    @property
    def state(self) -> dict[str, Any]:
        state = self.payload.get("state")
        return state if isinstance(state, dict) else {}


@dataclass(slots=True)
class LessonStreamTurnResult(LessonTurnResult):
    events: list[tuple[str, dict[str, Any]]]

    @property
    def action_payload(self) -> dict[str, Any]:
        for event_name, payload in self.events:
            if event_name == "action":
                return payload
        return {}

    @property
    def text_chunks(self) -> list[str]:
        return [
            str(payload.get("text") or "")
            for event_name, payload in self.events
            if event_name == "text_delta"
        ]


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _is_enabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _resolve_host() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_HOST", DEFAULT_HOST)


def _resolve_port() -> int:
    raw = _read_env("PEPTUTOR_LESSON_SMOKE_PORT")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            raise SmokeFailure(f"Invalid PEPTUTOR_LESSON_SMOKE_PORT: {raw}") from None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_resolve_host(), 0))
        return int(sock.getsockname()[1])


def _resolve_timeout_seconds() -> float:
    raw = _read_env(
        "PEPTUTOR_LESSON_SMOKE_TIMEOUT_SECONDS",
        str(DEFAULT_TIMEOUT_SECONDS),
    )
    try:
        return max(5.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _resolve_startup_timeout_seconds() -> float:
    raw = _read_env(
        "PEPTUTOR_LESSON_SMOKE_STARTUP_TIMEOUT_SECONDS",
        str(DEFAULT_STARTUP_TIMEOUT_SECONDS),
    )
    try:
        return max(10.0, float(raw))
    except ValueError:
        return DEFAULT_STARTUP_TIMEOUT_SECONDS


def _resolve_request_timeout_seconds() -> float:
    raw = _read_env(
        "PEPTUTOR_LESSON_SMOKE_REQUEST_TIMEOUT_SECONDS",
        str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
    )
    try:
        return max(5.0, float(raw))
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS


def _resolve_full_stack_mode() -> bool:
    return _is_enabled(os.getenv("PEPTUTOR_LESSON_SMOKE_FULL_STACK"))


def _resolve_keep_server() -> bool:
    return _is_enabled(os.getenv("PEPTUTOR_LESSON_SMOKE_KEEP_SERVER"))


def _resolve_page_uid() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_PAGE_UID", DEFAULT_PAGE_UID)


def _resolve_followup_page_uid() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_P25_PAGE_UID", DEFAULT_P25_PAGE_UID)


def _resolve_final_page_uid() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_P26_PAGE_UID", DEFAULT_P26_PAGE_UID)


def _resolve_g6_page_uid() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_G6_PAGE_UID", DEFAULT_G6_PAGE_UID)


def _resolve_g6_p49_page_uid() -> str:
    return _read_env("PEPTUTOR_LESSON_SMOKE_G6_P49_PAGE_UID", DEFAULT_G6_P49_PAGE_UID)


def _resolve_student_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}"


def _shorten(value: str, limit: int = 200) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        result[key] = value
    return result


def _build_server_env(*, full_stack: bool) -> dict[str, str]:
    env = dict(os.environ)
    for dotenv_path in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
        for key, value in _load_dotenv_file(dotenv_path).items():
            env.setdefault(key, value)

    env["PEPTUTOR_LESSON_LIVE_PROMPTS"] = "1"
    env["PEPTUTOR_DEBUG_SIGNALS"] = "1"

    if not full_stack:
        env["PEPTUTOR_LESSON_VECTOR_RETRIEVAL"] = "0"
        env["PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION"] = "0"
        env["PEPTUTOR_SIMPLEMEM_WRITEBACK"] = "0"
        env["PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL"] = "0"

    return env


def _latest_log_path() -> Path:
    SERVER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return SERVER_LOG_DIR / f"smoke_lesson_turn_{time.strftime('%Y%m%d_%H%M%S')}.log"


async def _wait_for_ready(
    session: aiohttp.ClientSession,
    *,
    backend: StartedBackend,
    timeout_seconds: float,
) -> None:
    deadline = time.perf_counter() + timeout_seconds
    request_url = f"{backend.base_url}/lesson/catalog"

    while time.perf_counter() < deadline:
        if backend.process.returncode is not None:
            raise SmokeFailure(
                "Temporary lesson backend exited before it became ready. "
                f"Check {backend.log_path}."
            )

        try:
            async with session.get(
                request_url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 200:
                    return
                await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass

        await asyncio.sleep(1)

    raise SmokeFailure(
        "Timed out waiting for the temporary lesson backend to answer "
        f"GET /lesson/catalog. Check {backend.log_path}."
    )


async def start_backend(
    session: aiohttp.ClientSession,
    *,
    host: str,
    port: int,
    startup_timeout_seconds: float,
    full_stack: bool,
) -> StartedBackend:
    if not SERVER_BIN.exists():
        raise SmokeFailure(
            f"LightRAG server binary is missing: {SERVER_BIN}. "
            "Install backend/LightRAG/.venv first."
        )

    log_path = _latest_log_path()
    log_handle = log_path.open("wb")

    try:
        process = await asyncio.create_subprocess_exec(
            str(SERVER_BIN),
            "--host",
            host,
            "--port",
            str(port),
            cwd=str(BACKEND_DIR),
            env=_build_server_env(full_stack=full_stack),
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception:
        log_handle.close()
        raise

    backend = StartedBackend(
        process=process,
        base_url=f"http://{host}:{port}",
        log_path=log_path,
        port=port,
    )

    try:
        await _wait_for_ready(
            session,
            backend=backend,
            timeout_seconds=startup_timeout_seconds,
        )
        return backend
    except Exception:
        await stop_backend(backend, keep_server=False)
        raise
    finally:
        log_handle.close()


async def stop_backend(backend: StartedBackend, *, keep_server: bool) -> None:
    if keep_server or backend.process.returncode is not None:
        return

    backend.process.terminate()
    try:
        await asyncio.wait_for(backend.process.wait(), timeout=10)
    except asyncio.TimeoutError:
        backend.process.kill()
        await backend.process.wait()


async def request_turn(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    payload: dict[str, Any],
    name: str,
    timeout_seconds: float,
) -> LessonTurnResult:
    request_url = f"{base_url}/lesson/turn"
    started_at = time.perf_counter()

    try:
        async with session.post(
            request_url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            text = await response.text()
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)

            if response.status != 200:
                raise SmokeFailure(
                    f"{name} returned HTTP {response.status}: {_shorten(text)}"
                )
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise SmokeFailure(
                    f"{name} returned invalid JSON: {_shorten(text)}"
                ) from exc
            if not isinstance(decoded, dict):
                raise SmokeFailure(f"{name} returned a non-object JSON payload.")
            return LessonTurnResult(name=name, elapsed_ms=elapsed_ms, payload=decoded)
    except aiohttp.ClientError as exc:
        raise SmokeFailure(f"{name} request failed: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise SmokeFailure(f"{name} timed out after {timeout_seconds:.0f}s.") from exc


def _parse_sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise SmokeFailure(
                f"Stream event {event_name} returned invalid JSON: {_shorten(block)}"
            ) from exc
        if not isinstance(payload, dict):
            raise SmokeFailure(f"Stream event {event_name} returned a non-object payload.")
        events.append((event_name, payload))
    return events


async def request_turn_stream(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    payload: dict[str, Any],
    name: str,
    timeout_seconds: float,
) -> LessonStreamTurnResult:
    request_url = f"{base_url}/lesson/turn/stream"
    turn_client_id = (
        "smoke-"
        + "".join(char if char.isalnum() else "-" for char in name.casefold()).strip("-")
    )
    stream_payload = {**payload, "turn_client_id": turn_client_id}
    started_at = time.perf_counter()

    try:
        async with session.post(
            request_url,
            json=stream_payload,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            text = await response.text()
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)

            if response.status != 200:
                raise SmokeFailure(
                    f"{name} stream returned HTTP {response.status}: {_shorten(text)}"
                )
            events = _parse_sse_events(text)
            event_names = [event_name for event_name, _payload in events]
            if not events:
                raise SmokeFailure(f"{name} stream returned no SSE events.")
            if event_names[0] != "meta":
                raise SmokeFailure(f"{name} stream did not start with meta.")
            if "error" in event_names:
                error_payload = next(payload for event_name, payload in events if event_name == "error")
                raise SmokeFailure(
                    f"{name} stream returned error event: {_shorten(json.dumps(error_payload, ensure_ascii=False))}"
                )
            if "action" not in event_names:
                raise SmokeFailure(f"{name} stream did not emit an action event.")
            if "text_delta" not in event_names:
                raise SmokeFailure(f"{name} stream did not emit text_delta events.")
            if event_names[-1] != "done":
                raise SmokeFailure(f"{name} stream did not finish with done.")

            meta = events[0][1]
            if meta.get("turn_client_id") != turn_client_id:
                raise SmokeFailure(f"{name} stream meta carried the wrong turn_client_id.")

            done_payload = events[-1][1]
            result_payload = done_payload.get("result")
            if not isinstance(result_payload, dict):
                raise SmokeFailure(f"{name} stream done event did not include a result object.")
            if done_payload.get("turn_client_id") != turn_client_id:
                raise SmokeFailure(f"{name} stream done carried the wrong turn_client_id.")

            chunks = [
                str(payload.get("text") or "")
                for event_name, payload in events
                if event_name == "text_delta"
            ]
            if "".join(chunks) != str(result_payload.get("teacher_response") or ""):
                raise SmokeFailure(
                    f"{name} stream text_delta chunks did not reconstruct teacher_response."
                )

            return LessonStreamTurnResult(
                name=name,
                elapsed_ms=elapsed_ms,
                payload=result_payload,
                events=events,
            )
    except aiohttp.ClientError as exc:
        raise SmokeFailure(f"{name} stream request failed: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise SmokeFailure(f"{name} stream timed out after {timeout_seconds:.0f}s.") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _response_summary(result: LessonTurnResult) -> str:
    state = result.state
    return (
        f"{result.name} in {result.elapsed_ms}ms "
        f"(turn={result.payload.get('turn_label')}, "
        f"action={result.payload.get('teaching_action')}, "
        f"mode={result.payload.get('retrieval_mode')}, "
        f"block={state.get('current_block_uid')}, "
        f"eval={result.payload.get('evaluation') or '-'}, "
        f"reply={_shorten(result.teacher_response, limit=120)})"
    )


def _assert_live_teacher(result: LessonTurnResult) -> None:
    debug_signals = result.payload.get("debug_signals")
    _require(isinstance(debug_signals, dict), f"{result.name} did not return debug_signals.")
    live_prompts = debug_signals.get("live_prompts")
    _require(
        isinstance(live_prompts, dict) and live_prompts.get("enabled") is True,
        f"{result.name} did not keep live_prompts enabled.",
    )


def _assert_page_entry(
    result: LessonTurnResult,
    *,
    expected_word: str | None,
    expected_page_uid: str,
    expected_block_uid: str,
) -> None:
    _assert_live_teacher(result)
    _require(result.payload.get("turn_label") == "page_entry", f"{result.name} did not return page_entry.")
    _require(
        result.payload.get("teaching_action") == "page_intro",
        f"{result.name} did not return page_intro.",
    )
    _require(
        result.payload.get("retrieval_mode") == "none",
        f"{result.name} unexpectedly changed retrieval_mode.",
    )
    _require(result.state.get("awaiting_answer") is True, f"{result.name} did not keep awaiting_answer=true.")
    _require(
        result.state.get("current_page_uid") == expected_page_uid,
        f"{result.name} switched to {result.state.get('current_page_uid')} instead of {expected_page_uid}.",
    )
    _require(
        result.state.get("current_block_uid") == expected_block_uid,
        f"{result.name} opened {result.state.get('current_block_uid')} instead of {expected_block_uid}.",
    )
    _require(_contains_cjk(result.teacher_response), f"{result.name} reply is not localized Chinese.")


def _assert_teacher_mentions_any(
    result: LessonTurnResult,
    *phrases: str,
) -> None:
    reply = result.teacher_response.casefold()
    _require(
        any(phrase.casefold() in reply for phrase in phrases),
        f"{result.name} reply did not mention any of: {', '.join(phrases)}.",
    )


def _assert_teacher_excludes(result: LessonTurnResult, *phrases: str) -> None:
    reply = result.teacher_response.casefold()
    leaked = [
        phrase
        for phrase in phrases
        if _matches_forbidden_teacher_phrase(reply, phrase)
    ]
    _require(
        not leaked,
        f"{result.name} reply leaked forbidden phrases: {', '.join(leaked)}.",
    )


def _matches_forbidden_teacher_phrase(reply_lower: str, phrase: str) -> bool:
    phrase_lower = phrase.casefold()
    if ASCII_TOKEN_RE.fullmatch(phrase_lower):
        return bool(
            re.search(
                rf"(?<![a-z0-9_]){re.escape(phrase_lower)}(?![a-z0-9_])",
                reply_lower,
            )
        )
    return phrase_lower in reply_lower


def _assert_p49_gold_stream_turn(
    result: LessonStreamTurnResult,
    *,
    expected_turn_label: str,
    expected_teaching_action: str,
    expected_evaluation: str | None,
    expected_block_uid: str,
    forbidden_phrases: tuple[str, ...] = (),
) -> None:
    _assert_live_teacher(result)
    _require(
        result.payload.get("turn_label") == expected_turn_label,
        f"{result.name} returned {result.payload.get('turn_label')} instead of {expected_turn_label}.",
    )
    _require(
        result.payload.get("teaching_action") == expected_teaching_action,
        f"{result.name} returned action {result.payload.get('teaching_action')} instead of {expected_teaching_action}.",
    )
    _require(
        result.payload.get("retrieval_mode") == "none",
        f"{result.name} unexpectedly used retrieval_mode={result.payload.get('retrieval_mode')}.",
    )
    _require(
        result.payload.get("evaluation") == expected_evaluation,
        f"{result.name} returned evaluation {result.payload.get('evaluation')} instead of {expected_evaluation}.",
    )
    _require(
        result.state.get("current_block_uid") == expected_block_uid,
        f"{result.name} expected block {expected_block_uid}, got {result.state.get('current_block_uid')}.",
    )
    _require(
        result.state.get("awaiting_answer") is True,
        f"{result.name} did not keep awaiting_answer=true.",
    )
    _require(_contains_cjk(result.teacher_response), f"{result.name} reply is not localized Chinese.")
    _assert_teacher_excludes(
        result,
        *P49_FORBIDDEN_TEACHER_META_PHRASES,
        *forbidden_phrases,
    )

    action = result.action_payload
    _require(
        action.get("teaching_action") == expected_teaching_action,
        f"{result.name} action event did not match teaching_action.",
    )
    _require(
        action.get("evaluation") == expected_evaluation,
        f"{result.name} action event did not match evaluation.",
    )
    _require(
        action.get("content_source") == "lesson_runtime_teacher_response",
        f"{result.name} action event did not keep lesson_runtime_teacher_response.",
    )
    _require(
        action.get("performance_source") == "lesson_persona_context",
        f"{result.name} action event did not use lesson_persona_context.",
    )


def _assert_same_block(left: LessonTurnResult, right: LessonTurnResult) -> None:
    _require(
        left.state.get("current_block_uid") == right.state.get("current_block_uid"),
        f"{right.name} drifted from {left.state.get('current_block_uid')} to {right.state.get('current_block_uid')}.",
    )


async def run_lesson_turn_smoke(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    timeout_seconds: float,
) -> list[LessonTurnResult]:
    student_id = _resolve_student_id("lesson-smoke")
    page_uid = _resolve_page_uid()
    p25_page_uid = _resolve_followup_page_uid()
    p26_page_uid = _resolve_final_page_uid()
    g6_page_uid = _resolve_g6_page_uid()
    g6_p49_page_uid = _resolve_g6_p49_page_uid()

    results: list[LessonTurnResult] = []

    start = await request_turn(
        session,
        base_url=base_url,
        payload={"page_uid": page_uid, "student_id": student_id},
        name="P24 page entry",
        timeout_seconds=timeout_seconds,
    )
    _assert_page_entry(
        start,
        expected_word="hungry",
        expected_page_uid=page_uid,
        expected_block_uid="TB-G5S1U3-P24-D2",
    )
    results.append(start)

    knowledge = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": page_uid,
            "student_id": student_id,
            "state": start.state,
            "learner_input": "What does salad mean?",
        },
        name="P24 knowledge interruption",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(knowledge)
    _require(
        knowledge.payload.get("turn_label") == "ask_knowledge",
        "P24 knowledge interruption did not route to ask_knowledge.",
    )
    _require(
        knowledge.payload.get("retrieval_mode") == "unit",
        "P24 knowledge interruption did not stay at unit retrieval.",
    )
    _assert_same_block(start, knowledge)
    _require(
        knowledge.state.get("awaiting_answer") is True,
        "P24 knowledge interruption did not preserve awaiting_answer=true.",
    )
    _require(
        "salad" in knowledge.teacher_response.casefold(),
        "P24 knowledge interruption did not explain salad.",
    )
    results.append(knowledge)

    first_hint = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": page_uid,
            "student_id": student_id,
            "state": start.state,
            "learner_input": "I am hungry.",
        },
        name="P24 answer correction",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(first_hint)
    _require(
        first_hint.payload.get("turn_label") == "answer_question",
        "P24 answer correction did not stay on answer_question.",
    )
    _require(
        first_hint.payload.get("teaching_action") == "hint",
        "P24 answer correction did not return hint.",
    )
    _assert_same_block(start, first_hint)
    _require(
        first_hint.state.get("awaiting_answer") is True,
        "P24 answer correction did not keep awaiting_answer=true.",
    )
    results.append(first_hint)

    help_turn = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": page_uid,
            "student_id": student_id,
            "state": first_hint.state,
            "learner_input": "help",
        },
        name="P24 help turn",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(help_turn)
    _require(
        help_turn.payload.get("turn_label") == "ask_help",
        "P24 help turn did not route to ask_help.",
    )
    _assert_same_block(first_hint, help_turn)
    _require(
        help_turn.state.get("awaiting_answer") is True,
        "P24 help turn did not preserve awaiting_answer=true.",
    )
    _require(
        "hungry" in help_turn.teacher_response.casefold() or "饿" in help_turn.teacher_response,
        "P24 help turn did not stay on the active hungry target.",
    )
    results.append(help_turn)

    fragment = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": page_uid,
            "student_id": student_id,
            "state": first_hint.state,
            "learner_input": "water",
        },
        name="P24 fragment answer",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(fragment)
    _require(
        fragment.payload.get("turn_label") == "answer_question",
        "P24 fragment answer did not stay on answer_question.",
    )
    _require(
        fragment.payload.get("evaluation") == "partially_correct",
        "P24 fragment answer did not stay partially_correct.",
    )
    _assert_same_block(first_hint, fragment)
    _require(
        fragment.state.get("awaiting_answer") is True,
        "P24 fragment answer did not preserve awaiting_answer=true.",
    )
    _require(
        fragment.teacher_response != first_hint.teacher_response,
        "P24 fragment answer repeated the exact same correction reply twice.",
    )
    results.append(fragment)

    wrong_domain = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": page_uid,
            "student_id": student_id,
            "state": first_hint.state,
            "learner_input": "I'd like chicken and bread.",
        },
        name="P24 wrong-domain answer",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(wrong_domain)
    _require(
        wrong_domain.payload.get("turn_label") == "answer_question",
        "P24 wrong-domain answer did not stay on answer_question.",
    )
    _require(
        wrong_domain.payload.get("evaluation") == "incorrect",
        "P24 wrong-domain answer did not stay incorrect.",
    )
    _assert_same_block(first_hint, wrong_domain)
    _require(
        wrong_domain.state.get("awaiting_answer") is True,
        "P24 wrong-domain answer did not preserve awaiting_answer=true.",
    )
    results.append(wrong_domain)

    p25_entry = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p25_page_uid,
            "student_id": student_id,
            "state": wrong_domain.state,
            "learner_input": "next page",
        },
        name="P24 -> P25 page switch",
        timeout_seconds=timeout_seconds,
    )
    _assert_page_entry(
        p25_entry,
        expected_word="tea",
        expected_page_uid=p25_page_uid,
        expected_block_uid="TB-G5S1U3-P25-D1",
    )
    results.append(p25_entry)

    p25_vocab = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p25_page_uid,
            "student_id": student_id,
            "state": p25_entry.state,
            "learner_input": "tea",
        },
        name="P25 vocabulary answer",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(p25_vocab)
    _require(
        p25_vocab.payload.get("turn_label") == "answer_question",
        "P25 vocabulary answer did not stay on answer_question.",
    )
    _require(
        p25_vocab.payload.get("evaluation") == "correct",
        "P25 vocabulary answer did not validate tea as correct.",
    )
    _require(
        p25_vocab.state.get("current_block_uid") == "TB-G5S1U3-P25-D2",
        "P25 vocabulary answer did not advance into the service-question block.",
    )
    _require(
        p25_vocab.state.get("awaiting_answer") is True,
        "P25 vocabulary answer did not keep awaiting_answer=true.",
    )
    _require(
        "what would you like to eat" in p25_vocab.teacher_response.casefold(),
        "P25 vocabulary answer did not bridge into the service question.",
    )
    results.append(p25_vocab)

    p25_service_echo = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p25_page_uid,
            "student_id": student_id,
            "state": p25_vocab.state,
            "learner_input": "What would you like to eat?",
        },
        name="P25 service-question echo",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(p25_service_echo)
    _require(
        p25_service_echo.payload.get("turn_label") == "answer_question",
        "P25 service-question echo did not stay on answer_question.",
    )
    _require(
        p25_service_echo.payload.get("evaluation") == "correct",
        "P25 service-question echo did not validate as correct.",
    )
    _require(
        p25_service_echo.state.get("current_block_uid") == "TB-G5S1U3-P25-D2",
        "P25 service-question echo unexpectedly left the service-question block.",
    )
    _require(
        _contains_cjk(p25_service_echo.teacher_response),
        "P25 service-question echo reply is not localized Chinese.",
    )
    results.append(p25_service_echo)

    p25_roleplay = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p25_page_uid,
            "student_id": student_id,
            "state": p25_service_echo.state,
            "learner_input": "I'd like a sandwich, please.",
        },
        name="P25 role-play setup",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(p25_roleplay)
    _require(
        p25_roleplay.payload.get("turn_label") == "answer_question",
        "P25 role-play setup did not stay on answer_question.",
    )
    _require(
        p25_roleplay.payload.get("evaluation") == "correct",
        "P25 role-play setup did not validate the sandwich answer.",
    )
    _require(
        p25_roleplay.state.get("current_block_uid") == "TB-G5S1U3-P25-D3",
        "P25 role-play setup did not advance into the role-play block.",
    )
    _require(
        _contains_cjk(p25_roleplay.teacher_response),
        "P25 role-play setup reply is not localized Chinese.",
    )
    results.append(p25_roleplay)

    p26_entry = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p26_page_uid,
            "student_id": student_id,
            "state": p25_roleplay.state,
            "learner_input": "next page",
        },
        name="P25 -> P26 page switch",
        timeout_seconds=timeout_seconds,
    )
    _assert_page_entry(
        p26_entry,
        expected_word="listen",
        expected_page_uid=p26_page_uid,
        expected_block_uid="TB-G5S1U3-P26-D2",
    )
    results.append(p26_entry)

    p26_knowledge = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": p26_page_uid,
            "student_id": student_id,
            "state": p26_entry.state,
            "learner_input": "What does snow mean?",
        },
        name="P26 knowledge interruption",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(p26_knowledge)
    _require(
        p26_knowledge.payload.get("turn_label") == "ask_knowledge",
        "P26 knowledge interruption did not route to ask_knowledge.",
    )
    _require(
        p26_knowledge.payload.get("retrieval_mode") in {"block", "page", "unit"},
        "P26 knowledge interruption did not stay in a lesson retrieval scope.",
    )
    _require(
        p26_knowledge.state.get("current_block_uid") == "TB-G5S1U3-P26-D2",
        "P26 knowledge interruption drifted off the active listening block.",
    )
    _require(
        p26_knowledge.state.get("awaiting_answer") is True,
        "P26 knowledge interruption did not preserve awaiting_answer=true.",
    )
    _require(
        "TB-G5S1U3-P26-D1" in (p26_knowledge.payload.get("retrieved_block_uids") or []),
        "P26 knowledge interruption did not retrieve the nearby phonics block for snow.",
    )
    _require(
        "snow" in p26_knowledge.teacher_response.casefold(),
        "P26 knowledge interruption did not explain snow.",
    )
    results.append(p26_knowledge)

    g6_student_id = f"{student_id}-g6"
    g6_entry = await request_turn(
        session,
        base_url=base_url,
        payload={"page_uid": g6_page_uid, "student_id": g6_student_id},
        name="G6 P13 page entry",
        timeout_seconds=timeout_seconds,
    )
    _assert_page_entry(
        g6_entry,
        expected_word=None,
        expected_page_uid=g6_page_uid,
        expected_block_uid="TB-G6S2U2-P13-D2",
    )
    results.append(g6_entry)

    g6_stayed_home = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": g6_page_uid,
            "student_id": g6_student_id,
            "state": g6_entry.state,
            "learner_input": "What does stayed at home mean?",
        },
        name="G6 P13 stayed-at-home interruption",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(g6_stayed_home)
    _require(
        g6_stayed_home.payload.get("turn_label") == "ask_knowledge",
        "G6 stayed-at-home interruption did not route to ask_knowledge.",
    )
    _require(
        g6_stayed_home.payload.get("retrieval_mode") == "unit",
        "G6 stayed-at-home interruption did not use unit retrieval.",
    )
    _assert_same_block(g6_entry, g6_stayed_home)
    _require(
        g6_stayed_home.state.get("awaiting_answer") is True,
        "G6 stayed-at-home interruption did not preserve awaiting_answer=true.",
    )
    _require(
        (g6_stayed_home.payload.get("retrieved_block_uids") or [None])[0] == "TB-G6S2U2-P15-D1",
        "G6 stayed-at-home interruption did not hit TB-G6S2U2-P15-D1 at top-1.",
    )
    _assert_teacher_mentions_any(
        g6_stayed_home,
        "stayed at home",
        "待在家里",
        "待在家",
        "在家",
    )
    results.append(g6_stayed_home)

    g6_had_cold = await request_turn(
        session,
        base_url=base_url,
        payload={
            "page_uid": g6_page_uid,
            "student_id": g6_student_id,
            "state": g6_entry.state,
            "learner_input": "What does had a cold mean?",
        },
        name="G6 P13 had-a-cold interruption",
        timeout_seconds=timeout_seconds,
    )
    _assert_live_teacher(g6_had_cold)
    _require(
        g6_had_cold.payload.get("turn_label") == "ask_knowledge",
        "G6 had-a-cold interruption did not route to ask_knowledge.",
    )
    _require(
        g6_had_cold.payload.get("retrieval_mode") == "unit",
        "G6 had-a-cold interruption did not use unit retrieval.",
    )
    _assert_same_block(g6_entry, g6_had_cold)
    _require(
        g6_had_cold.state.get("awaiting_answer") is True,
        "G6 had-a-cold interruption did not preserve awaiting_answer=true.",
    )
    _require(
        (g6_had_cold.payload.get("retrieved_block_uids") or [None])[0] == "TB-G6S2U2-P17-D1",
        "G6 had-a-cold interruption did not hit TB-G6S2U2-P17-D1 at top-1.",
    )
    _assert_teacher_mentions_any(
        g6_had_cold,
        "had a cold",
        "感冒",
    )
    results.append(g6_had_cold)

    g6_p49_student_id = f"{student_id}-g6-p49"
    g6_p49_entry = await request_turn(
        session,
        base_url=base_url,
        payload={"page_uid": g6_p49_page_uid, "student_id": g6_p49_student_id},
        name="G6 P49 page entry",
        timeout_seconds=timeout_seconds,
    )
    _assert_page_entry(
        g6_p49_entry,
        expected_word=None,
        expected_page_uid=g6_p49_page_uid,
        expected_block_uid="TB-G6S2Recycle2-P49-D4",
    )
    _assert_teacher_excludes(g6_p49_entry, *P49_FORBIDDEN_TEACHER_META_PHRASES)
    results.append(g6_p49_entry)

    for case in P49_GOLD_STREAM_CASES:
        stream_turn = await request_turn_stream(
            session,
            base_url=base_url,
            payload={
                "page_uid": g6_p49_page_uid,
                "student_id": g6_p49_student_id,
                "state": g6_p49_entry.state,
                "learner_input": case["learner_input"],
            },
            name=case["name"],
            timeout_seconds=timeout_seconds,
        )
        _assert_p49_gold_stream_turn(
            stream_turn,
            expected_turn_label=case["expected_turn_label"],
            expected_teaching_action=case["expected_teaching_action"],
            expected_evaluation=case["expected_evaluation"],
            expected_block_uid=case["expected_block_uid"],
            forbidden_phrases=case.get("forbidden_phrases", ()),
        )
        results.append(stream_turn)

    return results


async def async_main() -> int:
    host = _resolve_host()
    port = _resolve_port()
    full_stack = _resolve_full_stack_mode()
    keep_server = _resolve_keep_server()
    startup_timeout_seconds = _resolve_startup_timeout_seconds()
    request_timeout_seconds = _resolve_request_timeout_seconds()
    session_timeout = aiohttp.ClientTimeout(total=_resolve_timeout_seconds())

    print(f"[INFO] Lesson smoke host: {host}")
    print(f"[INFO] Lesson smoke port: {port}")
    print(f"[INFO] Route-focused mode: {'off' if full_stack else 'on'}")
    if full_stack:
        print("[INFO] Full-stack mode keeps current vector/SimpleMem settings.")
    else:
        print("[INFO] Route-focused mode disables vector retrieval and SimpleMem add-ons for faster startup.")

    async with aiohttp.ClientSession(timeout=session_timeout, trust_env=False) as session:
        backend: StartedBackend | None = None
        try:
            backend = await start_backend(
                session,
                host=host,
                port=port,
                startup_timeout_seconds=startup_timeout_seconds,
                full_stack=full_stack,
            )
            print(
                f"[PASS] Temporary lesson backend ready at {backend.base_url} "
                f"(log={backend.log_path})"
            )

            results = await run_lesson_turn_smoke(
                session,
                base_url=backend.base_url,
                timeout_seconds=request_timeout_seconds,
            )
            for result in results:
                print(f"[PASS] {_response_summary(result)}")

            print(
                "[PASS] Lesson turn smoke completed across "
                f"{_resolve_page_uid()} -> {_resolve_followup_page_uid()} -> {_resolve_final_page_uid()} "
                f"plus {_resolve_g6_page_uid()} and P49 stream gold set {_resolve_g6_p49_page_uid()}."
            )
            return 0
        except SmokeFailure as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            if backend is not None:
                print(f"[FAIL] Backend log: {backend.log_path}", file=sys.stderr)
            print("[FAIL] Lesson turn smoke failed.", file=sys.stderr)
            return 1
        finally:
            if backend is not None:
                await stop_backend(backend, keep_server=keep_server)
                if keep_server:
                    print(
                        f"[INFO] Temporary lesson backend left running at {backend.base_url} "
                        f"(log={backend.log_path})"
                    )


def main() -> int:
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(async_main())
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
