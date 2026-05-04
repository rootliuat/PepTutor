import json
from pathlib import Path

from lightrag.orchestrator.lesson_brief_builder import LessonBriefBuilder
from lightrag.orchestrator.lesson_evidence import LessonEvidenceLookup
from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.teaching_move_planner import (
    ClassroomTargetPhraseCandidate,
    TeachingMovePlanner,
    classroom_target_phrase_reasons,
    select_classroom_target_phrase,
)
from lightrag.pedagogy.teaching_move import TeachingMoveActionContract
from lightrag.pedagogy.planner import PlannerDecision
from lightrag.pedagogy.responder import LessonResponder


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _general_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _general_overlay_manifest_path() -> Path:
    return (
        _repo_root()
        / "app/knowledge/structured/general/general-with-pilot-overrides-manifest.json"
    )


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


def test_teaching_move_planner_single_block_guard_payload_is_structural():
    payload = TeachingMovePlanner().plan_single_block_guard(
        learner_input="我想学第二块",
    ).to_prompt_payload()

    assert payload["schema_version"] == "peptutor-teaching-move-v1"
    assert payload["detected_signal"] == "module_navigation_unavailable"
    assert payload["move"] == "single_block_guard"
    assert payload["teaching_action"] == "redirect"
    assert "page_overview.modules" in payload["evidence_fields_used"]
    assert "runtime_state.current_block_uid" in payload["evidence_fields_used"]
    combined_text = " ".join(str(value) for value in payload.values())
    assert "第二块" not in combined_text
    assert "TB-" not in combined_text


def test_teaching_move_planner_vocab_answer_return_payload_is_structural():
    payload = TeachingMovePlanner().plan_vocab_answer_return(
        learner_input="What does stayed at home mean?",
        retrieval_mode="unit",
        return_anchor="What did you do last weekend?",
        active_prompt="What did you do last weekend?",
        retrieval_count=2,
        support_count=1,
    ).to_prompt_payload()

    assert payload["schema_version"] == "peptutor-teaching-move-v1"
    assert payload["detected_signal"] == "vocabulary_question"
    assert payload["move"] == "vocab_answer_return"
    assert payload["teaching_action"] == "explain"
    assert "return_anchor" in payload["evidence_fields_used"]
    assert "support_hits" in payload["evidence_fields_used"]
    assert payload["payload_fields"] == {
        "query_term": "stayed at home",
        "retrieval_mode": "unit",
        "return_anchor": "What did you do last weekend?",
        "active_prompt": "What did you do last weekend?",
        "return_to_current_task": True,
        "retrieval_evidence_count": 2,
        "support_evidence_count": 1,
        "target_role": "question",
        "expected_student_action": "answer",
        "question_target": "What did you do last weekend?",
        "answer_target": "",
        "answer_frame": "I ... last weekend.",
        "action_source": "active_prompt",
        "preserve_page_uid": "",
        "preserve_block_uid": "",
        "target_phrase": "What did you do last weekend?",
    }
    assert "Do not change the current page or block." in payload["constraints"]


def test_teaching_move_action_contract_validates_allowed_fields():
    contract = TeachingMoveActionContract.from_payload_fields(
        {
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": "How tall is it?",
            "answer_target": "",
            "answer_frame": "It's ... metres tall.",
            "action_source": "block_core_pattern",
            "preserve_page_uid": "TB-G6S2U1-P4",
            "preserve_block_uid": "TB-G6S2U1-P4-D2",
            "active_prompt": "How tall is it?",
            "return_anchor": "How tall is it?",
            "target_phrase": "How tall is it?",
        }
    )

    assert contract.to_payload_fields() == {
        "target_role": "question",
        "expected_student_action": "answer",
        "question_target": "How tall is it?",
        "answer_target": "",
        "answer_frame": "It's ... metres tall.",
        "action_source": "block_core_pattern",
        "preserve_page_uid": "TB-G6S2U1-P4",
        "preserve_block_uid": "TB-G6S2U1-P4-D2",
        "active_prompt": "How tall is it?",
        "return_anchor": "How tall is it?",
        "target_phrase": "How tall is it?",
    }


