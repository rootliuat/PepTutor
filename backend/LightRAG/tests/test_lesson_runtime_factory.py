import json
import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pytest

from lightrag.orchestrator.lesson_runtime_factory import (
    LLMCallLoopRunner,
    _resolve_lesson_manifest_path,
    _resolve_qdrant_client_kwargs,
    build_lesson_runtime,
)
from lightrag.utils import EmbeddingFunc


@pytest.fixture(autouse=True)
def _isolate_lesson_runtime_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(
        "PEPTUTOR_SUPPORT_ASSET_PATH",
        str(tmp_path / "missing-support-assets.json"),
    )
    for key in (
        "PEPTUTOR_LESSON_MANIFEST",
        "PEPTUTOR_PILOT_MANIFEST",
        "PEPTUTOR_LESSON_LIVE_PROMPTS",
        "PEPTUTOR_LESSON_VECTOR_RETRIEVAL",
        "PEPTUTOR_LESSON_QDRANT_LOCATION",
        "PEPTUTOR_LESSON_QDRANT_URL",
        "PEPTUTOR_LESSON_QDRANT_API_KEY",
        "PEPTUTOR_LESSON_QDRANT_COLLECTION",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION",
        "PEPTUTOR_SIMPLEMEM_WRITEBACK",
        "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL",
        "PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH",
        "PEPTUTOR_SIMPLEMEM_PROJECT",
        "PEPTUTOR_SIMPLEMEM_LANCEDB_PATH",
        "PEPTUTOR_SIMPLEMEM_LANCEDB_TABLE",
        "PEPTUTOR_SIMPLEMEM_MAX_SUMMARIES",
        "PEPTUTOR_SIMPLEMEM_MAX_OBSERVATIONS",
        "PEPTUTOR_SIMPLEMEM_CATEGORY_LIMIT",
        "PEPTUTOR_DEBUG_SIGNALS",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_test_pilot(tmp_path):
    pilot_file = tmp_path / "pilot.json"
    manifest_file = tmp_path / "manifest.json"

    pilot_payload = {
        "pilot_id": "g5s1u3-factory-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24, 25, 26]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "page_intro_cn": "这一页练习点餐和饮料表达。",
                "entry_probe_questions": ["Can you say: What would you like to drink?"],
                "priority_blocks": ["TB-G5S1U3-P24-D1", "TB-G5S1U3-P24-D2"],
            },
            {
                "page_uid": "TB-G5S1U3-P25",
                "page_type": "reading",
                "page_intro_cn": "这一页练习菜单和沙拉。",
                "entry_probe_questions": ["Can you say salad?"],
                "priority_blocks": ["TB-G5S1U3-P25-D1"],
            },
            {
                "page_uid": "TB-G5S1U3-P26",
                "page_type": "dialogue",
                "page_intro_cn": "这一页允许短暂聊早餐话题。",
                "entry_probe_questions": ["What do you eat for breakfast?"],
                "priority_blocks": ["TB-G5S1U3-P26-D1"],
            },
        ],
        "teaching_blocks": [
            {
                "block_uid": "TB-G5S1U3-P24-D1",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "Use the target drink question and answer.",
                "teaching_summary": "Restaurant ordering with the drink question.",
                "focus_vocabulary": ["water", "juice"],
                "core_patterns": [
                    "What would you like to drink?",
                    "I'd like some water.",
                ],
                "allowed_answer_scope": [
                    "I'd like some water.",
                    "I'd like some juice.",
                ],
                "entry_probe_questions": ["Can you answer: What would you like to drink?"],
                "repair_modes": ["repeat", "sentence_drill"],
                "next_block_uids": ["TB-G5S1U3-P24-D2"],
                "learning_target_uids": ["LT-1"],
                "branchable_topics": ["drink"],
                "return_anchors": ["What would you like to drink?"],
            },
            {
                "block_uid": "TB-G5S1U3-P24-D2",
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "roleplay_task",
                "teaching_goal": "Do a short drink role-play.",
                "teaching_summary": "One-step role-play with a drink choice.",
                "focus_vocabulary": ["water", "juice"],
                "core_patterns": ["I'd like some water."],
                "allowed_answer_scope": ["I'd like some water."],
                "entry_probe_questions": ["Now say one full drink sentence."],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-2"],
                "branchable_topics": ["drink", "roleplay"],
                "return_anchors": ["I'd like some water."],
            },
            {
                "block_uid": "TB-G5S1U3-P25-D1",
                "page_uid": "TB-G5S1U3-P25",
                "page_type": "reading",
                "block_type": "reading_passage",
                "teaching_goal": "Read about salad on a menu.",
                "teaching_summary": "A short menu text about salad and soup.",
                "focus_vocabulary": ["salad", "soup"],
                "core_patterns": ["The salad is fresh."],
                "allowed_answer_scope": ["The salad is fresh."],
                "entry_probe_questions": ["Can you read salad?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-3"],
                "branchable_topics": [],
                "return_anchors": ["What would you like to eat?"],
            },
            {
                "block_uid": "TB-G5S1U3-P26-D1",
                "page_uid": "TB-G5S1U3-P26",
                "page_type": "dialogue",
                "block_type": "extension_task",
                "teaching_goal": "Talk about breakfast food briefly.",
                "teaching_summary": "A short breakfast extension with noodles and eggs.",
                "focus_vocabulary": ["breakfast", "noodles", "eggs"],
                "core_patterns": ["I'd like noodles for breakfast."],
                "allowed_answer_scope": ["I'd like noodles for breakfast."],
                "entry_probe_questions": ["What do you eat for breakfast?"],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": ["LT-4"],
                "branchable_topics": ["breakfast", "noodles", "eggs"],
                "return_anchors": ["What would you like to eat?"],
            },
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def _write_test_support_assets(tmp_path):
    support_file = tmp_path / "support.json"
    support_payload = {
        "asset_id": "g5s1u3-support-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24, 25, 26]},
        "source_files": ["raw_wordlist_g5s1", "raw_useful_expressions_g5s1"],
        "lexicon_entries": [
            {
                "entry_uid": "LEX-G5S1U3-sandwich",
                "entry_type": "word",
                "english": "sandwich",
                "chinese": "三明治",
                "phonetic": "/'sænwɪtʃ/",
                "source_refs": ["raw_wordlist_g5s1"],
                "page_refs": ["p.24", "p.25"],
                "linked_page_uids": ["TB-G5S1U3-P24", "TB-G5S1U3-P25"],
                "linked_block_uids": ["TB-G5S1U3-P24-D2", "TB-G5S1U3-P25-D1"],
            }
        ],
        "expression_entries": [],
    }
    support_file.write_text(json.dumps(support_payload), encoding="utf-8")
    return support_file


def _write_test_simplemem_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "simplemem-cross.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                content_session_id TEXT UNIQUE NOT NULL,
                memory_session_id TEXT UNIQUE NOT NULL,
                project TEXT NOT NULL,
                user_prompt TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT DEFAULT 'active',
                metadata_json TEXT
            );
            CREATE TABLE observations (
                obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                facts_json TEXT,
                narrative TEXT,
                concepts_json TEXT,
                files_json TEXT,
                vector_ref TEXT
            );
            CREATE TABLE session_summaries (
                summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                request TEXT,
                investigated TEXT,
                learned TEXT,
                completed TEXT,
                next_steps TEXT,
                vector_ref TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "student-1",
                "content-1",
                "memory-1",
                "peptutor-lesson",
                "start lesson",
                "2026-03-24T12:00:00Z",
                "completed",
            ),
        )
        conn.execute(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "memory-1",
                "2026-03-24T12:05:00Z",
                "Student often omits some when ordering drinks.",
                "Student can now answer I'd like some water correctly.",
                "Student prefers Chinese explanation before retry.",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _assert_feature_statuses(bundle, *, expected_enabled=None):
    feature_keys = {
        "support_assets",
        "live_prompts",
        "semantic_recall",
        "prompt_injection",
        "writeback",
        "vector_retrieval",
    }
    assert set(bundle.feature_statuses) == feature_keys
    for status in bundle.feature_statuses.values():
        assert status.reason.strip()
        assert not (status.enabled is False and status.reason is None)
    if expected_enabled is not None:
        for feature_name, enabled in expected_enabled.items():
            assert bundle.feature_statuses[feature_name].enabled is enabled


def test_build_lesson_runtime_logs_feature_status_summary(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    logged_messages = []

    def _fake_logger_info(message, *args):
        if args:
            message = message % args
        logged_messages.append(str(message))

    monkeypatch.setattr(
        "lightrag.orchestrator.lesson_runtime_factory.logger.info",
        _fake_logger_info,
    )

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_strict_llm,
    )

    _assert_feature_statuses(bundle)
    log_text = "\n".join(logged_messages)
    assert "Lesson feature status summary:" in log_text
    assert "- live_prompts: ENABLED [auto]" in log_text
    assert "- vector_retrieval: DOWNGRADED [auto]" in log_text
    assert "- prompt_injection: DOWNGRADED [auto]" in log_text
    assert "No embedding_func was provided for vector retrieval" in log_text
    assert "SQLite DB was not found" in log_text


def test_llm_call_loop_runner_streams_async_model_chunks():
    async def _streaming_llm(
        prompt,
        system_prompt=None,
        history_messages=None,
        stream=False,
        **kwargs,
    ):
        _ = (prompt, system_prompt, history_messages, kwargs)
        assert stream is True

        async def _chunks():
            yield "Live "
            yield {"text": "teacher."}

        return _chunks()

    runner = LLMCallLoopRunner(_streaming_llm)
    try:
        assert list(runner.stream_text("prompt")) == ["Live ", "teacher."]
    finally:
        runner.close()


async def _fake_embed(texts, _priority=None):
    vectors = []
    for text in texts:
        lower = text.casefold()
        if "role play" in lower or "role-play" in lower:
            vectors.append([1.0, 0.0, 0.0])
        elif "salad" in lower:
            vectors.append([0.0, 1.0, 0.0])
        elif "breakfast" in lower or "noodles" in lower:
            vectors.append([0.0, 0.0, 1.0])
        else:
            vectors.append([0.1, 0.1, 0.1])
    return np.array(vectors, dtype=np.float32)


async def _strict_embed(texts):
    return await _fake_embed(texts)


async def _fake_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
    _ = (history_messages, kwargs)
    system_prompt = (system_prompt or "").casefold()
    if "route classifier" in system_prompt:
        parsed = json.loads(prompt)
        learner_input = parsed["learner_input"].casefold()
        if learner_input == "sandwich please" or "mean" in learner_input or "what does" in learner_input:
            return json.dumps(
                {
                    "turn_label": "ask_knowledge",
                    "reason": "Treat it as a knowledge request.",
                }
            )
        return json.dumps({"turn_label": "social"})
    if "lesson planner" in system_prompt:
        return json.dumps(
            {
                "teaching_action": "redirect",
                "retrieval_mode": "none",
                "response_focus": "Briefly redirect to the page prompt.",
            }
        )
    return "我们先把这个小问题收一下，回到这一页继续。"


async def _strict_llm(
    prompt,
    system_prompt=None,
    history_messages=None,
    max_tokens=None,
):
    _ = (history_messages, max_tokens)
    return await _fake_llm(prompt, system_prompt=system_prompt, history_messages=history_messages)


async def _fake_memory_aware_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
    _ = (history_messages, kwargs)
    parsed = json.loads(prompt)
    system_prompt = (system_prompt or "").casefold()
    learner_memory = parsed.get("learner_memory", {})
    if "route classifier" in system_prompt:
        return json.dumps(
            {
                "turn_label": "ask_help",
                "reason": "Use the learner preference for scaffolded help.",
            }
        )
    if "lesson planner" in system_prompt:
        if learner_memory.get("preferences"):
            return json.dumps(
                {
                    "teaching_action": "redirect",
                    "retrieval_mode": "none",
                    "response_focus": "Use Chinese scaffold before retry.",
                }
            )
        return json.dumps(
            {
                "teaching_action": "hint",
                "retrieval_mode": "none",
                "response_focus": "Fallback without learner memory.",
            }
        )
    if learner_memory.get("preferences"):
        return "按你更喜欢的中文拆解，我们先回到这一页。"
    return "缺少 learner memory。"


async def _fake_semantic_memory_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
    _ = (history_messages, kwargs)
    parsed = json.loads(prompt)
    system_prompt = (system_prompt or "").casefold()
    learner_memory = parsed.get("learner_memory", {})
    if "route classifier" in system_prompt:
        return json.dumps(
            {
                "turn_label": "ask_help",
                "reason": "Use recalled learner memory for help.",
            }
        )
    if "lesson planner" in system_prompt:
        return json.dumps(
            {
                "teaching_action": "redirect",
                "retrieval_mode": "none",
                "response_focus": "Use recalled semantic memory if present.",
            }
        )
    if learner_memory.get("semantic_memories"):
        return "我记得你之前也会卡在这句，我们这次慢一点拆开。"
    return "没有召回到 semantic memory。"


def test_build_lesson_runtime_falls_back_without_qdrant_settings(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    embedding_func = EmbeddingFunc(embedding_dim=3, func=_fake_embed)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        embedding_func=embedding_func,
        manifest_path=manifest_path,
        vector_enabled=True,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
        qdrant_client_kwargs={},
    )

    _assert_feature_statuses(
        bundle,
        expected_enabled={
            "live_prompts": False,
            "semantic_recall": False,
            "prompt_injection": False,
            "writeback": False,
            "vector_retrieval": False,
        },
    )
    assert bundle.close is None
    assert bundle.runtime.retriever.__class__.__name__ == "ScopedRetriever"
    assert "Qdrant" in bundle.feature_statuses["vector_retrieval"].reason


def test_build_lesson_runtime_can_enable_vector_retrieval(tmp_path):
    pytest.importorskip("qdrant_client")
    manifest_path = _write_test_pilot(tmp_path)
    embedding_func = EmbeddingFunc(embedding_dim=3, func=_strict_embed)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Payload indexes have no effect in the local Qdrant.*",
        )
        bundle = build_lesson_runtime(
            workspace="test-workspace",
            embedding_func=embedding_func,
            manifest_path=manifest_path,
            vector_enabled=True,
            live_prompts_enabled=False,
            semantic_recall_enabled=False,
            prompt_injection_enabled=False,
            writeback_enabled=False,
            qdrant_client_kwargs={"location": ":memory:"},
            collection_name="lesson_factory_vectors",
        )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})

        unit_result = bundle.runtime.handle_turn(open_state, "What does salad mean?")
        branch_result = bundle.runtime.handle_turn(
            open_state,
            "Can I eat noodles for breakfast?",
        )
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.close is not None
    assert bundle.runtime.retriever.__class__.__name__ == "QdrantLessonRetriever"
    assert bundle.feature_statuses["vector_retrieval"].enabled is True
    assert bundle.feature_statuses["vector_retrieval"].mode == "explicit"
    assert unit_result.retrieval_mode == "unit"
    assert unit_result.retrieved_block_uids[0] == "TB-G5S1U3-P25-D1"
    assert branch_result.retrieval_mode == "branch"
    assert branch_result.retrieved_block_uids[0] == "TB-G5S1U3-P26-D1"


