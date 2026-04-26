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
            "runtime_snapshot": {"selectedPageUid": "TB-G5S2U1-P4"},
            "messages": [
                {
                    "role": "assistant",
                    "content": "你好，我是米粒老师。",
                    "createdAt": 1766720001234,
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
    assert '"format": "peptutor-chat-history:v1"' in saved
    assert "你好，我是米粒老师。" in saved
    assert "TB-G5S2U1-P4" in saved


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

    loaded = client.get("/lesson/chat-history/sessions/session-b")
    assert loaded.status_code == 200
    assert loaded.json()["metadata"]["title"] == "newer"