def test_teaching_move_action_contract_treats_optional_none_as_empty_string():
    contract = TeachingMoveActionContract.from_payload_fields(
        {
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": "How tall is it?",
            "answer_target": None,
            "answer_frame": "It's ... metres tall.",
            "action_source": "block_core_pattern",
            "preserve_page_uid": "TB-G6S2U1-P4",
            "preserve_block_uid": "TB-G6S2U1-P4-D2",
            "active_prompt": "How tall is it?",
            "return_anchor": None,
            "target_phrase": "How tall is it?",
        }
    )

    assert contract.answer_target == ""
    assert contract.return_anchor == ""


def test_teaching_move_action_contract_rejects_unknown_role_and_non_strings():
    assert TeachingMoveActionContract.try_from_payload_fields(
        {
            "target_role": "mystery",
            "expected_student_action": "answer",
            "question_target": "How tall is it?",
            "answer_target": "",
            "answer_frame": "It's ... metres tall.",
            "action_source": "block_core_pattern",
            "active_prompt": "How tall is it?",
            "return_anchor": "How tall is it?",
            "target_phrase": "How tall is it?",
        }
    ) is None
    assert TeachingMoveActionContract.try_from_payload_fields(
        {
            "target_role": "question",
            "expected_student_action": "answer",
            "question_target": 123,
            "answer_target": "",
            "answer_frame": "It's ... metres tall.",
            "action_source": "block_core_pattern",
            "active_prompt": "How tall is it?",
            "return_anchor": "How tall is it?",
            "target_phrase": "How tall is it?",
        }
    ) is None


def test_teaching_move_action_contract_rejects_phonics_without_answer_target():
    assert TeachingMoveActionContract.try_from_payload_fields(
        {
            "target_role": "phonics",
            "expected_student_action": "repeat",
            "question_target": "",
            "answer_target": "",
            "answer_frame": "",
            "action_source": "phonics_context",
            "active_prompt": "Listen and repeat: clean.",
            "return_anchor": "Listen and repeat: clean.",
            "target_phrase": "Listen and repeat: clean.",
        }
    ) is None


def test_teaching_move_planner_vocab_answer_return_uses_anchor_as_active_prompt_fallback():
    payload = TeachingMovePlanner().plan_vocab_answer_return(
        learner_input="What does because mean?",
        retrieval_mode="unit",
        return_anchor="I like spring because there are beautiful flowers everywhere.",
        active_prompt="",
        retrieval_count=2,
        support_count=1,
    ).to_prompt_payload()

    assert payload["payload_fields"]["active_prompt"] == (
        "I like spring because there are beautiful flowers everywhere."
    )
    assert payload["payload_fields"]["return_to_current_task"] is True


def test_teaching_move_planner_gentle_redirect_payload_is_structural():
    payload = TeachingMovePlanner().plan_gentle_redirect(
        learner_input="I want to play basketball.",
        interpreted_intent="off_topic",
        current_target="Talk about favourite food.",
        target_phrase="What's your favourite food?",
        active_prompt="What's your favourite food?",
        return_anchor="What's your favourite food?",
        next_action="return_to_active_task",
        correction_kind="incorrect",
        route="answer_turn_policy",
        turn_label="answer_question",
        preserve_page_uid="TB-G5S1U3-P22",
        preserve_block_uid="TB-G5S1U3-P22-D1",
    ).to_prompt_payload()

    assert payload["schema_version"] == "peptutor-teaching-move-v1"
    assert payload["detected_signal"] == "off_topic"
    assert payload["move"] == "gentle_redirect"
    assert payload["teaching_action"] == "redirect"
    assert payload["payload_fields"] == {
        "learner_input": "I want to play basketball.",
        "interpreted_intent": "off_topic",
        "current_target": "Talk about favourite food.",
        "target_phrase": "What's your favourite food?",
        "active_prompt": "What's your favourite food?",
        "return_anchor": "What's your favourite food?",
        "next_action": "return_to_active_task",
        "correction_kind": "incorrect",
        "route": "answer_turn_policy",
        "turn_label": "answer_question",
        "preserve_page_uid": "TB-G5S1U3-P22",
        "preserve_block_uid": "TB-G5S1U3-P22-D1",
        "target_role": "question",
        "expected_student_action": "answer",
        "question_target": "What's your favourite food?",
        "answer_target": "",
        "answer_frame": "My favourite food is ...",
        "action_source": "active_prompt",
    }
    assert "Do not change the runtime route." in payload["constraints"]