def test_build_lesson_runtime_loads_support_assets_from_env(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    support_path = _write_test_support_assets(tmp_path)
    monkeypatch.setenv("PEPTUTOR_SUPPORT_ASSET_PATH", str(support_path))

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        live_prompts_enabled=False,
        vector_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
    open_state = start.state.model_copy(update={"awaiting_answer": False})
    result = bundle.runtime.handle_turn(open_state, "What does sandwich mean?")

    assert result.retrieval_mode == "block"
    assert result.retrieved_block_uids == ["TB-G5S1U3-P24-D1"]
    assert result.support_entry_uids == ["LEX-G5S1U3-sandwich"]
    assert "三明治" in result.teacher_response


def test_build_lesson_runtime_can_enable_live_prompts(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_strict_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "What does water mean?")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.close is not None
    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "none"
    assert result.teacher_response == "我们先把这个小问题收一下，回到这一页继续。"


def test_build_lesson_runtime_live_route_classifier_can_promote_open_turn(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_fake_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "sandwich please")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.close is not None
    assert result.turn_label == "ask_knowledge"
    assert result.retrieval_mode == "none"
    assert result.teacher_response == "我们先把这个小问题收一下，回到这一页继续。"


def test_build_lesson_runtime_can_enable_simplemem_prompt_injection(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    db_path = _write_test_simplemem_db(tmp_path)
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION", "true")
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_fake_memory_aware_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        semantic_recall_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "help me")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.close is not None
    assert result.turn_label == "ask_help"
    assert result.retrieval_mode == "none"
    assert result.teacher_response == "按你更喜欢的中文拆解，我们先回到这一页。"


def test_build_lesson_runtime_can_enable_simplemem_writeback(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    db_path = tmp_path / "simplemem-writeback.db"
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_WRITEBACK", "true")
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        vector_enabled=False,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        wrong = bundle.runtime.handle_turn(start.state, "want tea")
        switched = bundle.runtime.handle_turn(
            wrong.state,
            "next page",
            requested_page_uid="TB-G5S1U3-P25",
        )
    finally:
        if bundle.close:
            bundle.close()

    conn = sqlite3.connect(db_path)
    try:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        observation_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        summary_count = conn.execute("SELECT COUNT(*) FROM session_summaries").fetchone()[0]
    finally:
        conn.close()

    assert bundle.close is not None
    _assert_feature_statuses(bundle)
    assert start.state.simplemem_memory_session_id is not None
    assert switched.state.simplemem_memory_session_id is not None
    assert session_count == 2
    assert observation_count >= 1
    assert summary_count >= 1


def test_build_lesson_runtime_can_inject_semantic_recall(tmp_path, monkeypatch):
    from types import SimpleNamespace

    class _FakeSemanticStore:
        def semantic_search(self, **kwargs):
            _ = kwargs
            return [
                SimpleNamespace(
                    entry_id="m1",
                    lossless_restatement="Learner gets shy when asked to answer aloud.",
                    tenant_id="student-1",
                    memory_session_id="old-memory-1",
                    source_kind="lesson_trace",
                )
            ]

        def close(self):
            return None

    manifest_path = _write_test_pilot(tmp_path)
    db_path = _write_test_simplemem_db(tmp_path)
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION", "true")
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL", "true")
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")
    monkeypatch.setattr(
        "lightrag.orchestrator.lesson_runtime_factory._build_simplemem_semantic_store",
        lambda **kwargs: (_FakeSemanticStore(), "fake semantic store is ready"),
    )

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        embedding_func=EmbeddingFunc(embedding_dim=3, func=_fake_embed),
        llm_model_func=_fake_semantic_memory_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "help me")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert result.turn_label == "ask_help"
    assert result.teacher_response == "我记得你之前也会卡在这句，我们这次慢一点拆开。"


def test_build_lesson_runtime_auto_enables_live_prompts_without_flag(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_strict_llm,
        vector_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "What does water mean?")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["live_prompts"].enabled is True
    assert bundle.feature_statuses["live_prompts"].mode == "auto"
    assert result.turn_label == "ask_knowledge"
    assert result.teacher_response == "我们先把这个小问题收一下，回到这一页继续。"


def test_build_lesson_runtime_auto_enables_vector_retrieval_without_flag(tmp_path):
    pytest.importorskip("qdrant_client")
    manifest_path = _write_test_pilot(tmp_path)
    embedding_func = EmbeddingFunc(embedding_dim=3, func=_strict_embed)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Payload indexes have no effect in the local Qdrant.*",
        )
        bundle = build_lesson_runtime(
            workspace="test-workspace",
            embedding_func=embedding_func,
            manifest_path=manifest_path,
            live_prompts_enabled=False,
            semantic_recall_enabled=False,
            prompt_injection_enabled=False,
            writeback_enabled=False,
            qdrant_client_kwargs={"location": ":memory:"},
            collection_name="lesson_factory_auto_vectors",
        )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "Can I eat noodles for breakfast?")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["vector_retrieval"].enabled is True
    assert bundle.feature_statuses["vector_retrieval"].mode == "auto"
    assert result.retrieval_mode == "branch"
    assert result.retrieved_block_uids[0] == "TB-G5S1U3-P26-D1"


