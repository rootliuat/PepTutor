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

from lightrag.api.utils_api import get_combined_auth_dependency


_SAFE_PATH_PART_RE = re.compile(r"[^A-Za-z0-9._-]+")


class LessonChatHistorySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    user_id: str = Field(default="local", min_length=1)
    character_id: str = Field(default="lesson", min_length=1)
    title: Optional[str] = None
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    active: bool = False
    page_uid: Optional[str] = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    runtime_snapshot: dict[str, Any] | None = None


class LessonChatHistorySessionSummary(BaseModel):
    session_id: str
    user_id: str
    character_id: str
    title: str | None = None
    created_at: int
    updated_at: int
    active: bool = False
    page_uid: str | None = None
    message_count: int
    path: str


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


def _compact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system" or role not in {"assistant", "user", "error"}:
            continue
        content = _coerce_text(_message_content(message), max_chars=2_000)
        if not content:
            continue
        compacted_message: dict[str, Any] = {
            "role": role,
            "content": content,
        }
        if isinstance(message.get("id"), str) and message["id"].strip():
            compacted_message["id"] = message["id"].strip()
        created_at = message.get("createdAt")
        if isinstance(created_at, int | float):
            compacted_message["createdAt"] = int(created_at)
        compacted.append(compacted_message)
    return compacted


def _compact_recent_turns(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    compacted: list[dict[str, str | None]] = []
    for item in value[-3:]:
        if not isinstance(item, dict):
            continue
        compacted.append(
            {
                "turn_label": _coerce_text(item.get("turn_label"), max_chars=64),
                "teacher_text": _coerce_text(item.get("teacher_text"), max_chars=600)
                or None,
                "learner_text": _coerce_text(item.get("learner_text"), max_chars=400)
                or None,
            }
        )
    return compacted


def _compact_runtime_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    state = dict(value)
    state["last_teacher_question"] = (
        _coerce_text(state.get("last_teacher_question"), max_chars=500) or None
    )
    state["recent_turns"] = _compact_recent_turns(state.get("recent_turns"))
    return state


def _compact_active_turn(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    turn = dict(value)
    turn["teacher_response"] = _coerce_text(
        turn.get("teacher_response"), max_chars=2_000
    )
    turn["state"] = _compact_runtime_state(turn.get("state"))
    return turn


def _compact_transcript(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    transcript: list[dict[str, Any]] = []
    for entry in value[-16:]:
        if not isinstance(entry, dict):
            continue
        compacted = dict(entry)
        compacted["text"] = _coerce_text(compacted.get("text"), max_chars=1_000)
        transcript.append(compacted)
    return transcript


def _compact_runtime_snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "version": value.get("version", 1),
        "selectedPageUid": value.get("selectedPageUid"),
        "studentId": value.get("studentId"),
        "runtimeState": _compact_runtime_state(value.get("runtimeState")),
        "activeTurn": _compact_active_turn(value.get("activeTurn")),
        "transcript": _compact_transcript(value.get("transcript")),
        "updatedAt": value.get("updatedAt"),
    }


def _build_history_payload(request: LessonChatHistorySessionRequest) -> dict[str, Any]:
    return {
        "format": "peptutor-chat-history:v1",
        "metadata": {
            "session_id": request.session_id,
            "user_id": request.user_id,
            "character_id": request.character_id,
            "title": request.title,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "active": request.active,
            "page_uid": request.page_uid,
        },
        "runtime_snapshot": _compact_runtime_snapshot(request.runtime_snapshot),
        "messages": _compact_messages(request.messages),
    }


def _read_history_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") != "peptutor-chat-history:v1":
        return None
    return payload


def _session_summary(path: Path, payload: dict[str, Any], root: Path) -> LessonChatHistorySessionSummary | None:
    metadata = payload.get("metadata")
    messages = payload.get("messages")
    if not isinstance(metadata, dict) or not isinstance(messages, list):
        return None
    session_id = str(metadata.get("session_id") or "").strip()
    if not session_id:
        return None
    return LessonChatHistorySessionSummary(
        session_id=session_id,
        user_id=str(metadata.get("user_id") or "local"),
        character_id=str(metadata.get("character_id") or "lesson"),
        title=metadata.get("title") if isinstance(metadata.get("title"), str) else None,
        created_at=int(metadata.get("created_at") or 0),
        updated_at=int(metadata.get("updated_at") or 0),
        active=bool(metadata.get("active")),
        page_uid=metadata.get("page_uid") if isinstance(metadata.get("page_uid"), str) else None,
        message_count=len(messages),
        path=str(path.relative_to(root)),
    )


def _iter_history_files(root: Path):
    if not root.exists():
        return
    yield from root.glob("*/*.json")


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
    ) -> list[LessonChatHistorySessionSummary]:
        root = _repo_chat_history_dir()
        summaries: list[LessonChatHistorySessionSummary] = []
        for path in _iter_history_files(root):
            payload = _read_history_file(path)
            if payload is None:
                continue
            summary = _session_summary(path, payload, root)
            if summary is None:
                continue
            if character_id and summary.character_id != character_id:
                continue
            summaries.append(summary)
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    @router.get(
        "/sessions/{session_id}",
        dependencies=[Depends(combined_auth)],
    )
    async def get_lesson_chat_history_session(session_id: str) -> dict[str, Any]:
        root = _repo_chat_history_dir()
        safe_session_id = _safe_path_part(session_id, "")
        if not safe_session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        for path in _iter_history_files(root):
            if not path.name.endswith(f"_{safe_session_id}.json"):
                continue
            payload = _read_history_file(path)
            if payload is not None:
                return payload
        raise HTTPException(status_code=404, detail="chat history session not found")

    return router
