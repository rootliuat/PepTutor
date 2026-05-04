"""File-backed PepTutor lesson chat history endpoints."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from lightrag.api.lesson_chat_history_audit import (
    audit_chat_history_payload,
    build_chat_history_audit_report,
    write_chat_history_audit_report,
)
from lightrag.api.utils_api import get_combined_auth_dependency


_SAFE_PATH_PART_RE = re.compile(r"[^A-Za-z0-9._-]+")


class LessonChatHistorySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    user_id: str = Field(default="local", min_length=1)
    student_id: Optional[str] = None
    character_id: str = Field(default="lesson", min_length=1)
    title: Optional[str] = None
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    active: bool = False
    page_uid: Optional[str] = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    raw_chat_session: dict[str, Any] | None = None
    runtime_snapshot: dict[str, Any] | None = None


class LessonChatHistorySessionSummary(BaseModel):
    session_id: str
    user_id: str
    student_id: str | None = None
    character_id: str
    title: str | None = None
    preview: str | None = None
    created_at: int
    updated_at: int
    active: bool = False
    page_uid: str | None = None
    message_count: int
    path: str
    history_format: str = "unknown"
    audit_status: str = "legacy_readonly"
    audit_reason: str | None = None
    audit_warnings: list[str] = Field(default_factory=list)
    message_page_ownership: str = "none"
    restore_safety: str = "none"
    safe_to_migrate: bool = False
    history_access: str = "read_only"


class LessonChatHistorySyncResponse(BaseModel):
    session_id: str
    path: str
    directory: str


def _repo_chat_history_dir() -> Path:
    env_path = os.getenv("PEPTUTOR_CHAT_HISTORY_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        if (ancestor / "backend" / "LightRAG").exists() and (
            ancestor / "frontend" / "airi"
        ).exists():
            return (ancestor / "chat_history").resolve()

    return (Path.cwd() / "chat_history").resolve()


def _safe_path_part(value: str, default: str) -> str:
    normalized = _SAFE_PATH_PART_RE.sub("_", value.strip())[:96].strip("._-")
    return normalized or default


def _timestamp_label(milliseconds: int) -> str:
    seconds = milliseconds / 1000 if milliseconds > 10_000_000_000 else milliseconds
    try:
        return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d_%H-%M-%S")
    except (OverflowError, OSError, ValueError):
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _session_path(root: Path, request: LessonChatHistorySessionRequest) -> Path:
    character_dir = root / _safe_path_part(request.character_id, "lesson")
    timestamp = _timestamp_label(request.created_at)
    session_id = _safe_path_part(request.session_id, "session")
    return character_dir / f"{timestamp}_{session_id}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _coerce_text(value: Any, *, max_chars: int) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = ""
    text = " ".join(text.split())
    if len(text) > max_chars:
        return f"{text[:max_chars]}..."
    return text


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    slices = message.get("slices")
    if isinstance(slices, list):
        return "".join(
            slice_item.get("text", "")
            for slice_item in slices
            if isinstance(slice_item, dict) and isinstance(slice_item.get("text"), str)
        )
    return ""


def _dialogue_speaker(role: str) -> str:
    if role == "assistant":
        return "米粒"
    if role == "user":
        return "学生"
    return "系统"


def _compact_dialogue(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dialogue: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system" or role not in {"assistant", "user", "error"}:
            continue
        text = _coerce_text(_message_content(message), max_chars=2_000)
        if not text:
            continue
        entry: dict[str, Any] = {
            "speaker": _dialogue_speaker(str(role)),
            "role": role,
            "text": text,
        }
        created_at = message.get("createdAt")
        if isinstance(created_at, int | float):
            entry["created_at"] = int(created_at)
        dialogue.append(entry)
    return dialogue


def _raw_chat_messages(request: LessonChatHistorySessionRequest) -> list[dict[str, Any]]:
    raw_messages: Any = None
    if isinstance(request.raw_chat_session, dict):
        raw_messages = request.raw_chat_session.get("messages")
    if not isinstance(raw_messages, list):
        raw_messages = request.messages

    messages: list[dict[str, Any]] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "system" or role not in {"assistant", "user", "error", "tool"}:
            continue
        next_message = dict(message)
        next_message.pop("context", None)
        messages.append(next_message)
    return messages


def _compact_runtime_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    state = dict(value)
    state["last_teacher_question"] = (
        _coerce_text(state.get("last_teacher_question"), max_chars=500) or None
    )
    state.pop("recent_turns", None)
    return state


def _compact_runtime_snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "version": value.get("version", 1),
        "selectedPageUid": value.get("selectedPageUid"),
        "studentId": value.get("studentId"),
        "runtimeState": _compact_runtime_state(value.get("runtimeState")),
        "updatedAt": value.get("updatedAt"),
    }


def _runtime_snapshot_student_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    runtime_state = value.get("runtimeState")
    runtime_student_id = (
        runtime_state.get("student_id")
        if isinstance(runtime_state, dict)
        else None
    )
    if isinstance(runtime_student_id, str) and runtime_student_id.strip():
        return runtime_student_id.strip()
    snapshot_student_id = value.get("studentId")
    return snapshot_student_id.strip() if isinstance(snapshot_student_id, str) else ""


def _runtime_snapshot_page_uid(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    runtime_state = value.get("runtimeState")
    runtime_page_uid = (
        runtime_state.get("current_page_uid")
        if isinstance(runtime_state, dict)
        else None
    )
    if isinstance(runtime_page_uid, str) and runtime_page_uid.strip():
        return runtime_page_uid.strip()
    snapshot_page_uid = value.get("selectedPageUid")
    return snapshot_page_uid.strip() if isinstance(snapshot_page_uid, str) else ""


def _payload_restore_snapshot(payload: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = payload.get("restore_snapshot") or payload.get("runtime_snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def _payload_student_id(payload: dict[str, Any]) -> str:
    snapshot_student_id = _runtime_snapshot_student_id(_payload_restore_snapshot(payload))
    if snapshot_student_id:
        return snapshot_student_id
    metadata = payload.get("metadata")
    metadata_student_id = (
        metadata.get("student_id")
        if isinstance(metadata, dict)
        else None
    )
    if isinstance(metadata_student_id, str) and metadata_student_id.strip():
        return metadata_student_id.strip()
    metadata_user_id = (
        metadata.get("user_id")
        if isinstance(metadata, dict)
        else None
    )
    if isinstance(metadata_user_id, str) and metadata_user_id.strip() != "local":
        return metadata_user_id.strip()
    return ""


def _payload_page_uid(payload: dict[str, Any]) -> str:
    snapshot_page_uid = _runtime_snapshot_page_uid(_payload_restore_snapshot(payload))
    if snapshot_page_uid:
        return snapshot_page_uid
    metadata = payload.get("metadata")
    metadata_page_uid = (
        metadata.get("page_uid")
        if isinstance(metadata, dict)
        else None
    )
    return metadata_page_uid.strip() if isinstance(metadata_page_uid, str) else ""


def _history_student_identity_is_restorable(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return False
    metadata_student_id = str(metadata.get("student_id") or "").strip()
    metadata_user_id = str(metadata.get("user_id") or "").strip()
    metadata_identity = metadata_student_id or (
        metadata_user_id if metadata_user_id != "local" else ""
    )
    snapshot = _payload_restore_snapshot(payload)
    snapshot_student_id = _runtime_snapshot_student_id(snapshot)
    if not snapshot_student_id:
        return False
    return metadata_identity == snapshot_student_id


def _request_student_id(request: LessonChatHistorySessionRequest) -> str:
    restore_snapshot = _compact_runtime_snapshot(request.runtime_snapshot)
    snapshot_student_id = _runtime_snapshot_student_id(restore_snapshot)
    request_student_id = (
        request.student_id.strip()
        if isinstance(request.student_id, str)
        else ""
    )
    request_user_id = request.user_id.strip()
    if request_student_id:
        return request_student_id
    if snapshot_student_id and request_user_id in {"", "local"}:
        return snapshot_student_id
    return request_user_id or snapshot_student_id or "local"


def _build_history_payload(request: LessonChatHistorySessionRequest) -> dict[str, Any]:
    restore_snapshot = _compact_runtime_snapshot(request.runtime_snapshot)
    raw_messages = _raw_chat_messages(request)
    student_id = _request_student_id(request)
    return {
        "format": "peptutor-chat-history:v3",
        "metadata": {
            "session_id": request.session_id,
            "user_id": student_id,
            "student_id": student_id,
            "character_id": request.character_id,
            "title": request.title,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "active": request.active,
            "page_uid": request.page_uid,
        },
        "raw_chat_session": {
            "messages": raw_messages,
        },
        "restore_snapshot": restore_snapshot,
        "dialogue": _compact_dialogue(raw_messages),
    }


def _read_history_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") not in {
        "peptutor-chat-history:v1",
        "peptutor-chat-history:v2",
        "peptutor-chat-history:v3",
    }:
        return None
    return payload


def _history_access_from_audit(audit: dict[str, Any], payload: dict[str, Any]) -> str:
    if (
        audit.get("format") == "peptutor-chat-history:v3"
        and audit.get("status") == "clean"
        and audit.get("restore_safety") == "block"
    ):
        return "continue" if _history_student_identity_is_restorable(payload) else "read_only"
    if audit.get("status") in {"legacy_readonly", "repairable"}:
        return "read_only"
    return "view_only"


def _session_summary(
    path: Path,
    payload: dict[str, Any],
    root: Path,
) -> LessonChatHistorySessionSummary | None:
    metadata = payload.get("metadata")
    messages = payload.get("messages")
    dialogue = payload.get("dialogue")
    if not isinstance(metadata, dict):
        return None
    message_count = len(dialogue) if isinstance(dialogue, list) else (
        len(messages) if isinstance(messages, list) else 0
    )
    session_id = str(metadata.get("session_id") or "").strip()
    if not session_id:
        return None
    preview = None
    if isinstance(dialogue, list):
        for entry in dialogue:
            if isinstance(entry, dict):
                preview_text = _coerce_text(entry.get("text"), max_chars=80)
                if preview_text:
                    preview = preview_text
                    break
    elif isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                preview_text = _coerce_text(_message_content(message), max_chars=80)
                if preview_text:
                    preview = preview_text
                    break
    audit = audit_chat_history_payload(path, payload, root)
    return LessonChatHistorySessionSummary(
        session_id=session_id,
        user_id=str(metadata.get("user_id") or "local"),
        student_id=_payload_student_id(payload) or None,
        character_id=str(metadata.get("character_id") or "lesson"),
        title=metadata.get("title") if isinstance(metadata.get("title"), str) else None,
        preview=preview,
        created_at=int(metadata.get("created_at") or 0),
        updated_at=int(metadata.get("updated_at") or 0),
        active=bool(metadata.get("active")),
        page_uid=metadata.get("page_uid") if isinstance(metadata.get("page_uid"), str) else None,
        message_count=message_count,
        path=str(path.relative_to(root)),
        history_format=str(audit.get("format") or "unknown"),
        audit_status=str(audit.get("status") or "legacy_readonly"),
        audit_reason=(
            str(audit.get("reason"))
            if isinstance(audit.get("reason"), str)
            else None
        ),
        audit_warnings=[
            str(warning)
            for warning in audit.get("warnings", [])
            if isinstance(warning, str)
        ],
        message_page_ownership=str(audit.get("message_page_ownership") or "none"),
        restore_safety=str(audit.get("restore_safety") or "none"),
        safe_to_migrate=bool(audit.get("safe_to_migrate")),
        history_access=_history_access_from_audit(audit, payload),
    )


def _iter_history_files(root: Path):
    if not root.exists():
        return
    yield from root.glob("*/*.json")


def _payload_matches_filter(
    payload: dict[str, Any],
    *,
    character_id: str | None = None,
    student_id: str | None = None,
    page_uid: str | None = None,
) -> bool:
    normalized_character_id = character_id.strip() if isinstance(character_id, str) else ""
    normalized_student_id = student_id.strip() if isinstance(student_id, str) else ""
    normalized_page_uid = page_uid.strip() if isinstance(page_uid, str) else ""
    if normalized_character_id:
        metadata = payload.get("metadata")
        metadata_character_id = (
            metadata.get("character_id")
            if isinstance(metadata, dict)
            else None
        )
        if not isinstance(metadata_character_id, str):
            return False
        if metadata_character_id.strip() != normalized_character_id:
            return False
    if normalized_student_id and _payload_student_id(payload) != normalized_student_id:
        return False
    if normalized_page_uid and _payload_page_uid(payload) != normalized_page_uid:
        return False
    return True


def create_lesson_chat_history_routes(api_key: Optional[str] = None) -> APIRouter:
    router = APIRouter(prefix="/lesson/chat-history", tags=["lesson-chat-history"])
    combined_auth = get_combined_auth_dependency(api_key)

    @router.post(
        "/session",
        response_model=LessonChatHistorySyncResponse,
        dependencies=[Depends(combined_auth)],
    )
    async def sync_lesson_chat_history_session(
        request: LessonChatHistorySessionRequest,
    ) -> LessonChatHistorySyncResponse:
        root = _repo_chat_history_dir()
        path = _session_path(root, request)
        _atomic_write_json(path, _build_history_payload(request))
        return LessonChatHistorySyncResponse(
            session_id=request.session_id,
            path=str(path),
            directory=str(root),
        )

    @router.get(
        "/sessions",
        response_model=list[LessonChatHistorySessionSummary],
        dependencies=[Depends(combined_auth)],
    )
    async def list_lesson_chat_history_sessions(
        character_id: str | None = None,
        student_id: str | None = None,
        page_uid: str | None = None,
    ) -> list[LessonChatHistorySessionSummary]:
        root = _repo_chat_history_dir()
        summaries: list[LessonChatHistorySessionSummary] = []
        for path in _iter_history_files(root):
            payload = _read_history_file(path)
            if payload is None:
                continue
            if not _payload_matches_filter(
                payload,
                student_id=student_id,
                page_uid=page_uid,
            ):
                continue
            summary = _session_summary(path, payload, root)
            if summary is None:
                continue
            if character_id and summary.character_id != character_id:
                continue
            summaries.append(summary)
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    @router.get(
        "/audit",
        dependencies=[Depends(combined_auth)],
    )
    async def audit_lesson_chat_history_sessions(
        character_id: str | None = None,
        write_report: bool = False,
    ) -> dict[str, Any]:
        root = _repo_chat_history_dir()
        report = build_chat_history_audit_report(root, character_id=character_id)
        if write_report:
            report["report_path"] = str(write_chat_history_audit_report(root, report))
        return report

    @router.get(
        "/sessions/{session_id}",
        dependencies=[Depends(combined_auth)],
    )
    async def get_lesson_chat_history_session(
        session_id: str,
        character_id: str | None = None,
        student_id: str | None = None,
        page_uid: str | None = None,
    ) -> dict[str, Any]:
        root = _repo_chat_history_dir()
        safe_session_id = _safe_path_part(session_id, "")
        if not safe_session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        for path in _iter_history_files(root):
            if not path.name.endswith(f"_{safe_session_id}.json"):
                continue
            payload = _read_history_file(path)
            if payload is not None and _payload_matches_filter(
                payload,
                character_id=character_id,
                student_id=student_id,
                page_uid=page_uid,
            ):
                return payload
        raise HTTPException(status_code=404, detail="chat history session not found")

    return router
