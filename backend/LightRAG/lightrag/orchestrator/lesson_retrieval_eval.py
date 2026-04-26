"""Offline gold-set evaluation for lesson retrieval behavior."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_retrieval import ScopedRetriever
from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog
from lightrag.orchestrator.support_asset_retrieval import SupportAssetRetriever
from lightrag.pedagogy.types import RetrievalMode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_eval_gold_path() -> Path:
    return _repo_root() / "app/knowledge/evals/lesson-retrieval-gold.json"


def default_manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


class LessonRetrievalEvalSample(BaseModel):
    """One gold query with expected retrieval scope and hits."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    grade: str
    semester: str
    unit: str
    page_uid: str
    current_block_uid: str
    query: str
    expected_mode: RetrievalMode
    expected_block_uids: list[str] = Field(min_length=1)
    expected_support_entry_uids: list[str] = Field(default_factory=list)


class LessonRetrievalGoldSet(BaseModel):
    """Versioned collection of retrieval gold samples."""

    model_config = ConfigDict(extra="forbid")

    version: int
    description: str | None = None
    samples: list[LessonRetrievalEvalSample] = Field(default_factory=list)


class LessonRetrievalSampleOutcome(BaseModel):
    """Observed result for one gold retrieval sample."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    grade: str
    expected_mode: RetrievalMode
    actual_mode: RetrievalMode
    expected_block_uids: list[str] = Field(default_factory=list)
    actual_block_uids: list[str] = Field(default_factory=list)
    expected_support_entry_uids: list[str] = Field(default_factory=list)
    actual_support_entry_uids: list[str] = Field(default_factory=list)
    mode_match: bool
    top1_block_hit: bool
    top3_block_hit: bool
    support_hit: bool | None = None
    cross_grade_leakage: bool = False
    strict_pass: bool


class LessonRetrievalMetricSummary(BaseModel):
    """Aggregate metrics over a sample slice."""

    model_config = ConfigDict(extra="forbid")

    sample_count: int
    strict_pass_count: int
    scope_match_count: int
    top1_block_hit_count: int
    top3_block_hit_count: int
    support_expectation_count: int
    support_hit_count: int
    cross_grade_leakage_count: int
    strict_pass_rate: float
    scope_accuracy: float
    top1_block_hit_rate: float
    top3_block_hit_rate: float
    support_hit_rate: float | None = None


class LessonRetrievalEvalReport(BaseModel):
    """Full eval report with per-sample outcomes and aggregates."""

    model_config = ConfigDict(extra="forbid")

    gold_path: str
    manifest_path: str
    support_paths: list[str] = Field(default_factory=list)
    sample_count: int
    overall: LessonRetrievalMetricSummary
    by_grade: dict[str, LessonRetrievalMetricSummary] = Field(default_factory=dict)
    outcomes: list[LessonRetrievalSampleOutcome] = Field(default_factory=list)

    @property
    def failed_outcomes(self) -> list[LessonRetrievalSampleOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.strict_pass]


def load_eval_gold_set(gold_path: Path | None = None) -> LessonRetrievalGoldSet:
    path = (gold_path or default_eval_gold_path()).resolve()
    return LessonRetrievalGoldSet.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_lesson_retrieval(
    *,
    gold_path: Path | None = None,
    manifest_path: Path | None = None,
    support_paths: list[Path] | None = None,
) -> LessonRetrievalEvalReport:
    resolved_gold_path = (gold_path or default_eval_gold_path()).resolve()
    resolved_manifest_path = (manifest_path or default_manifest_path()).resolve()
    gold = load_eval_gold_set(resolved_gold_path)

    catalog = PilotLessonCatalog(manifest_path=resolved_manifest_path)
    retriever = ScopedRetriever(catalog)
    support_retriever = SupportAssetRetriever(
        catalog,
        support_paths=support_paths,
    )
    resolved_support_paths = [str(path.resolve()) for path in support_retriever.support_paths]

    outcomes = [
        _evaluate_sample(
            sample=sample,
            catalog=catalog,
            retriever=retriever,
            support_retriever=support_retriever,
        )
        for sample in gold.samples
    ]

    by_grade: dict[str, list[LessonRetrievalSampleOutcome]] = {}
    for outcome in outcomes:
        by_grade.setdefault(outcome.grade, []).append(outcome)

    return LessonRetrievalEvalReport(
        gold_path=str(resolved_gold_path),
        manifest_path=str(resolved_manifest_path),
        support_paths=resolved_support_paths,
        sample_count=len(outcomes),
        overall=_build_summary(outcomes),
        by_grade={grade: _build_summary(grade_outcomes) for grade, grade_outcomes in sorted(by_grade.items())},
        outcomes=outcomes,
    )


def render_eval_report(report: LessonRetrievalEvalReport) -> str:
    lines = [
        "Lesson retrieval eval",
        f"Gold set: {report.gold_path}",
        f"Manifest: {report.manifest_path}",
        f"Samples: {report.sample_count}",
        _format_summary("Overall", report.overall),
    ]
    for grade, summary in report.by_grade.items():
        lines.append(_format_summary(f"Grade {grade}", summary))

    if report.failed_outcomes:
        lines.append("Failures:")
        for outcome in report.failed_outcomes:
            detail = (
                f"- {outcome.sample_id}: expected mode={outcome.expected_mode}, "
                f"actual mode={outcome.actual_mode}, expected blocks={outcome.expected_block_uids}, "
                f"actual blocks={outcome.actual_block_uids}, expected support={outcome.expected_support_entry_uids}, "
                f"actual support={outcome.actual_support_entry_uids}, leakage={outcome.cross_grade_leakage}"
            )
            lines.append(detail)
    else:
        lines.append("PASS: gold retrieval samples matched the current baseline.")
    return "\n".join(lines)


def _evaluate_sample(
    *,
    sample: LessonRetrievalEvalSample,
    catalog: PilotLessonCatalog,
    retriever: ScopedRetriever,
    support_retriever: SupportAssetRetriever,
) -> LessonRetrievalSampleOutcome:
    page_scope = catalog.get_scope_for_page(sample.page_uid)
    if (
        page_scope.grade != sample.grade
        or page_scope.semester != sample.semester
        or page_scope.unit != sample.unit
    ):
        raise ValueError(
            f"Gold sample {sample.sample_id} scope does not match page {sample.page_uid}: "
            f"expected {(sample.grade, sample.semester, sample.unit)}, "
            f"actual {(page_scope.grade, page_scope.semester, page_scope.unit)}"
        )

    selection = retriever.select(
        current_page_uid=sample.page_uid,
        current_block_uid=sample.current_block_uid,
        query=sample.query,
    )
    support_hits = support_retriever.search(
        current_page_uid=sample.page_uid,
        current_block_uid=sample.current_block_uid,
        selection=selection,
        query=sample.query,
    )

    actual_block_uids = list(selection.block_uids)
    actual_support_entry_uids = [item.entry_uid for item in support_hits]
    expected_blocks = set(sample.expected_block_uids)
    expected_support = set(sample.expected_support_entry_uids)
    actual_top_three = actual_block_uids[:3]

    mode_match = selection.mode == sample.expected_mode
    top1_block_hit = bool(actual_block_uids) and actual_block_uids[0] in expected_blocks
    top3_block_hit = any(block_uid in expected_blocks for block_uid in actual_top_three)
    support_hit = None
    if expected_support:
        support_hit = expected_support.issubset(actual_support_entry_uids)

    cross_grade_leakage = False
    for block_uid in actual_block_uids:
        block = catalog.get_block(block_uid)
        scope = catalog.get_scope_for_page(block.page_uid)
        if scope.grade != sample.grade:
            cross_grade_leakage = True
            break

    strict_pass = mode_match and top1_block_hit and not cross_grade_leakage
    if support_hit is not None:
        strict_pass = strict_pass and support_hit

    return LessonRetrievalSampleOutcome(
        sample_id=sample.sample_id,
        grade=sample.grade,
        expected_mode=sample.expected_mode,
        actual_mode=selection.mode,
        expected_block_uids=sample.expected_block_uids,
        actual_block_uids=actual_block_uids,
        expected_support_entry_uids=sample.expected_support_entry_uids,
        actual_support_entry_uids=actual_support_entry_uids,
        mode_match=mode_match,
        top1_block_hit=top1_block_hit,
        top3_block_hit=top3_block_hit,
        support_hit=support_hit,
        cross_grade_leakage=cross_grade_leakage,
        strict_pass=strict_pass,
    )


def _build_summary(outcomes: list[LessonRetrievalSampleOutcome]) -> LessonRetrievalMetricSummary:
    sample_count = len(outcomes)
    strict_pass_count = sum(1 for item in outcomes if item.strict_pass)
    scope_match_count = sum(1 for item in outcomes if item.mode_match)
    top1_block_hit_count = sum(1 for item in outcomes if item.top1_block_hit)
    top3_block_hit_count = sum(1 for item in outcomes if item.top3_block_hit)
    support_items = [item for item in outcomes if item.support_hit is not None]
    support_expectation_count = len(support_items)
    support_hit_count = sum(1 for item in support_items if item.support_hit)
    cross_grade_leakage_count = sum(1 for item in outcomes if item.cross_grade_leakage)
    support_hit_rate = None
    if support_expectation_count:
        support_hit_rate = support_hit_count / support_expectation_count

    return LessonRetrievalMetricSummary(
        sample_count=sample_count,
        strict_pass_count=strict_pass_count,
        scope_match_count=scope_match_count,
        top1_block_hit_count=top1_block_hit_count,
        top3_block_hit_count=top3_block_hit_count,
        support_expectation_count=support_expectation_count,
        support_hit_count=support_hit_count,
        cross_grade_leakage_count=cross_grade_leakage_count,
        strict_pass_rate=_ratio(strict_pass_count, sample_count),
        scope_accuracy=_ratio(scope_match_count, sample_count),
        top1_block_hit_rate=_ratio(top1_block_hit_count, sample_count),
        top3_block_hit_rate=_ratio(top3_block_hit_count, sample_count),
        support_hit_rate=support_hit_rate,
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _format_summary(title: str, summary: LessonRetrievalMetricSummary) -> str:
    parts = [
        f"{title}: "
        f"strict={summary.strict_pass_count}/{summary.sample_count} ({summary.strict_pass_rate:.1%}), "
        f"scope={summary.scope_match_count}/{summary.sample_count} ({summary.scope_accuracy:.1%}), "
        f"top1={summary.top1_block_hit_count}/{summary.sample_count} ({summary.top1_block_hit_rate:.1%}), "
        f"top3={summary.top3_block_hit_count}/{summary.sample_count} ({summary.top3_block_hit_rate:.1%}), "
        f"leakage={summary.cross_grade_leakage_count}"
    ]
    if summary.support_hit_rate is not None:
        parts.append(
            f", support={summary.support_hit_count}/{summary.support_expectation_count} ({summary.support_hit_rate:.1%})"
        )
    return "".join(parts)
