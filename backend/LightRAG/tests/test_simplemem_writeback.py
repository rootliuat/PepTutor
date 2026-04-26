import importlib
import json
import sqlite3
import sys

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
lesson_runtime_module = importlib.import_module("lightrag.orchestrator.lesson_runtime")
lesson_state_module = importlib.import_module("lightrag.orchestrator.lesson_state")
simplemem_writeback_module = importlib.import_module(
    "lightrag.orchestrator.simplemem_writeback"
)
simplemem_prompt_memory_module = importlib.import_module(
    "lightrag.orchestrator.simplemem_prompt_memory"
)
simplemem_semantic_memory_module = importlib.import_module(
    "lightrag.orchestrator.simplemem_semantic_memory"
)
sys.argv = _PYTEST_ARGV

LessonTurnResult = lesson_runtime_module.LessonTurnResult
PageLessonRecord = lesson_runtime_module.PageLessonRecord
TeachingBlockRecord = lesson_runtime_module.TeachingBlockRecord
LessonRuntimeState = lesson_state_module.LessonRuntimeState
SimpleMemSQLiteLessonMemoryWriter = (
    simplemem_writeback_module.SimpleMemSQLiteLessonMemoryWriter
)
SimpleMemSQLitePromptMemoryProvider = (
    simplemem_prompt_memory_module.SimpleMemSQLitePromptMemoryProvider
)
build_semantic_tenant_namespace = (
    simplemem_semantic_memory_module.build_semantic_tenant_namespace
)


class _FakeSemanticStore:
    def __init__(self):
        self.entries = []

    def add_entries(self, entries):
        self.entries.extend(entries)


def _page():
    return PageLessonRecord(
        page_uid="TB-G5S1U3-P24",
        page_type="dialogue",
        page_intro_cn="这一页练习点餐和饮料表达。",
        entry_probe_questions=["Can you answer: What would you like to drink?"],
        priority_blocks=["TB-G5S1U3-P24-D1"],
    )


def _block():
    return TeachingBlockRecord(
        block_uid="TB-G5S1U3-P24-D1",
        page_uid="TB-G5S1U3-P24",
        page_type="dialogue",
        block_type="dialogue_core",
        teaching_goal="Use the target drink question and answer.",
        teaching_summary="Restaurant ordering with the drink question.",
        focus_vocabulary=["water", "juice"],
        core_patterns=["What would you like to drink?", "I'd like some water."],
        allowed_answer_scope=["I'd like some water."],
        entry_probe_questions=["Can you answer: What would you like to drink?"],
        repair_modes=["repeat", "sentence_drill"],
        next_block_uids=[],
        learning_target_uids=["LT-1"],
        branchable_topics=["drink"],
        return_anchors=["What would you like to drink?"],
    )


def _state():
    return LessonRuntimeState(
        student_id="student-1",
        current_grade="G5",
        current_semester="S1",
        current_unit="U3",
        current_page=24,
        current_page_uid="TB-G5S1U3-P24",
        current_page_type="dialogue",
        current_block_uid="TB-G5S1U3-P24-D1",
        current_activity_type="teaching",
        awaiting_answer=True,
        recent_turn_labels=["page_entry", "answer_question", "ask_help"],
        same_goal_attempt_count=1,
        simplemem_content_session_id="lesson-TB-G5S1U3-P24-test",
    )


