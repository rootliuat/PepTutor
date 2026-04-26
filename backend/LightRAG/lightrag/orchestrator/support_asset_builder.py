"""Deterministic builders for unit-level lexicon and expression support assets."""

from __future__ import annotations

from pathlib import Path
import re

from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog, ScopeInfo, TeachingBlockRecord
from lightrag.orchestrator.raw_curriculum import (
    NormalizedUsefulExpressionEntry,
    NormalizedWordListSection,
)
from lightrag.orchestrator.support_asset_types import (
    ExpressionEntryRecord,
    LexiconEntryRecord,
    SupportAssetFile,
    SupportScopeInfo,
)

_TEXT_NORMALIZATION_RE = re.compile(r"[^a-z0-9]+")
_CONTRACTIONS = {
    "what's": "what is",
    "it's": "it is",
    "i'm": "i am",
    "they're": "they are",
    "don't": "do not",
    "can't": "cannot",
    "isn't": "is not",
    "aren't": "are not",
    "i'd": "id",
}


def build_support_assets(
    *,
    asset_id: str,
    catalog: PilotLessonCatalog,
    word_sections: list[NormalizedWordListSection],
    useful_expressions: list[NormalizedUsefulExpressionEntry],
) -> SupportAssetFile:
    """Project parsed markdown support assets into stable unit-level records."""
    scope = _build_catalog_scope(catalog)
    unit_label = _scope_unit_label(scope)
    ordered_page_uids = _ordered_page_uids(catalog, scope)
    page_refs_by_uid = {
        page_uid: f"p.{_extract_page_number(page_uid)}" for page_uid in ordered_page_uids
    }
    page_uids_by_ref = {
        page_ref: page_uid for page_uid, page_ref in page_refs_by_uid.items()
    }
    ordered_blocks = [
        block
        for page_uid in ordered_page_uids
        for block in catalog.blocks_for_page(page_uid)
    ]
    source_files = _build_source_files(scope)

    return SupportAssetFile(
        asset_id=asset_id,
        scope=SupportScopeInfo(
            grade=scope.grade,
            semester=scope.semester,
            unit=scope.unit,
            pages=scope.pages,
        ),
        source_files=source_files,
        lexicon_entries=_build_lexicon_entries(
            scope=scope,
            unit_label=unit_label,
            word_sections=word_sections,
            ordered_blocks=ordered_blocks,
            page_refs_by_uid=page_refs_by_uid,
        ),
        expression_entries=_build_expression_entries(
            scope=scope,
            unit_label=unit_label,
            useful_expressions=useful_expressions,
            ordered_page_uids=ordered_page_uids,
            ordered_blocks=ordered_blocks,
            page_uids_by_ref=page_uids_by_ref,
            page_refs_by_uid=page_refs_by_uid,
            catalog=catalog,
        ),
    )


