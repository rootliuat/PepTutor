"""Build a compact four-book PepTutor curriculum map from structured assets."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.general_draft_builder import GeneralLessonDraftFile
from lightrag.orchestrator.lesson_runtime import (
    PageLessonRecord,
    PilotLessonFile,
    TeachingBlockRecord,
)
from lightrag.orchestrator.raw_curriculum import (
    NormalizedUsefulExpressionEntry,
    normalize_useful_expressions_markdown,
)

_MAX_CORE_VOCABULARY = 40
_MAX_CORE_PATTERNS = 40
_GRADE_LABELS = {
    "G5": "五年级",
    "G6": "六年级",
}
_SEMESTER_LABELS = {
    "S1": "上册",
    "S2": "下册",
}


class CurriculumVocabularyEntry(BaseModel):
    """Compact vocabulary index entry with source traceability."""

    model_config = ConfigDict(extra="forbid")

    word: str
    chinese: str | None = None
    phonetic: str | None = None
    emphasized: bool = False
    source_refs: list[str] = Field(default_factory=list)


class CurriculumPageTypeEntry(BaseModel):
    """Page-to-type mapping used for scoped preparation."""

    model_config = ConfigDict(extra="forbid")

    page_uid: str
    page: int | None = None
    page_type: str
    confidence: str
    source_refs: list[str] = Field(default_factory=list)


class CurriculumLearningTargetEntry(BaseModel):
    """Learning target index entry linked back to its block."""

    model_config = ConfigDict(extra="forbid")

    target_uid: str
    block_uid: str
    category: str
    text: str
    source_refs: list[str] = Field(default_factory=list)


class CurriculumUnitEntry(BaseModel):
    """One unit or recycle-scope entry in the curriculum map."""

    model_config = ConfigDict(extra="forbid")

    unit: str
    pages: list[int] = Field(default_factory=list)
    unit_theme: str | None = None
    core_vocabulary: list[CurriculumVocabularyEntry] = Field(default_factory=list)
    core_patterns: list[str] = Field(default_factory=list)
    page_types: list[CurriculumPageTypeEntry] = Field(default_factory=list)
    block_uids: list[str] = Field(default_factory=list)
    learning_targets: list[CurriculumLearningTargetEntry] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: str
    review_notes: list[str] = Field(default_factory=list)


class CurriculumBookEntry(BaseModel):
    """One PEP textbook volume in the curriculum map."""

    model_config = ConfigDict(extra="forbid")

    book_id: str
    grade: str
    semester: str
    source_refs: list[str] = Field(default_factory=list)
    units: list[CurriculumUnitEntry] = Field(default_factory=list)


class CurriculumMapFile(BaseModel):
    """Runtime-safe offline curriculum map.

    The map is an index and preparation input. It is intentionally not shaped
    as teacher wording and should not be injected wholesale into live turns.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = "peptutor_curriculum_map"
    map_id: str
    generated_at: str
    source_manifest: str
    book_count: int
    scope_count: int
    page_count: int
    block_count: int
    books: list[CurriculumBookEntry] = Field(default_factory=list)


