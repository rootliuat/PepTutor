"""Generic lesson draft builders for non-pilot PepTutor curriculum slices."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_runtime import (
    PageLessonRecord,
    ScopeInfo,
    TeachingBlockRecord,
)
from lightrag.orchestrator.raw_curriculum import (
    NormalizedTextbookBlock,
    NormalizedTextbookPage,
    NormalizedWordListEntry,
    NormalizedWordListSection,
)

_REPAIR_MODES_BY_BLOCK_TYPE = {
    "assessment_quiz": ["repeat", "choice_probe", "asr_clarify"],
    "dialogue_core": ["repeat", "slow_read", "word_drill", "sentence_drill", "asr_clarify"],
    "dialogue_practice": ["choice_probe", "word_drill", "sentence_drill"],
    "extension_task": ["choice_probe", "word_drill", "sentence_drill"],
    "grammar_point": ["repeat", "sentence_drill", "choice_probe"],
    "listening_probe": ["repeat", "choice_probe", "asr_clarify"],
    "phonics": ["repeat", "slow_read", "word_drill"],
    "practice_fill_blank": ["choice_probe", "sentence_drill"],
    "reading_passage": ["repeat", "slow_read", "choice_probe"],
    "story_time": ["repeat", "slow_read", "choice_probe"],
    "summary_wrap_up": ["repeat", "word_drill", "choice_probe"],
    "vocabulary_core": ["repeat", "word_drill", "choice_probe", "asr_clarify"],
}
_BLOCK_PRIORITY_WEIGHTS = {
    "dialogue_core": 0,
    "vocabulary_core": 0,
    "dialogue_practice": 1,
    "extension_task": 2,
    "listening_probe": 2,
    "reading_passage": 3,
    "practice_fill_blank": 4,
    "grammar_point": 4,
    "summary_wrap_up": 4,
    "phonics": 5,
    "assessment_quiz": 5,
    "story_time": 6,
}
_SKIP_DIALOGUE_ANSWERS = {
    "ok.",
    "sure.",
    "thanks.",
    "thank you.",
}
_MAIN_UNIT_RE = re.compile(r"^U\d+$")
_RECYCLE_RE = re.compile(r"^Recycle\d+$", re.IGNORECASE)
_GRADE_LABELS = {
    "G5": "五年级",
    "G6": "六年级",
}
_SEMESTER_LABELS = {
    "S1": "上册",
    "S2": "下册",
}


class WordListEntryRecord(BaseModel):
    """Structured word-list entry retained beside TeachingBlocks."""

    model_config = ConfigDict(extra="forbid")

    unit: str
    word: str
    phonetic: str | None = None
    chinese: str
    emphasized: bool = False
    linked_block_uids: list[str] = Field(default_factory=list)


class GeneralLessonDraftFile(BaseModel):
    """General lesson draft with runtime-compatible fields plus enrichment metadata."""

    model_config = ConfigDict(extra="ignore")

    pilot_id: str
    scope: ScopeInfo
    source_files: list[str] = Field(default_factory=list)
    draft_metadata: dict[str, Any] = Field(default_factory=dict)
    wordlist_entries: list[WordListEntryRecord] = Field(default_factory=list)
    learning_targets: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_atoms: list[dict[str, Any]] = Field(default_factory=list)
    page_lessons: list[PageLessonRecord] = Field(default_factory=list)
    teaching_blocks: list[TeachingBlockRecord] = Field(default_factory=list)


def build_general_draft(
    pages: list[NormalizedTextbookPage],
    *,
    draft_id: str,
    source_files: list[str],
    word_list_sections: list[NormalizedWordListSection] | None = None,
    display_name: str | None = None,
) -> GeneralLessonDraftFile:
    """Project one unit or recycle slice into a generic structured lesson JSON."""
    ordered_pages = _validate_and_sort_pages(pages)
    first = ordered_pages[0]
    priority_block_uids = {
        page.page_uid: _build_priority_block_uids(page) for page in ordered_pages
    }

    scoped_word_entries = _select_unit_word_list_entries(
        word_list_sections or [],
        first.unit,
    )
    word_entry_by_word = {
        _normalize_lookup_key(entry.word): entry for entry in scoped_word_entries
    }

    teaching_blocks = [
        record
        for page in ordered_pages
        for record in build_teaching_block_records(
            page,
            priority_block_uids=priority_block_uids[page.page_uid],
        )
    ]
    learning_targets = _build_learning_targets(first, teaching_blocks)
    target_uid_by_block = {
        target["block_uid"]: target["target_uid"]
        for target in learning_targets
    }
    teaching_blocks = [
        block.model_copy(
            update={
                "learning_target_uids": [target_uid_by_block[block.block_uid]],
            }
        )
        for block in teaching_blocks
    ]
    page_lessons = [
        build_page_lesson_record(
            page,
            priority_block_uids=priority_block_uids[page.page_uid],
        )
        for page in ordered_pages
    ]
    wordlist_entries = _build_wordlist_records(scoped_word_entries, teaching_blocks)
    knowledge_atoms = _build_knowledge_atoms(
        pages=ordered_pages,
        teaching_blocks=teaching_blocks,
        word_entry_by_word=word_entry_by_word,
    )

    return GeneralLessonDraftFile(
        pilot_id=draft_id,
        scope=ScopeInfo(
            grade=first.grade,
            semester=first.semester,
            unit=first.unit,
            pages=_scope_page_numbers(ordered_pages),
        ),
        source_files=source_files,
        draft_metadata={
            "builder": "general_draft_builder",
            "display_name": default_display_name(
                grade=first.grade,
                semester=first.semester,
            ),
            "raw_display_name": display_name or first.book,
            "page_count": len(ordered_pages),
            "block_count": len(teaching_blocks),
            "source_kind": first.source_kind,
            "source_format": first.source_format,
        },
        wordlist_entries=wordlist_entries,
        learning_targets=learning_targets,
        knowledge_atoms=knowledge_atoms,
        page_lessons=page_lessons,
        teaching_blocks=teaching_blocks,
    )


def build_teaching_block_records(
    page: NormalizedTextbookPage,
    *,
    priority_block_uids: list[str],
) -> list[TeachingBlockRecord]:
    """Convert normalized raw page blocks into runtime TeachingBlock records."""
    priority_index = {
        block_uid: index for index, block_uid in enumerate(priority_block_uids)
    }
    result: list[TeachingBlockRecord] = []

    for block in page.blocks:
        block_type = _canonical_block_type(block.block_type)
        focus_vocabulary = _build_focus_vocabulary(block)
        core_patterns = _build_core_patterns(block)
        allowed_answer_scope = _build_allowed_answer_scope(
            block,
            focus_vocabulary=focus_vocabulary,
            core_patterns=core_patterns,
        )
        block_index = priority_index.get(block.block_uid, len(priority_block_uids))
        result.append(
            TeachingBlockRecord(
                block_uid=block.block_uid,
                page_uid=page.page_uid,
                page_type=page.page_type_hint,
                block_type=block_type,
                source_refs=[block.block_uid],
                teaching_goal=_build_block_goal(block_type),
                teaching_summary=_build_block_summary(
                    block,
                    focus_vocabulary=focus_vocabulary,
                    core_patterns=core_patterns,
                ),
                focus_vocabulary=focus_vocabulary,
                core_patterns=core_patterns,
                allowed_answer_scope=allowed_answer_scope,
                entry_probe_questions=_build_block_probe_questions(
                    block=block,
                    focus_vocabulary=focus_vocabulary,
                    core_patterns=core_patterns,
                ),
                repair_modes=_REPAIR_MODES_BY_BLOCK_TYPE.get(block_type, ["repeat"]),
                next_block_uids=priority_block_uids[block_index + 1 :],
                learning_target_uids=[],
                branchable_topics=_build_branchable_topics(
                    page=page,
                    block=block,
                    focus_vocabulary=focus_vocabulary,
                ),
                return_anchors=_dedupe_strings(core_patterns[:3] or focus_vocabulary[:3]),
            )
        )

    return result


def build_page_lesson_record(
    page: NormalizedTextbookPage,
    *,
    priority_block_uids: list[str],
) -> PageLessonRecord:
    """Create page-level runtime metadata from the normalized textbook page."""
    return PageLessonRecord(
        page_uid=page.page_uid,
        page_type=page.page_type_hint,
        page_intro_cn=_build_page_intro(
            page,
            priority_block_uids=priority_block_uids,
        ),
        entry_probe_questions=_build_page_probe_questions(
            page,
            priority_block_uids=priority_block_uids,
        ),
        priority_blocks=priority_block_uids,
        assumed_prior_knowledge=[],
    )


def select_general_scope_pages(
    pages: list[NormalizedTextbookPage],
    *,
    grade: str,
    semester: str,
    unit: str,
    page_numbers: list[int] | set[int] | tuple[int, ...] | None = None,
) -> list[NormalizedTextbookPage]:
    """Select one unit or recycle slice and normalize semester metadata."""
    requested_pages = {page for page in page_numbers or []}
    selected: list[NormalizedTextbookPage] = []
    for page in pages:
        if page.grade != grade:
            continue
        if requested_pages:
            if page.page not in requested_pages:
                continue
        else:
            if not _is_main_textbook_page(page):
                continue
            if not _page_matches_scope(page, unit):
                continue

        selected.append(
            _retag_page_for_scope(
                page,
                semester=semester,
                unit=unit,
            )
        )

    if requested_pages and {page.page for page in selected if page.page is not None} != requested_pages:
        raise ValueError(
            f"Failed to load all requested pages for {grade} {semester} {unit}: "
            f"expected {sorted(requested_pages)}"
        )

    return _validate_and_sort_pages(_dedupe_pages_by_uid(selected))


def default_display_name(
    *,
    grade: str,
    semester: str,
) -> str:
    """Return a normalized textbook display name independent of raw metadata quality."""
    grade_label = {
        "G5": "Grade 5",
        "G6": "Grade 6",
    }.get(grade, grade)
    semester_label = {
        "S1": "Volume 1",
        "S2": "Volume 2",
    }.get(semester, semester)
    return (
        f"English (Primary School, {grade_label} · {semester_label}), "
        "People's Education Press (PEP)"
    )


def detect_word_list_path(
    raw_root: Path,
    *,
    grade: str,
    semester: str,
) -> Path | None:
    """Locate the matching word-list markdown file for one textbook volume."""
    grade_label = _GRADE_LABELS.get(grade)
    semester_label = _SEMESTER_LABELS.get(semester)
    if grade_label is None or semester_label is None:
        return None

    for path in sorted(raw_root.glob("*.md")):
        name = path.name
        if "单词表" not in name:
            continue
        if grade_label in name and semester_label in name:
            return path.resolve()
    return None


def default_general_draft_output_path(
    *,
    grade: str,
    semester: str,
    unit: str,
    repo_root: Path | None = None,
) -> Path:
    """Return a stable repository path for a generated general lesson draft."""
    slug = f"{grade.lower()}{semester.lower()}{unit.lower()}-general"
    root = repo_root or _default_repo_root()
    return (root / "app" / "knowledge" / "structured" / "general" / f"{slug}.json").resolve()


def _build_page_intro(
    page: NormalizedTextbookPage,
    *,
    priority_block_uids: list[str],
) -> str:
    parts: list[str] = []
    if page.theme:
        parts.append(f"Theme: {page.theme}.")
    block_by_uid = {block.block_uid: block for block in page.blocks}
    first_scene = None
    for block_uid in priority_block_uids:
        block = block_by_uid.get(block_uid)
        if block is not None and block.scene_description:
            first_scene = block.scene_description
            break
    if first_scene is None:
        first_scene = next(
            (block.scene_description for block in page.blocks if block.scene_description),
            None,
        )
    if first_scene:
        parts.append(first_scene)
    else:
        parts.append(f"This page focuses on {page.page_type_hint} work.")
    return " ".join(parts)


def _build_page_probe_questions(
    page: NormalizedTextbookPage,
    *,
    priority_block_uids: list[str],
) -> list[str]:
    block_by_uid = {block.block_uid: block for block in page.blocks}
    for block_uid in priority_block_uids:
        block = block_by_uid.get(block_uid)
        if block is None:
            continue
        focus_vocabulary = _build_focus_vocabulary(block)
        core_patterns = _build_core_patterns(block)
        probes = _build_block_probe_questions(
            block=block,
            focus_vocabulary=focus_vocabulary,
            core_patterns=core_patterns,
        )
        if probes:
            return probes[:2]
    return []


def _build_priority_block_uids(page: NormalizedTextbookPage) -> list[str]:
    ordered_blocks = sorted(
        page.blocks,
        key=lambda block: (
            _BLOCK_PRIORITY_WEIGHTS.get(
                _canonical_block_type(block.block_type),
                99,
            ),
            page.blocks.index(block),
        ),
    )
    return [block.block_uid for block in ordered_blocks]


def _canonical_block_type(block_type: str) -> str:
    if block_type == "listening_exercise":
        return "listening_probe"
    return block_type


def _build_block_goal(block_type: str) -> str:
    return {
        "assessment_quiz": "Check whether the learner can complete the unit review task.",
        "dialogue_core": "Understand and say the core dialogue pattern on the page.",
        "dialogue_practice": "Use the page dialogue pattern in short guided practice.",
        "extension_task": "Transfer the page language into a new speaking task.",
        "listening_probe": "Catch the key information from the listening task.",
        "phonics": "Notice and repeat the target pronunciation pattern.",
        "practice_fill_blank": "Retell the reading content by filling in key blanks.",
        "reading_passage": "Read and understand the key information in the passage.",
        "story_time": "Read and retell the key story events.",
        "summary_wrap_up": "Review and consolidate the core language point.",
        "vocabulary_core": "Recognize and say the core vocabulary on the page.",
    }.get(block_type, f"Work on the {block_type.replace('_', ' ')} activity.")


def _build_block_summary(
    block: NormalizedTextbookBlock,
    *,
    focus_vocabulary: list[str],
    core_patterns: list[str],
) -> str:
    parts: list[str] = []
    if block.scene_description:
        parts.append(block.scene_description)
    if core_patterns:
        parts.append("Key patterns: " + "; ".join(core_patterns[:2]))
    elif focus_vocabulary:
        parts.append("Focus vocabulary: " + ", ".join(focus_vocabulary[:5]))
    elif block.section_title:
        parts.append(f"Section: {block.section_title}.")
    return " ".join(parts) or f"Practice block for {block.block_type}."


def _build_focus_vocabulary(block: NormalizedTextbookBlock) -> list[str]:
    if block.vocabulary:
        return _dedupe_strings([item.word for item in block.vocabulary])[:8]
    if block.word_bank:
        return _dedupe_strings(block.word_bank)[:8]
    return []


def _build_core_patterns(block: NormalizedTextbookBlock) -> list[str]:
    patterns = [item.english for item in block.patterns]
    if block.dialogue_lines:
        patterns.extend(
            line.english
            for line in block.dialogue_lines
            if line.english.strip().endswith("?")
        )
        patterns.extend(
            line.english
            for line in block.dialogue_lines
            if "?" not in line.english and len(line.english.strip()) >= 5
        )
    if not patterns and block.prose_passages:
        patterns.extend(item.english for item in block.prose_passages)
    if not patterns and block.prompts:
        patterns.extend(block.prompts)
    if not patterns and block.questions:
        patterns.extend(question.prompt for question in block.questions[:3])
    if not patterns and block.section_title:
        patterns.append(block.section_title)
    return _dedupe_strings(patterns)[:6]


def _build_allowed_answer_scope(
    block: NormalizedTextbookBlock,
    *,
    focus_vocabulary: list[str],
    core_patterns: list[str],
) -> list[str]:
    answers = [
        question.answer
        for question in block.questions
        if question.answer
    ]
    if answers:
        return _dedupe_strings(answers)[:6]

    if block.dialogue_lines:
        answers = [
            line.english
            for line in block.dialogue_lines
            if "?" not in line.english
            and line.english.strip().casefold() not in _SKIP_DIALOGUE_ANSWERS
        ]
        if answers:
            return _dedupe_strings(answers)[:6]

    if focus_vocabulary:
        return focus_vocabulary[:6]
    if block.word_bank:
        return _dedupe_strings(block.word_bank)[:6]
    if core_patterns:
        return core_patterns[:4]
    return core_patterns[:4]


def _build_block_probe_questions(
    *,
    block: NormalizedTextbookBlock,
    focus_vocabulary: list[str],
    core_patterns: list[str],
) -> list[str]:
    probes: list[str] = []
    if focus_vocabulary:
        probes.append(f"Do you know the word {focus_vocabulary[0]}?")
    if core_patterns:
        probes.append(f"Can you say: {core_patterns[0]}")
    if not probes and block.questions:
        probes.append(f"Can you answer: {block.questions[0].prompt}")
    if not probes and block.prompts:
        probes.append(f"Can you do this task: {block.prompts[0]}")
    if not probes and block.scene_description:
        probes.append(f"Can you work on this task: {block.scene_description}")
    return _dedupe_strings(probes)[:2]


def _build_branchable_topics(
    *,
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    focus_vocabulary: list[str],
) -> list[str]:
    topics = list(focus_vocabulary)
    if page.theme:
        topics.append(page.theme)
    if block.section_title:
        topics.append(block.section_title)
    return _dedupe_strings(topics)[:8]


def _build_learning_targets(
    scope: NormalizedTextbookPage,
    teaching_blocks: list[TeachingBlockRecord],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    scope_prefix = f"{scope.grade}{scope.semester}{scope.unit}"
    for block in teaching_blocks:
        target_uid = f"LT-{scope_prefix}-{_block_code(block.block_uid)}-goal"
        result.append(
            {
                "target_uid": target_uid,
                "block_uid": block.block_uid,
                "category": block.block_type,
                "text": block.teaching_goal,
                "mastery_signal_examples": _mastery_signals_for_block(block.block_type),
            }
        )
    return result


def _mastery_signals_for_block(block_type: str) -> dict[str, str]:
    if block_type in {"dialogue_core", "dialogue_practice", "extension_task", "story_time"}:
        return {
            "mastered": "Learner completes the spoken task with limited support.",
            "shaky": "Learner completes part of the task but still needs prompting.",
            "not_mastered": "Learner cannot complete the task without full imitation.",
        }
    if block_type in {"vocabulary_core", "summary_wrap_up", "phonics"}:
        return {
            "mastered": "Learner gives the target word or pattern accurately.",
            "shaky": "Learner recognizes the target but responds with noticeable hesitation or error.",
            "not_mastered": "Learner does not recognize or produce the target item.",
        }
    if block_type in {"listening_probe", "assessment_quiz", "practice_fill_blank", "reading_passage"}:
        return {
            "mastered": "Learner identifies the key answer correctly.",
            "shaky": "Learner identifies part of the answer only.",
            "not_mastered": "Learner cannot identify the key answer.",
        }
    return {
        "mastered": "Learner completes the target task accurately.",
        "shaky": "Learner completes the task with partial accuracy.",
        "not_mastered": "Learner cannot complete the task.",
    }


def _build_wordlist_records(
    word_entries: list[NormalizedWordListEntry],
    teaching_blocks: list[TeachingBlockRecord],
) -> list[WordListEntryRecord]:
    records: list[WordListEntryRecord] = []

    for entry in word_entries:
        key = _normalize_lookup_key(entry.word)
        records.append(
            WordListEntryRecord(
                unit=entry.unit,
                word=entry.word,
                phonetic=entry.phonetic,
                chinese=entry.chinese,
                emphasized=entry.emphasized,
                linked_block_uids=_link_word_to_blocks(key, teaching_blocks),
            )
        )
    return records


def _build_knowledge_atoms(
    *,
    pages: list[NormalizedTextbookPage],
    teaching_blocks: list[TeachingBlockRecord],
    word_entry_by_word: dict[str, NormalizedWordListEntry],
) -> list[dict[str, Any]]:
    word_gloss_by_text = _build_word_gloss_lookup(pages, word_entry_by_word)
    pattern_gloss_by_text = _build_pattern_gloss_lookup(pages)
    block_word_text_by_key = _build_block_word_text_lookup(teaching_blocks)
    linked_blocks_by_pattern = _build_pattern_block_links(teaching_blocks)
    result: list[dict[str, Any]] = []

    all_word_keys = sorted(set(block_word_text_by_key) | set(word_entry_by_word))
    for normalized_word in all_word_keys:
        entry = word_entry_by_word.get(normalized_word)
        text = entry.word if entry is not None else block_word_text_by_key[normalized_word]
        result.append(
            {
                "atom_uid": f"KA-{_slugify(text)}",
                "atom_type": "word",
                "text": text,
                "gloss": word_gloss_by_text.get(normalized_word),
                "linked_blocks": _link_word_to_blocks(normalized_word, teaching_blocks),
            }
        )

    for pattern_text, linked_blocks in sorted(linked_blocks_by_pattern.items()):
        result.append(
            {
                "atom_uid": f"KA-pattern-{_slugify(pattern_text)}",
                "atom_type": "sentence_pattern",
                "text": pattern_text,
                "gloss": pattern_gloss_by_text.get(pattern_text),
                "linked_blocks": linked_blocks,
            }
        )

    return result


def _build_word_gloss_lookup(
    pages: list[NormalizedTextbookPage],
    word_entry_by_word: dict[str, NormalizedWordListEntry],
) -> dict[str, str | None]:
    result = {
        key: entry.chinese for key, entry in word_entry_by_word.items()
    }
    for page in pages:
        for block in page.blocks:
            for item in block.vocabulary:
                key = _normalize_lookup_key(item.word)
                result.setdefault(key, item.chinese)
    return result


def _build_pattern_gloss_lookup(
    pages: list[NormalizedTextbookPage],
) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for page in pages:
        for block in page.blocks:
            for pattern in block.patterns:
                result.setdefault(pattern.english, pattern.chinese)
    return result


def _build_block_word_text_lookup(
    teaching_blocks: list[TeachingBlockRecord],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for block in teaching_blocks:
        for word in block.focus_vocabulary:
            key = _normalize_lookup_key(word)
            result.setdefault(key, word)
    return result


def _build_pattern_block_links(
    teaching_blocks: list[TeachingBlockRecord],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for block in teaching_blocks:
        for pattern in block.core_patterns:
            if not pattern:
                continue
            result.setdefault(pattern, []).append(block.block_uid)
    return result


def _link_word_to_blocks(
    normalized_word: str,
    teaching_blocks: list[TeachingBlockRecord],
) -> list[str]:
    linked_blocks: list[str] = []
    token_pattern = re.compile(rf"(^|\s){re.escape(normalized_word)}($|\s)")

    for block in teaching_blocks:
        matches = False
        for word in block.focus_vocabulary:
            normalized_focus = _normalize_lookup_key(word)
            if normalized_word == normalized_focus:
                matches = True
                break
            if token_pattern.search(normalized_focus):
                matches = True
                break
        if matches:
            linked_blocks.append(block.block_uid)

    return linked_blocks


def _select_unit_word_list_entries(
    sections: list[NormalizedWordListSection],
    unit: str | None,
) -> list[NormalizedWordListEntry]:
    if unit is None:
        return []
    label = _word_list_unit_label(unit)
    if label is None:
        return []
    for section in sections:
        if section.unit == label:
            return section.entries
    return []


def _word_list_unit_label(unit: str) -> str | None:
    match = re.fullmatch(r"U(\d+)", unit)
    if not match:
        return None
    return f"Unit {int(match.group(1))}"


def _page_matches_scope(page: NormalizedTextbookPage, unit: str) -> bool:
    if page.unit == unit:
        if _MAIN_UNIT_RE.fullmatch(unit):
            theme = (page.theme or "").casefold()
            return "recycle" not in theme
        return True

    if _RECYCLE_RE.fullmatch(unit):
        theme = (page.theme or "").casefold().replace(" ", "")
        recycle_key = unit.casefold().replace(" ", "")
        return recycle_key in theme
    return False


def _is_main_textbook_page(page: NormalizedTextbookPage) -> bool:
    unit = page.unit or ""
    if unit == "U0":
        return False
    if unit.startswith("A"):
        return False
    if unit.startswith("Appendix"):
        return False
    return True


def _validate_and_sort_pages(
    pages: list[NormalizedTextbookPage],
) -> list[NormalizedTextbookPage]:
    if not pages:
        raise ValueError("At least one normalized page is required")

    ordered_pages = sorted(
        pages,
        key=lambda page: (page.page if page.page is not None else 10**9, page.page_uid),
    )
    first = ordered_pages[0]
    for page in ordered_pages[1:]:
        if (
            page.grade != first.grade
            or page.semester != first.semester
            or page.unit != first.unit
        ):
            raise ValueError("All selected pages must share the same grade, semester, and unit")
    return ordered_pages


def _dedupe_pages_by_uid(
    pages: list[NormalizedTextbookPage],
) -> list[NormalizedTextbookPage]:
    deduped: dict[str, NormalizedTextbookPage] = {}
    ordered_uids: list[str] = []
    for page in pages:
        existing = deduped.get(page.page_uid)
        if existing is None:
            deduped[page.page_uid] = page
            ordered_uids.append(page.page_uid)
            continue
        if existing.model_dump(mode="json") != page.model_dump(mode="json"):
            raise ValueError(f"Conflicting duplicate page_uid detected: {page.page_uid}")
    return [deduped[page_uid] for page_uid in ordered_uids]


def _retag_page_for_scope(
    page: NormalizedTextbookPage,
    *,
    semester: str,
    unit: str,
) -> NormalizedTextbookPage:
    page_uid = _canonical_page_uid(
        grade=page.grade,
        semester=semester,
        unit=unit,
        page=page.page,
        raw_page_uid=page.page_uid,
    )
    blocks = [
        block.model_copy(
            update={
                "page_uid": page_uid,
                "block_uid": f"{page_uid}-D{index}",
            }
        )
        for index, block in enumerate(page.blocks, start=1)
    ]
    return page.model_copy(
        update={
            "semester": semester,
            "unit": unit,
            "page_uid": page_uid,
            "blocks": blocks,
        }
    )


def _scope_page_numbers(
    pages: list[NormalizedTextbookPage],
) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    for page in pages:
        for number in _page_numbers(page=page.page, raw_page_uid=page.page_uid):
            if number in seen:
                continue
            seen.add(number)
            numbers.append(number)
    return numbers


def _canonical_page_uid(
    *,
    grade: str,
    semester: str,
    unit: str | None,
    page: int | None,
    raw_page_uid: str,
) -> str:
    page_code = _page_code(page=page, raw_page_uid=raw_page_uid)
    return f"TB-{grade}{semester}{unit or 'UNKNOWN'}-P{page_code}"


def _page_numbers(
    *,
    page: int | None,
    raw_page_uid: str,
) -> list[int]:
    if page is not None:
        return [page]
    page_code = _page_code(page=page, raw_page_uid=raw_page_uid)
    if "-" not in page_code:
        return [int(page_code)]
    start, end = page_code.split("-", 1)
    return list(range(int(start), int(end) + 1))


def _page_code(
    *,
    page: int | None,
    raw_page_uid: str,
) -> str:
    if page is not None:
        return str(page)
    match = re.search(r"-P(\d+(?:-\d+)?)$", raw_page_uid)
    if not match:
        raise ValueError(f"Cannot extract page code from page uid: {raw_page_uid}")
    return match.group(1)


def _block_code(block_uid: str) -> str:
    match = re.search(r"(P\d+(?:-\d+)?-D\d+)$", block_uid)
    if match:
        return match.group(1)
    return _slugify(block_uid)


def _normalize_lookup_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _slugify(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _default_repo_root() -> Path:
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = ancestor / "app" / "knowledge"
        if candidate.exists():
            return ancestor
    raise FileNotFoundError("Unable to locate repository root containing app/knowledge")
