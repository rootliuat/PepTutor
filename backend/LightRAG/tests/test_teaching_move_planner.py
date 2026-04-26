import json
from pathlib import Path

from lightrag.orchestrator.lesson_brief_builder import LessonBriefBuilder
from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.teaching_move_planner import TeachingMovePlanner
from lightrag.pedagogy.planner import PlannerDecision
from lightrag.pedagogy.responder import LessonResponder


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _general_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _curriculum_map_path() -> Path:
    return _repo_root() / "app/knowledge/structured/curriculum-map.json"


def _catalog() -> PilotLessonCatalog:
    return PilotLessonCatalog(manifest_path=_general_manifest_path())


def _lookup(catalog: PilotLessonCatalog) -> LessonEvidenceLookup:
    return LessonEvidenceLookup(
        catalog,
        curriculum_map_path=_curriculum_map_path(),
    )


def _state(
    *,
    page_uid: str,
    block_uid: str,
    grade: str,
    semester: str,
    unit: str,
    page_type: str,
    last_teacher_question: str | None,
    last_eval_result: str | None,
    awaiting_answer: bool = True,
) -> LessonRuntimeState:
    return LessonRuntimeState(
        student_id="student-1",
        current_grade=grade,
        current_semester=semester,
        current_unit=unit,
        current_page=int(page_uid.rsplit("-P", 1)[1]),
        current_page_uid=page_uid,
        current_page_type=page_type,
        current_block_uid=block_uid,
        current_activity_type="practice",
        awaiting_answer=awaiting_answer,
        last_teacher_question=last_teacher_question,
        recent_turn_labels=["page_entry"],
        last_eval_result=last_eval_result,
    )


def _decision(action: str) -> PlannerDecision:
    return PlannerDecision(
        teaching_action=action,
        retrieval_mode="none",
        response_focus="Select the next reusable classroom move.",
    )


def _brief(
    *,
    catalog: PilotLessonCatalog,
    page_uid: str,
    block_uid: str,
    learner_input: str,
    turn_label: str,
    decision: PlannerDecision,
    state: LessonRuntimeState,
):
    evidence = _lookup(catalog).lookup(page_uid=page_uid, block_uid=block_uid)
    return LessonBriefBuilder().build(
        lesson_evidence=evidence,
        learner_input=learner_input,
        turn_label=turn_label,
        decision=decision,
        state=state,
    )


def _plan(
    *,
    catalog: PilotLessonCatalog,
    page_uid: str,
    block_uid: str,
    learner_input: str,
    turn_label: str,
    decision: PlannerDecision,
    state: LessonRuntimeState,
):
    brief = _brief(
        catalog=catalog,
        page_uid=page_uid,
        block_uid=block_uid,
        learner_input=learner_input,
        turn_label=turn_label,
        decision=decision,
        state=state,
    )
    return TeachingMovePlanner().plan(
        lesson_brief=brief,
        learner_input=learner_input,
        turn_label=turn_label,
        decision=decision,
        state=state,
    )


