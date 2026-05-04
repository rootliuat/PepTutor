from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
lesson_chat_history_routes = importlib.import_module(
    "lightrag.api.routers.lesson_chat_history_routes"
)
sys.argv = _PYTEST_ARGV

create_lesson_chat_history_routes = lesson_chat_history_routes.create_lesson_chat_history_routes


def _make_app():
    app = FastAPI()
    app.include_router(create_lesson_chat_history_routes())
    return app


def test_lesson_chat_history_route_writes_session_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(tmp_path / "chat_history"))

    client = TestClient(_make_app())
    response = client.post(
        "/lesson/chat-history/session",
        json={
            "session_id": "lesson-session-1",
            "user_id": "local",
            "character_id": "lesson",
            "title": "G5 S2 U1 P4",
            "created_at": 1766720000000,
            "updated_at": 1766720001234,
            "active": True,
            "page_uid": "TB-G5S2U1-P4",
            "raw_chat_session": {
                "messages": [
                    {
                        "role": "system",
                        "content": "raw system prompt must not be written",
                        "createdAt": 1766720001000,
                    },
                    {
                        "role": "assistant",
                        "content": "你好，我是米粒老师。",
                        "slices": [{"type": "text", "text": "你好，我是米粒老师。"}],
                        "tool_results": [],
                        "createdAt": 1766720001234,
                        "id": "assistant-1",
                    },
                    {
                        "role": "user",
                        "content": "老师好。",
                        "createdAt": 1766720002234,
                        "id": "user-1",
                    },
                ],
            },
            "runtime_snapshot": {
                "version": 1,
                "selectedPageUid": "TB-G5S2U1-P4",
                "studentId": "demo-student",
                "runtimeState": {
                    "current_page_uid": "TB-G5S2U1-P4",
                    "recent_turns": [
                        {
                            "teacher_text": "这段不应该写进历史文件。",
                            "learner_text": "这段也不应该写进历史文件。",
                        }
                    ],
                },
                "activeTurn": {
                    "teacher_response": "activeTurn 不能重复塞进历史文件。",
                },
            },
            "messages": [
                {
                    "role": "system",
                    "content": "system prompt must not be written",
                    "createdAt": 1766720001234,
                },
                {
                    "role": "assistant",
                    "content": "你好，我是米粒老师。",
                    "createdAt": 1766720001234,
                },
                {
                    "role": "user",
                    "content": "老师好。",
                    "createdAt": 1766720002234,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    written_path = Path(payload["path"])
    assert written_path.exists()
    assert written_path.parent == tmp_path / "chat_history" / "lesson"
    assert written_path.name.endswith("_lesson-session-1.json")

    saved = written_path.read_text(encoding="utf-8")
    assert '"format": "peptutor-chat-history:v3"' in saved
    assert '"raw_chat_session"' in saved
    assert '"dialogue"' in saved
    assert '"restore_snapshot"' in saved
    assert "system prompt must not be written" not in saved
    assert "raw system prompt must not be written" not in saved
    assert "activeTurn 不能重复塞进历史文件。" not in saved
    assert "这段不应该写进历史文件。" not in saved
    assert "你好，我是米粒老师。" in saved
    assert "老师好。" in saved
    assert '"id": "assistant-1"' in saved
    assert '"slices"' in saved
    assert "TB-G5S2U1-P4" in saved
    assert '"user_id": "demo-student"' in saved
    assert '"student_id": "demo-student"' in saved
    assert '"user_id": "local"' not in saved

    listed = client.get("/lesson/chat-history/sessions?character_id=lesson")
    assert listed.status_code == 200
    summary = listed.json()[0]
    assert summary["user_id"] == "demo-student"
    assert summary["student_id"] == "demo-student"
    assert summary["history_format"] == "peptutor-chat-history:v3"
    assert summary["audit_status"] == "clean"
    assert summary["restore_safety"] == "block"
    assert summary["history_access"] == "continue"


def test_lesson_chat_history_route_lists_and_reads_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(tmp_path / "chat_history"))
    client = TestClient(_make_app())

    client.post(
        "/lesson/chat-history/session",
        json={
            "session_id": "session-a",
            "user_id": "local",
            "character_id": "lesson",
            "title": "older",
            "created_at": 1766720000000,
            "updated_at": 1766720000000,
            "messages": [],
        },
    )
    client.post(
        "/lesson/chat-history/session",
        json={
            "session_id": "session-b",
            "user_id": "local",
            "character_id": "lesson",
            "title": "newer",
            "created_at": 1766721000000,
            "updated_at": 1766721000000,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    listed = client.get("/lesson/chat-history/sessions?character_id=lesson")
    assert listed.status_code == 200
    sessions = listed.json()
    assert [session["session_id"] for session in sessions] == ["session-b", "session-a"]
    assert sessions[0]["message_count"] == 1
    assert sessions[0]["preview"] == "hello"
    assert sessions[0]["audit_status"] == "legacy_readonly"
    assert sessions[0]["restore_safety"] == "none"
    assert sessions[0]["history_access"] == "read_only"

    loaded = client.get("/lesson/chat-history/sessions/session-b")
    assert loaded.status_code == 200
    assert loaded.json()["metadata"]["title"] == "newer"
    assert loaded.json()["dialogue"] == [
        {
            "speaker": "学生",
            "role": "user",
            "text": "hello",
        }
    ]


def test_lesson_chat_history_route_accepts_explicit_student_id(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(tmp_path / "chat_history"))
    client = TestClient(_make_app())

    response = client.post(
        "/lesson/chat-history/session",
        json={
            "session_id": "explicit-student",
            "user_id": "local",
            "student_id": "student-explicit",
            "character_id": "lesson",
            "title": "explicit student",
            "created_at": 1766720000000,
            "updated_at": 1766720000000,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    saved = Path(response.json()["path"]).read_text(encoding="utf-8")
    assert '"user_id": "student-explicit"' in saved
    assert '"student_id": "student-explicit"' in saved

    listed = client.get("/lesson/chat-history/sessions?student_id=student-explicit")
    assert listed.status_code == 200
    assert listed.json()[0]["student_id"] == "student-explicit"


def test_lesson_chat_history_route_filters_sessions_by_student_and_page(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(tmp_path / "chat_history"))
    client = TestClient(_make_app())

    for session_id, student_id, page_uid, updated_at in [
        ("student-a-p24", "student-a", "TB-G5S1U3-P24", 1766720000000),
        ("student-b-p24", "student-b", "TB-G5S1U3-P24", 1766720001000),
        ("student-a-p2", "student-a", "TB-G5S1U1-P2", 1766720002000),
    ]:
        response = client.post(
            "/lesson/chat-history/session",
            json={
                "session_id": session_id,
                "user_id": "local",
                "character_id": "lesson",
                "title": session_id,
                "created_at": updated_at,
                "updated_at": updated_at,
                "active": True,
                "page_uid": page_uid,
                "messages": [{"role": "user", "content": session_id}],
                "runtime_snapshot": {
                    "version": 1,
                    "selectedPageUid": page_uid,
                    "studentId": student_id,
                    "runtimeState": {
                        "student_id": student_id,
                        "current_page_uid": page_uid,
                        "current_block_uid": f"{page_uid}-D1",
                    },
                    "updatedAt": updated_at,
                },
            },
        )
        assert response.status_code == 200

    listed = client.get(
        "/lesson/chat-history/sessions"
        "?character_id=lesson&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )
    assert listed.status_code == 200
    sessions = listed.json()
    assert [session["session_id"] for session in sessions] == ["student-a-p24"]
    assert sessions[0]["user_id"] == "student-a"
    assert sessions[0]["student_id"] == "student-a"
    assert sessions[0]["page_uid"] == "TB-G5S1U3-P24"
    assert sessions[0]["history_access"] == "continue"

    loaded = client.get(
        "/lesson/chat-history/sessions/student-a-p24"
        "?student_id=student-a&page_uid=TB-G5S1U3-P24"
    )
    assert loaded.status_code == 200
    assert loaded.json()["metadata"]["session_id"] == "student-a-p24"

    mismatched_student = client.get(
        "/lesson/chat-history/sessions/student-a-p24"
        "?student_id=student-b&page_uid=TB-G5S1U3-P24"
    )
    assert mismatched_student.status_code == 404

    mismatched_page = client.get(
        "/lesson/chat-history/sessions/student-a-p24"
        "?student_id=student-a&page_uid=TB-G5S1U1-P2"
    )
    assert mismatched_page.status_code == 404


def test_lesson_chat_history_route_reads_session_by_character_identity(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(tmp_path / "chat_history"))
    client = TestClient(_make_app())

    for character_id, title in [
        ("default", "wrong character"),
        ("peptutor-mili-teacher", "teacher character"),
    ]:
        response = client.post(
            "/lesson/chat-history/session",
            json={
                "session_id": "shared-session",
                "user_id": "local",
                "character_id": character_id,
                "title": title,
                "created_at": 1766720000000,
                "updated_at": 1766720000000,
                "active": True,
                "page_uid": "TB-G5S1U3-P24",
                "messages": [{"role": "user", "content": title}],
                "runtime_snapshot": {
                    "version": 1,
                    "selectedPageUid": "TB-G5S1U3-P24",
                    "studentId": "student-a",
                    "runtimeState": {
                        "student_id": "student-a",
                        "current_page_uid": "TB-G5S1U3-P24",
                        "current_block_uid": "TB-G5S1U3-P24-D1",
                    },
                    "updatedAt": 1766720000000,
                },
            },
        )
        assert response.status_code == 200

    teacher = client.get(
        "/lesson/chat-history/sessions/shared-session"
        "?character_id=peptutor-mili-teacher"
        "&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )
    assert teacher.status_code == 200
    assert teacher.json()["metadata"]["character_id"] == "peptutor-mili-teacher"
    assert teacher.json()["metadata"]["title"] == "teacher character"

    default = client.get(
        "/lesson/chat-history/sessions/shared-session"
        "?character_id=default"
        "&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )
    assert default.status_code == 200
    assert default.json()["metadata"]["character_id"] == "default"
    assert default.json()["metadata"]["title"] == "wrong character"

    missing_character = client.get(
        "/lesson/chat-history/sessions/shared-session"
        "?character_id=missing"
        "&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )
    assert missing_character.status_code == 404


def test_lesson_chat_history_route_keeps_legacy_local_user_snapshots_read_only(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "chat_history"
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(root))
    path = root / "lesson" / "2026-04-29_00-00-00_legacy-local.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
{
  "format": "peptutor-chat-history:v3",
  "metadata": {
    "session_id": "legacy-local",
    "user_id": "local",
    "character_id": "lesson",
    "title": "legacy",
    "created_at": 1766720000000,
    "updated_at": 1766720000000,
    "active": true,
    "page_uid": "TB-G5S1U3-P24"
  },
  "raw_chat_session": {
    "messages": [
      {
        "role": "user",
        "content": "old",
        "metadata": {
          "page_uid": "TB-G5S1U3-P24"
        }
      }
    ]
  },
  "restore_snapshot": {
    "version": 1,
    "selectedPageUid": "TB-G5S1U3-P24",
    "studentId": "student-a",
    "runtimeState": {
      "student_id": "student-a",
      "current_page_uid": "TB-G5S1U3-P24",
      "current_block_uid": "TB-G5S1U3-P24-D1"
    },
    "updatedAt": 1766720000000
  },
  "dialogue": [
    {
      "speaker": "学生",
      "role": "user",
      "text": "old"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(_make_app())
    listed = client.get(
        "/lesson/chat-history/sessions"
        "?character_id=lesson&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )

    assert listed.status_code == 200
    summary = listed.json()[0]
    assert summary["session_id"] == "legacy-local"
    assert summary["student_id"] == "student-a"
    assert summary["user_id"] == "local"
    assert summary["audit_status"] == "legacy_readonly"
    assert summary["audit_reason"] == "student identity is not restorable"
    assert summary["restore_safety"] == "block"
    assert summary["history_access"] == "read_only"


def test_lesson_chat_history_route_keeps_path_orphan_histories_read_only(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "chat_history"
    monkeypatch.setenv("PEPTUTOR_CHAT_HISTORY_DIR", str(root))
    path = root / "default" / "2026-04-29_00-00-00_orphan-path.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
{
  "format": "peptutor-chat-history:v3",
  "metadata": {
    "session_id": "orphan-path",
    "user_id": "student-a",
    "character_id": "lesson",
    "title": "orphan",
    "created_at": 1766720000000,
    "updated_at": 1766720000000,
    "active": true,
    "page_uid": "TB-G5S1U3-P24"
  },
  "raw_chat_session": {
    "messages": [
      {
        "role": "user",
        "content": "old",
        "metadata": {
          "page_uid": "TB-G5S1U3-P24"
        }
      }
    ]
  },
  "restore_snapshot": {
    "version": 1,
    "selectedPageUid": "TB-G5S1U3-P24",
    "studentId": "student-a",
    "runtimeState": {
      "student_id": "student-a",
      "current_page_uid": "TB-G5S1U3-P24",
      "current_block_uid": "TB-G5S1U3-P24-D1"
    },
    "updatedAt": 1766720000000
  },
  "dialogue": [
    {
      "speaker": "学生",
      "role": "user",
      "text": "old"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(_make_app())
    listed = client.get(
        "/lesson/chat-history/sessions"
        "?character_id=lesson&student_id=student-a&page_uid=TB-G5S1U3-P24"
    )

    assert listed.status_code == 200
    summary = listed.json()[0]
    assert summary["session_id"] == "orphan-path"
    assert summary["audit_status"] == "legacy_readonly"
    assert summary["audit_reason"] == "file path identity does not match metadata"
    assert summary["restore_safety"] == "block"
    assert summary["history_access"] == "read_only"
