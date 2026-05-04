import json

import pytest
from pydantic import ValidationError

from lightrag.orchestrator.lesson_persona import (
    DEFAULT_ALLOWED_PERSONA_INFLUENCES,
    DEFAULT_PROTECTED_LESSON_AUTHORITIES,
    DEFAULT_TEACHER_PERSONA_PROFILE_ID,
    DEFAULT_TEACHER_PERSONA_PROFILE_VERSION,
    AiriPerformancePlan,
    LearnerRelationshipProfile,
    LessonPersonaContext,
    TeacherPersonaProfile,
    build_airi_performance_plan_for_turn,
    build_classroom_affect_state_for_turn,
    build_default_lesson_persona_context,
    build_learner_relationship_profile_from_memory,
    build_lesson_persona_context_for_turn,
    load_default_teacher_persona_profile,
)
from lightrag.orchestrator.simplemem_prompt_memory import LearnerMemorySummary


def test_default_teacher_persona_profile_is_versioned_and_deterministic():
    first = load_default_teacher_persona_profile()
    second = load_default_teacher_persona_profile()

    assert first.profile_id == DEFAULT_TEACHER_PERSONA_PROFILE_ID
    assert first.version == DEFAULT_TEACHER_PERSONA_PROFILE_VERSION
    assert first.display_name == "米粒"
    assert "Guangxi Normal University" in first.role
    assert any("learner's actual words" in item for item in first.teaching_style)
    assert any("waiter questions" in item for item in first.teaching_style)
    assert first.model_dump() == second.model_dump()
    assert first is not second

    first.stable_traits.append("mutated in one test object")
    assert "mutated in one test object" not in second.stable_traits


def test_default_persona_boundaries_protect_lesson_authority():
    profile = load_default_teacher_persona_profile()
    boundaries = profile.boundaries

    assert boundaries.content_authority == "lesson_runtime"
    assert boundaries.presentation_authority == "airi_runtime"
    assert boundaries.allowed_to_shape == list(DEFAULT_ALLOWED_PERSONA_INFLUENCES)
    assert boundaries.must_not_change == list(DEFAULT_PROTECTED_LESSON_AUTHORITIES)
    assert not boundaries.can_change_target_answer
    assert not boundaries.can_change_correctness_judgment
    assert not boundaries.can_change_page_progression
    assert "target_answer" not in boundaries.allowed_to_shape
    assert "speech_style" not in boundaries.must_not_change


def test_lesson_persona_context_is_compact_and_json_serializable():
    context = build_default_lesson_persona_context(
        student_id="student-1",
        relationship_signals=["slow_split_practice"],
    )

    payload = context.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=False)

    assert context.schema_version == "lesson-persona-context/v1"
    assert context.relationship.student_id == "student-1"
    assert context.relationship.relationship_signals == ["slow_split_practice"]
    assert payload["profile"]["profile_id"] == DEFAULT_TEACHER_PERSONA_PROFILE_ID
    assert len(encoded) < 6000


def test_persona_models_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        TeacherPersonaProfile.model_validate(
            {
                "profile_id": "test",
                "version": "v1",
                "display_name": "Teacher",
                "role": "Tutor",
                "stable_traits": ["calm"],
                "teaching_style": ["short"],
                "can_override_page": True,
            }
        )

    with pytest.raises(ValidationError):
        LessonPersonaContext.model_validate(
            {
                "profile": load_default_teacher_persona_profile().model_dump(),
                "relationship": {"student_id": "student-1"},
                "target_answer": "I can overwrite the lesson.",
            }
        )


def test_airi_performance_plan_carries_presentation_only():
    plan = AiriPerformancePlan(
        emotion="thinking",
        expression="thinking",
        motion="Explain",
        speech_style="slow_split",
        mouth_intensity=0.5,
    )
    payload = plan.model_dump()

    assert payload["content_source"] == "lesson_runtime_teacher_response"
    assert "teacher_response" not in payload
    assert "target_answer" not in payload

    with pytest.raises(ValidationError):
        AiriPerformancePlan.model_validate(
            {
                "emotion": "thinking",
                "expression": "thinking",
                "motion": "Explain",
                "speech_style": "slow_split",
                "teacher_response": "AIRI should not replace lesson text.",
            }
        )


def test_relationship_profile_rejects_empty_values_and_deduplicates_signals():
    with pytest.raises(ValidationError):
        LearnerRelationshipProfile(
            student_id=" ",
            relationship_signals=["slow_split_practice"],
        )

    profile = LearnerRelationshipProfile(
        student_id="student-1",
        relationship_signals=["slow_split_practice", "slow_split_practice"],
    )

    assert profile.relationship_signals == ["slow_split_practice"]


