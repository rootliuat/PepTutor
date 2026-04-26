import json
import sqlite3
from pathlib import Path

from lightrag.orchestrator.simplemem_prompt_memory import (
    SimpleMemSQLitePromptMemoryProvider,
)


class _FakeSemanticRecallProvider:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def recall(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.items)


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
                "Needs the full drink sentence on ordering turns.",
                "Can deliver the target drink sentence after guided practice.",
                "Start with a short L1 scaffold before retry.",
            ),
        )
        conn.execute(
            """
            INSERT INTO observations (
                memory_session_id, timestamp, type, title, subtitle, facts_json, narrative
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-1",
                "2026-03-24T12:06:00Z",
                "decision",
                "Chunked scaffold",
                "Break the sentence into smaller parts",
                json.dumps(
                    {
                        "candidate_kind": "preference",
                        "preference_key": "slow_split_practice",
                    }
                ),
                "Learner stays calmer when the sentence is chunked.",
            ),
        )
        conn.execute(
            """
            INSERT INTO observations (
                memory_session_id, timestamp, type, title, subtitle, facts_json, narrative
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-1",
                "2026-03-24T12:07:00Z",
                "discovery",
                "Ordering retry",
                "Drops part of the target answer",
                json.dumps(
                    {
                        "candidate_kind": "mistake",
                        "model_answer": "I'd like some water.",
                        "mistake_focus": "missing_full_pattern",
                    }
                ),
                "Learner answers with a short fragment instead of the full sentence.",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_simplemem_prompt_memory_provider_groups_student_memory(tmp_path):
    db_path = _write_test_simplemem_db(tmp_path)
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="What does water mean?",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == ['Learner still needs the full sentence "I\'d like some water."']
    assert summary.preferences == [
        "Learner prefers slower split practice when stuck.",
        "Learner prefers Chinese explanation before retry.",
    ]
    assert summary.mastery_signals == [
        'Learner can now answer "I\'d like some water." correctly'
    ]
    assert "Common mistakes:" in summary.summary_text
    assert "Preferences:" in summary.summary_text
    assert "Mastery signals:" in summary.summary_text


def test_simplemem_prompt_memory_provider_is_student_scoped(tmp_path):
    db_path = _write_test_simplemem_db(tmp_path)
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
    )

    summary = provider.get_summary(
        student_id="student-2",
        learner_input="What does water mean?",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={"focus_vocabulary": ["water"]},
    )

    assert summary.common_mistakes == []
    assert summary.preferences == []
    assert summary.mastery_signals == []
    assert summary.summary_text == ""


def test_simplemem_prompt_memory_provider_is_project_scoped(tmp_path):
    db_path = _write_test_simplemem_db(tmp_path)
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="other-project",
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="What does water mean?",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={"focus_vocabulary": ["water"]},
    )

    assert summary.common_mistakes == []
    assert summary.preferences == []
    assert summary.mastery_signals == []
    assert summary.summary_text == ""


def test_simplemem_prompt_memory_provider_can_exclude_current_session(tmp_path):
    db_path = _write_test_simplemem_db(tmp_path)
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="What does water mean?",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={"focus_vocabulary": ["water"]},
        exclude_memory_session_id="memory-1",
    )

    assert summary.common_mistakes == []
    assert summary.preferences == []
    assert summary.mastery_signals == []
    assert summary.summary_text == ""


def test_simplemem_prompt_memory_provider_includes_semantic_memories(tmp_path):
    db_path = _write_test_simplemem_db(tmp_path)
    semantic_provider = _FakeSemanticRecallProvider(
        [
            "Learner gets shy when asked to answer aloud.",
            "Learner prefers slower split practice when stuck.",
        ]
    )
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        semantic_recall_provider=semantic_provider,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "focus_vocabulary": ["water"],
        },
        exclude_memory_session_id="memory-99",
    )

    assert summary.semantic_memories == [
        "Learner gets shy when asked to answer aloud.",
    ]
    assert "Relevant past memories:" in summary.summary_text
    assert semantic_provider.calls[0]["exclude_memory_session_id"] == "memory-99"


