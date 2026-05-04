"""Read-only safety audit for PepTutor lesson chat history files."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CHAT_HISTORY_AUDIT_FORMAT = "peptutor-chat-history-audit:v1"

_PAGE_UID_RE = re.compile(r"\b(TB-[A-Za-z0-9]+-P\d+)\b")
_SAFE_PATH_PART_RE = re.compile(r"[^A-Za-z0-9._-]+")
_TIMESTAMPED_SESSION_FILE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(?P<session_id>.+)$"
)
_SUPPORTED_HISTORY_FORMATS = {
    "peptutor-chat-history:v1",
    "peptutor-chat-history:v2",
    "peptutor-chat-history:v3",
}
_TEXT_KEYS = {
    "content",
    "dialogue",
    "preview",
    "reasoning",
    "speech",
    "text",
    "title",
}


def _utc_timestamp_label() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")


def _safe_path_part(value: str, default: str) -> str:
    normalized = _SAFE_PATH_PART_RE.sub("_", value.strip())[:96].strip("._-")
    return normalized or default


def _page_uid_from_string(value: str) -> str | None:
    match = _PAGE_UID_RE.search(value)
    return match.group(1) if match else None


def _page_uids_from_structural_value(value: Any, *, parent_key: str = "") -> set[str]:
    """Extract explicit page UIDs from structural metadata, not free-form text."""

    if isinstance(value, dict):
        pages: set[str] = set()
        for key, child in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower in _TEXT_KEYS:
                continue
            pages.update(_page_uids_from_structural_value(child, parent_key=key_text))
        return pages

    if isinstance(value, list):
        pages: set[str] = set()
        for item in value:
            pages.update(_page_uids_from_structural_value(item, parent_key=parent_key))
        return pages

    if not isinstance(value, str):
        return set()

    key_lower = parent_key.lower()
    is_structural_uid = (
        "page" in key_lower
        or "block" in key_lower
        or key_lower.endswith("uid")
    )
    if not is_structural_uid:
        return set()
    page_uid = _page_uid_from_string(value)
    return {page_uid} if page_uid else set()


def _history_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    format_name = payload.get("format")
    if format_name == "peptutor-chat-history:v3":
        raw_chat_session = payload.get("raw_chat_session")
        messages = (
            raw_chat_session.get("messages")
            if isinstance(raw_chat_session, dict)
            else None
        )
    elif format_name == "peptutor-chat-history:v2":
        messages = payload.get("dialogue")
    else:
        messages = payload.get("messages")

    if not isinstance(messages, list):
        return []
    return [item for item in messages if isinstance(item, dict)]


def _visible_message_count(messages: list[dict[str, Any]]) -> int:
    count = 0
    for message in messages:
        role = str(message.get("role") or "")
        speaker = str(message.get("speaker") or "")
        if role in {"assistant", "user", "error", "tool"} or speaker:
            count += 1
    return count


def _session_page_uids(payload: dict[str, Any]) -> set[str]:
    metadata = payload.get("metadata")
    snapshot = payload.get("restore_snapshot") or payload.get("runtime_snapshot")
    pages: set[str] = set()
    if isinstance(metadata, dict):
        pages.update(_page_uids_from_structural_value(metadata))
    if isinstance(snapshot, dict):
        pages.update(_page_uids_from_structural_value(snapshot))
    return pages


def _message_page_sets(messages: list[dict[str, Any]]) -> list[set[str]]:
    return [_page_uids_from_structural_value(message) for message in messages]


def _status_for_history(
    *,
    detected_pages: set[str],
    messages: list[dict[str, Any]],
    message_pages: list[set[str]],
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if not detected_pages:
        return (
            "legacy_readonly",
            "no explicit page_uid or block_uid was found",
            ["missing page identity; runtime restore is unsafe"],
        )

    messages_without_page = sum(1 for pages in message_pages if not pages)
    messages_with_multiple_pages = sum(1 for pages in message_pages if len(pages) > 1)

    if messages_without_page:
        warnings.append(
            "some messages lack message-level page evidence; safe splitting is impossible",
        )
    if messages_with_multiple_pages:
        warnings.append(
            "some messages contain multiple explicit page identities",
        )

    if len(detected_pages) == 1:
        if messages_without_page:
            return (
                "clean",
                "single explicit page identity found; message ownership is unverified",
                warnings,
            )
        return ("clean", "single explicit page identity found", warnings)

    if messages and messages_without_page == 0 and messages_with_multiple_pages == 0:
        return (
            "repairable",
            "multiple explicit pages found and every message has one page owner",
            warnings,
        )

    return (
        "legacy_readonly",
        "multiple explicit pages found but message ownership is incomplete",
        warnings,
    )


def _message_page_ownership(message_pages: list[set[str]]) -> str:
    if not message_pages:
        return "none"
    messages_without_page = sum(1 for pages in message_pages if not pages)
    messages_with_multiple_pages = sum(1 for pages in message_pages if len(pages) > 1)
    if messages_with_multiple_pages:
        return "conflicting"
    if messages_without_page == len(message_pages):
        return "missing"
    if messages_without_page:
        return "partial"
    return "complete"


def _restore_safety(payload: dict[str, Any]) -> str:
    snapshot = payload.get("restore_snapshot") or payload.get("runtime_snapshot")
    if not isinstance(snapshot, dict):
        return "none"
    runtime_state = snapshot.get("runtimeState")
    if isinstance(runtime_state, dict):
        return "block"
    if _page_uids_from_structural_value(snapshot):
        return "page"
    return "none"


def _snapshot_student_id(payload: dict[str, Any]) -> str:
    snapshot = payload.get("restore_snapshot") or payload.get("runtime_snapshot")
    if not isinstance(snapshot, dict):
        return ""
    runtime_state = snapshot.get("runtimeState")
    runtime_student_id = (
        runtime_state.get("student_id")
        if isinstance(runtime_state, dict)
        else None
    )
    if isinstance(runtime_student_id, str) and runtime_student_id.strip():
        return runtime_student_id.strip()
    snapshot_student_id = snapshot.get("studentId")
    return snapshot_student_id.strip() if isinstance(snapshot_student_id, str) else ""


def _student_identity_audit(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_user_id = (
        str(metadata.get("user_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    metadata_student_id = (
        str(metadata.get("student_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    student_identity = metadata_student_id or (
        metadata_user_id if metadata_user_id != "local" else ""
    )
    student_identity_source = (
        "metadata.student_id"
        if metadata_student_id
        else "metadata.user_id"
        if student_identity
        else "none"
    )
    snapshot_student_id = _snapshot_student_id(payload)
    matches_snapshot = (
        student_identity == snapshot_student_id
        if student_identity and snapshot_student_id
        else False
    )
    warnings: list[str] = []
    if student_identity_source == "metadata.user_id":
        warnings.append("metadata.student_id missing; using metadata.user_id as legacy student identity")
    if snapshot_student_id and not student_identity:
        warnings.append("metadata has no restorable student identity")
    elif snapshot_student_id and not matches_snapshot:
        warnings.append("metadata student identity does not match restore snapshot")

    return {
        "metadata_user_id": metadata_user_id or None,
        "metadata_student_id": metadata_student_id or None,
        "student_identity": student_identity or None,
        "student_identity_source": student_identity_source,
        "snapshot_student_id": snapshot_student_id or None,
        "student_identity_matches_snapshot": matches_snapshot,
        "warnings": warnings,
    }


def _path_character_id(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return ""
    return relative.parts[0] if len(relative.parts) >= 2 else ""


def _path_session_id(path: Path) -> str:
    match = _TIMESTAMPED_SESSION_FILE_RE.match(path.stem)
    return match.group("session_id") if match else ""


def _path_identity_audit(path: Path, payload: dict[str, Any], root: Path) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_character_id = (
        str(metadata.get("character_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    metadata_session_id = (
        str(metadata.get("session_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    path_character_id = _path_character_id(path, root)
    path_session_id = _path_session_id(path)
    expected_character_id = _safe_path_part(metadata_character_id, "")
    expected_session_id = _safe_path_part(metadata_session_id, "")
    character_matches = not (
        path_character_id
        and expected_character_id
        and path_character_id != expected_character_id
    )
    session_matches = not (
        path_session_id
        and expected_session_id
        and path_session_id != expected_session_id
    )
    warnings: list[str] = []
    if not character_matches:
        warnings.append("file directory character_id does not match metadata.character_id")
    if not session_matches:
        warnings.append("file name session_id does not match metadata.session_id")
    return {
        "path_character_id": path_character_id,
        "path_session_id": path_session_id or None,
        "path_character_matches_metadata": character_matches,
        "path_session_matches_metadata": session_matches,
        "path_identity_mismatch": not character_matches or not session_matches,
        "warnings": warnings,
    }


def audit_chat_history_payload(path: Path, payload: dict[str, Any], root: Path) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    messages = _history_messages(payload)
    message_pages = _message_page_sets(messages)
    session_pages = _session_page_uids(payload)
    message_page_union = set().union(*message_pages) if message_pages else set()
    detected_pages = session_pages | message_page_union
    status, reason, warnings = _status_for_history(
        detected_pages=detected_pages,
        messages=messages,
        message_pages=message_pages,
    )
    path_identity = _path_identity_audit(path, payload, root)
    student_identity = _student_identity_audit(payload)
    warnings.extend(path_identity["warnings"])
    warnings.extend(student_identity["warnings"])
    if path_identity["path_identity_mismatch"]:
        status = "legacy_readonly"
        reason = "file path identity does not match metadata"
    elif (
        student_identity["snapshot_student_id"]
        and student_identity["student_identity_source"] == "none"
    ):
        status = "legacy_readonly"
        reason = "student identity is not restorable"
    elif (
        student_identity["snapshot_student_id"]
        and not student_identity["student_identity_matches_snapshot"]
    ):
        status = "legacy_readonly"
        reason = "student identity does not match restore snapshot"

    snapshot = payload.get("restore_snapshot") or payload.get("runtime_snapshot")
    runtime_state = snapshot.get("runtimeState") if isinstance(snapshot, dict) else None
    if isinstance(snapshot, dict) and not isinstance(runtime_state, dict):
        warnings.append("restore snapshot has no runtimeState; block-level resume is limited")

    message_count = _visible_message_count(messages)
    return {
        "file": str(path.relative_to(root)),
        "format": payload.get("format") if isinstance(payload.get("format"), str) else "unknown",
        "session_id": str(metadata.get("session_id") or ""),
        "character_id": str(metadata.get("character_id") or ""),
        "metadata_user_id": student_identity["metadata_user_id"],
        "metadata_student_id": student_identity["metadata_student_id"],
        "student_identity": student_identity["student_identity"],
        "student_identity_source": student_identity["student_identity_source"],
        "snapshot_student_id": student_identity["snapshot_student_id"],
        "student_identity_matches_snapshot": student_identity[
            "student_identity_matches_snapshot"
        ],
        "path_character_id": path_identity["path_character_id"],
        "path_session_id": path_identity["path_session_id"],
        "path_character_matches_metadata": path_identity["path_character_matches_metadata"],
        "path_session_matches_metadata": path_identity["path_session_matches_metadata"],
        "path_identity_mismatch": path_identity["path_identity_mismatch"],
        "metadata_page_uid": metadata.get("page_uid") if isinstance(metadata.get("page_uid"), str) else None,
        "detected_pages": sorted(detected_pages),
        "session_level_pages": sorted(session_pages),
        "message_level_pages": sorted(message_page_union),
        "message_count": message_count,
        "messages_without_page_evidence": sum(1 for pages in message_pages if not pages),
        "messages_with_multiple_pages": sum(1 for pages in message_pages if len(pages) > 1),
        "message_page_ownership": _message_page_ownership(message_pages),
        "restore_safety": _restore_safety(payload),
        "safe_to_migrate": status == "repairable",
        "status": status,
        "reason": reason,
        "warnings": warnings,
    }


def read_chat_history_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") not in _SUPPORTED_HISTORY_FORMATS:
        return None
    return payload


def iter_chat_history_files(root: Path, *, character_id: str | None = None):
    if not root.exists():
        return
    for path in sorted(root.glob("*/*.json")):
        if character_id and path.parent.name != character_id:
            continue
        yield path


def build_chat_history_audit_report(
    root: Path,
    *,
    character_id: str | None = None,
) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    skipped_files: list[str] = []
    for path in iter_chat_history_files(root, character_id=character_id):
        payload = read_chat_history_payload(path)
        if payload is None:
            skipped_files.append(str(path.relative_to(root)))
            continue
        sessions.append(audit_chat_history_payload(path, payload, root))

    counts = Counter(str(item["status"]) for item in sessions)
    unverified_message_ownership = sum(
        1
        for item in sessions
        if item["message_page_ownership"] in {"missing", "partial", "conflicting"}
    )
    return {
        "format": CHAT_HISTORY_AUDIT_FORMAT,
        "generated_at": _utc_timestamp_label(),
        "root": str(root),
        "character_id": character_id,
        "counts": {
            "clean": counts.get("clean", 0),
            "repairable": counts.get("repairable", 0),
            "legacy_readonly": counts.get("legacy_readonly", 0),
            "skipped": len(skipped_files),
            "safe_to_migrate": sum(1 for item in sessions if item["safe_to_migrate"]),
            "unverified_message_ownership": unverified_message_ownership,
            "path_identity_mismatch": sum(
                1 for item in sessions if item["path_identity_mismatch"]
            ),
        },
        "sessions": sessions,
        "skipped_files": skipped_files,
    }


def write_chat_history_audit_report(root: Path, report: dict[str, Any]) -> Path:
    report_dir = root / "_migration_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{_utc_timestamp_label()}_legacy_history_audit.json"
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return path