def test_build_lesson_runtime_auto_enables_simplemem_prompt_injection_without_flag(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    db_path = _write_test_simplemem_db(tmp_path)
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        llm_model_func=_fake_memory_aware_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        semantic_recall_enabled=False,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "help me")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["prompt_injection"].enabled is True
    assert bundle.feature_statuses["prompt_injection"].mode == "auto"
    assert result.teacher_response == "按你更喜欢的中文拆解，我们先回到这一页。"


def test_build_lesson_runtime_auto_enables_simplemem_writeback_without_flag(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    db_path = tmp_path / "simplemem-writeback-auto.db"
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        vector_enabled=False,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        result = bundle.runtime.handle_turn(start.state, "want tea")
    finally:
        if bundle.close:
            bundle.close()

    conn = sqlite3.connect(db_path)
    try:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        observation_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    finally:
        conn.close()

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["writeback"].enabled is True
    assert bundle.feature_statuses["writeback"].mode == "auto"
    assert result.state.simplemem_memory_session_id is not None
    assert session_count == 1
    assert observation_count >= 1


def test_build_lesson_runtime_auto_enables_semantic_recall_without_flag(tmp_path, monkeypatch):
    from types import SimpleNamespace

    class _FakeSemanticStore:
        def semantic_search(self, **kwargs):
            _ = kwargs
            return [
                SimpleNamespace(
                    entry_id="m1",
                    lossless_restatement="Learner gets shy when asked to answer aloud.",
                    tenant_id="student-1",
                    memory_session_id="old-memory-1",
                    source_kind="lesson_trace",
                )
            ]

        def close(self):
            return None

    manifest_path = _write_test_pilot(tmp_path)
    db_path = _write_test_simplemem_db(tmp_path)
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH", str(db_path))
    monkeypatch.setenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")
    monkeypatch.setattr(
        "lightrag.orchestrator.lesson_runtime_factory._build_simplemem_semantic_store",
        lambda **kwargs: (_FakeSemanticStore(), "fake semantic store is ready"),
    )

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        embedding_func=EmbeddingFunc(embedding_dim=3, func=_fake_embed),
        llm_model_func=_fake_semantic_memory_llm,
        live_prompts_enabled=True,
        vector_enabled=False,
        prompt_injection_enabled=True,
        writeback_enabled=False,
    )

    try:
        start = bundle.runtime.start_page("TB-G5S1U3-P24", "student-1")
        open_state = start.state.model_copy(update={"awaiting_answer": False})
        result = bundle.runtime.handle_turn(open_state, "help me")
    finally:
        if bundle.close:
            bundle.close()

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["semantic_recall"].enabled is True
    assert bundle.feature_statuses["semantic_recall"].mode == "auto"
    assert result.teacher_response == "我记得你之前也会卡在这句，我们这次慢一点拆开。"