def default_support_asset_output_path(
    asset_id: str,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Return a stable repository path for a generated support-asset file."""
    root = repo_root or _default_repo_root()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", asset_id).strip("-") or "support-assets"
    return (root / "app/knowledge/structured/support" / f"{slug}.json").resolve()


def _build_catalog_scope(catalog: PilotLessonCatalog) -> ScopeInfo:
    scopes = list(catalog.page_scopes.values())
    if not scopes:
        raise ValueError("PilotLessonCatalog must contain at least one page scope")

    first = scopes[0]
    pages = sorted({_extract_page_number(page_uid) for page_uid in catalog.page_scopes})
    for scope in scopes[1:]:
        if (
            scope.grade != first.grade
            or scope.semester != first.semester
            or scope.unit != first.unit
        ):
            raise ValueError("Support assets require a single grade/semester/unit scope")

    return ScopeInfo(
        grade=first.grade,
        semester=first.semester,
        unit=first.unit,
        pages=pages,
    )


def _ordered_page_uids(catalog: PilotLessonCatalog, scope: ScopeInfo) -> list[str]:
    page_uids = [
        page_uid
        for page_uid, page_scope in catalog.page_scopes.items()
        if (
            page_scope.grade == scope.grade
            and page_scope.semester == scope.semester
            and page_scope.unit == scope.unit
            and _extract_page_number(page_uid) in scope.pages
        )
    ]
    return sorted(page_uids, key=_extract_page_number)


def _build_lexicon_entries(
    *,
    scope: ScopeInfo,
    unit_label: str,
    word_sections: list[NormalizedWordListSection],
    ordered_blocks: list[TeachingBlockRecord],
    page_refs_by_uid: dict[str, str],
) -> list[LexiconEntryRecord]:
    section = next((item for item in word_sections if item.unit == unit_label), None)
    if section is None:
        return []

    result: list[LexiconEntryRecord] = []
    source_ref = f"raw_wordlist_{scope.grade.lower()}{scope.semester.lower()}"
    for entry in section.entries:
        linked_block_uids = [
            block.block_uid
            for block in ordered_blocks
            if _score_term_against_block(entry.word, block) > 0
        ]
        linked_page_uids = _dedupe_strings(
            [block.page_uid for block in ordered_blocks if block.block_uid in linked_block_uids]
        )
        page_refs = _dedupe_strings(
            [page_refs_by_uid[page_uid] for page_uid in linked_page_uids if page_uid in page_refs_by_uid]
        )
        result.append(
            LexiconEntryRecord(
                entry_uid=f"LEX-{scope.grade}{scope.semester}{scope.unit}-{_slugify(entry.word)}",
                entry_type="phrase" if " " in entry.word.strip() else "word",
                english=entry.word,
                chinese=entry.chinese,
                phonetic=entry.phonetic,
                emphasized=entry.emphasized,
                source_refs=[source_ref],
                page_refs=page_refs,
                linked_page_uids=linked_page_uids,
                linked_block_uids=linked_block_uids,
            )
        )
    return result


def _build_expression_entries(
    *,
    scope: ScopeInfo,
    unit_label: str,
    useful_expressions: list[NormalizedUsefulExpressionEntry],
    ordered_page_uids: list[str],
    ordered_blocks: list[TeachingBlockRecord],
    page_uids_by_ref: dict[str, str],
    page_refs_by_uid: dict[str, str],
    catalog: PilotLessonCatalog,
) -> list[ExpressionEntryRecord]:
    source_ref = f"raw_useful_expressions_{scope.grade.lower()}{scope.semester.lower()}"
    blocks_by_page = {
        page_uid: [block for block in ordered_blocks if block.page_uid == page_uid]
        for page_uid in ordered_page_uids
    }
    result: list[ExpressionEntryRecord] = []

    for entry in useful_expressions:
        if entry.unit != unit_label:
            continue

        page_uid = page_uids_by_ref.get(entry.page_ref or "")
        candidate_blocks = (
            blocks_by_page.get(page_uid, [])
            if page_uid is not None
            else ordered_blocks
        )
        linked_block_uids = [
            block.block_uid
            for block in candidate_blocks
            if _score_expression_against_block(entry.english, block) > 0
        ]
        if not linked_block_uids and page_uid is not None:
            linked_block_uids = [catalog.first_block_for_page(page_uid).block_uid]

        linked_page_uids = _dedupe_strings(
            ([page_uid] if page_uid is not None else [])
            + [
                block.page_uid
                for block in ordered_blocks
                if block.block_uid in linked_block_uids
            ]
        )
        page_refs = _dedupe_strings(
            ([entry.page_ref] if entry.page_ref else [])
            + [
                page_refs_by_uid[linked_page_uid]
                for linked_page_uid in linked_page_uids
                if linked_page_uid in page_refs_by_uid
            ]
        )
        result.append(
            ExpressionEntryRecord(
                entry_uid=f"EXP-{scope.grade}{scope.semester}{scope.unit}-{_slugify(entry.english)}",
                english=entry.english,
                chinese=entry.chinese,
                page_refs=page_refs,
                source_refs=[source_ref],
                linked_page_uids=linked_page_uids,
                linked_block_uids=linked_block_uids,
            )
        )
    return result


def _build_source_files(scope: ScopeInfo) -> list[str]:
    prefix = f"{scope.grade.lower()}{scope.semester.lower()}"
    return [
        f"raw_wordlist_{prefix}",
        f"raw_useful_expressions_{prefix}",
        f"structured_pilot_manifest_{prefix}{scope.unit.lower()}",
    ]


def _scope_unit_label(scope: ScopeInfo) -> str:
    match = re.fullmatch(r"U(\d+)", scope.unit)
    if not match:
        raise ValueError(f"Unsupported unit format for markdown mapping: {scope.unit}")
    return f"Unit {int(match.group(1))}"


def _score_term_against_block(term: str, block: TeachingBlockRecord) -> int:
    needle = _normalize_text(term)
    if not needle:
        return 0

    score = 0
    score = max(score, _match_list_score(block.focus_vocabulary, needle, exact=8, contains=4))
    score = max(score, _match_list_score(block.core_patterns, needle, exact=5, contains=3))
    score = max(
        score,
        _match_list_score(block.allowed_answer_scope, needle, exact=5, contains=3),
    )
    score = max(
        score,
        _match_list_score(block.entry_probe_questions, needle, exact=3, contains=2),
    )
    score = max(
        score,
        _match_list_score(block.return_anchors, needle, exact=4, contains=2),
    )
    score = max(
        score,
        _match_list_score(block.branchable_topics, needle, exact=4, contains=2),
    )
    score = max(score, _match_text_score(block.teaching_goal, needle, exact=2, contains=1))
    score = max(
        score,
        _match_text_score(block.teaching_summary, needle, exact=2, contains=1),
    )
    return score


def _score_expression_against_block(expression: str, block: TeachingBlockRecord) -> int:
    needle = _normalize_text(expression)
    if not needle:
        return 0

    score = 0
    score = max(score, _match_list_score(block.core_patterns, needle, exact=10, contains=5))
    score = max(
        score,
        _match_list_score(block.allowed_answer_scope, needle, exact=9, contains=4),
    )
    score = max(
        score,
        _match_list_score(block.entry_probe_questions, needle, exact=6, contains=3),
    )
    score = max(
        score,
        _match_list_score(block.return_anchors, needle, exact=7, contains=3),
    )
    score = max(score, _match_text_score(block.teaching_goal, needle, exact=3, contains=1))
    score = max(
        score,
        _match_text_score(block.teaching_summary, needle, exact=3, contains=1),
    )
    return score


def _match_list_score(
    values: list[str],
    needle: str,
    *,
    exact: int,
    contains: int,
) -> int:
    best = 0
    for value in values:
        best = max(best, _match_text_score(value, needle, exact=exact, contains=contains))
    return best


def _match_text_score(
    value: str | None,
    needle: str,
    *,
    exact: int,
    contains: int,
) -> int:
    normalized = _normalize_text(value or "")
    if not normalized:
        return 0
    if normalized == needle:
        return exact
    if needle in normalized:
        return contains
    return 0


def _normalize_text(text: str) -> str:
    normalized = text.casefold()
    for source, replacement in _CONTRACTIONS.items():
        normalized = normalized.replace(source, replacement)
    normalized = _TEXT_NORMALIZATION_RE.sub(" ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_page_number(page_uid: str) -> int:
    match = re.search(r"-P(\d+)(?:-\d+)?$", page_uid)
    if not match:
        raise ValueError(f"Cannot extract page number from page uid: {page_uid}")
    return int(match.group(1))


def _slugify(text: str) -> str:
    return _normalize_text(text).replace(" ", "-") or "item"


def _dedupe_strings(entries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _default_repo_root() -> Path:
    current = Path(__file__).resolve()
    matches: list[Path] = []
    for ancestor in current.parents:
        if (ancestor / "app/knowledge").exists():
            matches.append(ancestor)
    if matches:
        return matches[-1]
    raise FileNotFoundError("Unable to locate repository root containing app/knowledge")