def test_simplemem_writeback_records_observations_and_summary(tmp_path):
    db_path = tmp_path / "cross.db"
    writer = SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project="peptutor-lesson",
    )
    page = _page()
    block = _block()
    prior_state = _state()

    memory_session_id = writer.ensure_session(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        page=page,
        block=block,
    )

    wrong_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="answer_question",
        teaching_action="hint",
        retrieval_mode="none",
        teacher_response="先别急，再试试。",
        state=prior_state.model_copy(
            update={"simplemem_memory_session_id": memory_session_id}
        ),
        evaluation="incorrect",
    )
    help_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="ask_help",
        teaching_action="hint",
        retrieval_mode="none",
        teacher_response="我们先拆小一点。",
        state=prior_state.model_copy(
            update={
                "awaiting_answer": False,
                "simplemem_memory_session_id": memory_session_id,
            }
        ),
    )
    correct_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="answer_question",
        teaching_action="confirm",
        retrieval_mode="none",
        teacher_response="对了，这一块你已经会了。我们先收住这一页。",
        state=prior_state.model_copy(
            update={
                "awaiting_answer": False,
                "simplemem_memory_session_id": memory_session_id,
            }
        ),
        evaluation="correct",
    )

    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="water",
        prior_state=prior_state,
        result=wrong_result,
        page=page,
        block=block,
    )
    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="again slowly",
        prior_state=prior_state.model_copy(update={"awaiting_answer": False}),
        result=help_result,
        page=page,
        block=block,
    )
    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="I'd like some water.",
        prior_state=prior_state,
        result=correct_result,
        page=page,
        block=block,
    )
    assert writer.summarize_session(
        memory_session_id=memory_session_id,
        page=page,
        state=correct_result.state,
    )
    writer.finalize_session(memory_session_id=memory_session_id)
    writer.close()

    conn = sqlite3.connect(db_path)
    try:
        observation_rows = [
            (row[0], json.loads(row[1]))
            for row in conn.execute(
                "SELECT title, facts_json FROM observations ORDER BY obs_id ASC"
            ).fetchall()
        ]
        summary_row = conn.execute(
            """
            SELECT learned, completed, next_steps
            FROM session_summaries
            WHERE memory_session_id = ?
            """,
            (memory_session_id,),
        ).fetchone()
        status_row = conn.execute(
            "SELECT status FROM sessions WHERE memory_session_id = ?",
            (memory_session_id,),
        ).fetchone()
    finally:
        conn.close()

    assert [title for title, _ in observation_rows] == [
        "Learner struggles to answer with 'I'd like some water.' independently.",
        "Learner prefers slower split practice when stuck.",
        "Learner can now answer 'I'd like some water.' correctly.",
    ]
    assert observation_rows[0][1]["candidate_kind"] == "mistake"
    assert observation_rows[0][1]["memory_layer"] == "episode"
    assert observation_rows[0][1]["promotion_policy"] == (
        "episode_to_fact_after_repeated_supported_progress"
    )
    assert observation_rows[0][1]["model_answer"] == "I'd like some water."
    assert observation_rows[0][1]["mistake_focus"] == "missing_full_pattern"
    assert observation_rows[0][1]["same_goal_attempt_count"] == 1
    assert observation_rows[1][1]["candidate_kind"] == "preference"
    assert observation_rows[1][1]["memory_layer"] == "procedure"
    assert observation_rows[1][1]["preference_key"] == "slow_split_practice"
    assert observation_rows[2][1]["candidate_kind"] == "mastery"
    assert observation_rows[2][1]["memory_layer"] == "episode"
    assert observation_rows[2][1]["model_answer"] == "I'd like some water."
    assert summary_row == (
        'Learner still needs the full sentence "I\'d like some water."',
        'Learner can now answer "I\'d like some water." correctly',
        "Learner prefers slower split practice when stuck.",
    )
    assert status_row == ("completed",)


def test_simplemem_writeback_can_upsert_semantic_entries(tmp_path):
    db_path = tmp_path / "cross.db"
    semantic_store = _FakeSemanticStore()
    writer = SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project="peptutor-lesson",
        semantic_store=semantic_store,
    )
    page = _page()
    block = _block()
    prior_state = _state()
    memory_session_id = writer.ensure_session(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        page=page,
        block=block,
    )
    wrong_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="answer_question",
        teaching_action="hint",
        retrieval_mode="none",
        teacher_response="先别急，再试试。",
        state=prior_state.model_copy(
            update={"simplemem_memory_session_id": memory_session_id}
        ),
        evaluation="incorrect",
    )

    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="want tea",
        prior_state=prior_state,
        result=wrong_result,
        page=page,
        block=block,
    )

    assert len(semantic_store.entries) == 1
    entry = semantic_store.entries[0]
    assert entry.tenant_id == build_semantic_tenant_namespace(
        project="peptutor-lesson",
        student_id="student-1",
    )
    assert entry.memory_session_id == memory_session_id
    assert entry.source_kind == "lesson_trace"
    assert entry.topic == "mistake"
    assert "I'd like some water." in entry.lossless_restatement


