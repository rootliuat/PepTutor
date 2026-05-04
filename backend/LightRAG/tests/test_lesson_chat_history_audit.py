from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
lesson_chat_history_routes = importlib.import_module(
    "lightrag.api.routers.lesson_chat_history_routes"
)
lesson_chat_history_audit = importlib.import_module(
    "lightrag.api.lesson_chat_history_audit"
)
sys.argv = _PYTEST_ARGV

build_chat_history_audit_report = lesson_chat_history_audit.build_chat_history_audit_report
create_lesson_chat_history_routes = lesson_chat_history_routes.create_lesson_chat_history_routes


def _make_app():
    app = FastAPI()
    app.include_router(create_lesson_chat_history_routes())
    return app


def _write_history(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _v3_payload(
    *,
    session_id: str,
    page_uid: str,
    messages: list[dict],
    snapshot_page_uid: str | None = None,
    runtime_state: dict | None = None,
):
    return {
        "format": "peptutor-chat-history:v3",
        "metadata": {
            "session_id": session_id,
            "user_id": "demo-student",
            "student_id": "demo-student",
            "character_id": "peptutor-mili-teacher",
            "created_at": 1777330000000,
            "updated_at": 1777330000000,
            "page_uid": page_uid,
        },
        "raw_chat_session": {
            "messages": messages,
        },
        "restore_snapshot": {
            "version": 1,
            "selectedPageUid": snapshot_page_uid or page_uid,
            "studentId": "demo-student",
            "runtimeState": runtime_state,
            "updatedAt": 1777330000000,
        },
        "dialogue": [],
    }


def test_chat_history_audit_does_not_infer_page_from_message_text(tmp_path):
    root = tmp_path / "chat_history"
    path = root / "peptutor-mili-teacher" / "clean.json"
    _write_history(
        path,
        _v3_payload(
            session_id="clean",
            page_uid="TB-G5S1U1-P4",
            messages=[
                {
                    "role": "assistant",
                    "content": "这段正文里提到 TB-G5S1U3-P24，但这不是结构化归属证据。",
                }
            ],
            runtime_state={
                "current_page_uid": "TB-G5S1U1-P4",
                "current_block_uid": "TB-G5S1U1-P4-D1",
            },
        ),
    )

    report = build_chat_history_audit_report(root, character_id="peptutor-mili-teacher")
    session = report["sessions"][0]

    assert session["status"] == "clean"
    assert session["detected_pages"] == ["TB-G5S1U1-P4"]
    assert session["messages_without_page_evidence"] == 1
    assert session["message_page_ownership"] == "missing"
    assert session["restore_safety"] == "block"
    assert session["safe_to_migrate"] is False
    assert "safe splitting is impossible" in " ".join(session["warnings"])


def test_chat_history_audit_marks_repairable_only_with_message_page_owners(tmp_path):
    root = tmp_path / "chat_history"
    path = root / "peptutor-mili-teacher" / "repairable.json"
    _write_history(
        path,
        _v3_payload(
            session_id="repairable",
            page_uid="TB-G5S1U1-P4",
            messages=[
                {
                    "role": "assistant",
                    "content": "P4 message",
                    "metadata": {"page_uid": "TB-G5S1U1-P4"},
                },
                {
                    "role": "user",
                    "content": "P24 message",
                    "metadata": {"page_uid": "TB-G5S1U3-P24"},
                },
            ],
            runtime_state={
                "current_page_uid": "TB-G5S1U1-P4",
                "current_block_uid": "TB-G5S1U1-P4-D1",
            },
        ),
    )

    report = build_chat_history_audit_report(root, character_id="peptutor-mili-teacher")
    session = report["sessions"][0]

    assert session["status"] == "repairable"
    assert session["detected_pages"] == ["TB-G5S1U1-P4", "TB-G5S1U3-P24"]
    assert session["messages_without_page_evidence"] == 0
    assert session["messages_with_multiple_pages"] == 0
    assert session["message_page_ownership"] == "complete"
    assert session["safe_to_migrate"] is True


def test_chat_history_audit_marks_mixed_session_without_ownership_readonly(tmp_path):
    root = tmp_path / "chat_history"
    path = root / "peptutor-mili-teacher" / "legacy-readonly.json"
    _write_history(
        path,
        _v3_payload(
            session_id="legacy-readonly",
            page_uid="TB-G5S1U1-P4",
            snapshot_page_uid="TB-G5S1U3-P24",
            messages=[
                {
                    "role": "assistant",
                    "content": "这条消息没有结构化 page_uid，不能安全判断属于哪一页。",
                }
            ],
        ),
    )

    report = build_chat_history_audit_report(root, character_id="peptutor-mili-teacher")
    session = report["sessions"][0]

    assert session["status"] == "legacy_readonly"
    assert session["detected_pages"] == ["TB-G5S1U1-P4", "TB-G5S1U3-P24"]
    assert session["messages_without_page_evidence"] == 1
    assert session["message_page_ownership"] == "missing"
    assert session["restore_safety"] == "page"
    assert session["safe_to_migrate"] is False
    assert "message ownership is incomplete" in session["reason"]


def test_chat_history_audit_marks_local_metadata_user_readonly(tmp_path):
    root = tmp_path / "chat_history"
    path = root / "peptutor-mili-teacher" / "legacy-local.json"
    payload = _v3_payload(
        session_id="legacy-local",
        page_uid="TB-G5S1U3-P24",
        messages=[
            {
                "role": "assistant",
                "content": "P24 message",
                "metadata": {"page_uid": "TB-G5S1U3-P24"},
            }
        ],
        runtime_state={
            "student_id": "demo-student",
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D1",
        },
    )
    payload["metadata"].pop("student_id")
    payload["metadata"]["user_id"] = "local"
    _write_history(path, payload)

    report = build_chat_history_audit_report(root, character_id="peptutor-mili-teacher")
    session = report["sessions"][0]

    assert session["status"] == "legacy_readonly"
    assert session["reason"] == "student identity is not restorable"
    assert session["metadata_user_id"] == "local"
    assert session["metadata_student_id"] is None
    assert session["student_identity_source"] == "none"
    assert session["snapshot_student_id"] == "demo-student"
    assert session["student_identity_matches_snapshot"] is False
    assert "no restorable student identity" in " ".join(session["warnings"])


def test_chat_history_audit_marks_path_identity_mismatches_readonly(tmp_path):
    root = tmp_path / "chat_history"
    path = root / "default" / "2026-04-29_12-00-00_orphan-session.json"
    _write_history(
        path,
        _v3_payload(
            session_id="orphan-session",
            page_uid="TB-G5S1U3-P24",
            messages=[
                {
                    "role": "assistant",
                    "content": "P24 message",
                    "metadata": {"page_uid": "TB-G5S1U3-P24"},
                }
            ],
            runtime_state={
                "current_page_uid": "TB-G5S1U3-P24",
                "current_block_uid": "TB-G5S1U3-P24-D1",
            },
        ),
    )

    report = build_chat_history_audit_report(root)
    session = report["sessions"][0]

    assert session["status"] == "legacy_readonly"
    assert session["reason"] == "file path identity does not match metadata"
    assert session["path_character_id"] == "default"
    assert session["path_session_id"] == "orphan-session"
    assert session["path_character_matches_metadata"] is False
    assert session["path_session_matches_metadata"] is True
    assert session["path_identity_mismatch"] is True
    assert session["safe_to_migrate"] is False
    assert report["counts"]["path_identity_mismatch"] == 1
    assert "directory character_id" in " ".join(session["warnings"])


def test_chat_history_audit_route_can_write_report_without_mutating_history(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "chat_history"
    history_path = root / "peptutor-mili-teacher" / "clean.json"
    _write_history(
        history_path,
        _v3_payload(
            session_id="clean",
            page_uid="TB-G5S1U1-P4",
            messages=[{"role": "user", "content": "hello"}],
        ),
    )
    before = history_path.read_text(encoding="utf-8")
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(root))

    client = TestClient(_make_app())
    response = client.get(
        "/lesson/chat-history/audit"
        "?character_id=peptutor-mili-teacher&write_report=true"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "peptutor-chat-history-audit:v1"
    assert payload["counts"]["clean"] == 1
    assert payload["counts"]["safe_to_migrate"] == 0
    assert payload["counts"]["unverified_message_ownership"] == 1
    report_path = Path(payload["report_path"])
    assert report_path.exists()
    assert report_path.parent == root / "_migration_reports"
    assert history_path.read_text(encoding="utf-8") == before