@dataclass
class CurriculumPilotOverlay:
    """Page-level pilot corrections that should win over generic drafts."""

    page_records: dict[str, tuple[PageLessonRecord, str]] = field(default_factory=dict)
    scope_source_refs: dict[tuple[str, str, str], set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    scope_blocks: dict[tuple[str, str, str], list[TeachingBlockRecord]] = field(
        default_factory=lambda: defaultdict(list)
    )
    scope_targets: dict[tuple[str, str, str], list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )


def build_curriculum_map(
    *,
    manifest_path: Path,
    raw_root: Path | None = None,
    generated_at: str | None = None,
    map_id: str = "peptutor-curriculum-map-v1",
    repo_root: Path | None = None,
) -> CurriculumMapFile:
    """Build a curriculum map from the existing structured general manifest."""
    manifest_path = manifest_path.resolve()
    root = repo_root.resolve() if repo_root is not None else _find_repo_root(manifest_path)
    raw_root = (raw_root or root / "app" / "knowledge" / "raw").resolve()
    pilot_overlay = _load_pilot_overlay(
        root / "app" / "knowledge" / "structured",
        repo_root=root,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list) or not manifest_files:
        raise ValueError(f"Invalid general manifest: {manifest_path}")

    useful_expressions = _load_useful_expressions_by_volume(raw_root, repo_root=root)
    books: dict[tuple[str, str], list[CurriculumUnitEntry]] = defaultdict(list)
    book_source_refs: dict[tuple[str, str], set[str]] = defaultdict(set)

    for relative_file in manifest_files:
        if not isinstance(relative_file, str):
            continue
        draft_path = (manifest_path.parent / relative_file).resolve()
        draft = GeneralLessonDraftFile.model_validate_json(
            draft_path.read_text(encoding="utf-8")
        )
        grade = draft.scope.grade
        semester = draft.scope.semester
        volume_key = (grade, semester)
        structured_ref = draft_path.relative_to(root).as_posix()
        for source_ref in draft.source_files + [structured_ref]:
            book_source_refs[volume_key].add(source_ref)

        useful_path = detect_useful_expressions_path(
            raw_root,
            grade=grade,
            semester=semester,
        )
        useful_source_ref = None
        if useful_path is not None:
            useful_source_ref = useful_path.relative_to(root).as_posix()
            book_source_refs[volume_key].add(useful_source_ref)

        unit_entry = _build_unit_entry(
            draft=draft,
            structured_ref=structured_ref,
            useful_entries=useful_expressions.get(volume_key, {}).get(draft.scope.unit, []),
            useful_source_ref=useful_source_ref,
            pilot_overlay=pilot_overlay,
        )
        books[volume_key].append(unit_entry)

    book_entries = [
        CurriculumBookEntry(
            book_id=f"{grade}{semester}",
            grade=grade,
            semester=semester,
            source_refs=_sort_refs(book_source_refs[(grade, semester)]),
            units=sorted(
                units,
                key=lambda unit: _unit_sort_key(unit.unit),
            ),
        )
        for (grade, semester), units in sorted(books.items())
    ]

    scope_count = sum(len(book.units) for book in book_entries)
    page_count = sum(len(unit.page_types) for book in book_entries for unit in book.units)
    block_count = sum(len(unit.block_uids) for book in book_entries for unit in book.units)
    return CurriculumMapFile(
        map_id=map_id,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        source_manifest=manifest_path.relative_to(root).as_posix(),
        book_count=len(book_entries),
        scope_count=scope_count,
        page_count=page_count,
        block_count=block_count,
        books=book_entries,
    )


def default_curriculum_map_output_path(repo_root: Path | None = None) -> Path:
    """Return the checked curriculum-map output path."""
    root = repo_root.resolve() if repo_root is not None else _find_repo_root(Path(__file__))
    return (root / "app" / "knowledge" / "structured" / "curriculum-map.json").resolve()


def default_general_manifest_path(repo_root: Path | None = None) -> Path:
    """Return the checked general manifest path."""
    root = repo_root.resolve() if repo_root is not None else _find_repo_root(Path(__file__))
    return (
        root
        / "app"
        / "knowledge"
        / "structured"
        / "general"
        / "general-manifest.json"
    ).resolve()


def detect_useful_expressions_path(
    raw_root: Path,
    *,
    grade: str,
    semester: str,
) -> Path | None:
    """Locate the matching Useful expressions markdown file for one volume."""
    grade_label = _GRADE_LABELS.get(grade)
    semester_label = _SEMESTER_LABELS.get(semester)
    if grade_label is None or semester_label is None:
        return None

    for path in sorted(raw_root.glob("*.md")):
        name = path.name
        if "Useful expressions" not in name:
            continue
        if grade_label in name and semester_label in name:
            return path.resolve()
    return None


def _build_unit_entry(
    *,
    draft: GeneralLessonDraftFile,
    structured_ref: str,
    useful_entries: list[NormalizedUsefulExpressionEntry],
    useful_source_ref: str | None,
    pilot_overlay: CurriculumPilotOverlay,
) -> CurriculumUnitEntry:
    scope_key = (draft.scope.grade, draft.scope.semester, draft.scope.unit)
    source_refs = _sort_refs(
        set(draft.source_files + [structured_ref])
        | pilot_overlay.scope_source_refs.get(scope_key, set())
    )
    if useful_entries and useful_source_ref is not None:
        source_refs = _sort_refs(set(source_refs + [useful_source_ref]))

    pilot_blocks = pilot_overlay.scope_blocks.get(scope_key, [])
    core_vocabulary = _build_core_vocabulary(
        draft,
        source_refs=source_refs,
        pilot_blocks=pilot_blocks,
    )
    core_patterns = _build_core_patterns(
        draft,
        useful_entries=useful_entries,
        pilot_blocks=pilot_blocks,
    )
    page_types = _build_page_types(
        draft,
        structured_ref=structured_ref,
        pilot_pages=pilot_overlay.page_records,
    )
    block_uids = [block.block_uid for block in draft.teaching_blocks]
    learning_targets = _build_learning_target_entries(
        general_targets=draft.learning_targets,
        pilot_targets=pilot_overlay.scope_targets.get(scope_key, []),
        structured_ref=structured_ref,
        pilot_source_refs=pilot_overlay.scope_source_refs.get(scope_key, set()),
    )
    unit_theme, theme_confidence = _infer_unit_theme(draft)
    confidence, review_notes = _score_unit_confidence(
        draft=draft,
        unit_theme=unit_theme,
        theme_confidence=theme_confidence,
        core_vocabulary=core_vocabulary,
        core_patterns=core_patterns,
    )

    return CurriculumUnitEntry(
        unit=draft.scope.unit,
        pages=draft.scope.pages,
        unit_theme=unit_theme,
        core_vocabulary=core_vocabulary,
        core_patterns=core_patterns,
        page_types=page_types,
        block_uids=block_uids,
        learning_targets=learning_targets,
        source_refs=source_refs,
        confidence=confidence,
        review_notes=review_notes,
    )


def _build_core_vocabulary(
    draft: GeneralLessonDraftFile,
    *,
    source_refs: list[str],
    pilot_blocks: list[TeachingBlockRecord],
) -> list[CurriculumVocabularyEntry]:
    entries: list[CurriculumVocabularyEntry] = []
    seen: set[str] = set()

    for entry in sorted(
        draft.wordlist_entries,
        key=lambda item: (not item.emphasized, item.word.casefold()),
    ):
        key = _normalize_key(entry.word)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            CurriculumVocabularyEntry(
                word=entry.word,
                chinese=entry.chinese,
                phonetic=entry.phonetic,
                emphasized=entry.emphasized,
                source_refs=source_refs,
            )
        )
        if len(entries) >= _MAX_CORE_VOCABULARY:
            return entries

    for block in [*pilot_blocks, *draft.teaching_blocks]:
        for word in block.focus_vocabulary:
            key = _normalize_key(word)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                CurriculumVocabularyEntry(
                    word=word,
                    source_refs=_sort_refs(set(source_refs + block.source_refs + [block.block_uid])),
                )
            )
            if len(entries) >= _MAX_CORE_VOCABULARY:
                return entries

    return entries