def test_build_lesson_runtime_reports_non_empty_reasons_for_unavailable_auto_features(tmp_path, monkeypatch):
    manifest_path = _write_test_pilot(tmp_path)
    blocked_parent = tmp_path / "blocked-parent"
    blocked_parent.write_text("not-a-directory", encoding="utf-8")
    monkeypatch.setenv(
        "PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH",
        str(blocked_parent / "cross_memory.db"),
    )

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
    )

    _assert_feature_statuses(
        bundle,
        expected_enabled={
            "live_prompts": False,
            "semantic_recall": False,
            "prompt_injection": False,
            "writeback": False,
            "vector_retrieval": False,
        },
    )
    assert bundle.feature_statuses["live_prompts"].mode == "auto"
    assert "llm_model_func" in bundle.feature_statuses["live_prompts"].reason
    assert "embedding_func" in bundle.feature_statuses["semantic_recall"].reason
    assert "SQLite DB was not found" in bundle.feature_statuses["prompt_injection"].reason
    assert "writeback unavailable" in bundle.feature_statuses["writeback"].reason
    assert "embedding_func" in bundle.feature_statuses["vector_retrieval"].reason


def test_build_lesson_runtime_reports_missing_qdrant_reason_in_auto_mode(tmp_path):
    manifest_path = _write_test_pilot(tmp_path)
    embedding_func = EmbeddingFunc(embedding_dim=3, func=_fake_embed)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        manifest_path=manifest_path,
        embedding_func=embedding_func,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    _assert_feature_statuses(bundle)
    assert bundle.feature_statuses["vector_retrieval"].enabled is False
    assert bundle.feature_statuses["vector_retrieval"].mode == "auto"
    assert "Qdrant" in bundle.feature_statuses["vector_retrieval"].reason