def _gentle_payload_for_block(
    *,
    page_uid: str,
    block_uid: str,
    target_phrase: str,
    active_prompt: str,
    return_anchor: str,
    learner_input: str = "water",
) -> dict[str, object]:
    catalog = _catalog()
    block = catalog.get_block(block_uid)
    payload = TeachingMovePlanner().plan_gentle_redirect(
        learner_input=learner_input,
        interpreted_intent="off_topic",
        current_target=block.teaching_goal,
        target_phrase=target_phrase,
        active_prompt=active_prompt,
        return_anchor=return_anchor,
        next_action="return_to_active_task",
        correction_kind="incorrect",
        route="answer_turn_policy",
        turn_label="answer_question",
        preserve_page_uid=page_uid,
        preserve_block_uid=block_uid,
        block=block,
    ).to_prompt_payload()
    return payload["payload_fields"]


def test_gentle_redirect_action_payload_distinguishes_direction_question_and_answer():
    question_fields = _gentle_payload_for_block(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        target_phrase="Where is the museum shop?",
        active_prompt="Where is the museum shop?",
        return_anchor="Where is the museum shop?",
    )

    assert question_fields["target_role"] == "question"
    assert question_fields["expected_student_action"] == "answer"
    assert question_fields["question_target"] == "Where is the museum shop?"
    assert question_fields["answer_target"] == "It's near the door."
    assert question_fields["answer_frame"] == "It's near ..."
    assert question_fields["action_source"] == "block_core_pattern"

    answer_fields = _gentle_payload_for_block(
        page_uid="TB-G6S1U1-P4",
        block_uid="TB-G6S1U1-P4-D2",
        target_phrase="It's near the door.",
        active_prompt="Where is the museum shop?",
        return_anchor="It's near the door.",
    )

    assert answer_fields["target_role"] == "answer"
    assert answer_fields["expected_student_action"] == "repeat"
    assert answer_fields["question_target"] == "Where is the museum shop?"
    assert answer_fields["answer_target"] == "It's near the door."
    assert answer_fields["answer_frame"] == "It's near ..."


def test_gentle_redirect_action_payload_keeps_height_question_with_answer_frame():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        target_phrase="How tall is it?",
        active_prompt="How tall is it?",
        return_anchor="How tall is it?",
        learner_input="How tall are you?",
    )

    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "How tall is it?"
    assert fields["answer_frame"] == "It's ... metres tall."
    assert fields["action_source"] == "block_core_pattern"


def test_gentle_redirect_action_payload_adds_last_weekend_answer_frame():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U2-P13",
        block_uid="TB-G6S2U2-P13-D2",
        target_phrase="What did you do last weekend?",
        active_prompt="What did you do last weekend?",
        return_anchor="What did you do last weekend?",
        learner_input="I stayed at home.",
    )

    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "What did you do last weekend?"
    assert fields["answer_frame"] == "I ... last weekend."
    assert fields["action_source"] == "block_core_pattern"


def test_gentle_redirect_action_payload_rejects_personal_height_as_object_target():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D2",
        target_phrase="How tall are you",
        active_prompt="How tall is it?",
        return_anchor="How tall are you",
        learner_input="How tall are you?",
    )

    assert fields["target_phrase"] == "How tall is it?"
    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "How tall is it?"
    assert fields["question_target"] != "How tall are you"
    assert fields["answer_frame"] == "It's ... metres tall."
    assert fields["action_source"] == "block_core_pattern"