def _build_core_patterns(
    draft: GeneralLessonDraftFile,
    *,
    useful_entries: list[NormalizedUsefulExpressionEntry],
    pilot_blocks: list[TeachingBlockRecord],
) -> list[str]:
    patterns: list[str] = []
    for entry in sorted(
        useful_entries,
        key=lambda item: (not item.emphasized, item.page_ref or "", item.english),
    ):
        patterns.append(entry.english)

    for block in [*pilot_blocks, *draft.teaching_blocks]:
        patterns.extend(block.core_patterns)
        if len(_dedupe_strings(patterns)) >= _MAX_CORE_PATTERNS:
            break

    return _dedupe_strings(patterns)[:_MAX_CORE_PATTERNS]


def _build_page_types(
    draft: GeneralLessonDraftFile,
    *,
    structured_ref: str,
    pilot_pages: dict[str, tuple[PageLessonRecord, str]],
) -> list[CurriculumPageTypeEntry]:
    result: list[CurriculumPageTypeEntry] = []
    for page in draft.page_lessons:
        source_refs = [structured_ref, page.page_uid]
        page_type = page.page_type
        confidence = "high" if page.page_type != "unknown" else "low"
        pilot_record = pilot_pages.get(page.page_uid)
        if pilot_record is not None:
            pilot_page, pilot_source_ref = pilot_record
            page_type = pilot_page.page_type
            confidence = "high" if page_type != "unknown" else "low"
            source_refs.append(pilot_source_ref)
        result.append(
            CurriculumPageTypeEntry(
                page_uid=page.page_uid,
                page=_parse_page_number(page.page_uid),
                page_type=page_type,
                confidence=confidence,
                source_refs=_dedupe_strings(source_refs),
            )
        )
    return result


