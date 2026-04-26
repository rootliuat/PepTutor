from pathlib import Path

from lightrag.orchestrator.lesson_dialogue_quality_eval import (
    default_dialogue_quality_gold_path,
    evaluate_lesson_dialogue_quality,
    render_dialogue_quality_eval_report,
)


def test_lesson_dialogue_quality_gold_samples_match_current_baseline():
    report = evaluate_lesson_dialogue_quality(
        gold_path=default_dialogue_quality_gold_path(),
        manifest_path=Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json",
    )

    assert report.sample_count == 12
    assert report.overall.strict_pass_count == 12
    assert report.overall.retrieval_contract_pass_count == 12
    assert report.overall.source_grounding_contract_pass_count == 12
    assert report.overall.lesson_brief_contract_pass_count == 12
    assert report.overall.teaching_move_contract_pass_count == 12
    assert report.overall.state_progression_contract_pass_count == 12
    assert report.overall.prompt_contract_pass_count == 12
    assert report.overall.response_quality_pass_count == 12
    assert report.overall.persona_contract_pass_count == 12
    assert report.overall.memory_contract_pass_count == 12
    assert report.overall.average_quality_score == 1.0
    assert not report.failed_outcomes

    outcomes = {outcome.sample_id: outcome for outcome in report.outcomes}
    p31 = outcomes["g5_p31_story_overlay_stays_story_grounded"]
    assert p31.actual_lesson_evidence_page_type == "story"
    assert p31.actual_lesson_evidence_exact_block_uid == "TB-G5S1U3-P31-D1"
    assert p31.actual_teaching_move_signal == "incomplete_answer"
    assert p31.actual_teaching_move == "prompt_missing_piece"
    assert p31.actual_state_current_block_uid == "TB-G5S1U3-P31-D1"

    p49_task_echo = outcomes["g6_p49_task_repetition_is_not_completed_answer"]
    assert p49_task_echo.actual_teaching_move_signal == "task_echo"
    assert p49_task_echo.actual_teaching_move == "convert_task_echo_to_answer"
    assert (
        p49_task_echo.actual_lesson_evidence_exact_block_uid
        == "TB-G6S2Recycle2-P49-D4"
    )


def test_lesson_dialogue_quality_report_renders_failure_safe_summary():
    report = evaluate_lesson_dialogue_quality(
        gold_path=default_dialogue_quality_gold_path(),
        manifest_path=Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json",
    )

    rendered = render_dialogue_quality_eval_report(report)

    assert "Lesson dialogue quality eval" in rendered
    assert "strict=12/12" in rendered
    assert "retrieval=100%" in rendered
    assert "source=100%" in rendered
    assert "brief=100%" in rendered
    assert "move=100%" in rendered
    assert "state=100%" in rendered
    assert "prompt=100%" in rendered
    assert "response=100%" in rendered
    assert "persona=100%" in rendered
    assert "memory=100%" in rendered
    assert "PASS" in rendered