def test_relationship_profile_assembles_from_prompt_memory():
    memory = LearnerMemorySummary(
        student_id="student-1",
        common_mistakes=[
            "Learner often omits some in full sentence answers.",
            "Learner often omits some in full sentence answers.",
        ],
        stable_preferences=[
            "Learner prefers Chinese explanation before retry.",
            "Learner likes slow split practice.",
        ],
        stable_mastery_signals=[
            "Learner can now answer I'd like some water correctly."
        ],
        semantic_memories=["Learner gets shy when asked to answer aloud."],
    )

    relationship = build_learner_relationship_profile_from_memory(
        student_id="student-1",
        learner_memory=memory,
    )

    assert relationship.common_mistakes == [
        "Learner often omits some in full sentence answers."
    ]
    assert relationship.preferences == [
        "Learner prefers Chinese explanation before retry.",
        "Learner likes slow split practice.",
    ]
    assert relationship.relationship_signals == [
        "stored_mistake_pattern",
        "slow_split_practice",
        "chinese_scaffold",
        "target_sentence_completion_risk",
        "low_confidence_risk",
        "recent_mastery_available",
    ]


def test_affect_state_is_deterministic_and_explainable():
    affect = build_classroom_affect_state_for_turn(
        turn_label="ask_help",
        evaluation="incorrect",
        same_goal_attempt_count=2,
        repair_mode="sentence_drill",
        recent_turn_labels=["page_entry", "answer_question", "ask_help"],
        relationship_signals=["low_confidence_risk"],
    )

    assert affect.student_confidence == "low"
    assert affect.teacher_energy == "encouraging"
    assert affect.stuckness == 1.0
    assert affect.recent_turn_labels == ["page_entry", "answer_question", "ask_help"]

    recovered = build_classroom_affect_state_for_turn(
        turn_label="answer_question",
        evaluation="correct",
        same_goal_attempt_count=0,
        recent_turn_labels=["page_entry", "answer_question"],
    )

    assert recovered.student_confidence == "high"
    assert recovered.teacher_energy == "calm"
    assert recovered.stuckness == 0.0


def test_lesson_persona_context_for_turn_maps_airi_performance_plan():
    memory = LearnerMemorySummary(
        student_id="student-1",
        common_mistakes=["Learner often omits some in full sentence answers."],
        preferences=["Learner likes slow split practice."],
    )

    context = build_lesson_persona_context_for_turn(
        student_id="student-1",
        learner_memory=memory,
        turn_label="answer_question",
        teaching_action="hint",
        evaluation="incorrect",
        same_goal_attempt_count=1,
        repair_mode="repeat",
        recent_turn_labels=["page_entry", "answer_question"],
    )

    assert context.profile.profile_id == DEFAULT_TEACHER_PERSONA_PROFILE_ID
    assert context.relationship.relationship_signals == [
        "stored_mistake_pattern",
        "slow_split_practice",
        "target_sentence_completion_risk",
    ]
    assert context.affect_state.student_confidence == "low"
    assert context.airi_performance.emotion == "correction"
    assert context.airi_performance.motion == "Explain"
    assert context.airi_performance.speech_style == "gentle_correction"
    assert context.airi_performance.content_source == (
        "lesson_runtime_teacher_response"
    )


def test_airi_performance_plan_defers_interrupt_during_knowledge_explanation():
    affect = build_classroom_affect_state_for_turn(
        turn_label="ask_knowledge",
        evaluation=None,
    )

    plan = build_airi_performance_plan_for_turn(
        affect_state=affect,
        turn_label="ask_knowledge",
        teaching_action="explain",
    )

    assert plan.motion == "Explain"
    assert plan.speech_style == "normal"
    assert plan.interrupt_policy == "finish_current_sentence"


def test_airi_performance_plan_keeps_redirect_barge_in_allowed():
    affect = build_classroom_affect_state_for_turn(
        turn_label="answer_question",
        evaluation="off_topic",
    )

    plan = build_airi_performance_plan_for_turn(
        affect_state=affect,
        turn_label="answer_question",
        teaching_action="redirect",
        evaluation="off_topic",
    )

    assert plan.motion == "Listen"
    assert plan.speech_style == "short_prompt"
    assert plan.interrupt_policy == "barge_in_allowed"
