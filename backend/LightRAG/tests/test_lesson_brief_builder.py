import json
from pathlib import Path

from lightrag.orchestrator.lesson_brief_builder import LessonBriefBuilder
from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.pedagogy.planner import PlannerDecision
from lightrag.pedagogy.responder import LessonResponder


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _general_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _curriculum_map_path() -> Path:
    return _repo_root() / "app/knowledge/structured/curriculum-map.json"


def _lookup() -> LessonEvidenceLookup:
    return LessonEvidenceLookup(
        PilotLessonCatalog(manifest_path=_general_manifest_path()),
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
    last_teacher_question: str | None = None,
    last_eval_result: str | None = None,
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
        current_activity_type="page_entry",
        awaiting_answer=True,
        last_teacher_question=last_teacher_question,
        recent_turn_labels=["page_entry"],
        last_eval_result=last_eval_result,
    )


def _decision() -> PlannerDecision:
    return PlannerDecision(
        teaching_action="page_intro",
        retrieval_mode="none",
        response_focus="Open the active block with evidence-backed preparation.",
    )


def test_lesson_brief_builder_prepares_story_page_from_exact_overlay_content():
    evidence = _lookup().lookup(
        page_uid="TB-G5S1U3-P31",
        block_uid="TB-G5S1U3-P31-D1",
    )
    brief = LessonBriefBuilder().build(
        lesson_evidence=evidence,
        learner_input="",
        turn_label="page_entry",
        decision=_decision(),
        state=_state(
            page_uid="TB-G5S1U3-P31",
            block_uid="TB-G5S1U3-P31-D1",
            grade="G5",
            semester="S1",
            unit="U3",
            page_type="story",
            last_teacher_question="What would Zoom like to eat?",
        ),
    )
    payload = brief.to_prompt_payload()

    assert payload["page_context"]["page_type"] == "story"
    assert payload["page_context"]["lesson_title"] == "Zoom and Zip salad story"
    assert any("Zoom is hungry" in item["summary"] for item in payload["materials"])
    assert "salad" in payload["support_vocabulary"]
    assert "tomatoes" in payload["support_vocabulary"]
    assert "Zoom would like a salad." in payload["answer_scope"]["acceptable_answers"]
    assert payload["progression"]["condition"] == (
        "Advance only when the active answer rubric is correct or acceptable."
    )


def test_lesson_brief_builder_turns_party_task_into_answer_scope_not_script():
    evidence = _lookup().lookup(
        page_uid="TB-G6S2Recycle2-P49",
        block_uid="TB-G6S2Recycle2-P49-D4",
    )
    brief = LessonBriefBuilder().build(
        lesson_evidence=evidence,
        learner_input="Create a personal party shopping list.",
        turn_label="answer_question",
        decision=PlannerDecision(
            teaching_action="hint",
            retrieval_mode="none",
            response_focus="Repair a task-instruction echo.",
        ),
        state=_state(
            page_uid="TB-G6S2Recycle2-P49",
            block_uid="TB-G6S2Recycle2-P49-D4",
            grade="G6",
            semester="S2",
            unit="Recycle2",
            page_type="phonics",
            last_teacher_question="Can you say: Create a personal party shopping list.",
            last_eval_result="incorrect",
        ),
    )
    payload = brief.to_prompt_payload()

    assert payload["answer_scope"]["expected_answer_shape"] == (
        "A concrete party-list item or a short first-person list sentence, "
        "for example: cake / orange juice / I'm going to bring cake."
    )
    assert payload["answer_scope"]["must_not_accept"] == [
        "Create a personal party shopping list."
    ]
    assert "cake" in payload["answer_scope"]["acceptable_answers"]
    assert "orange juice" in payload["support_vocabulary"]
    assert payload["likely_mistakes"][0]["likely_error"] == "task_instruction_echo"
    assert "do not advance on the task instruction itself" in payload["progression"][
        "condition"
    ]


def test_runtime_prompt_receives_compact_lesson_brief_slice():
    captured: list[dict[str, object]] = []

    def _teacher_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        _ = (system_prompt, history_messages, kwargs)
        captured.append(json.loads(prompt))
        return "我们读 Zoom 和 Zip 做沙拉的小故事，先看看 Zoom 想吃什么。"

    runtime = LessonRuntime(
        PilotLessonCatalog(manifest_path=_general_manifest_path()),
        responder=LessonResponder(_teacher_llm),
    )

    runtime.start_page("TB-G5S1U3-P31", "student-1")

    lesson_brief = captured[0]["lesson_brief"]
    teaching_move = captured[0]["teaching_move"]
    assert lesson_brief["schema_version"] == "peptutor-current-turn-brief-v2"
    assert teaching_move["schema_version"] == "peptutor-teaching-move-v1"
    assert teaching_move["detected_signal"] == "page_entry"
    assert set(
        [
            "teaching_focus",
            "materials",
            "answer_scope",
            "support_vocabulary",
            "likely_mistakes",
            "progression",
        ]
    ).issubset(lesson_brief)
    assert any("Zoom is hungry" in item["summary"] for item in lesson_brief["materials"])
    assert "books" not in lesson_brief
    assert "units" not in lesson_brief