def _build_learning_target_entries(
    *,
    general_targets: list[dict[str, Any]],
    pilot_targets: list[dict[str, Any]],
    structured_ref: str,
    pilot_source_refs: set[str],
) -> list[CurriculumLearningTargetEntry]:
    result: list[CurriculumLearningTargetEntry] = []
    seen: set[str] = set()
    for target, extra_refs in [
        *[(target, [structured_ref]) for target in general_targets],
        *[(target, list(pilot_source_refs)) for target in pilot_targets],
    ]:
        target_uid = target.get("target_uid")
        block_uid = target.get("block_uid")
        text = target.get("text")
        if not isinstance(target_uid, str) or not target_uid:
            continue
        if not isinstance(block_uid, str) or not block_uid:
            continue
        if not isinstance(text, str) or not text:
            continue
        if target_uid in seen:
            continue
        seen.add(target_uid)
        result.append(
            CurriculumLearningTargetEntry(
                target_uid=target_uid,
                block_uid=block_uid,
                category=str(target.get("category", "")),
                text=text,
                source_refs=_target_source_refs(
                    target,
                    structured_ref=structured_ref,
                    extra_refs=extra_refs,
                ),
            )
        )
    return result


def _target_source_refs(
    target: dict[str, Any],
    *,
    structured_ref: str,
    extra_refs: list[str] | None = None,
) -> list[str]:
    refs = {structured_ref}
    refs.update(extra_refs or [])
    block_uid = target.get("block_uid")
    if isinstance(block_uid, str) and block_uid:
        refs.add(block_uid)
    target_uid = target.get("target_uid")
    if isinstance(target_uid, str) and target_uid:
        refs.add(target_uid)
    return _sort_refs(refs)


def _infer_unit_theme(draft: GeneralLessonDraftFile) -> tuple[str | None, str]:
    themes: list[str] = []
    for page in draft.page_lessons:
        theme = _extract_theme_from_intro(page.page_intro_cn)
        if theme:
            themes.append(theme)

    if themes:
        counts = Counter(themes)
        ordered = sorted(counts, key=lambda item: (-counts[item], themes.index(item)))
        return " / ".join(ordered[:4]), "high"

    fallback_patterns = _dedupe_strings(
        pattern
        for block in draft.teaching_blocks
        for pattern in block.core_patterns
    )
    if fallback_patterns:
        return fallback_patterns[0], "medium"

    fallback_words = _dedupe_strings(
        entry.word for entry in draft.wordlist_entries
    )
    if fallback_words:
        return ", ".join(fallback_words[:5]), "low"

    return None, "low"


def _score_unit_confidence(
    *,
    draft: GeneralLessonDraftFile,
    unit_theme: str | None,
    theme_confidence: str,
    core_vocabulary: list[CurriculumVocabularyEntry],
    core_patterns: list[str],
) -> tuple[str, list[str]]:
    review_notes: list[str] = []
    if not unit_theme:
        review_notes.append("unit_theme_missing")
    if theme_confidence != "high":
        review_notes.append(f"unit_theme_confidence_{theme_confidence}")
    if not core_vocabulary:
        review_notes.append("core_vocabulary_missing_or_not_in_wordlist")
    if not core_patterns:
        review_notes.append("core_patterns_missing")
    if not draft.page_lessons:
        review_notes.append("page_lessons_missing")
    if not draft.teaching_blocks:
        review_notes.append("teaching_blocks_missing")
    if not draft.learning_targets:
        review_notes.append("learning_targets_missing")

    if "page_lessons_missing" in review_notes or "teaching_blocks_missing" in review_notes:
        return "low", review_notes
    if review_notes:
        return "medium", review_notes
    return "high", review_notes