def test_teaching_move_planner_handles_required_learner_signals():
    catalog = _catalog()
    p31_state = _state(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
        grade="G5",
        semester="S1",
        unit="U3",
        page_type="story",
        last_teacher_question="What would Zoom like to eat?",
        last_eval_result="correct",
    )
    p49_state = _state(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
        grade="G6",
        semester="S2",
        unit="Recycle2",
        page_type="phonics",
        last_teacher_question="Can you say: Create a personal party shopping list.",
        last_eval_result="incorrect",
    )

    cases = [
        (
            "good_answer",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="Zoom would like a salad.",
                turn_label="answer_question",
                decision=_decision("confirm"),
                state=p31_state,
            ),
            "confirm_and_advance",
        ),
        (
            "task_echo",
            _plan(
                catalog=catalog,
                page_uid="TB-G6S2Recycle2-P49",
                block_uid="TB-G6S2Recycle2-P49-D4",
                learner_input="Create a personal party shopping list.",
                turn_label="answer_question",
                decision=_decision("hint"),
                state=p49_state,
            ),
            "convert_task_echo_to_answer",
        ),
        (
            "small_error",
            _plan(
                catalog=catalog,
                page_uid="TB-G6S2Recycle2-P49",
                block_uid="TB-G6S2Recycle2-P49-D4",
                learner_input="I bring apple.",
                turn_label="answer_question",
                decision=_decision("hint"),
                state=p49_state.model_copy(update={"last_eval_result": "partially_correct"}),
            ),
            "light_recast",
        ),
        (
            "incomplete_answer",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="salad",
                turn_label="answer_question",
                decision=_decision("hint"),
                state=p31_state.model_copy(update={"last_eval_result": "unclear"}),
            ),
            "prompt_missing_piece",
        ),
        (
            "refusal",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="No, I don't want to say it.",
                turn_label="answer_question",
                decision=_decision("hint"),
                state=p31_state.model_copy(update={"last_eval_result": "incorrect"}),
            ),
            "lower_pressure_reinvite",
        ),
        (
            "help_request",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="I don't know.",
                turn_label="ask_help",
                decision=_decision("hint"),
                state=p31_state.model_copy(update={"last_eval_result": None}),
            ),
            "give_one_step_hint",
        ),
        (
            "knowledge_question",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="What does salad mean?",
                turn_label="ask_knowledge",
                decision=PlannerDecision(
                    teaching_action="explain",
                    retrieval_mode="page",
                    response_focus="Answer the word question briefly.",
                ),
                state=p31_state.model_copy(update={"last_eval_result": None}),
            ),
            "answer_briefly_then_return",
        ),
        (
            "off_topic",
            _plan(
                catalog=catalog,
                page_uid="TB-G5S1U3-P31",
                block_uid="TB-G5S1U3-P31-D1",
                learner_input="I played football yesterday.",
                turn_label="social",
                decision=PlannerDecision(
                    teaching_action="redirect",
                    retrieval_mode="none",
                    response_focus="Return to the active story prompt.",
                ),
                state=p31_state.model_copy(update={"last_eval_result": None}),
            ),
            "redirect_to_active_task",
        ),
    ]

    for expected_signal, move_plan, expected_move in cases:
        payload = move_plan.to_prompt_payload()
        assert payload["schema_version"] == "peptutor-teaching-move-v1"
        assert payload["detected_signal"] == expected_signal
        assert payload["move"] == expected_move
        assert payload["rationale"]
        assert payload["evidence_fields_used"]
        assert payload["expected_next_learner_action"]


def test_teaching_move_planner_does_not_emit_page_specific_templates():
    catalog = _catalog()
    state = _state(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
        grade="G6",
        semester="S2",
        unit="Recycle2",
        page_type="phonics",
        last_teacher_question="Can you say: Create a personal party shopping list.",
        last_eval_result="incorrect",
    )

    payload = _plan(
        catalog=catalog,
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
        learner_input="Create a personal party shopping list.",
        turn_label="answer_question",
        decision=_decision("hint"),
        state=state,
    ).to_prompt_payload()
    combined_text = " ".join(
        str(value)
        for key, value in payload.items()
        if key not in {"schema_version", "detected_signal"}
    )

    assert "TB-" not in combined_text
    assert "P49" not in combined_text
    assert "Zoom" not in combined_text
    assert "Farewell party" not in combined_text


def test_runtime_prompt_receives_teaching_move_payload():
    captured: list[dict[str, object]] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        captured.append(json.loads(prompt))
        return "我们把任务句换成自己的答案，比如 cake。"

    runtime = LessonRuntime(
        _catalog(),
        responder=LessonResponder(_teacher_llm),
    )
    start = runtime.start_page("TB-G6S2Recycle2-P49", "student-1")
    runtime.handle_turn(start.state, "Create a personal party shopping list.")

    teaching_move = captured[-1]["teaching_move"]
    assert teaching_move["schema_version"] == "peptutor-teaching-move-v1"
    assert teaching_move["detected_signal"] == "task_echo"
    assert teaching_move["move"] == "convert_task_echo_to_answer"
    assert "expected_next_learner_action" in teaching_move