def test_simplemem_writeback_namespaces_content_session_by_project_and_student(tmp_path):
    db_path = tmp_path / "cross.db"
    page = _page()
    block = _block()

    writer_a = SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project="peptutor-lesson",
    )
    writer_b = SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project="other-project",
    )

    try:
        memory_a = writer_a.ensure_session(
            student_id="student-1",
            content_session_id="shared-content",
            page=page,
            block=block,
        )
        memory_a_repeat = writer_a.ensure_session(
            student_id="student-1",
            content_session_id="shared-content",
            page=page,
            block=block,
        )
        memory_b = writer_b.ensure_session(
            student_id="student-1",
            content_session_id="shared-content",
            page=page,
            block=block,
        )
        memory_c = writer_a.ensure_session(
            student_id="student-2",
            content_session_id="shared-content",
            page=page,
            block=block,
        )
    finally:
        writer_a.close()
        writer_b.close()

    conn = sqlite3.connect(db_path)
    try:
        session_rows = conn.execute(
            """
            SELECT tenant_id, project, content_session_id, memory_session_id
            FROM sessions
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    assert memory_a == memory_a_repeat
    assert memory_b != memory_a
    assert memory_c != memory_a
    assert len(session_rows) == 3
    assert session_rows[0] == (
        "student-1",
        "peptutor-lesson",
        "peptutor-lesson::student-1::shared-content",
        memory_a,
    )
    assert session_rows[1] == (
        "student-1",
        "other-project",
        "other-project::student-1::shared-content",
        memory_b,
    )
    assert session_rows[2] == (
        "student-2",
        "peptutor-lesson",
        "peptutor-lesson::student-2::shared-content",
        memory_c,
    )


def test_simplemem_writeback_round_trip_into_prompt_memory_provider(tmp_path):
    db_path = tmp_path / "cross.db"
    writer = SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project="peptutor-lesson",
    )
    page = _page()
    block = _block()
    prior_state = _state()

    memory_session_id = writer.ensure_session(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        page=page,
        block=block,
    )

    wrong_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="answer_question",
        teaching_action="hint",
        retrieval_mode="none",
        teacher_response="先别急，再试试。",
        state=prior_state.model_copy(
            update={"simplemem_memory_session_id": memory_session_id}
        ),
        evaluation="incorrect",
    )
    help_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="ask_help",
        teaching_action="hint",
        retrieval_mode="none",
        teacher_response="我们先拆小一点。",
        state=prior_state.model_copy(
            update={
                "awaiting_answer": False,
                "simplemem_memory_session_id": memory_session_id,
            }
        ),
    )
    correct_result = LessonTurnResult(
        page_uid=page.page_uid,
        block_uid=block.block_uid,
        turn_label="answer_question",
        teaching_action="confirm",
        retrieval_mode="none",
        teacher_response="对了，这一块你已经会了。我们先收住这一页。",
        state=prior_state.model_copy(
            update={
                "awaiting_answer": False,
                "simplemem_memory_session_id": memory_session_id,
            }
        ),
        evaluation="correct",
    )

    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="water",
        prior_state=prior_state,
        result=wrong_result,
        page=page,
        block=block,
    )
    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="again slowly",
        prior_state=prior_state.model_copy(update={"awaiting_answer": False}),
        result=help_result,
        page=page,
        block=block,
    )
    writer.record_turn(
        student_id="student-1",
        content_session_id=prior_state.simplemem_content_session_id,
        memory_session_id=memory_session_id,
        learner_input="I'd like some water.",
        prior_state=prior_state,
        result=correct_result,
        page=page,
        block=block,
    )
    assert writer.summarize_session(
        memory_session_id=memory_session_id,
        page=page,
        state=correct_result.state,
    )
    writer.finalize_session(memory_session_id=memory_session_id)
    writer.close()

    conn = sqlite3.connect(db_path)
    try:
        observation_rows = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT facts_json FROM observations ORDER BY obs_id ASC"
            ).fetchall()
        ]
    finally:
        conn.close()

    provider = SimpleMemSQLitePromptMemoryProvider(
        db_path=db_path,
        project="peptutor-lesson",
        max_summaries=4,
        max_observations=8,
        category_limit=2,
    )
    summary = provider.get_summary(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={
            "current_page_uid": page.page_uid,
            "current_block_uid": block.block_uid,
        },
        block_snapshot={
            "page_uid": page.page_uid,
            "block_uid": block.block_uid,
            "block_type": block.block_type,
            "teaching_goal": block.teaching_goal,
            "teaching_summary": block.teaching_summary,
            "focus_vocabulary": block.focus_vocabulary,
            "allowed_answer_scope": block.allowed_answer_scope,
        },
    )

    assert observation_rows[0]["candidate_kind"] == "mistake"
    assert observation_rows[0]["memory_layer"] == "episode"
    assert observation_rows[0]["model_answer"] == "I'd like some water."
    assert observation_rows[0]["mistake_focus"] == "missing_full_pattern"
    assert observation_rows[0]["same_goal_attempt_count"] == 1
    assert observation_rows[1]["candidate_kind"] == "preference"
    assert observation_rows[1]["memory_layer"] == "procedure"
    assert observation_rows[1]["preference_key"] == "slow_split_practice"
    assert observation_rows[2]["candidate_kind"] == "mastery"
    assert observation_rows[2]["memory_layer"] == "episode"
    assert observation_rows[2]["model_answer"] == "I'd like some water."
    assert summary.common_mistakes == [
        'Learner still needs the full sentence "I\'d like some water."'
    ]
    assert summary.preferences == [
        "Learner prefers slower split practice when stuck.",
    ]
    assert summary.mastery_signals == [
        'Learner can now answer "I\'d like some water." correctly'
    ]