def test_gentle_redirect_action_payload_treats_height_declaratives_as_answers():
    first_person_fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        target_phrase="I'm 1.6 metres tall?",
        active_prompt="I'm 1.6 metres tall.",
        return_anchor="I'm 1.6 metres tall?",
        learner_input="water",
    )

    assert first_person_fields["target_phrase"] == "I'm 1.6 metres tall."
    assert first_person_fields["target_role"] == "answer"
    assert first_person_fields["expected_student_action"] == "repeat"
    assert first_person_fields["question_target"] == ""
    assert first_person_fields["answer_target"] == "I'm 1.6 metres tall."

    comparison_fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        target_phrase="I'm taller than this dinosaur?",
        active_prompt="I'm 1.6 metres tall?",
        return_anchor="I'm taller than this dinosaur?",
        learner_input="water",
    )

    assert comparison_fields["target_phrase"] == "I'm taller than this dinosaur."
    assert comparison_fields["target_role"] == "answer"
    assert comparison_fields["expected_student_action"] == "repeat"
    assert comparison_fields["question_target"] == ""
    assert comparison_fields["answer_target"] == "I'm taller than this dinosaur."


def test_gentle_redirect_action_payload_cleans_orphan_target_quote():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P2",
        block_uid="TB-G6S2U1-P2-D1",
        target_phrase="I'm 1.6 metres tall'.",
        active_prompt="I'm 1.6 metres tall'.",
        return_anchor="I'm 1.6 metres tall'.",
        learner_input="water",
    )

    assert fields["target_phrase"] == "I'm 1.6 metres tall."
    assert fields["target_role"] == "answer"
    assert fields["answer_target"] == "I'm 1.6 metres tall."


def test_gentle_redirect_action_payload_adds_personal_height_answer_frame():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S2U1-P4",
        block_uid="TB-G6S2U1-P4-D4",
        target_phrase="How tall are you?",
        active_prompt="How tall are you?",
        return_anchor="How tall are you?",
        learner_input="water",
    )

    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "How tall are you?"
    assert fields["answer_frame"] == "I'm ... metres tall."


def test_gentle_redirect_action_payload_records_story_answer_frame():
    catalog = PilotLessonCatalog(manifest_path=_general_overlay_manifest_path())
    block = catalog.get_block("TB-G5S1U3-P31-D1")
    payload = TeachingMovePlanner().plan_gentle_redirect(
        learner_input="Zip",
        interpreted_intent="short_answer_pullback",
        current_target=block.teaching_goal,
        target_phrase="What would Zoom like to eat?",
        active_prompt="What would Zoom like to eat?",
        return_anchor="What would Zoom like to eat?",
        next_action="connect_or_redirect_to_current_target",
        correction_kind="incorrect",
        route="answer_turn_policy",
        turn_label="answer_question",
        preserve_page_uid="TB-G5S1U3-P31",
        preserve_block_uid="TB-G5S1U3-P31-D1",
        block=block,
    ).to_prompt_payload()
    fields = payload["payload_fields"]

    assert fields["target_role"] == "story"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "What would Zoom like to eat?"
    assert fields["answer_target"] == "Zoom would like a salad."
    assert fields["answer_frame"] == "Zoom would like ..."
    assert fields["action_source"] == "story_context"


def test_gentle_redirect_action_payload_records_phonics_repeat_target():
    fields = _gentle_payload_for_block(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D1",
        target_phrase="Learn the consonant blend 'cl' as in 'clean'.",
        active_prompt="Can you say: Learn the consonant blend 'cl' as in 'clean'.",
        return_anchor="Learn the consonant blend 'cl' as in 'clean'.",
        learner_input="I want to play basketball.",
    )

    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "clean"
    assert fields["answer_frame"] == ""
    assert fields["action_source"] == "phonics_context"


def test_gentle_redirect_action_payload_extracts_phonics_target_from_word_list():
    fields = _gentle_payload_for_block(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D2",
        target_phrase="Class, clock, plate, eggplant, clean, play.",
        active_prompt="Class, clock, plate, eggplant, clean, play.",
        return_anchor="Class, clock, plate, eggplant, clean, play.",
        learner_input="water",
    )

    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "class"
    assert fields["answer_target"] != "water"


def test_gentle_redirect_action_payload_extracts_phonics_target_from_instruction():
    fields = _gentle_payload_for_block(
        page_uid="TB-G5S2U1-P6",
        block_uid="TB-G5S2U1-P6-D2",
        target_phrase="Listen and repeat: clean.",
        active_prompt="Class, clock, plate, eggplant, clean, play.",
        return_anchor="Listen and repeat: clean.",
        learner_input="I want to play basketball.",
    )

    assert fields["target_role"] == "phonics"
    assert fields["expected_student_action"] == "repeat"
    assert fields["question_target"] == ""
    assert fields["answer_target"] == "clean"
    assert fields["answer_target"] != "basketball"