def test_resolve_qdrant_client_kwargs_keeps_memory_mode(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_LESSON_QDRANT_LOCATION", ":memory:")
    monkeypatch.delenv("PEPTUTOR_LESSON_QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)

    assert _resolve_qdrant_client_kwargs() == {"location": ":memory:"}


def test_resolve_qdrant_client_kwargs_uses_path_for_persistent_local_store(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_LESSON_QDRANT_LOCATION", "/tmp/peptutor-qdrant")
    monkeypatch.delenv("PEPTUTOR_LESSON_QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)

    assert _resolve_qdrant_client_kwargs() == {"path": "/tmp/peptutor-qdrant"}


def test_resolve_lesson_manifest_path_prefers_env_override(tmp_path, monkeypatch):
    manifest_path = tmp_path / "custom-manifest.json"
    manifest_path.write_text(json.dumps({"files": []}), encoding="utf-8")
    monkeypatch.setenv("PEPTUTOR_LESSON_MANIFEST", str(manifest_path))
    monkeypatch.delenv("PEPTUTOR_PILOT_MANIFEST", raising=False)

    assert _resolve_lesson_manifest_path() == manifest_path.resolve()


def test_resolve_lesson_manifest_path_defaults_to_general_manifest(monkeypatch):
    monkeypatch.delenv("PEPTUTOR_LESSON_MANIFEST", raising=False)
    monkeypatch.delenv("PEPTUTOR_PILOT_MANIFEST", raising=False)

    resolved = _resolve_lesson_manifest_path()

    assert resolved.name == "general-manifest.json"
    assert resolved.exists()


def test_build_lesson_runtime_uses_general_manifest_by_default(monkeypatch):
    monkeypatch.delenv("PEPTUTOR_LESSON_MANIFEST", raising=False)
    monkeypatch.delenv("PEPTUTOR_PILOT_MANIFEST", raising=False)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        vector_enabled=False,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    try:
        scope = bundle.runtime.catalog.get_scope_for_page("TB-G6S1U1-P2")
        result = bundle.runtime.start_page("TB-G6S1U1-P2", "student-1")
    finally:
        if bundle.close:
            bundle.close()

    assert scope.grade == "G6"
    assert scope.semester == "S1"
    assert scope.unit == "U1"
    assert result.page_uid == "TB-G6S1U1-P2"


def test_build_lesson_runtime_general_manifest_exposes_catalog_outline(monkeypatch):
    monkeypatch.delenv("PEPTUTOR_LESSON_MANIFEST", raising=False)
    monkeypatch.delenv("PEPTUTOR_PILOT_MANIFEST", raising=False)

    bundle = build_lesson_runtime(
        workspace="test-workspace",
        vector_enabled=False,
        live_prompts_enabled=False,
        semantic_recall_enabled=False,
        prompt_injection_enabled=False,
        writeback_enabled=False,
    )

    try:
        outline = bundle.runtime.catalog.catalog_outline()
    finally:
        if bundle.close:
            bundle.close()

    assert outline.scope_count >= 30
    assert outline.page_count >= 253
    assert outline.block_count >= 579
    assert any(
        scope.grade == "G6" and scope.semester == "S2" and scope.unit == "Recycle2"
        for scope in outline.scopes
    )
    recycle2_scope = next(
        scope
        for scope in outline.scopes
        if scope.grade == "G6" and scope.semester == "S2" and scope.unit == "Recycle2"
    )
    assert any(page.page_uid == "TB-G6S2Recycle2-P51" for page in recycle2_scope.pages)
