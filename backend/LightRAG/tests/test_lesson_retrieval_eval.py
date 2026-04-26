from pathlib import Path

from lightrag.orchestrator.lesson_retrieval_eval import (
    default_eval_gold_path,
    evaluate_lesson_retrieval,
)


def test_lesson_retrieval_eval_gold_samples_match_current_baseline():
    report = evaluate_lesson_retrieval(
        gold_path=default_eval_gold_path(),
        manifest_path=Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json",
    )

    assert report.sample_count == 26
    assert report.overall.strict_pass_count == 26
    assert report.overall.scope_match_count == 26
    assert report.overall.top1_block_hit_count == 26
    assert report.overall.top3_block_hit_count == 26
    assert report.overall.cross_grade_leakage_count == 0
    assert report.overall.support_expectation_count == 3
    assert report.overall.support_hit_count == 3
    assert not report.failed_outcomes


def test_lesson_retrieval_eval_splits_metrics_by_grade():
    report = evaluate_lesson_retrieval(
        gold_path=default_eval_gold_path(),
        manifest_path=Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json",
    )

    assert sorted(report.by_grade) == ["G5", "G6"]
    assert report.by_grade["G5"].sample_count == 9
    assert report.by_grade["G5"].strict_pass_count == 9
    assert report.by_grade["G5"].support_expectation_count == 3
    assert report.by_grade["G6"].sample_count == 17
    assert report.by_grade["G6"].strict_pass_count == 17
    assert report.by_grade["G6"].support_expectation_count == 0