def test_gentle_redirect_action_payload_adds_suggestion_answer_frame():
    fields = _gentle_payload_for_block(
        page_uid="TB-G6S1U2-P19",
        block_uid="TB-G6S1U2-P19-D3",
        target_phrase="What suggestions will you give to your friends? Make a poster.",
        active_prompt="What suggestions will you give to your friends? Make a poster.",
        return_anchor="What suggestions will you give to your friends?",
        learner_input="sled",
    )

    assert fields["target_role"] == "question"
    assert fields["expected_student_action"] == "answer"
    assert fields["question_target"] == "What suggestions will you give to your friends?"
    assert fields["answer_frame"] == "You should ..."


def test_gentle_redirect_action_payload_uses_conservative_phrase_fallback():
    fields = TeachingMovePlanner().plan_gentle_redirect(
        learner_input="water",
        interpreted_intent="off_topic",
        current_target="Practice a short classroom phrase.",
        target_phrase="classroom phrase",
        active_prompt="",
        return_anchor="",
        next_action="return_to_active_task",
        correction_kind="incorrect",
        route="answer_turn_policy",
        turn_label="answer_question",
        preserve_page_uid="TB-G0S0U0-P1",
        preserve_block_uid="TB-G0S0U0-P1-D1",
    ).to_prompt_payload()["payload_fields"]

    assert fields["target_role"] == "phrase"
    assert fields["expected_student_action"] == "read"
    assert fields["action_source"] == "fallback_conservative"


def test_select_classroom_target_phrase_rejects_bad_redirect_targets():
    cases = [
        (
            "Can you try",
            "I'm 1.6 metres tall.",
            "target_phrase_is_teacher_instruction",
        ),
        ("I'm.", "I'm 1.6 metres tall.", "target_phrase_unhelpful_short_fragment"),
        (
            "suggestion.",
            "What suggestions will you give to your friends? Make a poster.",
            "target_phrase_unhelpful_short_fragment",
        ),
        (
            "Comprehension ques",
            "What does the story tell us?",
            "target_phrase_looks_truncated",
        ),
        (
            "A table showing tr",
            "You must stop at a red light.",
            "target_phrase_looks_truncated",
        ),
        ("Let's talk", "Where is the museum shop?", "target_phrase_too_generic"),
        ("Robin", "What is Robin's new feature?", "target_phrase_too_generic"),
    ]

    for bad_phrase, fallback_phrase, reason in cases:
        selection = select_classroom_target_phrase(
            [
                ClassroomTargetPhraseCandidate("state", bad_phrase),
                ClassroomTargetPhraseCandidate("block.core_patterns", fallback_phrase),
            ]
        )

        assert reason in classroom_target_phrase_reasons(bad_phrase)
        assert selection.phrase == fallback_phrase


def test_select_classroom_target_phrase_extracts_instruction_payload():
    selection = select_classroom_target_phrase(
        [
            ClassroomTargetPhraseCandidate(
                "state",
                "Can you try: I'm 1.6 metres tall.",
            )
        ]
    )

    assert selection.phrase == "I'm 1.6 metres tall."
    assert selection.source == "state"


def test_select_classroom_target_phrase_strips_visible_instruction_wrappers():
    selection = select_classroom_target_phrase(
        [
            ("active_prompt", "Try to say: I often get up at 7 o'clock."),
            ("return_anchor", "Say after me: clean."),
        ],
        allow_short_word_target=True,
    )

    assert selection.phrase == "I often get up at 7 o'clock."
    assert "Try to say" not in selection.phrase
    assert selection.source == "active_prompt"


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
    selected = runtime.handle_turn(start.state, "第四块")
    runtime.handle_turn(selected.state, "Create a personal party shopping list.")

    teaching_move = captured[-1]["teaching_move"]
    assert teaching_move["schema_version"] == "peptutor-teaching-move-v1"
    assert teaching_move["detected_signal"] == "task_echo"
    assert teaching_move["move"] == "convert_task_echo_to_answer"
    assert "expected_next_learner_action" in teaching_move
