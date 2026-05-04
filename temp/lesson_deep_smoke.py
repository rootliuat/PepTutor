from __future__ import annotations

import argparse
import contextlib
import json
import re
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:
    PlaywrightError = Exception
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


PAGES = [
    {
        "page_uid": "TB-G5S1U3-P24",
        "label": "P24 Let's try + Let's talk",
        "reason": "known food/drink block-boundary risk",
    },
    {
        "page_uid": "TB-G5S1U1-P2",
        "label": "one-block pure dialogue",
        "reason": "single dialogue block baseline",
    },
    {
        "page_uid": "TB-G5S1U1-P4",
        "label": "three-block dialogue",
        "reason": "listening + core dialogue + practice",
    },
    {
        "page_uid": "TB-G5S1U3-P26",
        "label": "suspect structure",
        "reason": "ow phonics, duplicate/overlay block risk",
    },
    {
        "page_uid": "TB-G6S2U2-P13",
        "label": "G6 dialogue",
        "reason": "higher-grade in-context vocabulary questions",
    },
    {
        "page_uid": "TB-G6S2Recycle2-P49",
        "label": "G6 recycle multi-block",
        "reason": "phonics + open party-shopping task",
    },
]

SCENARIOS = [
    ("normal_answer", "I'd like some water."),
    ("off_topic", "Yesterday I played football all day."),
    ("chinese_answer", "我想喝水。"),
    ("short_answer", "pizza"),
    ("delegate", "随便，你安排"),
    ("select_second_block", "我想学第二块"),
]

QUICK_DOUBLE = ("quick_double", "First quick message.", "Second quick message.")
AFTER_REFRESH = ("after_refresh", "刷新后继续，我想再试一次。")