def test_simplemem_prompt_memory_provider_dedupes_semantic_memories_against_current_buckets(
    tmp_path,
):
    db_path = _write_test_simplemem_db(tmp_path)
    semantic_provider = _FakeSemanticRecallProvider(
        [
            "Needs the full drink sentence on ordering turns.",
            "Learner prefers slower split practice when stuck.",
            "Learner gets shy when asked to answer aloud.",
        ]
    )
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        semantic_recall_provider=semantic_provider,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
        exclude_memory_session_id="memory-99",
    )

    assert summary.semantic_memories == [
        "Learner gets shy when asked to answer aloud.",
    ]


def test_simplemem_prompt_memory_provider_skips_generic_semantic_progress_noise(
    tmp_path,
):
    db_path = _write_test_simplemem_db(tmp_path)
    semantic_provider = _FakeSemanticRecallProvider(
        [
            "Learner still needs more guided help here.",
            "Learner gets shy when asked to answer aloud.",
        ]
    )
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        semantic_recall_provider=semantic_provider,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
        exclude_memory_session_id="memory-99",
    )

    assert summary.semantic_memories == [
        "Learner gets shy when asked to answer aloud.",
    ]


def test_simplemem_prompt_memory_provider_filters_conflicting_semantic_progress(
    tmp_path,
):
    db_path = tmp_path / "simplemem-semantic-progress-conflict.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-1",
                    "memory-1",
                    "peptutor-lesson",
                    "session 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-2",
                    "memory-2",
                    "peptutor-lesson",
                    "session 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-1",
                    "2026-03-21T12:05:00Z",
                    None,
                    'Learner can now answer "I\'d like some water." correctly',
                    None,
                ),
                (
                    "memory-2",
                    "2026-03-22T12:05:00Z",
                    None,
                    'Learner can now answer "I\'d like some water." correctly',
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    semantic_provider = _FakeSemanticRecallProvider(
        [
            "Learner struggles to answer with 'I'd like some water.' independently.",
            "Learner gets shy when asked to answer aloud.",
        ]
    )
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=1,
        category_limit=2,
        semantic_recall_provider=semantic_provider,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.mastery_signals == [
        'Learner can now answer "I\'d like some water." correctly'
    ]
    assert summary.stable_mastery_signals == []
    assert summary.semantic_memories == [
        "Learner gets shy when asked to answer aloud.",
    ]


def test_simplemem_prompt_memory_provider_dedupes_same_fact_across_all_memory_buckets(
    tmp_path,
):
    db_path = _write_test_simplemem_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "student-1",
                "content-2",
                "memory-2",
                "peptutor-lesson",
                "repeat drink page",
                "2026-03-25T12:00:00Z",
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
                "memory-2",
                "2026-03-25T12:05:00Z",
                "Needs the full drink sentence on ordering turns.",
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    semantic_provider = _FakeSemanticRecallProvider(
        ['Learner still needs the full sentence "I\'d like some water."']
    )
    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=6,
        category_limit=2,
        semantic_recall_provider=semantic_provider,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
        exclude_memory_session_id="memory-99",
    )

    canonical_mistake = 'Learner still needs the full sentence "I\'d like some water."'
    assert summary.common_mistakes == [canonical_mistake]
    assert summary.stable_common_mistakes == []
    assert summary.semantic_memories == []
    assert summary.summary_text.count(canonical_mistake) == 1


def test_simplemem_prompt_memory_provider_reads_legacy_mastery_variant_without_facts(
    tmp_path,
):
    db_path = tmp_path / "simplemem-legacy-mastery-variant.db"
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
                "content-legacy-mastery",
                "memory-legacy-mastery",
                "peptutor-lesson",
                "legacy mastery page",
                "2026-03-25T12:00:00Z",
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
                "memory-legacy-mastery",
                "2026-03-25T12:05:00Z",
                None,
                "Can now say the drink sentence on her own.",
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=1,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == []
    assert summary.preferences == []
    assert summary.mastery_signals == [
        'Learner can now answer "I\'d like some water." correctly'
    ]
    assert summary.stable_mastery_signals == []


