#!/usr/bin/env python3
"""Collect a 20-page PepTutor lesson smoke matrix against /lesson/turn.

This is a route/content smoke, not a replacement for the checked-in browser
suite. It keeps the run cheap enough to repeat while covering representative
pages across G5/G6 and both semesters.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp


REGRESSION_SET_ID = "lesson-core-20-v1"
EXPECTED_PAGE_COUNT = 20
EXPECTED_TURN_COUNT = 160

ACCEPTANCE_CRITERIA: tuple[str, ...] = (
    "page_count == 20",
    "turn_count == 160",
    "http_error_count == 0",
    "fallback_count == 0",
    "state_drift_count == 0",
    "issue_count == 0",
)

QUALITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "rule_fallback_copy": re.compile(r"规则兜底|兜底|rules fallback", re.I),
    "generic_praise": re.compile(r"很棒|真棒|太棒|非常好|非常准确|完全正确|做得很好|good job|great job|excellent", re.I),
    "phonics_tautology": re.compile(
        r"\b([A-Za-z]{2,20})\s+uses\s+the\s+\1\s+sound\b|"
        r"\b(cow|flower|down|wow|snow|slow|yellow|window|tomorrow)\s+sound\b",
        re.I,
    ),
    "next_page_copy": re.compile(r"下一页"),
    "traditional_chinese": re.compile(r"[這個學麼嗎說給聽裡對開關歡飲讓請後會應該來進選擇]"),
    "broken_mixed_english": re.compile(
        r"\b(?:I(?:'|’)d like|What would|you can)\.\s*(?:开头|回答|说)|"
        r"\b(?:I(?:'|’)d like|What would|you can)\b\s*(?:开头|回答|说)|"
        r"\b(?:turn left|go straight)\b\s*(?:是|意思是)|"
        r"\b(?:please|clean)\b[，,、]\s*(?:开头|回答|说)",
        re.I,
    ),
    "incomplete_sentence_tail": re.compile(r"(?:，|,|：|:|；|;|——|-)\s*$"),
}
SHORT_ANSWER_OBJECT_PRAISE_RE = re.compile(
    r"很好吃|很好玩|很好看|好可爱|很可爱|很棒|真棒|太棒|不错|真好|非常好|good job|great job|excellent",
    re.I,
)
SHORT_ANSWER_TASK_GROUNDING_RE = re.compile(
    r"属于|归到|可以算|分类|category|food|drink|drinks|supplies|"
    r"party word|本页|这页|图上|这一步|先找|再找|回到|"
    r"跟我|试着|可以说|读",
    re.I,
)
SHORT_ANSWER_NAVIGATION_RE = re.compile(
    r"第[一二三四五六七八九十0-9]+(?:块|部分|模块)|想学|模块|哪一块|"
    r"\?|？|what\s+(?:does|is)\b|是什么意思|什么意思",
    re.I,
)


@dataclass(frozen=True)
class PagePlan:
    book: str
    page_uid: str
    label: str
    block_count: int
    risk: str
    inputs: tuple[str, ...]


PAGES: tuple[PagePlan, ...] = (
    PagePlan("G5S1", "TB-G5S1U3-P24", "P24 Let's try + Let's talk", 4, "known food/drink boundary", ("第一块", "I'd like some water.", "pizza", "我想学第二块", "随便，你安排")),
    PagePlan("G5S1", "TB-G5S1U3-P22", "single-block dialogue", 1, "single-block route baseline", ("I like sandwiches.", "Yesterday I played football.", "中文可以吗", "tea", "我想学第二块")),
    PagePlan("G5S1", "TB-G5S1U3-P25", "three-block ordering", 3, "module choice and role play", ("第一块", "salad", "I'd like a sandwich, please.", "中文回答可以吗", "我想学第二块")),
    PagePlan("G5S1", "TB-G5S1U3-P26", "phonics/listening boundary", 4, "suspect block boundary", ("第一块", "snow", "What does cow mean?", "随便", "我想学第二块")),
    PagePlan("G5S1", "TB-G5S1U3-P31", "story overlay", 1, "pilot overlay grounding", ("I can read the story.", "What does thirsty mean?", "我不知道", "Zip", "我想学第二块")),
    PagePlan("G5S2", "TB-G5S2U1-P2", "single-block dialogue", 1, "new book baseline", ("At 7 o'clock.", "I played football yesterday.", "我七点起床。", "get up", "我想学第二块")),
    PagePlan("G5S2", "TB-G5S2U1-P4", "three-block dialogue", 3, "listen + dialogue + practice", ("At 7 o'clock.", "Spain", "中文可以吗", "start class", "我想学第二块")),
    PagePlan("G5S2", "TB-G5S2U1-P6", "phonics + practice", 3, "phonics branch and task page", ("clean", "What does clock mean?", "我不会", "please", "我想学第二块")),
    PagePlan("G5S2", "TB-G5S2U2-P14", "three-block season dialogue", 3, "dialogue with vocabulary support", ("spring", "I like summer best.", "中文可以吗", "because", "我想学第二块")),
    PagePlan("G5S2", "TB-G5S2U2-P19", "reading + writing", 3, "reading/writing page", ("I like spring.", "What does because mean?", "我不知道", "winter", "我想学第二块")),
    PagePlan("G6S1", "TB-G6S1U1-P2", "single-block dialogue", 1, "higher-grade single-block baseline", ("It's near the door.", "I played football yesterday.", "中文可以吗", "museum", "我想学第二块")),
    PagePlan("G6S1", "TB-G6S1U1-P4", "three-block directions", 3, "listen + direction dialogue", ("Where is the museum shop?", "turn left", "中文可以吗", "bookstore", "我想学第二块")),
    PagePlan("G6S1", "TB-G6S1U1-P9", "reading + phonics", 3, "mixed reading/phonics structure", ("GPS", "What does feature mean?", "我不知道", "right", "我想学第二块")),
    PagePlan("G6S1", "TB-G6S1U2-P14", "four-block transport dialogue", 4, "multi-block module choice", ("By bus.", "How do you come to school?", "中文可以吗", "subway", "我想学第二块")),
    PagePlan("G6S1", "TB-G6S1U2-P19", "reading + grammar + phonics", 4, "dense mixed page", ("helmet", "What does must mean?", "我不知道", "sled", "我想学第二块")),
    PagePlan("G6S2", "TB-G6S2U1-P2", "single-block size dialogue", 1, "known G6 route drift risk", ("I'm 1.60 metres.", "taller", "中文可以吗", "dinosaur", "我想学第二块")),
    PagePlan("G6S2", "TB-G6S2U1-P4", "four-block height dialogue", 4, "multi-block measurement lesson", ("How tall are you?", "I'm 1.58 metres.", "我不知道", "heavier", "我想学第二块")),
    PagePlan("G6S2", "TB-G6S2U2-P13", "G6 illness dialogue", 2, "known vocabulary interruption slice", ("What does stayed at home mean?", "I stayed at home.", "had a cold", "我不知道", "我想学第二块")),
    PagePlan("G6S2", "TB-G6S2U2-P16", "four-block weekend dialogue", 4, "multi-block past-tense lesson", ("I watched TV.", "What did you do last weekend?", "中文可以吗", "magazine", "我想学第二块")),
    PagePlan("G6S2", "TB-G6S2Recycle2-P49", "Recycle2 party task", 4, "known ordering/task-instruction risk", ("第一块", "pizza", "news", "我不知道", "我想学第二块")),
)


def utcish_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def is_short_answer_input(text: str | None) -> bool:
    if text is None:
        return False
    cleaned = " ".join(str(text).strip().split()).strip(" .,!?:;，。！？：；、")
    if not cleaned or SHORT_ANSWER_NAVIGATION_RE.search(cleaned):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z'’ -]{0,60}", cleaned):
        return len([word for word in re.split(r"[\s-]+", cleaned) if word]) <= 3
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{1,8}", cleaned))


def quality_flags(text: str, *, learner_input: str | None = None) -> list[str]:
    flags = [
        name
        for name, pattern in QUALITY_PATTERNS.items()
        if pattern.search(text or "")
    ]
    if (
        is_short_answer_input(learner_input)
        and SHORT_ANSWER_OBJECT_PRAISE_RE.search(text or "")
        and not SHORT_ANSWER_TASK_GROUNDING_RE.search(text or "")
    ):
        flags.append("generic_praise_for_short_answer")
    return flags


def nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def compact_turn(
    *,
    page: PagePlan,
    step: str,
    learner_input: str | None,
    status: int,
    elapsed_ms: int,
    payload: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    debug = nested_dict(payload.get("debug_signals"))
    audit = nested_dict(debug.get("response_audit"))
    llm_token_usage = nested_dict(audit.get("llm_token_usage"))
    persona = nested_dict(debug.get("persona"))
    performance = nested_dict(persona.get("airi_performance"))
    state = nested_dict(payload.get("state"))
    teacher_response = str(payload.get("teacher_response") or "")

    return {
        "book": page.book,
        "page_uid": page.page_uid,
        "page_label": page.label,
        "page_risk": page.risk,
        "block_count": page.block_count,
        "step": step,
        "learner_input": learner_input,
        "http_status": status,
        "elapsed_ms": elapsed_ms,
        "turn_label": payload.get("turn_label"),
        "evaluation": payload.get("evaluation"),
        "state_page_uid": state.get("current_page_uid"),
        "state_block_uid": state.get("current_block_uid"),
        "awaiting_answer": state.get("awaiting_answer"),
        "teacher_response": teacher_response,
        "quality_flags": quality_flags(teacher_response, learner_input=learner_input),
        "teacherresponsesource": audit.get("source"),
        "fallbackused": audit.get("fallback_used"),
        "fallback_reason": audit.get("fallback_reason"),
        "repair_reason": audit.get("repair_reason"),
        "latencyms": audit.get("latency_ms"),
        "route": audit.get("route"),
        "llm_called": audit.get("llm_called"),
        "llm_token_usage": llm_token_usage or None,
        "persona_source": persona.get("persona_source"),
        "persona_version": persona.get("persona_version"),
        "full_soul_injected": persona.get("full_soul_injected"),
        "answer_turn_policy_persona_capsule_enabled": persona.get(
            "answer_turn_policy_persona_capsule_enabled"
        ),
        "current_llm_call_persona_capsule_injected": persona.get(
            "current_llm_call_persona_capsule_injected"
        ),
        "persona_capsule_bytes_configured": persona.get(
            "persona_capsule_bytes_configured"
        ),
        "persona_capsule_bytes_metered": persona.get(
            "persona_capsule_bytes_metered"
        ),
        "live2d_motion": performance.get("motion"),
        "live2d_expression": performance.get("expression"),
        "live2d_emotion": performance.get("emotion"),
        "speech_style": performance.get("speech_style"),
        "interrupt_policy": performance.get("interrupt_policy"),
        "mouth_intensity": performance.get("mouth_intensity"),
        "error": error,
        "_state": state,
    }


async def request_turn(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    page: PagePlan,
    step: str,
    student_id: str,
    state: dict[str, Any] | None,
    learner_input: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "page_uid": page.page_uid,
        "student_id": student_id,
    }
    if state:
        body["state"] = state
    if learner_input is not None:
        body["learner_input"] = learner_input

    started = time.perf_counter()
    transient_errors = (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError)
    for attempt in range(2):
        try:
            async with session.post(
                f"{base_url.rstrip('/')}/lesson/turn",
                json=body,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as response:
                text = await response.text()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                payload: dict[str, Any] | None = None
                error: str | None = None
                try:
                    decoded = json.loads(text)
                    if isinstance(decoded, dict):
                        payload = decoded
                    else:
                        error = f"non_object_json:{type(decoded).__name__}"
                except json.JSONDecodeError:
                    error = text[:500] or "invalid_json"
                if response.status != 200 and error is None:
                    error = text[:500]
                return compact_turn(
                    page=page,
                    step=step,
                    learner_input=learner_input,
                    status=response.status,
                    elapsed_ms=elapsed_ms,
                    payload=payload,
                    error=error,
                )
        except transient_errors as exc:
            if attempt == 0:
                await asyncio.sleep(0.1)
                continue
            return compact_turn(
                page=page,
                step=step,
                learner_input=learner_input,
                status=0,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                payload=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - smoke collector must keep going.
            return compact_turn(
                page=page,
                step=step,
                learner_input=learner_input,
                status=0,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                payload=None,
                error=f"{type(exc).__name__}: {exc}",
            )

    return compact_turn(
        page=page,
        step=step,
        learner_input=learner_input,
        status=0,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        payload=None,
        error="transient_disconnect_retry_exhausted",
    )


async def collect_page(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    page: PagePlan,
    run_id: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    student_id = f"smoke20-{run_id}-{page.page_uid.lower()}"
    turns: list[dict[str, Any]] = []

    current = await request_turn(
        session,
        base_url=base_url,
        page=page,
        step="page_entry",
        student_id=student_id,
        state=None,
        learner_input=None,
        timeout_seconds=timeout_seconds,
    )
    turns.append(current)
    state = current.get("_state") if isinstance(current.get("_state"), dict) else None
    rapid_state: dict[str, Any] | None = None

    for index, learner_input in enumerate(page.inputs, start=1):
        current = await request_turn(
            session,
            base_url=base_url,
            page=page,
            step=f"turn_{index}",
            student_id=student_id,
            state=state,
            learner_input=learner_input,
            timeout_seconds=timeout_seconds,
        )
        turns.append(current)
        if index == 2:
            rapid_state = state
        next_state = current.get("_state")
        if current["http_status"] == 200 and isinstance(next_state, dict):
            state = next_state

    if rapid_state:
        rapid_a, rapid_b = await asyncio.gather(
            request_turn(
                session,
                base_url=base_url,
                page=page,
                step="rapid_a_same_state",
                student_id=student_id,
                state=rapid_state,
                learner_input="water",
                timeout_seconds=timeout_seconds,
            ),
            request_turn(
                session,
                base_url=base_url,
                page=page,
                step="rapid_b_same_state",
                student_id=student_id,
                state=rapid_state,
                learner_input="I want to play basketball.",
                timeout_seconds=timeout_seconds,
            ),
        )
        turns.extend([rapid_a, rapid_b])

    for turn in turns:
        turn.pop("_state", None)
    return turns


def issue(severity: str, area: str, page_uid: str, title: str, evidence: str) -> dict[str, str]:
    return {
        "severity": severity,
        "area": area,
        "page_uid": page_uid,
        "title": title,
        "evidence": evidence,
    }


def analyze(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for turn in turns:
        page_uid = str(turn["page_uid"])
        step = str(turn["step"])
        response = str(turn.get("teacher_response") or "")
        evidence_prefix = f"{step} input={turn.get('learner_input')!r}"

        if turn["http_status"] != 200 or turn.get("error"):
            issues.append(issue("critical", "S6", page_uid, "lesson turn request failed", f"{evidence_prefix}; status={turn['http_status']} error={turn.get('error')}"))
            continue
        if turn.get("state_page_uid") and turn.get("state_page_uid") != page_uid:
            issues.append(issue("critical", "S5", page_uid, "turn state drifted to another page", f"{evidence_prefix}; state_page_uid={turn.get('state_page_uid')}"))
        if turn.get("fallbackused") is True or turn.get("teacherresponsesource") == "fallback":
            issues.append(issue("critical", "S3", page_uid, "backend fallback used", f"{evidence_prefix}; reason={turn.get('fallback_reason')} route={turn.get('route')}"))
        if not turn.get("teacherresponsesource"):
            issues.append(issue("major", "S2", page_uid, "teacher response source missing", evidence_prefix))
        if "rule_fallback_copy" in turn.get("quality_flags", []):
            issues.append(issue("major", "S2", page_uid, "fallback wording leaked into response", f"{evidence_prefix}; reply={response[:180]}"))
        if "next_page_copy" in turn.get("quality_flags", []):
            issues.append(issue("major", "S3", page_uid, "reply mentions next page", f"{evidence_prefix}; reply={response[:180]}"))
        if "traditional_chinese" in turn.get("quality_flags", []):
            issues.append(issue("minor", "S3", page_uid, "traditional Chinese character detected", f"{evidence_prefix}; reply={response[:180]}"))
        if "broken_mixed_english" in turn.get("quality_flags", []):
            issues.append(issue("major", "S3", page_uid, "English sentence appears mixed/broken with Chinese", f"{evidence_prefix}; reply={response[:180]}"))
        if "generic_praise" in turn.get("quality_flags", []):
            issues.append(issue("minor", "S3", page_uid, "generic praise remains in response", f"{evidence_prefix}; reply={response[:180]}"))
        if "generic_praise_for_short_answer" in turn.get("quality_flags", []):
            issues.append(issue("minor", "S3", page_uid, "generic praise for short answer lacks task grounding", f"{evidence_prefix}; reply={response[:180]}"))
        if "phonics_tautology" in turn.get("quality_flags", []):
            issues.append(issue("major", "S3", page_uid, "phonics reply uses tautological sound label", f"{evidence_prefix}; reply={response[:180]}"))
        if "incomplete_sentence_tail" in turn.get("quality_flags", []):
            issues.append(issue("minor", "S3", page_uid, "teacher response ends with incomplete punctuation", f"{evidence_prefix}; reply={response[:180]}"))
        if int(turn.get("block_count") or 0) == 1 and re.search(r"第二块|下一块|转到第二", response):
            issues.append(issue("major", "S5", page_uid, "single-block page talks about a second block", f"{evidence_prefix}; reply={response[:180]}"))
        latency = turn.get("latencyms")
        if isinstance(latency, int) and latency >= 20000:
            issues.append(issue("major", "S6", page_uid, "high backend audit latency", f"{evidence_prefix}; latencyms={latency}"))
        elif isinstance(latency, int) and latency >= 10000:
            issues.append(issue("minor", "S6", page_uid, "elevated backend audit latency", f"{evidence_prefix}; latencyms={latency}"))
        if turn.get("live2d_motion") is None or turn.get("live2d_expression") is None:
            issues.append(issue("minor", "S4", page_uid, "AIRI performance plan missing motion or expression", f"{evidence_prefix}; motion={turn.get('live2d_motion')} expression={turn.get('live2d_expression')}"))
    return issues


def summarize(turns: list[dict[str, Any]], issues: list[dict[str, str]]) -> dict[str, Any]:
    by_area: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in issues:
        by_area[item["area"]] = by_area.get(item["area"], 0) + 1
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
    page_count = len({turn["page_uid"] for turn in turns})
    turn_count = len(turns)
    http_error_count = sum(1 for turn in turns if turn["http_status"] != 200 or turn.get("error"))
    fallback_count = sum(1 for turn in turns if turn.get("fallbackused") is True or turn.get("teacherresponsesource") == "fallback")
    state_drift_count = sum(
        1
        for turn in turns
        if turn.get("state_page_uid") and turn.get("state_page_uid") != turn.get("page_uid")
    )
    issue_count = len(issues)
    llm_token_usages = [
        turn["llm_token_usage"]
        for turn in turns
        if isinstance(turn.get("llm_token_usage"), dict)
    ]
    interrupt_policy_counts: dict[str, int] = {}
    for turn in turns:
        policy = turn.get("interrupt_policy")
        if isinstance(policy, str) and policy:
            interrupt_policy_counts[policy] = interrupt_policy_counts.get(policy, 0) + 1
    acceptance_passed = (
        page_count == EXPECTED_PAGE_COUNT
        and turn_count == EXPECTED_TURN_COUNT
        and http_error_count == 0
        and fallback_count == 0
        and state_drift_count == 0
        and issue_count == 0
    )
    return {
        "regression_set_id": REGRESSION_SET_ID,
        "expected_page_count": EXPECTED_PAGE_COUNT,
        "expected_turn_count": EXPECTED_TURN_COUNT,
        "page_count": page_count,
        "turn_count": turn_count,
        "http_error_count": http_error_count,
        "fallback_count": fallback_count,
        "state_drift_count": state_drift_count,
        "issue_count": issue_count,
        "acceptance_passed": acceptance_passed,
        "sources": sorted({str(turn["teacherresponsesource"]) for turn in turns if turn.get("teacherresponsesource")}),
        "max_elapsed_ms": max((int(turn.get("elapsed_ms") or 0) for turn in turns), default=0),
        "max_latencyms": max((int(turn.get("latencyms") or 0) for turn in turns if turn.get("latencyms") is not None), default=0),
        "llm_call_count": sum(
            int(usage.get("llm_call_count") or 0) for usage in llm_token_usages
        ),
        "llm_prompt_token_estimate": sum(
            int(usage.get("prompt_token_estimate") or 0)
            for usage in llm_token_usages
        ),
        "llm_completion_token_estimate": sum(
            int(usage.get("completion_token_estimate") or 0)
            for usage in llm_token_usages
        ),
        "interrupt_policy_counts": interrupt_policy_counts,
        "issue_count_by_area": by_area,
        "issue_count_by_severity": by_severity,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Lesson 20-Page Smoke Matrix",
        "",
        f"Generated: {report['finished_at']}",
        f"Backend: `{report['base_url']}`",
        f"Regression set: `{report['regression_set_id']}`",
        "",
        "## Summary",
        "",
    ]
    summary = report["summary"]
    for key in (
        "acceptance_passed",
        "page_count",
        "turn_count",
        "http_error_count",
        "fallback_count",
        "state_drift_count",
        "issue_count",
        "sources",
        "max_elapsed_ms",
        "max_latencyms",
        "llm_call_count",
        "llm_prompt_token_estimate",
        "llm_completion_token_estimate",
        "interrupt_policy_counts",
    ):
        lines.append(f"- {key}: `{summary[key]}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in report["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.extend(["", "## Issues", ""])
    if not report["issues"]:
        lines.append("- none")
    else:
        for item in report["issues"]:
            lines.append(f"- [{item['area']}] {item['severity']} `{item['page_uid']}`: {item['title']} - {item['evidence']}")
    lines.extend(["", "## Pages", ""])
    for page in report["pages"]:
        lines.append(f"- `{page['page_uid']}` {page['book']} {page['label']} ({page['risk']})")
    lines.append("")
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = utcish_stamp()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    turns: list[dict[str, Any]] = []

    connector = aiohttp.TCPConnector(force_close=True)
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=args.timeout),
        trust_env=False,
        connector=connector,
    ) as session:
        for page in PAGES:
            print(f"[smoke20] {page.book} {page.page_uid} {page.label}", flush=True)
            turns.extend(
                await collect_page(
                    session,
                    base_url=args.base_url,
                    page=page,
                    run_id=run_id,
                    timeout_seconds=args.timeout,
                )
            )

    issues = analyze(turns)
    report = {
        "regression_set_id": REGRESSION_SET_ID,
        "acceptance_criteria": list(ACCEPTANCE_CRITERIA),
        "run_id": run_id,
        "base_url": args.base_url,
        "started_at": run_id,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "pages": [page.__dict__ for page in PAGES],
        "turns": turns,
        "issues": issues,
        "summary": summarize(turns, issues),
    }
    json_path = out_dir / f"lesson_smoke_matrix_{run_id}.json"
    md_path = out_dir / f"lesson_smoke_matrix_{run_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["markdown_path"] = str(md_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:9625")
    parser.add_argument("--out-dir", default="temp/lesson-smoke-artifacts")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--allow-issues",
        action="store_true",
        help="Write the report but return exit code 0 even when the fixed regression acceptance criteria fail.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(run(args))
    print(json.dumps({
        "json_path": report["json_path"],
        "markdown_path": report["markdown_path"],
        "summary": report["summary"],
        "top_issues": report["issues"][:20],
    }, ensure_ascii=False, indent=2))
    if args.allow_issues:
        return 0
    return 0 if report["summary"]["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
