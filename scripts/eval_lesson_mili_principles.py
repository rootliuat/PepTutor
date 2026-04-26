#!/usr/bin/env python3
"""Run a naive-student lesson simulation and judge Mili's teaching principles."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import aiohttp
from openai import OpenAI

import smoke_lesson_turn as smoke


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend" / "LightRAG"
PRINCIPLES_PATH = ROOT_DIR / "app" / "knowledge" / "evals" / "lesson-mili-teaching-filters.json"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "temp"
DEFAULT_JUDGE_PRINCIPLES = (
    "hear_child_before_teaching",
    "one_small_step",
    "role_logic_stays_clear",
)
DEFAULT_START_PAGE_UID = "TB-G5S1U3-P24"
NEXT_PAGE_BY_PAGE_UID = {
    "TB-G5S1U3-P24": "TB-G5S1U3-P25",
    "TB-G5S1U3-P25": "TB-G5S1U3-P26",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-report",
        type=Path,
        help="Write the full simulation and judge report to this JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report JSON instead of a compact text summary.",
    )
    parser.add_argument(
        "--max-latency-ms",
        type=int,
        default=15_000,
        help="Maximum expected response latency per generated teacher turn.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=10,
        help="Number of teacher turns to generate, including the page-entry turn.",
    )
    return parser.parse_args()


def _load_dotenv_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
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
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _load_env() -> None:
    for dotenv_path in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
        for key, value in _load_dotenv_file(dotenv_path).items():
            os.environ.setdefault(key, value)


def _default_output_path() -> Path:
    return DEFAULT_OUTPUT_DIR / f"lesson_mili_principles_naive_{time.strftime('%Y%m%d_%H%M%S')}.json"


def _llm_config() -> tuple[str, str | None, str]:
    _load_env()
    api_key = (
        os.getenv("LLM_BINDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
    )
    base_url = (
        os.getenv("LLM_BINDING_HOST")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
    )
    model = os.getenv("LLM_MODEL") or "deepseek-chat"
    if not api_key:
        raise RuntimeError("Missing LLM API key for student simulation or judge.")
    return api_key, base_url or None, model


def _openai_client() -> tuple[OpenAI, str, bool]:
    api_key, base_url, model = _llm_config()
    return OpenAI(api_key=api_key, base_url=base_url), model, bool(base_url)


def _live_prompts_enabled(payload: dict[str, Any]) -> bool:
    debug_signals = payload.get("debug_signals")
    if not isinstance(debug_signals, dict):
        return False
    live_prompts = debug_signals.get("live_prompts")
    return isinstance(live_prompts, dict) and live_prompts.get("enabled") is True


def _compact_turn(
    *,
    name: str,
    student_input: str,
    student_profile_note: str,
    student_generation: dict[str, Any] | None,
    result: smoke.LessonTurnResult,
    turn_number: int,
) -> dict[str, Any]:
    state = result.state
    return {
        "turn": turn_number,
        "name": name,
        "student_profile_note": student_profile_note,
        "student_input": student_input,
        "student_generated_by_llm": student_generation is not None,
        "student_generation_reason": (
            student_generation.get("reason") if isinstance(student_generation, dict) else None
        ),
        "elapsed_ms": result.elapsed_ms,
        "turn_label": result.payload.get("turn_label"),
        "teaching_action": result.payload.get("teaching_action"),
        "evaluation": result.payload.get("evaluation"),
        "retrieval_mode": result.payload.get("retrieval_mode"),
        "page_uid": state.get("current_page_uid") or result.payload.get("page_uid"),
        "block_uid": state.get("current_block_uid") or result.payload.get("block_uid"),
        "awaiting_answer": state.get("awaiting_answer"),
        "live_prompts_enabled": _live_prompts_enabled(result.payload),
        "teacher_response": result.teacher_response,
        "retrieved_block_uids": result.payload.get("retrieved_block_uids") or [],
    }


def _history_for_student(transcript: list[dict[str, Any]]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in transcript[-8:]:
        student_input = str(turn.get("student_input") or "").strip()
        if student_input and not student_input.startswith("("):
            history.append({"speaker": "student", "text": student_input})
        teacher_response = str(turn.get("teacher_response") or "").strip()
        if teacher_response:
            history.append({"speaker": "teacher", "text": teacher_response})
    return history


def _generate_student_input(
    *,
    client: OpenAI,
    model: str,
    transcript: list[dict[str, Any]],
    current_page_uid: str,
    turn_number: int,
) -> dict[str, str]:
    last_teacher_response = str(transcript[-1].get("teacher_response") or "")
    prompt_payload = {
        "role": "You are the learner, not the teacher.",
        "student_profile": {
            "grade": "G5",
            "level": "low mastery elementary English learner",
            "policy": (
                "你不知道教材答案，只能根据老师刚才怎么教来回应。"
                "不要提前给标准答案；老师没有示范过的完整句不要自己凭空说全。"
            ),
            "behavior": [
                "如果老师给了一个很短的英文模型并明确让你跟读，可以尝试跟读，但可以漏词、带问号或只说半句。",
                "如果老师一下子给太多内容，要说 help、慢一点、中文什么意思，或只抓住一个词。",
                "如果老师问词义，可以猜错、用中文求确认，或问中文意思。",
                "如果老师给出完整英文句后没有中文支撑，可以问“中文什么意思？”",
                "如果你觉得这一页已经有点跟上了，或者老师推进到新内容太快，可以说 next page。",
            ],
        },
        "current_page_uid": current_page_uid,
        "turn_number_to_generate": turn_number,
        "last_teacher_response": last_teacher_response,
        "visible_dialogue_history": _history_for_student(transcript),
        "output_schema": {
            "student_input": "one short natural learner utterance",
            "reason": "short Chinese reason for why this low-mastery learner says it",
        },
    }
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你模拟一个真实低掌握小学生。只输出 JSON。"
                    "你看不到答案库、教学目标、评分原则或后端状态。"
                    "你只能根据老师上一句话自然反应。不要替老师完成测试。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            },
        ],
        temperature=0.5,
        max_tokens=180,
    )
    content = response.choices[0].message.content or ""
    decoded = json.loads(_strip_json_fence(content))
    if not isinstance(decoded, dict):
        raise ValueError("Student simulator did not return a JSON object")
    student_input = str(decoded.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("Student simulator returned empty student_input")
    return {
        "student_input": student_input,
        "reason": str(decoded.get("reason") or "").strip(),
    }


def _requested_next_page(student_input: str) -> bool:
    lowered = student_input.casefold()
    return any(token in lowered for token in ("next page", "下一页", "翻页", "下一个"))


def _request_page_uid_for_student_input(current_page_uid: str, student_input: str) -> str:
    if _requested_next_page(student_input):
        return NEXT_PAGE_BY_PAGE_UID.get(current_page_uid, current_page_uid)
    return current_page_uid


async def _run_naive_simulation(
    *,
    base_url: str,
    session: aiohttp.ClientSession,
    timeout_seconds: float,
    turn_count: int,
) -> list[dict[str, Any]]:
    student_id = smoke._resolve_student_id("mili-dynamic-naive-principles")
    student_client, student_model, _base_url_configured = _openai_client()
    state: dict[str, Any] | None = None
    transcript: list[dict[str, Any]] = []

    start = await smoke.request_turn(
        session,
        base_url=base_url,
        payload={"page_uid": DEFAULT_START_PAGE_UID, "student_id": student_id},
        name="01 P24 page entry",
        timeout_seconds=timeout_seconds,
    )
    state = start.state
    transcript.append(
        _compact_turn(
            name="01 P24 page entry",
            student_input="(进入 P24)",
            student_profile_note="新页面，动态学生还不知道教材答案。",
            student_generation=None,
            result=start,
            turn_number=1,
        )
    )

    for turn_number in range(2, max(2, turn_count + 1)):
        current_page_uid = str(state.get("current_page_uid") or DEFAULT_START_PAGE_UID)
        student_generation = _generate_student_input(
            client=student_client,
            model=student_model,
            transcript=transcript,
            current_page_uid=current_page_uid,
            turn_number=turn_number,
        )
        student_input = student_generation["student_input"]
        request_page_uid = _request_page_uid_for_student_input(
            current_page_uid,
            student_input,
        )
        payload: dict[str, Any] = {
            "page_uid": request_page_uid,
            "student_id": student_id,
            "state": state,
            "learner_input": student_input,
        }

        result = await smoke.request_turn(
            session,
            base_url=base_url,
            payload=payload,
            name=f"{turn_number:02d} dynamic naive student",
            timeout_seconds=timeout_seconds,
        )
        state = result.state
        transcript.append(
            _compact_turn(
                name=f"{turn_number:02d} dynamic naive student",
                student_input=student_input,
                student_profile_note="LLM dynamic low-mastery student, generated only from teacher reply and visible history.",
                student_generation=student_generation,
                result=result,
                turn_number=turn_number,
            )
        )

    return transcript


def _select_principles(principles_payload: dict[str, Any]) -> list[dict[str, Any]]:
    principles = principles_payload.get("teaching_principles")
    if not isinstance(principles, list):
        raise ValueError("lesson-mili-teaching-filters.json is missing teaching_principles")

    selected: list[dict[str, Any]] = []
    by_id = {
        str(principle.get("id")): principle
        for principle in principles
        if isinstance(principle, dict)
    }
    for principle_id in DEFAULT_JUDGE_PRINCIPLES:
        principle = by_id.get(principle_id)
        if not isinstance(principle, dict):
            raise ValueError(f"Missing teaching principle: {principle_id}")
        selected.append(principle)
    return selected


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        return stripped[first : last + 1]
    return stripped


def _judge_with_llm(
    *,
    transcript: list[dict[str, Any]],
    principles_payload: dict[str, Any],
) -> dict[str, Any]:
    client, model, base_url_configured = _openai_client()
    selected_principles = _select_principles(principles_payload)
    prompt_payload = {
        "task": "Judge whether each generated 米粒 teacher reply follows the selected teaching principles. Be strict: keyword mention plus target sentence is not enough.",
        "judge_principles": selected_principles,
        "evaluation_boundary": principles_payload.get("evaluation_boundary", {}),
        "transcript": transcript,
        "output_schema": {
            "overall_pass": "boolean",
            "turns": [
                {
                    "turn": "number",
                    "name": "string",
                    "principles": {
                        "hear_child_before_teaching": {
                            "status": "pass | fail | na",
                            "reason": "short Chinese reason",
                        },
                        "one_small_step": {
                            "status": "pass | fail | na",
                            "reason": "short Chinese reason",
                        },
                        "role_logic_stays_clear": {
                            "status": "pass | fail | na",
                            "reason": "short Chinese reason",
                        },
                    },
                    "failed_principles": ["principle id list"],
                    "summary": "short Chinese judgment",
                }
            ],
        },
    }
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是小学英语课堂质量评审。只输出 JSON。"
                    "不要按关键词放水；要判断老师有没有真实接住学生、"
                    "有没有一次只给一个台阶、角色逻辑有没有混乱。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            },
        ],
        temperature=0,
    )
    content = response.choices[0].message.content or ""
    decoded = json.loads(_strip_json_fence(content))
    if not isinstance(decoded, dict):
        raise ValueError("Judge did not return a JSON object")
    return {
        "model": model,
        "base_url_configured": base_url_configured,
        "result": decoded,
    }


def _read_backend_log_warnings(log_path: Path) -> list[str]:
    if not log_path.exists():
        return []
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    patterns = (
        "using deterministic teacher response",
        "Lesson responder failed",
        "dropped required practice phrase",
        "Lesson planner failed",
    )
    return [pattern for pattern in patterns if pattern in log_text]


def _build_summary(
    *,
    transcript: list[dict[str, Any]],
    judge: dict[str, Any],
    backend_log_path: Path,
    max_latency_ms: int,
) -> dict[str, Any]:
    judge_result = judge["result"]
    judge_turns = judge_result.get("turns")
    failed_turns: list[dict[str, Any]] = []
    if isinstance(judge_turns, list):
        for judged_turn in judge_turns:
            if not isinstance(judged_turn, dict):
                continue
            failed = judged_turn.get("failed_principles")
            if isinstance(failed, list) and failed:
                failed_turns.append(judged_turn)

    return {
        "turn_count": len(transcript),
        "dynamic_student_generated_turn_count": sum(
            1 for turn in transcript if turn.get("student_generated_by_llm") is True
        ),
        "live_prompt_enabled_turn_count": sum(
            1 for turn in transcript if turn.get("live_prompts_enabled") is True
        ),
        "max_latency_ms": max((int(turn.get("elapsed_ms") or 0) for turn in transcript), default=0),
        "latency_pass_count": sum(
            1 for turn in transcript if int(turn.get("elapsed_ms") or 0) <= max_latency_ms
        ),
        "backend_warning_patterns": _read_backend_log_warnings(backend_log_path),
        "judge_overall_pass": bool(judge_result.get("overall_pass")),
        "failed_turn_count": len(failed_turns),
        "failed_turns": failed_turns,
    }


def _render_text_summary(report: dict[str, Any]) -> str:
    lines = [
        "Mili Teaching Principles Eval",
        f"- report: {report['report_path']}",
        f"- backend_log: {report['backend_log']}",
        f"- judge_model: {report['judge']['model']}",
        f"- turns: {report['summary']['turn_count']}",
        f"- dynamic_student_generated: {report['summary']['dynamic_student_generated_turn_count']}/{max(0, report['summary']['turn_count'] - 1)}",
        f"- live_prompts_enabled: {report['summary']['live_prompt_enabled_turn_count']}/{report['summary']['turn_count']}",
        f"- judge_overall_pass: {report['summary']['judge_overall_pass']}",
        f"- failed_turn_count: {report['summary']['failed_turn_count']}",
    ]
    warnings = report["summary"].get("backend_warning_patterns") or []
    if warnings:
        lines.append(f"- backend_warnings: {', '.join(warnings)}")

    judged_turns = report["judge"]["result"].get("turns") or []
    if isinstance(judged_turns, list):
        for turn in judged_turns:
            if not isinstance(turn, dict):
                continue
            failed = turn.get("failed_principles") or []
            status = "FAIL" if failed else "PASS"
            lines.append(
                f"{turn.get('turn'):02d} {status} {turn.get('name')}: {turn.get('summary')}"
            )
            principles = turn.get("principles")
            if isinstance(principles, dict):
                for principle_id in DEFAULT_JUDGE_PRINCIPLES:
                    value = principles.get(principle_id)
                    if isinstance(value, dict):
                        lines.append(
                            f"  - {principle_id}: {value.get('status')} - {value.get('reason')}"
                        )
    return "\n".join(lines)


async def async_main() -> int:
    args = _parse_args()
    output_path = args.write_report or _default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    host = smoke._resolve_host()
    port = smoke._resolve_port()
    full_stack = smoke._resolve_full_stack_mode()
    keep_server = smoke._resolve_keep_server()
    startup_timeout_seconds = smoke._resolve_startup_timeout_seconds()
    request_timeout_seconds = smoke._resolve_request_timeout_seconds()
    session_timeout = aiohttp.ClientTimeout(total=smoke._resolve_timeout_seconds())

    principles_payload = json.loads(PRINCIPLES_PATH.read_text(encoding="utf-8"))
    async with aiohttp.ClientSession(timeout=session_timeout, trust_env=False) as session:
        backend: smoke.StartedBackend | None = None
        try:
            backend = await smoke.start_backend(
                session,
                host=host,
                port=port,
                startup_timeout_seconds=startup_timeout_seconds,
                full_stack=full_stack,
            )
            transcript = await _run_naive_simulation(
                base_url=backend.base_url,
                session=session,
                timeout_seconds=request_timeout_seconds,
                turn_count=args.turns,
            )
            judge = _judge_with_llm(
                transcript=transcript,
                principles_payload=principles_payload,
            )
            report: dict[str, Any] = {
                "captured_at": time.strftime("%Y%m%d_%H%M%S"),
                "mode": "route-focused /lesson/turn dynamic naive-student Mili principle eval",
                "student_policy": (
                    "动态低掌握学生：学生模型只看老师回复和可见历史，"
                    "不看答案库、教学目标、评分原则或后端状态；"
                    "只在老师明确示范后尝试跟读或修正。"
                ),
                "student_simulator": {
                    "model": os.getenv("LLM_MODEL") or "deepseek-chat",
                    "sees": ["last_teacher_response", "visible_dialogue_history"],
                    "does_not_see": [
                        "answer_key",
                        "lesson target",
                        "judge principles",
                        "private lesson state",
                    ],
                },
                "principles_path": str(PRINCIPLES_PATH),
                "judge_principles": list(DEFAULT_JUDGE_PRINCIPLES),
                "backend_log": str(backend.log_path),
                "report_path": str(output_path),
                "summary": _build_summary(
                    transcript=transcript,
                    judge=judge,
                    backend_log_path=backend.log_path,
                    max_latency_ms=args.max_latency_ms,
                ),
                "judge": judge,
                "compact_transcript": transcript,
            }
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _render_text_summary(report))
            return 0 if report["summary"]["failed_turn_count"] == 0 else 1
        finally:
            if backend is not None:
                await smoke.stop_backend(backend, keep_server=keep_server)


def main() -> int:
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(async_main())
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