def _load_useful_expressions_by_volume(
    raw_root: Path,
    *,
    repo_root: Path,
) -> dict[tuple[str, str], dict[str, list[NormalizedUsefulExpressionEntry]]]:
    result: dict[tuple[str, str], dict[str, list[NormalizedUsefulExpressionEntry]]] = {}
    for grade in ("G5", "G6"):
        for semester in ("S1", "S2"):
            path = detect_useful_expressions_path(
                raw_root,
                grade=grade,
                semester=semester,
            )
            if path is None:
                continue
            unit_entries: dict[str, list[NormalizedUsefulExpressionEntry]] = defaultdict(list)
            for entry in normalize_useful_expressions_markdown(path):
                normalized_unit = _normalize_unit_label(entry.unit)
                unit_entries[normalized_unit].append(
                    entry.model_copy(
                        update={
                            "page_ref": entry.page_ref,
                        }
                    )
                )
            result[(grade, semester)] = dict(unit_entries)
    return result


def _load_pilot_overlay(
    structured_root: Path,
    *,
    repo_root: Path,
) -> CurriculumPilotOverlay:
    overlay = CurriculumPilotOverlay()
    for path in sorted(structured_root.glob("*-pilot.json")):
        try:
            pilot = PilotLessonFile.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        source_ref = path.resolve().relative_to(repo_root).as_posix()
        scope_key = (pilot.scope.grade, pilot.scope.semester, pilot.scope.unit)
        overlay.scope_source_refs[scope_key].add(source_ref)
        for page in pilot.page_lessons:
            overlay.page_records[page.page_uid] = (page, source_ref)
        overlay.scope_blocks[scope_key].extend(pilot.teaching_blocks)
        overlay.scope_targets[scope_key].extend(pilot.learning_targets)
    return overlay


def _extract_theme_from_intro(page_intro_cn: str) -> str | None:
    match = re.match(r"^Theme:\s*(.+?)\.\s*", page_intro_cn.strip())
    if match:
        return match.group(1).strip()
    return None


def _parse_page_number(page_uid: str) -> int | None:
    match = re.search(r"-P(\d+)", page_uid)
    if not match:
        return None
    return int(match.group(1))


def _normalize_unit_label(value: str) -> str:
    normalized = value.strip()
    unit_match = re.match(r"^Unit\s+(\d+)$", normalized, re.IGNORECASE)
    if unit_match:
        return f"U{unit_match.group(1)}"
    recycle_match = re.match(r"^Recycle\s*(\d+)$", normalized, re.IGNORECASE)
    if recycle_match:
        return f"Recycle{recycle_match.group(1)}"
    return normalized.replace(" ", "")


def _unit_sort_key(unit: str) -> tuple[int, int, str]:
    unit_match = re.match(r"^U(\d+)$", unit, re.IGNORECASE)
    if unit_match:
        return (0, int(unit_match.group(1)), unit)
    recycle_match = re.match(r"^Recycle(\d+)$", unit, re.IGNORECASE)
    if recycle_match:
        return (1, int(recycle_match.group(1)), unit)
    return (2, 0, unit)


def _sort_refs(refs: set[str] | list[str]) -> list[str]:
    return sorted(_dedupe_strings(list(refs)))


def _dedupe_strings(items) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        normalized = re.sub(r"\s+", " ", item.strip())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for ancestor in [current, *current.parents]:
        if (ancestor / "app" / "knowledge").exists():
            return ancestor
    raise FileNotFoundError("Unable to locate repository root containing app/knowledge")