def test_simplemem_prompt_memory_provider_prefers_relevant_memories_over_newer_noise(tmp_path):
    db_path = tmp_path / "simplemem-ranking.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-drink",
                    "memory-drink",
                    "peptutor-lesson",
                    "drink page",
                    "2026-03-24T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-breakfast",
                    "memory-breakfast",
                    "peptutor-lesson",
                    "breakfast page",
                    "2026-03-25T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-drink",
                    "2026-03-24T12:05:00Z",
                    "Needs the full drink sentence on ordering turns.",
                    "Can deliver the target drink sentence after guided practice.",
                    "Use chunked scaffold for drink sentence practice.",
                ),
                (
                    "memory-breakfast",
                    "2026-03-25T12:05:00Z",
                    "Needs the breakfast sentence about noodles.",
                    "Can talk about breakfast foods independently.",
                    "Use gesture prompts for breakfast chat.",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO observations (
                memory_session_id, timestamp, type, title, subtitle, facts_json, narrative
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-drink",
                    "2026-03-24T12:06:00Z",
                    "discovery",
                    "Drink retry",
                    "Full sentence still needed",
                    json.dumps(
                        {
                            "candidate_kind": "mistake",
                            "page_uid": "TB-G5S1U3-P24",
                            "block_uid": "TB-G5S1U3-P24-D1",
                            "block_type": "dialogue_core",
                            "model_answer": "I'd like some water.",
                            "mistake_focus": "missing_full_pattern",
                        }
                    ),
                    "Learner drops the full drink sentence.",
                ),
                (
                    "memory-breakfast",
                    "2026-03-25T12:06:00Z",
                    "discovery",
                    "Breakfast retry",
                    "Breakfast answer still shaky",
                    json.dumps(
                        {
                            "candidate_kind": "mistake",
                            "page_uid": "TB-G5S1U3-P26",
                            "block_uid": "TB-G5S1U3-P26-D1",
                            "block_type": "extension_task",
                            "model_answer": "I'd like noodles for breakfast.",
                            "mistake_focus": "wrong_target_pattern",
                        }
                    ),
                    "Learner goes vague on breakfast talk.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=4,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D1",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D1",
            "block_type": "dialogue_core",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water", "juice"],
            "core_patterns": [
                "What would you like to drink?",
                "I'd like some water.",
            ],
            "allowed_answer_scope": ["I'd like some water."],
            "repair_modes": ["repeat", "sentence_drill"],
            "branchable_topics": ["drink"],
            "return_anchors": ["What would you like to drink?"],
        },
    )

    assert summary.common_mistakes == ['Learner still needs the full sentence "I\'d like some water."']
    assert summary.preferences == ["Learner prefers slower split practice when stuck."]
    assert summary.mastery_signals == [
        'Learner can now answer "I\'d like some water." correctly'
    ]


def test_simplemem_prompt_memory_provider_prioritizes_repeated_profile_signals(tmp_path):
    db_path = tmp_path / "simplemem-profile-ranking.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-1",
                    "memory-1",
                    "peptutor-lesson",
                    "session 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-2",
                    "memory-2",
                    "peptutor-lesson",
                    "session 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-3",
                    "memory-3",
                    "peptutor-lesson",
                    "session 3",
                    "2026-03-23T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-1",
                    "2026-03-21T12:05:00Z",
                    "Needs the full drink sentence on ordering turns.",
                    None,
                    "Learner prefers Chinese explanation before retry.",
                ),
                (
                    "memory-2",
                    "2026-03-22T12:05:00Z",
                    "Needs the full drink sentence on ordering turns.",
                    None,
                    "Learner prefers Chinese explanation before retry.",
                ),
                (
                    "memory-3",
                    "2026-03-23T12:05:00Z",
                    "Needs the full drink sentence on ordering turns.",
                    None,
                    "Learner prefers slower split practice when stuck.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={"focus_vocabulary": ["water"]},
    )

    assert summary.preferences == ["Learner prefers Chinese explanation before retry."]
    assert summary.stable_preferences == []
    assert "Stable learner profile:" not in summary.summary_text