GENERIC_PRAISE_RE = re.compile(r"很棒|很好|太棒|不错")
SHORT_ANSWER_OBJECT_PRAISE_RE = re.compile(
    r"很好吃|很好玩|很好看|好可爱|很可爱|很棒|真棒|太棒|不错|真好|非常好",
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
RULE_FALLBACK_RE = re.compile(r"规则兜底|兜底|rules fallback", re.I)
RELEVANT_NETWORK_MARKERS = (
    "/lesson/",
    "/peptutor-api",
    "/api/peptutor",
    "tts",
    "6121",
)


class SmokeTimeoutError(RuntimeError):
    pass


@contextlib.contextmanager
def timeout_scope(seconds: int, label: str):
    if seconds <= 0:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(signum, frame):
        _ = (signum, frame)
        raise SmokeTimeoutError(f"{label} timed out after {seconds}s")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def now_label() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def append_limited(items: list[dict[str, Any]], item: dict[str, Any], *, limit: int = 500) -> None:
    if len(items) < limit:
        items.append(item)


def is_relevant_network_url(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in RELEVANT_NETWORK_MARKERS)


def parse_sse_done(body: str) -> dict[str, Any] | None:
    current_event = ""
    data_lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if current_event == "done" and data_lines:
                try:
                    payload = json.loads("\n".join(data_lines))
                    result = payload.get("result")
                    return result if isinstance(result, dict) else None
                except json.JSONDecodeError:
                    return None
            current_event = ""
            data_lines = []
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
            data_lines = []
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    return None


def safe_text(page, test_id: str) -> str:
    try:
        return page.locator(f'[data-testid="{test_id}"]').inner_text(timeout=900).strip()
    except PlaywrightError:
        return ""


def body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except PlaywrightError:
        return ""


def audit_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    debug = result.get("debug_signals")
    if not isinstance(debug, dict):
        return {}
    audit = debug.get("response_audit")
    return audit if isinstance(audit, dict) else {}


def performance_from_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not result:
        return {}
    debug = result.get("debug_signals")
    if not isinstance(debug, dict):
        return {}
    persona = debug.get("persona")
    if not isinstance(persona, dict):
        return {}
    performance = persona.get("airi_performance")
    return performance if isinstance(performance, dict) else {}


def result_summary(
    result: dict[str, Any] | None,
    elapsed_ms: int | None,
    ui: dict[str, str],
    *,
    learner_input: str | None = None,
) -> dict[str, Any]:
    audit = audit_from_result(result)
    performance = performance_from_result(result)
    teacher_response = str(result.get("teacher_response") if result else "") if result else ""
    return {
        "turn_label": result.get("turn_label") if result else None,
        "page_uid": result.get("page_uid") if result else None,
        "block_uid": result.get("block_uid") if result else None,
        "evaluation": result.get("evaluation") if result else None,
        "teacher_response": teacher_response,
        "teacher_response_source": audit.get("source"),
        "fallback_used": audit.get("fallback_used"),
        "fallback_reason": audit.get("fallback_reason"),
        "latency_ms": audit.get("latency_ms") if audit.get("latency_ms") is not None else elapsed_ms,
        "route": audit.get("route"),
        "llm_called": audit.get("llm_called"),
        "generic_praise": bool(GENERIC_PRAISE_RE.search(teacher_response)),
        "generic_praise_for_short_answer": (
            is_short_answer_input(learner_input)
            and bool(SHORT_ANSWER_OBJECT_PRAISE_RE.search(teacher_response))
            and not bool(SHORT_ANSWER_TASK_GROUNDING_RE.search(teacher_response))
        ),
        "rule_fallback_text": bool(RULE_FALLBACK_RE.search(teacher_response)),
        "airi_performance": {
            "motion": performance.get("motion"),
            "expression": performance.get("expression"),
            "speech_style": performance.get("speech_style"),
            "mouth_intensity": performance.get("mouth_intensity"),
            "content_source": performance.get("content_source"),
        },
        "ui": ui,
    }


def is_short_answer_input(text: str | None) -> bool:
    if text is None:
        return False
    cleaned = " ".join(str(text).strip().split()).strip(" .,!?:;，。！？：；、")
    if not cleaned or SHORT_ANSWER_NAVIGATION_RE.search(cleaned):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z'’ -]{0,60}", cleaned):
        return len([word for word in re.split(r"[\s-]+", cleaned) if word]) <= 3
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{1,8}", cleaned))


def read_ui_state(page) -> dict[str, str]:
    return {
        "reply_path": safe_text(page, "lesson-airi-visible-fact-reply_path"),
        "tts": safe_text(page, "lesson-airi-visible-fact-tts"),
        "teaching_stance": safe_text(page, "lesson-airi-teaching-stance"),
        "performance_source": safe_text(page, "lesson-runtime-fact-performance_source"),
        "requested_motion": safe_text(page, "lesson-runtime-fact-motion"),
        "requested_expression": safe_text(page, "lesson-runtime-fact-expression"),
        "performance_apply": safe_text(page, "lesson-runtime-fact-performance_apply"),
        "applied_motion": safe_text(page, "lesson-runtime-fact-applied_motion"),
        "applied_expression": safe_text(page, "lesson-runtime-fact-applied_expression"),
        "chat_status": safe_text(page, "lesson-chat-status-label"),
        "chat_detail": safe_text(page, "lesson-chat-status-detail"),
        "memory_student_id": safe_text(page, "lesson-memory-debug-value-student_id"),
        "memory_session_id": safe_text(page, "lesson-memory-debug-value-memory_session_id"),
        "memory_recall_status": safe_text(page, "lesson-memory-debug-status-recall"),
        "memory_writeback_status": safe_text(page, "lesson-memory-debug-status-writeback"),
    }


def collect_runtime_observation(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
              const facts = {}
              for (const node of document.querySelectorAll('[data-testid]')) {
                const id = node.getAttribute('data-testid') || ''
                if (
                  id.startsWith('lesson-airi-visible-fact-')
                  || id.startsWith('lesson-runtime-fact-')
                  || id === 'lesson-airi-visible-state'
                ) {
                  facts[id] = (node.textContent || '').trim()
                }
              }
              const audioElements = Array.from(document.querySelectorAll('audio')).map((audio) => ({
                paused: audio.paused,
                ended: audio.ended,
                currentTime: Number.isFinite(audio.currentTime) ? audio.currentTime : null,
                duration: Number.isFinite(audio.duration) ? audio.duration : null,
                readyState: audio.readyState,
                srcPresent: Boolean(audio.currentSrc || audio.src),
              }))
              const mouthOpenText = facts['lesson-runtime-fact-mouth_open'] || facts['lesson-airi-visible-fact-mouth_open'] || ''
              const mouthOpen = Number.parseFloat(mouthOpenText)
              const ttsSynthesisState = facts['lesson-runtime-fact-tts_synthesis_state'] || facts['lesson-airi-visible-fact-tts_synthesis_state'] || ''
              const ttsPlaybackStateText = facts['lesson-runtime-fact-tts_playback_state'] || facts['lesson-airi-visible-fact-tts_playback_state'] || ''
              const ttsPlaybackState = (ttsPlaybackStateText.split('·')[0] || '').trim()
              const ttsPlaybackId = facts['lesson-runtime-fact-tts_playback_id'] || facts['lesson-airi-visible-fact-tts_playback_id'] || ''
              const activeReplyId = facts['lesson-runtime-fact-active_reply_id'] || facts['lesson-airi-visible-fact-active_reply_id'] || ''
              const ttsStopReason = facts['lesson-runtime-fact-tts_stop_reason'] || facts['lesson-airi-visible-fact-tts_stop_reason'] || ''
              const rawTtsStopType = facts['lesson-runtime-fact-tts_stop_type'] || facts['lesson-airi-visible-fact-tts_stop_type'] || ''
              const normalizeStopType = (reason, stopType) => {
                const existing = String(stopType || '').trim()
                if (existing && existing !== 'none') return existing
                const normalizedReason = String(reason || '').trim()
                if (!normalizedReason || normalizedReason === 'none') return existing || 'none'
                if (normalizedReason === 'lesson-learner-barge-in') return 'volume_barge_in'
                if (normalizedReason === 'lesson-learner-transcription') return 'final_transcript_interrupt'
                if (normalizedReason === 'lesson-learner-send') return 'manual_send_interrupt'
                if (normalizedReason === 'new-message' || normalizedReason === 'replace') return 'new_teacher_turn_replace'
                if (normalizedReason === 'lesson-new-turn' || normalizedReason.includes('lesson-turn-abort')) return 'lesson_turn_abort'
                if (normalizedReason === 'stage-unmount') return 'unmount_cleanup'
                if (normalizedReason === 'lesson-stop-button') return 'user_stop'
                if (normalizedReason === 'ended') return 'playback_ended'
                if (normalizedReason.includes('error') || normalizedReason.includes('rejected') || normalizedReason.includes('suspended')) return 'playback_error'
                return 'unknown'
              }
              const ttsStopType = normalizeStopType(ttsStopReason, rawTtsStopType)
              const ttsOverlapText = facts['lesson-runtime-fact-tts_overlap_detected'] || facts['lesson-airi-visible-fact-tts_overlap_detected'] || ''
              const ttsOverlapDetected = ttsOverlapText.startsWith('true')
              const performanceFallbackKind = facts['lesson-runtime-fact-performance_fallback_kind'] || facts['lesson-airi-visible-fact-performance_fallback_kind'] || ''
              const audioStartedFromElements = audioElements.some((audio) => (
                (typeof audio.currentTime === 'number' && audio.currentTime > 0)
                || (audio.paused === false && audio.ended === false)
              ))
              const audioStartedFromRuntime = ['playing', 'play_resolved', 'ended'].includes(ttsPlaybackState)
              return {
                observed_at: new Date().toISOString(),
                facts,
                tts_status_text: facts['lesson-airi-visible-fact-tts'] || '',
                tts_synthesis_state: ttsSynthesisState,
                tts_playback_state: ttsPlaybackState,
                tts_playback_state_text: ttsPlaybackStateText,
                tts_playback_id: ttsPlaybackId,
                active_reply_id: activeReplyId,
                tts_stop_reason: ttsStopReason,
                tts_stop_type: ttsStopType,
                tts_overlap_detected: ttsOverlapDetected,
                tts_overlap_text: ttsOverlapText,
                requested_motion: facts['lesson-runtime-fact-motion'] || '',
                requested_expression: facts['lesson-runtime-fact-expression'] || '',
                performance_apply: facts['lesson-airi-visible-fact-performance_apply'] || facts['lesson-runtime-fact-performance_apply'] || '',
                performance_fallback_kind: performanceFallbackKind,
                applied_motion: facts['lesson-airi-visible-fact-applied_motion'] || '',
                applied_expression: facts['lesson-airi-visible-fact-applied_expression'] || '',
                mouth_open_text: mouthOpenText,
                mouth_open_observed: Number.isFinite(mouthOpen) && mouthOpen > 0,
                audio_elements: audioElements,
                audio_started: audioStartedFromElements || audioStartedFromRuntime,
                audio_started_from_elements: audioStartedFromElements,
                audio_started_from_runtime: audioStartedFromRuntime,
                audio_probe: window.__PEPTUTOR_DEEP_SMOKE_PROBE__ || {},
              }
            }"""
        )
    except PlaywrightError as exc:
        return {"error": repr(exc)}


def _has_active_tts_stop_reason(value: Any) -> bool:
    reason = str(value or "").strip()
    return bool(reason and reason != "none")


def should_wait_for_tts_runtime_progress(initial_observation: dict[str, Any]) -> bool:
    playback_state = str(initial_observation.get("tts_playback_state") or "").strip()
    synthesis_state = str(initial_observation.get("tts_synthesis_state") or "").strip()
    if playback_state and playback_state != "idle":
        return False
    if _has_active_tts_stop_reason(initial_observation.get("tts_stop_reason")):
        return False
    if (
        initial_observation.get("mouth_open_observed")
        and playback_state != "playing"
    ):
        return True
    return synthesis_state in {"requesting", "http_ok"}


def wait_for_tts_runtime_progress(page, initial_observation: dict[str, Any]) -> None:
    if not should_wait_for_tts_runtime_progress(initial_observation):
        return

    try:
        page.wait_for_function(
            """(initialMouthOpenObserved) => {
              const text = (id) => (document.querySelector(`[data-testid="${id}"]`)?.textContent || '').trim()
              const synthesis = text('lesson-runtime-fact-tts_synthesis_state') || text('lesson-airi-visible-fact-tts_synthesis_state')
              const playbackText = text('lesson-runtime-fact-tts_playback_state') || text('lesson-airi-visible-fact-tts_playback_state')
              const playback = (playbackText.split('·')[0] || '').trim()
              const stopReason = text('lesson-runtime-fact-tts_stop_reason') || text('lesson-airi-visible-fact-tts_stop_reason')
              const mouthText = text('lesson-runtime-fact-mouth_open') || text('lesson-airi-visible-fact-mouth_open')
              const mouthOpen = Number.parseFloat(mouthText)
              if (playback && playback !== 'idle') return true
              if (stopReason && stopReason !== 'none') return true
              if (['http_error', 'empty_audio', 'unsupported_provider'].includes(synthesis)) return true
              return initialMouthOpenObserved && Number.isFinite(mouthOpen) && mouthOpen <= 0
            }""",
            arg=bool(initial_observation.get("mouth_open_observed")),
            timeout=5000,
        )
    except PlaywrightTimeoutError:
        pass


def append_runtime_observation(page_result: dict[str, Any], page, label: str) -> dict[str, Any]:
    initial_observation = collect_runtime_observation(page)
    wait_for_tts_runtime_progress(page, initial_observation)
    observation = {
        "label": label,
        **collect_runtime_observation(page),
    }
    if any(
        initial_observation.get(key) != observation.get(key)
        for key in (
            "tts_synthesis_state",
            "tts_playback_state",
            "tts_playback_state_text",
            "tts_playback_id",
            "active_reply_id",
            "tts_stop_reason",
            "tts_stop_type",
            "tts_overlap_text",
            "performance_fallback_kind",
            "mouth_open_text",
            "audio_started",
        )
    ):
        observation["pre_wait_observation"] = initial_observation
    page_result.setdefault("runtime_observations", []).append(observation)
    page_result["runtime_observation"] = observation
    return observation


def set_textarea_text(page, text: str) -> dict[str, Any]:
    return page.evaluate(
        """(text) => {
          const textarea = document.querySelector('textarea')
          if (!textarea) return {ok: false, reason: 'textarea_missing'}
          textarea.focus()
          textarea.value = text
          textarea.dispatchEvent(new Event('input', { bubbles: true }))
          textarea.dispatchEvent(new Event('change', { bubbles: true }))
          return {ok: true, textareaValue: textarea.value}
        }""",
        text,
    )


def click_send_button(page, wait_until_enabled: bool) -> dict[str, Any]:
    button = page.locator('button[aria-label="发送"], button[title="发送"], button:has-text("发送")').first
    if wait_until_enabled:
        page.wait_for_function(
            """() => {
              const button = Array.from(document.querySelectorAll('button')).find((candidate) => {
                const label = [
                  candidate.textContent || '',
                  candidate.getAttribute('aria-label') || '',
                  candidate.getAttribute('title') || '',
                ].map(value => value.trim())
                return label.includes('发送')
              })
              return Boolean(button && !button.disabled && button.getAttribute('aria-disabled') !== 'true')
            }""",
            timeout=5000,
        )

    metadata = page.evaluate(
        """() => {
          const button = Array.from(document.querySelectorAll('button')).find((candidate) => {
            const label = [
              candidate.textContent || '',
              candidate.getAttribute('aria-label') || '',
              candidate.getAttribute('title') || '',
            ].map(value => value.trim())
            return label.includes('发送')
          })
          const textarea = document.querySelector('textarea')
          if (!button) return {ok: false, reason: 'send_button_missing', textareaValue: textarea ? textarea.value : ''}
          const disabled = Boolean(button.disabled || button.getAttribute('aria-disabled') === 'true')
          return {ok: !disabled, disabled, textareaValue: textarea ? textarea.value : ''}
        }"""
    )
    if not metadata.get("ok"):
        return metadata

    button.click(timeout=5000)
    metadata["trusted_click"] = True
    return metadata


def run_stream_turn(page, text: str, timeout_ms: int = 120_000) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.time()
    set_meta = set_textarea_text(page, text)
    with page.expect_response(
        lambda response: "/lesson/turn/stream" in response.url and response.request.method == "POST",
        timeout=timeout_ms,
    ) as response_info:
        send_meta = click_send_button(page, wait_until_enabled=True)
    response = response_info.value
    body = response.text()
    elapsed_ms = int((time.time() - started) * 1000)
    result = parse_sse_done(body)
    page.wait_for_timeout(700)
    meta = {
        "set_text": set_meta,
        "send": send_meta,
        "http_status": response.status,
        "elapsed_ms": elapsed_ms,
        "response_url": response.url,
    }
    return result, meta


def try_quick_double(page) -> dict[str, Any]:
    first_set = set_textarea_text(page, QUICK_DOUBLE[1])
    with page.expect_response(
        lambda response: "/lesson/turn/stream" in response.url and response.request.method == "POST",
        timeout=120_000,
    ) as response_info:
        first = click_send_button(page, wait_until_enabled=True)
    page.wait_for_timeout(80)
    second_set = set_textarea_text(page, QUICK_DOUBLE[2])
    second = click_send_button(page, wait_until_enabled=False)
    stream_result = None
    meta: dict[str, Any] = {
        "first_set_text": first_set,
        "first_send": first,
        "second_set_text": second_set,
        "second_send": second,
    }
    try:
        started = time.time()
        response = response_info.value
        body = response.text()
        stream_result = parse_sse_done(body)
        meta.update({
            "http_status": response.status,
            "elapsed_ms_after_response": int((time.time() - started) * 1000),
            "response_url": response.url,
        })
    except PlaywrightTimeoutError as exc:
        meta["error"] = f"timeout waiting for stream response: {exc}"
    page.wait_for_timeout(700)
    return {
        "scenario": QUICK_DOUBLE[0],
        "result": result_summary(
            stream_result,
            meta.get("elapsed_ms_after_response"),
            read_ui_state(page),
            learner_input=QUICK_DOUBLE[1],
        ),
        "meta": meta,
    }


def page_turn_response(page, page_uid: str, student_id: str, frontend_url: str) -> dict[str, Any]:
    url = f"{frontend_url}/lesson?page_uid={page_uid}&student_id={student_id}"
    started = time.time()
    with page.expect_response(
        lambda response: "/lesson/turn" in response.url
        and "/stream" not in response.url
        and response.request.method == "POST",
        timeout=120_000,
    ) as response_info:
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    response = response_info.value
    elapsed_ms = int((time.time() - started) * 1000)
    payload = response.json()
    page.wait_for_timeout(1000)
    return {
        "result": payload,
        "meta": {
            "http_status": response.status,
            "elapsed_ms": elapsed_ms,
            "response_url": response.url,
        },
    }


def collect_history_files(root: Path, student_prefix: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted((root / "peptutor-mili-teacher").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        snapshot = payload.get("restore_snapshot") if isinstance(payload, dict) else None
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        student_id = ""
        if isinstance(snapshot, dict):
            student_id = str(snapshot.get("studentId") or "")
        runtime_state = snapshot.get("runtimeState") if isinstance(snapshot, dict) else None
        runtime_page = runtime_state.get("current_page_uid") if isinstance(runtime_state, dict) else None
        if not student_id.startswith(student_prefix):
            continue
        raw_messages = (payload.get("raw_chat_session") or {}).get("messages") if isinstance(payload, dict) else []
        dialogue = payload.get("dialogue") if isinstance(payload, dict) else []
        files.append({
            "path": str(path),
            "format": payload.get("format"),
            "metadata_user_id": metadata.get("user_id") if isinstance(metadata, dict) else None,
            "metadata_page_uid": metadata.get("page_uid") if isinstance(metadata, dict) else None,
            "metadata_active": metadata.get("active") if isinstance(metadata, dict) else None,
            "student_id": student_id,
            "snapshot_page_uid": snapshot.get("selectedPageUid") if isinstance(snapshot, dict) else None,
            "runtime_page_uid": runtime_page,
            "raw_message_count": len(raw_messages) if isinstance(raw_messages, list) else None,
            "dialogue_count": len(dialogue) if isinstance(dialogue, list) else None,
            "has_restore_snapshot": isinstance(snapshot, dict),
        })
    return files


def make_issue(issue_id: str, severity: str, page_uid: str, title: str, evidence: str) -> dict[str, str]:
    return {
        "id": issue_id,
        "severity": severity,
        "page_uid": page_uid,
        "title": title,
        "evidence": evidence,
    }


def analyze(report: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for page_result in report["pages"]:
        page_uid = page_result["page_uid"]
        if page_result.get("fatal_error"):
            issues.append(make_issue(
                "S6", "major", page_uid, "browser smoke page failed before completion",
                str(page_result.get("fatal_error"))[:260],
            ))

        turns = []
        initial_turn = page_result.get("initial") or {}
        if isinstance(initial_turn.get("result"), dict):
            turns.append(initial_turn)
        turns.extend(page_result.get("turns") or [])
        for turn in turns:
            result = turn.get("result", {})
            if result.get("fallback_used") is True:
                issues.append(make_issue(
                    "S3", "critical", page_uid, "fallback used in teacher turn",
                    f"{turn.get('scenario', 'initial')}: {result.get('fallback_reason')}",
                ))
            if result.get("rule_fallback_text"):
                issues.append(make_issue(
                    "S2", "major", page_uid, "rule fallback text leaked to visible surface",
                    f"{turn.get('scenario', 'initial')}: {result.get('teacher_response', '')[:160]}",
                ))
            if result.get("generic_praise"):
                issues.append(make_issue(
                    "S3", "minor", page_uid, "generic praise phrase remains in teacher response",
                    f"{turn.get('scenario', 'initial')}: {result.get('teacher_response', '')[:160]}",
                ))
            if result.get("generic_praise_for_short_answer"):
                issues.append(make_issue(
                    "S3", "minor", page_uid, "generic praise for short answer lacks task grounding",
                    f"{turn.get('scenario', 'initial')}: {result.get('teacher_response', '')[:160]}",
                ))

        initial = initial_turn.get("result") or {}
        initial_perf = initial.get("airi_performance") or {}
        initial_ui = initial.get("ui") or {}
        if initial_perf.get("motion") and initial_ui.get("performance_source") in {"未收到", "", "待命"}:
            issues.append(make_issue(
                "S4", "major", page_uid, "backend AIRI performance plan is not reflected in visible runtime state",
                f"backend motion={initial_perf.get('motion')}, expression={initial_perf.get('expression')}; UI performance_source={initial_ui.get('performance_source')}, motion={initial_ui.get('requested_motion')}",
            ))

        tts_statuses = page_result.get("tts_statuses") or []
        if not tts_statuses:
            issues.append(make_issue(
                "S4", "major", page_uid, "TTS provider is configured but no TTS HTTP request was observed",
                f"UI TTS={initial_ui.get('tts')}, runtime TTS configured as peptutor-edge-tts; console may contain autoplay warnings.",
            ))
        else:
            failed_tts_statuses = [
                item
                for item in tts_statuses
                if not (
                    isinstance(item.get("status"), int)
                    and 200 <= item["status"] < 300
                )
            ]
            if failed_tts_statuses and any(item.get("status") == 200 for item in tts_statuses):
                issues.append(make_issue(
                    "S4", "major", page_uid, "TTS HTTP request returned non-2xx",
                    json.dumps(failed_tts_statuses[:3], ensure_ascii=False)[:260],
                ))
        if tts_statuses and not any(item.get("status") == 200 for item in tts_statuses):
            issues.append(make_issue(
                "S4", "major", page_uid, "TTS HTTP request did not return 200",
                json.dumps(tts_statuses[:3], ensure_ascii=False)[:260],
            ))

        diagnostic_playback_states = {
            "play_requested",
            "playing",
            "play_resolved",
            "play_rejected",
            "autoplay_blocked",
            "audio_context_suspended",
            "ended",
            "interrupted",
            "skipped",
        }
        runtime_observations = page_result.get("runtime_observations") or []
        runtime_observation = page_result.get("runtime_observation") or (runtime_observations[-1] if runtime_observations else {})
        observed_playback_states = {
            str(observation.get("tts_playback_state") or "")
            for observation in runtime_observations
        }
        observed_playback_progress = any(
            state in diagnostic_playback_states
            for state in observed_playback_states
        )
        failed_playback_observation = next(
            (
                observation
                for observation in runtime_observations
                if observation.get("tts_playback_state") in {"play_rejected", "autoplay_blocked", "audio_context_suspended"}
            ),
            None,
        )
        mouth_without_playback = [
            observation
            for observation in runtime_observations
            if observation.get("mouth_open_observed")
            and observation.get("tts_playback_state") != "playing"
        ]
        playback_overlap_observation = next(
            (
                observation
                for observation in runtime_observations
                if observation.get("tts_overlap_detected")
            ),
            None,
        )
        if mouth_without_playback:
            issues.append(make_issue(
                "S4", "major", page_uid, "mouthOpen was driven without confirmed TTS playback",
                json.dumps(mouth_without_playback[0], ensure_ascii=False)[:260],
            ))
        if playback_overlap_observation:
            issues.append(make_issue(
                "S4", "major", page_uid, "TTS playback overlap was detected by runtime ownership guard",
                json.dumps({
                    "tts_playback_state": playback_overlap_observation.get("tts_playback_state"),
                    "tts_playback_id": playback_overlap_observation.get("tts_playback_id"),
                    "active_reply_id": playback_overlap_observation.get("active_reply_id"),
                    "tts_overlap_text": playback_overlap_observation.get("tts_overlap_text"),
                    "label": playback_overlap_observation.get("label"),
                }, ensure_ascii=False)[:260],
            ))
        if tts_statuses and not observed_playback_progress:
            issues.append(make_issue(
                "S4", "major", page_uid, "TTS HTTP was observed but runtime playback conclusion was not classified",
                json.dumps(runtime_observation, ensure_ascii=False)[:260],
            ))
        elif failed_playback_observation:
            failed_playback_state = str(failed_playback_observation.get("tts_playback_state") or "")
            issues.append(make_issue(
                "S4", "minor", page_uid, "TTS playback failed with a classified browser/runtime reason",
                json.dumps({
                    "tts_synthesis_state": failed_playback_observation.get("tts_synthesis_state"),
                    "tts_playback_state": failed_playback_state,
                    "tts_playback_state_text": failed_playback_observation.get("tts_playback_state_text"),
                }, ensure_ascii=False)[:260],
            ))
        if (
            initial_perf.get("expression")
            and runtime_observation.get("applied_expression") in {"", "motion-only", "unavailable"}
            and runtime_observation.get("performance_fallback_kind") != "known_capability_gap"
        ):
            issues.append(make_issue(
                "S4", "minor", page_uid, "Live2D expression request was not applied as an expression",
                f"requested={initial_perf.get('expression')} applied={runtime_observation.get('applied_expression')} apply={runtime_observation.get('performance_apply')}",
            ))

        if page_result.get("audio_autoplay_warning"):
            issues.append(make_issue(
                "S4", "minor", page_uid, "browser autoplay policy warning during lesson speech setup",
                page_result["audio_autoplay_warning"][:220],
            ))

        refresh = page_result.get("refresh", {})
        if refresh.get("auto_started_new_turn"):
            issues.append(make_issue(
                "S1", "major", page_uid, "refresh triggered a new page-entry turn instead of pure restore",
                json.dumps(refresh, ensure_ascii=False)[:260],
            ))
        if not refresh.get("after_refresh_turn_ok"):
            issues.append(make_issue(
                "S6", "major", page_uid, "could not continue reliably after refresh",
                json.dumps(refresh, ensure_ascii=False)[:260],
            ))

        quick = next((turn for turn in page_result["turns"] if turn.get("scenario") == "quick_double"), None)
        if quick:
            second_send = ((quick.get("meta") or {}).get("second_send") or {})
            if second_send.get("ok"):
                issues.append(make_issue(
                    "S6", "major", page_uid, "quick double-send accepted a second message while a turn was pending",
                    json.dumps(quick.get("meta"), ensure_ascii=False)[:220],
                ))
            elif second_send.get("reason") == "send_button_missing":
                issues.append(make_issue(
                    "S6", "minor", page_uid, "send button missing during quick double-send attempt",
                    json.dumps(quick.get("meta"), ensure_ascii=False)[:220],
                ))

        if any("6121" in url for url in page_result.get("websockets", [])):
            issues.append(make_issue(
                "S6", "major", page_uid, "unexpected ws://localhost:6121 connection observed",
                ", ".join(page_result.get("websockets", [])),
            ))

    history_files = report.get("history_files", [])
    if history_files:
        local_user_count = sum(1 for item in history_files if item.get("metadata_user_id") == "local")
        if local_user_count:
            issues.append(make_issue(
                "S1", "major", "all", "history metadata user_id is not the lesson student_id",
                f"{local_user_count}/{len(history_files)} new files use metadata.user_id=local and rely on restore_snapshot.studentId for student isolation.",
            ))
        active_count = sum(1 for item in history_files if item.get("metadata_active") is True)
        if active_count > len(PAGES):
            issues.append(make_issue(
                "S1", "minor", "all", "multiple synced history files are marked active",
                f"{active_count}/{len(history_files)} new files have metadata.active=true.",
            ))
        for item in history_files:
            if not item.get("has_restore_snapshot") or not item.get("raw_message_count"):
                issues.append(make_issue(
                    "S1", "major", item.get("metadata_page_uid") or "unknown", "orphan or incomplete lesson history JSON",
                    json.dumps(item, ensure_ascii=False)[:260],
                ))
            if item.get("metadata_page_uid") != item.get("runtime_page_uid"):
                issues.append(make_issue(
                    "S1", "critical", item.get("metadata_page_uid") or "unknown", "mixed-page lesson history JSON",
                    json.dumps(item, ensure_ascii=False)[:260],
                ))

    if report.get("server_history_detail_fetches"):
        mismatches = [
            item for item in report["server_history_detail_fetches"]
            if item.get("student_id") and not str(item.get("student_id")).startswith(report["student_prefix"])
        ]
        if mismatches:
            issues.append(make_issue(
                "S1", "major", "all", "frontend hydrates unrelated server history details for this smoke run",
                f"{len(mismatches)} fetched session payloads belonged to other students; first={json.dumps(mismatches[0], ensure_ascii=False)[:220]}",
            ))

    return issues


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    pages = report.get("pages") or []
    tts_statuses = [
        item
        for page_result in pages
        for item in (page_result.get("tts_statuses") or [])
    ]
    runtime_observations = [
        observation
        for page_result in pages
        for observation in (page_result.get("runtime_observations") or [])
    ]
    issues = report.get("issues") or []
    return {
        "page_count": len(pages),
        "turn_count": sum(
            (1 if (page_result.get("initial") or {}).get("result") else 0)
            + len(page_result.get("turns") or [])
            + (1 if (page_result.get("refresh") or {}).get("after_refresh_turn") else 0)
            for page_result in pages
        ),
        "tts_request_count": len(tts_statuses),
        "tts_http_status_codes": sorted({item.get("status") for item in tts_statuses if item.get("status") is not None}),
        "audio_started_observation_count": sum(1 for item in runtime_observations if item.get("audio_started")),
        "mouth_open_observation_count": sum(1 for item in runtime_observations if item.get("mouth_open_observed")),
        "tts_playback_state_counts": {
            state: sum(1 for item in runtime_observations if item.get("tts_playback_state") == state)
            for state in sorted({str(item.get("tts_playback_state") or "") for item in runtime_observations if item.get("tts_playback_state")})
        },
        "tts_playback_overlap_observation_count": sum(
            1 for item in runtime_observations if item.get("tts_overlap_detected")
        ),
        "tts_playback_stop_reason_counts": {
            reason: sum(1 for item in runtime_observations if item.get("tts_stop_reason") == reason)
            for reason in sorted({
                str(item.get("tts_stop_reason") or "")
                for item in runtime_observations
                if item.get("tts_stop_reason") and item.get("tts_stop_reason") != "none"
            })
        },
        "tts_stop_type_counts": {
            stop_type: sum(1 for item in runtime_observations if item.get("tts_stop_type") == stop_type)
            for stop_type in sorted({
                str(item.get("tts_stop_type") or "")
                for item in runtime_observations
                if item.get("tts_stop_type") and item.get("tts_stop_type") != "none"
            })
        },
        "barge_in_stop_count": sum(
            1 for item in runtime_observations if item.get("tts_stop_type") == "volume_barge_in"
        ),
        "final_transcript_interrupt_count": sum(
            1 for item in runtime_observations if item.get("tts_stop_type") == "final_transcript_interrupt"
        ),
        "finish_current_sentence_defer_count": sum(
            1
            for item in runtime_observations
            if item.get("facts", {}).get("lesson-airi-visible-fact-interrupt_policy") == "finish_current_sentence"
            and item.get("tts_stop_type") in {"", "none"}
            and item.get("tts_playback_state") == "playing"
        ),
        "no_interrupt_count": sum(
            1
            for item in runtime_observations
            if item.get("facts", {}).get("lesson-airi-visible-fact-interrupt_policy") == "no_interrupt"
        ),
        "playback_overlap_count": sum(1 for item in runtime_observations if item.get("tts_overlap_detected")),
        "live2d_expression_known_gap_count": sum(
            1
            for item in runtime_observations
            if item.get("requested_expression")
            and item.get("applied_expression") in {"", "motion-only", "unavailable"}
            and item.get("performance_fallback_kind") == "known_capability_gap"
        ),
        "live2d_expression_unapplied_count": sum(
            1
            for item in runtime_observations
            if item.get("requested_expression")
            and item.get("applied_expression") in {"", "motion-only", "unavailable"}
            and item.get("performance_fallback_kind") != "known_capability_gap"
        ),
        "websocket_6121_seen": any(
            "6121" in url
            for page_result in pages
            for url in (page_result.get("websockets") or [])
        ),
        "fatal_page_count": sum(1 for page_result in pages if page_result.get("fatal_error")),
        "issue_count_by_id": {
            issue_id: sum(1 for item in issues if item.get("id") == issue_id)
            for issue_id in sorted({str(item.get("id")) for item in issues})
        },
        "issue_count_by_severity": {
            severity: sum(1 for item in issues if item.get("severity") == severity)
            for severity in sorted({str(item.get("severity")) for item in issues})
        },
    }


def write_report(
    report: dict[str, Any],
    artifact_dir: Path,
    *,
    history_root: Path,
    student_prefix: str,
    status: str,
) -> Path:
    report["status"] = status
    report["history_files"] = collect_history_files(history_root, student_prefix)
    report["issues"] = analyze(report)
    report["summary"] = summarize_report(report)
    report["updated_at"] = datetime.now().isoformat()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifact_dir / "lesson_deep_smoke_report.json"
    report["report_path"] = str(json_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def run(args: argparse.Namespace) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir) / now_label()
    screenshot_dir = artifact_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    student_prefix = f"deep-smoke-{now_label()}"

    report: dict[str, Any] = {
        "started_at": datetime.now().isoformat(),
        "frontend_url": args.frontend_url,
        "student_prefix": student_prefix,
        "pages": [],
        "server_history_detail_fetches": [],
        "history_files": [],
        "issues": [],
    }

    history_root = Path(args.history_root)
    if sync_playwright is None:
        report["runner_error"] = "playwright is not installed in this Python environment"
        report["finished_at"] = datetime.now().isoformat()
        write_report(
            report,
            artifact_dir,
            history_root=history_root,
            student_prefix=student_prefix,
            status="completed",
        )
        return report

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for page_case in PAGES:
                    page_uid = page_case["page_uid"]
                    student_id = f"{student_prefix}-{page_uid.lower().replace('-', '_')}"
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 900},
                        ignore_https_errors=True,
                    )
                    context.add_init_script(
                        """window.__PEPTUTOR_RUNTIME_CONFIG__ = {
                          ...(window.__PEPTUTOR_RUNTIME_CONFIG__ || {}),
                          VITE_PEPTUTOR_LESSON_API_URL: '/peptutor-api',
                          VITE_PEPTUTOR_TTS_PROVIDER: 'edge-tts',
                          VITE_PEPTUTOR_TTS_MODEL: 'edge-tts',
                          VITE_PEPTUTOR_TTS_VOICE: 'zh-CN-XiaoxiaoNeural',
                        };
                        (() => {
                          if (window.__PEPTUTOR_DEEP_SMOKE_PROBE__) return
                          const probe = {
                            audioPlayCalls: [],
                            audioPlayErrors: [],
                            audioContextEvents: [],
                          }
                          Object.defineProperty(window, '__PEPTUTOR_DEEP_SMOKE_PROBE__', {
                            value: probe,
                            configurable: false,
                          })

                          const originalPlay = window.HTMLMediaElement && window.HTMLMediaElement.prototype.play
                          if (typeof originalPlay === 'function') {
                            window.HTMLMediaElement.prototype.play = function (...args) {
                              const item = {
                                at: new Date().toISOString(),
                                tagName: this.tagName,
                                srcPresent: Boolean(this.currentSrc || this.src),
                                pausedBefore: this.paused,
                                currentTimeBefore: Number.isFinite(this.currentTime) ? this.currentTime : null,
                              }
                              probe.audioPlayCalls.push(item)
                              try {
                                const result = originalPlay.apply(this, args)
                                if (result && typeof result.then === 'function') {
                                  return result.then((value) => {
                                    item.resolved = true
                                    item.pausedAfter = this.paused
                                    item.currentTimeAfter = Number.isFinite(this.currentTime) ? this.currentTime : null
                                    return value
                                  }).catch((error) => {
                                    item.rejected = true
                                    item.error = String(error && (error.message || error))
                                    probe.audioPlayErrors.push(item)
                                    throw error
                                  })
                                }
                                item.resolved = true
                                return result
                              } catch (error) {
                                item.rejected = true
                                item.error = String(error && (error.message || error))
                                probe.audioPlayErrors.push(item)
                                throw error
                              }
                            }
                          }

                          const wrapAudioContext = (name) => {
                            const Original = window[name]
                            if (typeof Original !== 'function') return
                            window[name] = function (...args) {
                              const context = new Original(...args)
                              probe.audioContextEvents.push({
                                event: 'construct',
                                constructor: name,
                                state: context.state,
                                at: new Date().toISOString(),
                              })
                              const originalResume = typeof context.resume === 'function' ? context.resume.bind(context) : null
                              if (originalResume) {
                                context.resume = (...resumeArgs) => {
                                  const event = {
                                    event: 'resume',
                                    before: context.state,
                                    at: new Date().toISOString(),
                                  }
                                  probe.audioContextEvents.push(event)
                                  return originalResume(...resumeArgs).then((value) => {
                                    event.after = context.state
                                    event.resolved = true
                                    return value
                                  }).catch((error) => {
                                    event.after = context.state
                                    event.rejected = true
                                    event.error = String(error && (error.message || error))
                                    throw error
                                  })
                                }
                              }
                              return context
                            }
                            window[name].prototype = Original.prototype
                          }
                          wrapAudioContext('AudioContext')
                          wrapAudioContext('webkitAudioContext')
                        })();"""
                    )
                    page = context.new_page()

                    console_messages: list[dict[str, str]] = []
                    request_failures: list[dict[str, str]] = []
                    network_events: list[dict[str, Any]] = []
                    tts_statuses: list[dict[str, Any]] = []
                    websockets: list[str] = []
                    history_detail_fetches: list[dict[str, Any]] = []
                    auto_turns_after_refresh: list[str] = []

                    def on_console(message):
                        text = message.text
                        if message.type in {"error", "warning"}:
                            console_messages.append({"type": message.type, "text": text})

                    def on_request(request):
                        if is_relevant_network_url(request.url):
                            append_limited(network_events, {
                                "event": "request",
                                "url": request.url,
                                "method": request.method,
                                "resource_type": request.resource_type,
                            })

                    def on_request_failed(request):
                        failure = request.failure
                        item = {
                            "url": request.url,
                            "method": request.method,
                            "failure": failure or "",
                        }
                        request_failures.append(item)
                        append_limited(network_events, {"event": "requestfailed", **item})

                    def on_response(response):
                        url = response.url
                        if is_relevant_network_url(url):
                            append_limited(network_events, {
                                "event": "response",
                                "url": url,
                                "method": response.request.method,
                                "status": response.status,
                                "content_type": response.headers.get("content-type", ""),
                            })
                        if "tts" in url.lower():
                            tts_statuses.append({
                                "url": url,
                                "status": response.status,
                                "content_type": response.headers.get("content-type", ""),
                            })
                        if "/lesson/chat-history/sessions/" in url:
                            try:
                                payload = response.json()
                                snapshot = payload.get("restore_snapshot") if isinstance(payload, dict) else {}
                                runtime = snapshot.get("runtimeState") if isinstance(snapshot, dict) else {}
                                item = {
                                    "url": url,
                                    "status": response.status,
                                    "student_id": snapshot.get("studentId") if isinstance(snapshot, dict) else None,
                                    "page_uid": runtime.get("current_page_uid") if isinstance(runtime, dict) else None,
                                }
                                history_detail_fetches.append(item)
                                report["server_history_detail_fetches"].append(item)
                            except Exception:
                                history_detail_fetches.append({
                                    "url": url,
                                    "status": response.status,
                                    "parse_error": True,
                                })

                    page.on("console", on_console)
                    page.on("request", on_request)
                    page.on("requestfailed", on_request_failed)
                    page.on("response", on_response)
                    page.on("websocket", lambda websocket: websockets.append(websocket.url))

                    page_result: dict[str, Any] = {
                        **page_case,
                        "student_id": student_id,
                        "initial": {},
                        "turns": [],
                        "refresh": {},
                        "console_messages": console_messages,
                        "request_failures": request_failures,
                        "network_events": network_events,
                        "tts_statuses": tts_statuses,
                        "websockets": websockets,
                        "history_detail_fetches": history_detail_fetches,
                        "runtime_observations": [],
                    }

                    try:
                        with timeout_scope(args.page_timeout_seconds, page_uid):
                            initial = page_turn_response(page, page_uid, student_id, args.frontend_url)
                            page_result["initial"] = {
                                "scenario": "page_entry",
                                "result": result_summary(
                                    initial["result"],
                                    initial["meta"].get("elapsed_ms"),
                                    read_ui_state(page),
                                    learner_input=None,
                                ),
                                "meta": initial["meta"],
                            }
                            append_runtime_observation(page_result, page, "after_page_entry")

                            for scenario, text in SCENARIOS:
                                try:
                                    stream_result, meta = run_stream_turn(page, text)
                                    page_result["turns"].append({
                                        "scenario": scenario,
                                        "input": text,
                                        "result": result_summary(
                                            stream_result,
                                            meta.get("elapsed_ms"),
                                            read_ui_state(page),
                                            learner_input=text,
                                        ),
                                        "meta": meta,
                                    })
                                    append_runtime_observation(page_result, page, f"after_{scenario}")
                                except Exception as exc:
                                    page_result["turns"].append({
                                        "scenario": scenario,
                                        "input": text,
                                        "error": repr(exc),
                                        "result": result_summary(
                                            None,
                                            None,
                                            read_ui_state(page),
                                            learner_input=text,
                                        ),
                                    })
                                    append_runtime_observation(page_result, page, f"after_{scenario}_error")

                            page_result["turns"].append(try_quick_double(page))
                            append_runtime_observation(page_result, page, "after_quick_double")

                            before_refresh_text = body_text(page)
                            before_refresh_teacher_count = before_refresh_text.count("米粒")
                            turn_count_before_refresh = len([
                                turn for turn in page_result["turns"]
                                if not turn.get("error") and (turn.get("result") or {}).get("turn_label")
                            ])
                            page.on(
                                "response",
                                lambda response: auto_turns_after_refresh.append(response.url)
                                if "/lesson/turn" in response.url and response.request.method == "POST"
                                else None,
                            )
                            page.reload(wait_until="domcontentloaded", timeout=90_000)
                            page.wait_for_timeout(7000)
                            append_runtime_observation(page_result, page, "after_refresh_reload")
                            after_refresh_text = body_text(page)
                            page_result["refresh"] = {
                                "teacher_marker_count_before": before_refresh_teacher_count,
                                "teacher_marker_count_after": after_refresh_text.count("米粒"),
                                "auto_started_new_turn": any("/lesson/turn" in url for url in auto_turns_after_refresh),
                                "auto_turn_urls": auto_turns_after_refresh,
                                "ui": read_ui_state(page),
                            }
                            try:
                                stream_result, meta = run_stream_turn(page, AFTER_REFRESH[1])
                                page_result["refresh"]["after_refresh_turn_ok"] = bool(stream_result)
                                page_result["refresh"]["after_refresh_turn"] = result_summary(
                                    stream_result,
                                    meta.get("elapsed_ms"),
                                    read_ui_state(page),
                                    learner_input=AFTER_REFRESH[1],
                                )
                                page_result["refresh"]["after_refresh_meta"] = meta
                                append_runtime_observation(page_result, page, "after_refresh_turn")
                            except Exception as exc:
                                page_result["refresh"]["after_refresh_turn_ok"] = False
                                page_result["refresh"]["after_refresh_error"] = repr(exc)
                                append_runtime_observation(page_result, page, "after_refresh_turn_error")

                            screenshot_path = screenshot_dir / f"{page_uid}.png"
                            page.screenshot(path=str(screenshot_path), full_page=True)
                            page_result["screenshot"] = str(screenshot_path)
                            page_result["audio_autoplay_warning"] = next(
                                (
                                    item["text"]
                                    for item in console_messages
                                    if "AudioContext was not allowed to start" in item["text"]
                                ),
                                "",
                            )
                            page_result["turn_count_before_refresh"] = turn_count_before_refresh
                    except Exception as exc:
                        page_result["fatal_error"] = repr(exc)
                        append_runtime_observation(page_result, page, "fatal_error")
                        try:
                            screenshot_path = screenshot_dir / f"{page_uid}-fatal.png"
                            page.screenshot(path=str(screenshot_path), full_page=True)
                            page_result["screenshot"] = str(screenshot_path)
                        except Exception:
                            pass
                    finally:
                        report["pages"].append(page_result)
                        write_report(
                            report,
                            artifact_dir,
                            history_root=history_root,
                            student_prefix=student_prefix,
                            status="partial",
                        )
                        try:
                            context.close()
                        except Exception as exc:
                            page_result["context_close_error"] = repr(exc)
                            write_report(
                                report,
                                artifact_dir,
                                history_root=history_root,
                                student_prefix=student_prefix,
                                status="partial",
                            )
            finally:
                try:
                    browser.close()
                except Exception as exc:
                    report["browser_close_error"] = repr(exc)
                    write_report(
                        report,
                        artifact_dir,
                        history_root=history_root,
                        student_prefix=student_prefix,
                        status="partial",
                    )
    except Exception as exc:
        report["runner_error"] = repr(exc)
        write_report(
            report,
            artifact_dir,
            history_root=history_root,
            student_prefix=student_prefix,
            status="partial",
        )

    report["finished_at"] = datetime.now().isoformat()
    write_report(
        report,
        artifact_dir,
        history_root=history_root,
        student_prefix=student_prefix,
        status="completed",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-url", default="http://127.0.0.1:5173")
    parser.add_argument("--history-root", default="chat_history")
    parser.add_argument("--artifact-dir", default="temp/lesson-smoke-artifacts")
    parser.add_argument("--page-timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    report = run(args)
    summary = report.get("summary", {})
    print(json.dumps({
        "report_path": report["report_path"],
        "page_count": summary.get("page_count", len(report["pages"])),
        "turn_count": summary.get("turn_count", sum(1 + len(page.get("turns", [])) for page in report["pages"])),
        "history_file_count": len(report["history_files"]),
        "summary": summary,
        "issues": report["issues"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