def test_simplemem_prompt_memory_provider_stable_profile_prefers_latest_supported_progress(
    tmp_path,
):
    db_path = tmp_path / "simplemem-stable-progress.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-1",
                    "memory-1",
                    "peptutor-lesson",
                    "session 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-2",
                    "memory-2",
                    "peptutor-lesson",
                    "session 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-3",
                    "memory-3",
                    "peptutor-lesson",
                    "session 3",
                    "2026-03-23T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-4",
                    "memory-4",
                    "peptutor-lesson",
                    "session 4",
                    "2026-03-24T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-1",
                    "2026-03-21T12:05:00Z",
                    'Learner still needs the full sentence "I\'d like some water."',
                    None,
                    None,
                ),
                (
                    "memory-2",
                    "2026-03-22T12:05:00Z",
                    'Learner still needs the full sentence "I\'d like some water."',
                    None,
                    None,
                ),
                (
                    "memory-3",
                    "2026-03-23T12:05:00Z",
                    None,
                    'Learner can now answer "I\'d like some water." correctly',
                    None,
                ),
                (
                    "memory-4",
                    "2026-03-24T12:05:00Z",
                    None,
                    'Learner can now answer "I\'d like some water." correctly',
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=8,
        max_observations=1,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.stable_common_mistakes == []
    assert summary.stable_mastery_signals == []
    assert "Stable mastery:" not in summary.summary_text
    assert "Stable mistake:" not in summary.summary_text
    assert [item.model_dump() for item in summary.memory_conflicts] == [
        {
            "target": "I'd like some water.",
            "chosen_category": "mastery",
            "suppressed_category": "mistake",
            "reason": (
                "Repeated progress signals conflict; choose the better supported "
                "and more recent stable category for prompt use."
            ),
        }
    ]
    assert any(
        item.layer == "fact"
        and item.category == "mastery"
        and item.stability == "stable"
        and item.text == 'Learner can now answer "I\'d like some water." correctly'
        for item in summary.memory_layers
    )
    assert "Resolved memory conflicts:" in summary.summary_text


def test_simplemem_prompt_memory_provider_merges_legacy_summary_with_canonical_target(
    tmp_path,
):
    db_path = tmp_path / "simplemem-legacy-summary-merge.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-legacy",
                    "memory-legacy",
                    "peptutor-lesson",
                    "legacy session",
                    "2026-03-20T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-modern",
                    "memory-modern",
                    "peptutor-lesson",
                    "modern session",
                    "2026-03-21T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "memory-legacy",
                "2026-03-20T12:05:00Z",
                "Needs the full drink sentence on ordering turns.",
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO observations (
                memory_session_id, timestamp, type, title, subtitle, facts_json, narrative
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-modern",
                "2026-03-21T12:06:00Z",
                "discovery",
                "Drink retry",
                "Full sentence still needed",
                json.dumps(
                    {
                        "candidate_kind": "mistake",
                        "model_answer": "I'd like some water.",
                        "mistake_focus": "missing_full_pattern",
                    }
                ),
                "Learner drops the full drink sentence.",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=4,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == ['Learner still needs the full sentence "I\'d like some water."']
    assert summary.stable_common_mistakes == []
    assert summary.memory_conflicts == []
    assert summary.memory_layers[0].model_dump() == {
        "layer": "fact",
        "category": "mistake",
        "text": 'Learner still needs the full sentence "I\'d like some water."',
        "stability": "stable",
        "prompt_use": (
            "Predict likely difficulty; keep lesson correctness authoritative."
        ),
    }


def test_simplemem_prompt_memory_provider_uses_session_metadata_to_merge_legacy_variants(
    tmp_path,
):
    db_path = tmp_path / "simplemem-legacy-metadata-merge.db"
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
        session_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P24-D1",
                "block_type": "dialogue_core",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-1",
                    "memory-1",
                    "peptutor-lesson",
                    "session 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                    session_metadata,
                ),
                (
                    "student-1",
                    "content-2",
                    "memory-2",
                    "peptutor-lesson",
                    "session 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                    session_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-1",
                    "2026-03-21T12:05:00Z",
                    "Still needs another guided try here.",
                    None,
                    None,
                ),
                (
                    "memory-2",
                    "2026-03-22T12:05:00Z",
                    "Needs one more supported response on this page.",
                    None,
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D1",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D1",
            "block_type": "dialogue_core",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == [
        'Learner still needs the target sentence "I\'d like some water."'
    ]
    assert summary.stable_common_mistakes == []


def test_simplemem_prompt_memory_provider_stable_preferences_respect_page_scope(
    tmp_path,
):
    db_path = tmp_path / "simplemem-preference-page-scope.db"
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
        current_page_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P24-D1",
                "block_type": "dialogue_core",
            }
        )
        other_page_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P25",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P25-D1",
                "block_type": "dialogue_core",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-current",
                    "memory-current",
                    "peptutor-lesson",
                    "current page",
                    "2026-03-21T12:00:00Z",
                    "completed",
                    current_page_metadata,
                ),
                (
                    "student-1",
                    "content-other-1",
                    "memory-other-1",
                    "peptutor-lesson",
                    "other page 1",
                    "2026-03-22T12:00:00Z",
                    "completed",
                    other_page_metadata,
                ),
                (
                    "student-1",
                    "content-other-2",
                    "memory-other-2",
                    "peptutor-lesson",
                    "other page 2",
                    "2026-03-23T12:00:00Z",
                    "completed",
                    other_page_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-current",
                    "2026-03-21T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-other-1",
                    "2026-03-22T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-other-2",
                    "2026-03-23T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D1",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D1",
            "block_type": "dialogue_core",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.preferences == ["Learner prefers Chinese explanation before retry."]
    assert summary.stable_preferences == []


def test_simplemem_prompt_memory_provider_layers_block_preference_over_page_profile(
    tmp_path,
):
    db_path = tmp_path / "simplemem-preference-layering.db"
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
        page_only_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
            }
        )
        current_block_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P24-D2",
                "block_type": "dialogue_drill",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-page-1",
                    "memory-page-1",
                    "peptutor-lesson",
                    "page profile 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                    page_only_metadata,
                ),
                (
                    "student-1",
                    "content-page-2",
                    "memory-page-2",
                    "peptutor-lesson",
                    "page profile 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                    page_only_metadata,
                ),
                (
                    "student-1",
                    "content-block-now",
                    "memory-block-now",
                    "peptutor-lesson",
                    "current block",
                    "2026-03-23T12:00:00Z",
                    "completed",
                    current_block_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-page-1",
                    "2026-03-21T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-page-2",
                    "2026-03-22T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-block-now",
                    "2026-03-23T12:05:00Z",
                    None,
                    None,
                    "Use chunked scaffold for drink sentence practice.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=1,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D2",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D2",
            "block_type": "dialogue_drill",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.preferences == ["Learner prefers slower split practice when stuck."]
    assert summary.stable_preferences == [
        "Learner prefers Chinese explanation before retry."
    ]


def test_simplemem_prompt_memory_provider_avoids_duplicate_global_preference_when_block_matches(
    tmp_path,
):
    db_path = tmp_path / "simplemem-preference-global-vs-block.db"
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
        current_block_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P24-D2",
                "block_type": "dialogue_drill",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-global-1",
                    "memory-global-1",
                    "peptutor-lesson",
                    "global 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                    None,
                ),
                (
                    "student-1",
                    "content-global-2",
                    "memory-global-2",
                    "peptutor-lesson",
                    "global 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                    None,
                ),
                (
                    "student-1",
                    "content-block",
                    "memory-block",
                    "peptutor-lesson",
                    "current block",
                    "2026-03-23T12:00:00Z",
                    "completed",
                    current_block_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-global-1",
                    "2026-03-21T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-global-2",
                    "2026-03-22T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-block",
                    "2026-03-23T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=1,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D2",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D2",
            "block_type": "dialogue_drill",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.preferences == ["Learner prefers Chinese explanation before retry."]
    assert summary.stable_preferences == []


def test_simplemem_prompt_memory_provider_stable_preferences_prioritize_global_traits(
    tmp_path,
):
    db_path = tmp_path / "simplemem-stable-preference-priority.db"
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
        current_page_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-global-1",
                    "memory-global-1",
                    "peptutor-lesson",
                    "global 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                    None,
                ),
                (
                    "student-1",
                    "content-global-2",
                    "memory-global-2",
                    "peptutor-lesson",
                    "global 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                    None,
                ),
                (
                    "student-1",
                    "content-page-1",
                    "memory-page-1",
                    "peptutor-lesson",
                    "page 1",
                    "2026-03-23T12:00:00Z",
                    "completed",
                    current_page_metadata,
                ),
                (
                    "student-1",
                    "content-page-2",
                    "memory-page-2",
                    "peptutor-lesson",
                    "page 2",
                    "2026-03-24T12:00:00Z",
                    "completed",
                    current_page_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-global-1",
                    "2026-03-21T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-global-2",
                    "2026-03-22T12:05:00Z",
                    None,
                    None,
                    "Start with a short L1 scaffold before retry.",
                ),
                (
                    "memory-page-1",
                    "2026-03-23T12:05:00Z",
                    None,
                    None,
                    "Use chunked scaffold for drink sentence practice.",
                ),
                (
                    "memory-page-2",
                    "2026-03-24T12:05:00Z",
                    None,
                    None,
                    "Use chunked scaffold for drink sentence practice.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=8,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.preferences == ["Learner prefers slower split practice when stuck."]
    assert summary.stable_preferences == [
        "Learner prefers Chinese explanation before retry."
    ]


def test_simplemem_prompt_memory_provider_infers_stable_preference_from_legacy_phrase_variants(
    tmp_path,
):
    db_path = tmp_path / "simplemem-stable-preference-legacy-variants.db"
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
        current_page_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-page-legacy-1",
                    "memory-page-legacy-1",
                    "peptutor-lesson",
                    "legacy slow split 1",
                    "2026-03-25T12:00:00Z",
                    "completed",
                    current_page_metadata,
                ),
                (
                    "student-1",
                    "content-page-legacy-2",
                    "memory-page-legacy-2",
                    "peptutor-lesson",
                    "legacy slow split 2",
                    "2026-03-26T12:00:00Z",
                    "completed",
                    current_page_metadata,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-page-legacy-1",
                    "2026-03-25T12:05:00Z",
                    None,
                    None,
                    "Walk through the drink sentence part by part before another try.",
                ),
                (
                    "memory-page-legacy-2",
                    "2026-03-26T12:05:00Z",
                    None,
                    None,
                    "Give a phrase-by-phrase scaffold for the drink sentence first.",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=6,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.preferences == ["Learner prefers slower split practice when stuck."]
    assert summary.stable_preferences == []


def test_simplemem_prompt_memory_provider_skips_generic_stable_progress_noise(
    tmp_path,
):
    db_path = tmp_path / "simplemem-stable-progress-noise.db"
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
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-generic-1",
                    "memory-generic-1",
                    "peptutor-lesson",
                    "generic 1",
                    "2026-03-21T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-generic-2",
                    "memory-generic-2",
                    "peptutor-lesson",
                    "generic 2",
                    "2026-03-22T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-generic-3",
                    "memory-generic-3",
                    "peptutor-lesson",
                    "generic 3",
                    "2026-03-23T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-specific-1",
                    "memory-specific-1",
                    "peptutor-lesson",
                    "specific 1",
                    "2026-03-24T12:00:00Z",
                    "completed",
                ),
                (
                    "student-1",
                    "content-specific-2",
                    "memory-specific-2",
                    "peptutor-lesson",
                    "specific 2",
                    "2026-03-25T12:00:00Z",
                    "completed",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "memory-generic-1",
                    "2026-03-21T12:05:00Z",
                    "Learner still needs more guided help here.",
                    None,
                    None,
                ),
                (
                    "memory-generic-2",
                    "2026-03-22T12:05:00Z",
                    "Learner still needs more guided help here.",
                    None,
                    None,
                ),
                (
                    "memory-generic-3",
                    "2026-03-23T12:05:00Z",
                    "Learner still needs more guided help here.",
                    None,
                    None,
                ),
                (
                    "memory-specific-1",
                    "2026-03-24T12:05:00Z",
                    'Learner still needs the full sentence "I\'d like some water."',
                    None,
                    None,
                ),
                (
                    "memory-specific-2",
                    "2026-03-25T12:05:00Z",
                    'Learner still needs the full sentence "I\'d like some water."',
                    None,
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=8,
        max_observations=1,
        category_limit=1,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == ['Learner still needs the full sentence "I\'d like some water."']
    assert summary.stable_common_mistakes == []
    assert "Stable mistake:" not in summary.summary_text


def test_simplemem_prompt_memory_provider_collapses_same_target_progress_variants(
    tmp_path,
):
    db_path = tmp_path / "simplemem-progress-variant-collapse.db"
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
        session_metadata = json.dumps(
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_uid": "TB-G5S1U3-P24-D1",
                "block_type": "dialogue_core",
            }
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                tenant_id, content_session_id, memory_session_id, project,
                user_prompt, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "student-1",
                    "content-legacy",
                    "memory-legacy",
                    "peptutor-lesson",
                    "legacy session",
                    "2026-03-24T12:00:00Z",
                    "completed",
                    session_metadata,
                ),
                (
                    "student-1",
                    "content-structured",
                    "memory-structured",
                    "peptutor-lesson",
                    "structured session",
                    "2026-03-25T12:00:00Z",
                    "completed",
                    session_metadata,
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO session_summaries (
                memory_session_id, timestamp, learned, completed, next_steps
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "memory-legacy",
                "2026-03-24T12:05:00Z",
                "Still needs one more supported response on this page.",
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO observations (
                memory_session_id, timestamp, type, title, subtitle, facts_json, narrative
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-structured",
                "2026-03-25T12:06:00Z",
                "discovery",
                "Drink retry",
                "Full sentence still needed",
                json.dumps(
                    {
                        "candidate_kind": "mistake",
                        "page_uid": "TB-G5S1U3-P24",
                        "block_uid": "TB-G5S1U3-P24-D1",
                        "block_type": "dialogue_core",
                        "model_answer": "I'd like some water.",
                        "mistake_focus": "missing_full_pattern",
                    }
                ),
                "Learner drops the full drink sentence.",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=4,
        category_limit=2,
    )

    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": "TB-G5S1U3-P24",
            "current_block_uid": "TB-G5S1U3-P24-D1",
        },
        block_snapshot={
            "page_uid": "TB-G5S1U3-P24",
            "block_uid": "TB-G5S1U3-P24-D1",
            "block_type": "dialogue_core",
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water"],
            "allowed_answer_scope": ["I'd like some water."],
        },
    )

    assert summary.common_mistakes == ['Learner still needs the full sentence "I\'d like some water."']
    assert summary.stable_common_mistakes == []
