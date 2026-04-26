"""Deterministic draft builders from normalized raw textbook pages."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from pathlib import Path

from lightrag.orchestrator.lesson_runtime import (
    PageLessonRecord,
    PilotLessonFile,
    ScopeInfo,
    TeachingBlockRecord,
)
from lightrag.orchestrator.raw_curriculum import (
    NormalizedTextbookBlock,
    NormalizedTextbookPage,
)

_REPAIR_MODES_BY_BLOCK_TYPE = {
    "listening_exercise": ["repeat", "choice_probe", "asr_clarify"],
    "listening_probe": ["repeat", "choice_probe", "asr_clarify"],
    "dialogue_core": ["repeat", "slow_read", "word_drill", "sentence_drill", "asr_clarify"],
    "dialogue_practice": ["choice_probe", "word_drill", "sentence_drill"],
    "sentence_pattern_practice": ["slow_read", "word_drill", "sentence_drill"],
    "roleplay_task": ["choice_probe", "word_drill", "sentence_drill"],
    "vocabulary_core": ["repeat", "word_drill", "choice_probe", "asr_clarify"],
    "reading_passage": ["repeat", "slow_read", "choice_probe"],
    "grammar_point": ["repeat", "sentence_drill", "choice_probe"],
    "phonics": ["repeat", "slow_read", "word_drill"],
    "writing_prompt": ["choice_probe", "sentence_drill"],
    "practice_write": ["choice_probe", "sentence_drill"],
    "story_time": ["repeat", "slow_read", "choice_probe"],
}
_SKIP_DIALOGUE_ANSWERS = {
    "ok.",
    "thanks.",
    "thank you.",
    "here you are.",
}
_DRINK_WORDS = {
    "coffee",
    "juice",
    "milk",
    "orange juice",
    "tea",
    "water",
}
_SOME_WORDS = _DRINK_WORDS | {
    "ice cream",
}
_BLOCK_PRIORITY_WEIGHTS = {
    "dialogue_core": 0,
    "vocabulary_core": 0,
    "sentence_pattern_practice": 1,
    "dialogue_practice": 2,
    "roleplay_task": 3,
    "listening_probe": 4,
    "listening_exercise": 4,
    "reading_passage": 5,
    "grammar_point": 5,
    "phonics": 5,
    "writing_prompt": 6,
    "practice_write": 6,
    "story_time": 6,
}
_P24_SPLIT_DIALOGUE_PRACTICE_PAGE_UID = "TB-G5S1U3-P24"
_P24_SPLIT_DIALOGUE_PRACTICE_SOURCE_UID = "TB-G5S1U3-P24-D3"
_P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID = "TB-G5S1U3-P24-D4"


@dataclass(frozen=True)
class DraftTargetSpec:
    target_uid: str
    block_uid: str
    category: str
    text: str


def build_pilot_draft(
    pages: list[NormalizedTextbookPage],
    *,
    pilot_id: str,
) -> PilotLessonFile:
    """Project one normalized unit slice into a draft pilot schema."""
    ordered_pages = _validate_and_sort_pages(pages)
    first = ordered_pages[0]
    priority_block_uids = {
        page.page_uid: _build_priority_block_uids(page) for page in ordered_pages
    }
    teaching_blocks = [
        record
        for page in ordered_pages
        for record in build_teaching_block_records(
            page,
            priority_block_uids=priority_block_uids[page.page_uid],
        )
    ]
    target_specs = _sort_target_specs(
        ordered_pages,
        priority_block_uids,
        _collect_target_specs(ordered_pages),
    )
    learning_targets = _build_learning_targets(target_specs)
    knowledge_atoms = _build_knowledge_atoms(first, target_specs, ordered_pages, teaching_blocks)
    block_target_uids = _group_target_uids_by_block(target_specs)
    page_by_uid = {page.page_uid: page for page in ordered_pages}
    raw_block_by_uid = {
        block.block_uid: block
        for page in ordered_pages
        for block in page.blocks
    }
    teaching_blocks = [
        block.model_copy(
            update={
                "learning_target_uids": _refine_block_target_uids(
                    page_by_uid[block.page_uid],
                    raw_block_by_uid[_source_block_uid_for_generated_block(block.block_uid)],
                    block_target_uids.get(block.block_uid, []),
                )
            }
        )
        for block in teaching_blocks
    ]
    page_lessons = [
        build_page_lesson_record(
            page,
            ordered_pages=ordered_pages,
            block_target_uids=block_target_uids,
            priority_block_uids=priority_block_uids[page.page_uid],
        )
        for page in ordered_pages
    ]

    return PilotLessonFile(
        pilot_id=pilot_id,
        scope=ScopeInfo(
            grade=first.grade,
            semester=first.semester,
            unit=first.unit,
            pages=[page.page for page in ordered_pages],
        ),
        source_files=_build_source_files(first),
        learning_targets=learning_targets,
        knowledge_atoms=knowledge_atoms,
        page_lessons=page_lessons,
        teaching_blocks=teaching_blocks,
    )


def default_pilot_draft_output_path(
    pilot_id: str,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Return a stable repository path for a generated pilot draft."""
    root = repo_root or _default_repo_root()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", pilot_id).strip("-") or "pilot-draft"
    return (root / "app/knowledge/structured/drafts" / f"{slug}.json").resolve()


def build_page_lesson_record(
    page: NormalizedTextbookPage,
    *,
    ordered_pages: list[NormalizedTextbookPage],
    block_target_uids: dict[str, list[str]],
    priority_block_uids: list[str],
) -> PageLessonRecord:
    return PageLessonRecord(
        page_uid=page.page_uid,
        page_type=page.page_type_hint,
        page_intro_cn=_build_page_intro(page),
        entry_probe_questions=_build_page_probe_questions(page),
        priority_blocks=priority_block_uids,
        assumed_prior_knowledge=_build_assumed_prior_knowledge(
            page,
            ordered_pages=ordered_pages,
            block_target_uids=block_target_uids,
        ),
    )


def build_teaching_block_records(
    page: NormalizedTextbookPage,
    *,
    priority_block_uids: list[str],
) -> list[TeachingBlockRecord]:
    records: list[TeachingBlockRecord] = []
    priority_index = {
        block_uid: index for index, block_uid in enumerate(priority_block_uids)
    }

    for block in page.blocks:
        if _is_p24_split_dialogue_practice_block(page, block):
            for record in _build_p24_split_dialogue_practice_records(
                page,
                block,
                priority_block_uids=priority_block_uids,
                priority_index=priority_index,
            ):
                records.append(record)
            continue

        pilot_block_type = _pilot_block_type(block)
        focus_vocabulary = _build_focus_vocabulary(page, block)
        core_patterns = _build_core_patterns(page, block)
        allowed_answer_scope = _build_allowed_answer_scope(page, block)
        block_index = priority_index.get(block.block_uid, len(priority_block_uids))
        records.append(
            TeachingBlockRecord(
                block_uid=block.block_uid,
                page_uid=page.page_uid,
                page_type=page.page_type_hint,
                block_type=pilot_block_type,
                source_refs=[block.block_uid],
                teaching_goal=_build_block_goal(page, block),
                teaching_summary=_build_block_summary(
                    page,
                    block,
                    focus_vocabulary,
                    core_patterns,
                ),
                focus_vocabulary=focus_vocabulary,
                core_patterns=core_patterns,
                allowed_answer_scope=allowed_answer_scope,
                entry_probe_questions=_build_block_probe_questions(page, block),
                repair_modes=_REPAIR_MODES_BY_BLOCK_TYPE.get(pilot_block_type, ["repeat"]),
                next_block_uids=priority_block_uids[block_index + 1 :],
                learning_target_uids=[],
                branchable_topics=_build_branchable_topics(page, block),
                return_anchors=_build_return_anchors(
                    page,
                    block,
                    core_patterns,
                    allowed_answer_scope,
                ),
            )
        )

    return records


def _validate_and_sort_pages(
    pages: list[NormalizedTextbookPage],
) -> list[NormalizedTextbookPage]:
    if not pages:
        raise ValueError("At least one normalized page is required to build a pilot draft")

    first = pages[0]
    if first.unit is None:
        raise ValueError("Pilot draft pages must have a unit value")
    if first.page is None:
        raise ValueError("Pilot draft pages must have a page number")

    ordered_pages = sorted(pages, key=lambda page: (page.page, page.page_uid))
    for page in ordered_pages[1:]:
        if page.unit is None:
            raise ValueError("Pilot draft pages must have a unit value")
        if page.page is None:
            raise ValueError("Pilot draft pages must have a page number")
        if (
            page.grade != first.grade
            or page.semester != first.semester
            or page.unit != first.unit
        ):
            raise ValueError("Pilot draft pages must share one grade/semester/unit scope")

    return ordered_pages


def _build_page_intro(page: NormalizedTextbookPage) -> str:
    dialogue_core = _first_block_by_types(page, {"dialogue_core"})
    vocabulary_core = _first_block_by_types(page, {"vocabulary_core"})
    sentence_pattern = _first_block_by_types(page, {"sentence_pattern_practice"})

    if dialogue_core is not None and _page_mentions_ordering_language(page):
        if _block_has_need_state_word(dialogue_core):
            return (
                "This page teaches ordering food and drinks. "
                "The teacher should first check whether the learner understands "
                "hungry and the two core questions."
            )
        return (
            "This page teaches ordering food and drinks. "
            "The teacher should first check whether the learner can ask the two core questions."
        )

    if (
        page.page_type_hint == "vocabulary"
        and vocabulary_core is not None
        and sentence_pattern is not None
        and _page_mentions_ordering_language(page)
    ):
        return "This page teaches food and drink words, then uses I'd like ... for ordering."

    parts: list[str] = []
    if page.theme:
        parts.append(f"本页主题：{page.theme}。")
    first_scene = next(
        (block.scene_description for block in page.blocks if block.scene_description),
        None,
    )
    if first_scene:
        parts.append(first_scene)
    elif page.page_type_hint:
        parts.append(f"本页包含 {page.page_type_hint} 相关练习。")

    return " ".join(parts) or "本页需要人工补充导语。"


def _build_page_probe_questions(page: NormalizedTextbookPage) -> list[str]:
    probes: list[str] = []
    dialogue_core = _first_block_by_types(page, {"dialogue_core"})
    sentence_pattern = _first_block_by_types(page, {"sentence_pattern_practice"})
    vocabulary_core = _first_block_by_types(page, {"vocabulary_core"})

    if dialogue_core is not None:
        target_word = _select_dialogue_core_word_target(dialogue_core)
        first_question = _first_question_pattern(_build_core_patterns(page, dialogue_core))
        if target_word:
            probes.append(f"What does {target_word} mean?")
        if first_question:
            probes.append(f"Can you say: {first_question}")
        return _dedupe_strings(probes)[:2]

    model_sentence = _first_id_like_sentence(sentence_pattern) if sentence_pattern else None
    if model_sentence:
        anchor_word = _extract_order_item(model_sentence)
        if anchor_word:
            probes.append(f"Do you know the word {anchor_word}?")
        probes.append(_render_say_prompt(model_sentence))
        return _dedupe_strings(probes)[:2]

    if vocabulary_core is not None:
        probes.extend(_build_block_probe_questions(page, vocabulary_core))
    return _dedupe_strings(probes)[:2]


def _build_assumed_prior_knowledge(
    page: NormalizedTextbookPage,
    *,
    ordered_pages: list[NormalizedTextbookPage],
    block_target_uids: dict[str, list[str]],
) -> list[dict]:
    dialogue_core = _first_block_by_types(page, {"dialogue_core"})
    sentence_pattern = _first_block_by_types(page, {"sentence_pattern_practice"})
    vocabulary_core = _first_block_by_types(page, {"vocabulary_core"})
    page_index = next(
        (index for index, candidate in enumerate(ordered_pages) if candidate.page_uid == page.page_uid),
        0,
    )

    if page_index == 0 and dialogue_core is not None:
        target_uids = block_target_uids.get(dialogue_core.block_uid, [])
        if not target_uids:
            return []
        topic = "basic target words and response language from earlier grades"
        if _page_mentions_ordering_language(page) or _block_has_need_state_word(dialogue_core):
            topic = "basic food words and need-state language from earlier grades"
        return [
            {
                "topic": topic,
                "source": "grade_level_default",
                "confidence": "low",
                "verification_status": "unverified",
                "verify_by_block_uid": dialogue_core.block_uid,
                "learning_target_uids": target_uids,
            }
        ]

    previous_page = ordered_pages[page_index - 1] if page_index > 0 else None
    if previous_page is None or sentence_pattern is None:
        return []

    target_uids = list(block_target_uids.get(sentence_pattern.block_uid, []))
    model_sentence = _first_id_like_sentence(sentence_pattern)
    anchor_word = _extract_order_item(model_sentence) if model_sentence else None
    if anchor_word and vocabulary_core is not None:
        anchor_target_uid = _find_word_target_uid(
            anchor_word,
            block_target_uids.get(vocabulary_core.block_uid, []),
        )
        if anchor_target_uid and anchor_target_uid not in target_uids:
            target_uids.append(anchor_target_uid)
    if not target_uids:
        return []

    previous_page_number = previous_page.page or "previous"
    topic = f"page {previous_page_number} ordering frame with I'd like answers"
    return [
        {
            "topic": topic,
            "source": "unit_progression",
            "confidence": "medium",
            "verification_status": "unverified",
            "verify_by_block_uid": sentence_pattern.block_uid,
            "learning_target_uids": target_uids,
        }
    ]


def _build_source_files(page: NormalizedTextbookPage) -> list[str]:
    grade_semester = f"{page.grade.lower()}{page.semester.lower()}"
    unit_ref = _normalize_unit_ref(page.unit)
    if unit_ref is None:
        return [f"raw_textbook_{grade_semester}"]
    return [
        f"raw_textbook_{grade_semester}_{unit_ref}",
        f"raw_wordlist_{grade_semester}",
        f"raw_useful_expressions_{grade_semester}",
    ]


def _collect_target_specs(
    pages: list[NormalizedTextbookPage],
) -> list[DraftTargetSpec]:
    seen_target_uids: set[str] = set()
    result: list[DraftTargetSpec] = []

    for page in pages:
        scope_prefix = _scope_prefix(page)
        for block in page.blocks:
            raw_specs = _target_specs_for_block(scope_prefix, page, block)
            for spec in _refine_target_specs(page, block, raw_specs):
                if spec.target_uid in seen_target_uids:
                    result.append(spec)
                    continue
                seen_target_uids.add(spec.target_uid)
                result.append(spec)

    return result


def _build_learning_targets(target_specs: list[DraftTargetSpec]) -> list[dict]:
    seen_target_uids: set[str] = set()
    result: list[dict] = []
    for spec in target_specs:
        if spec.target_uid in seen_target_uids:
            continue
        seen_target_uids.add(spec.target_uid)
        result.append(
            {
                "target_uid": spec.target_uid,
                "category": spec.category,
                "mastery_signal_examples": _mastery_signal_examples(
                    spec.target_uid,
                    spec.category,
                    spec.text,
                ),
            }
        )
    return result


def _sort_target_specs(
    ordered_pages: list[NormalizedTextbookPage],
    priority_block_uids: dict[str, list[str]],
    target_specs: list[DraftTargetSpec],
) -> list[DraftTargetSpec]:
    page_order = {
        page.page_uid: index
        for index, page in enumerate(ordered_pages)
    }
    block_order = {
        block_uid: index
        for page in ordered_pages
        for index, block_uid in enumerate(priority_block_uids[page.page_uid])
    }
    block_to_page = {
        block_uid: page.page_uid
        for page in ordered_pages
        for block_uid in priority_block_uids[page.page_uid]
    }
    enumerated_specs = list(enumerate(target_specs))
    enumerated_specs.sort(
        key=lambda pair: (
            page_order.get(block_to_page.get(pair[1].block_uid, ""), 99),
            block_order.get(pair[1].block_uid, 99),
            pair[0],
        )
    )
    return [spec for _, spec in enumerated_specs]


def _build_knowledge_atoms(
    page: NormalizedTextbookPage,
    target_specs: list[DraftTargetSpec],
    pages: list[NormalizedTextbookPage],
    teaching_blocks: list[TeachingBlockRecord],
) -> list[dict]:
    result: list[dict] = []
    seen_atom_uids: set[str] = set()
    word_target_texts = []
    pattern_target_texts = []

    for spec in target_specs:
        if spec.category == "word":
            word_target_texts.append(spec.text)
        elif spec.category == "sentence_pattern":
            pattern_target_texts.append(spec.text)

    for word in _dedupe_strings(word_target_texts):
        atom_uid = f"KA-{_scope_prefix(page)}-word-{_slugify(word)}"
        if atom_uid in seen_atom_uids:
            continue
        seen_atom_uids.add(atom_uid)
        result.append(
            {
                "atom_uid": atom_uid,
                "atom_type": "word",
                "text": word,
                "gloss": _lookup_word_gloss(word, pages),
                "linked_blocks": _linked_blocks_for_word(word, teaching_blocks),
            }
        )

    for pattern in _dedupe_strings(pattern_target_texts):
        atom_uid = f"KA-{_scope_prefix(page)}-{_atom_pattern_suffix(pattern)}"
        if atom_uid in seen_atom_uids:
            continue
        seen_atom_uids.add(atom_uid)
        result.append(
            {
                "atom_uid": atom_uid,
                "atom_type": "sentence_pattern",
                "text": pattern,
                "linked_blocks": _linked_blocks_for_pattern(pattern, teaching_blocks),
            }
        )

    return result


def _group_target_uids_by_block(
    target_specs: list[DraftTargetSpec],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for spec in target_specs:
        if spec.target_uid not in grouped[spec.block_uid]:
            grouped[spec.block_uid].append(spec.target_uid)
    return dict(grouped)


def _build_block_goal(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> str:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        if _page_mentions_ordering_language(page):
            return "Catch key food words from a short listening task."
        return "Catch the key answer from a short listening task."

    if pilot_block_type == "dialogue_core":
        if _has_food_and_drink_questions(block):
            return "Understand and say the core ordering questions for food and drink."
        return "Understand and say the core dialogue pattern."

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        return "Use the food and drink question-answer pattern in short role-play."

    if pilot_block_type == "sentence_pattern_practice":
        return "Use I'd like ... to order one food item politely."

    if pilot_block_type == "roleplay_task":
        return "Role-play waiter and customer with one food item and one drink item."

    if pilot_block_type == "vocabulary_core":
        if _page_mentions_ordering_language(page):
            return "Recognize and say the core food and drink words on the page."
        return "Recognize and say the core vocabulary on the page."

    base = {
        "reading_passage": "Read and understand the short passage",
        "grammar_point": "Understand and use the target grammar pattern",
        "phonics": "Notice and repeat the target sounds",
        "writing_prompt": "Respond to the writing prompt with a short sentence",
        "practice_write": "Complete the writing practice",
    }.get(pilot_block_type, f"Work on the {pilot_block_type.replace('_', ' ')} activity")
    return f"{base}."


def _pilot_block_type(block: NormalizedTextbookBlock) -> str:
    if block.block_type == "listening_exercise":
        return "listening_probe"
    if block.block_type != "dialogue_practice":
        return block.block_type

    section_title = (block.section_title or "").casefold()
    pattern_texts = _canonical_pattern_texts(block)
    has_order_question = any(
        "what would you like to " in pattern.casefold() for pattern in pattern_texts
    )
    has_id_like = any("i'd like" in pattern.casefold() for pattern in pattern_texts)

    if block.templates or "role-play" in section_title or "role play" in section_title:
        return "roleplay_task"
    if has_id_like and not block.word_bank:
        return "sentence_pattern_practice"
    if has_order_question and block.word_bank:
        return "dialogue_practice"
    return "dialogue_practice"


def _target_specs_for_block(
    scope_prefix: str,
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[DraftTargetSpec]:
    result: list[DraftTargetSpec] = []
    page_code = _page_code(page.page_uid)
    section_title = (block.section_title or "").casefold()
    pattern_texts = _canonical_pattern_texts(block)
    has_order_question = any(
        "what would you like to " in pattern.casefold() for pattern in pattern_texts
    )
    has_id_like = any("i'd like" in pattern.casefold() for pattern in pattern_texts)

    if block.block_type == "listening_exercise":
        result.append(
            _make_target_spec(
                scope_prefix,
                page_code,
                block.block_uid,
                "listening-food-keywords",
                "listening_task",
                "key words from the listening task",
            )
        )
        return result

    if block.block_type == "dialogue_core":
        for pattern in pattern_texts:
            if "?" not in pattern:
                continue
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    _pattern_suffix(pattern),
                    "sentence_pattern",
                    pattern,
                )
            )

        word_target = _select_dialogue_core_word_target(block)
        if word_target:
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    f"word-{_slugify(word_target)}",
                    "word",
                    word_target,
                )
            )
        return result

    if block.block_type == "vocabulary_core":
        for item in block.vocabulary:
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    f"word-{_slugify(item.word)}",
                    "word",
                    item.word,
                )
            )
        return result

    if block.block_type == "dialogue_practice":
        if _is_p24_split_dialogue_practice_block(page, block):
            return [
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    "answer-id-like",
                    "sentence_pattern",
                    "I'd like ... , please.",
                ),
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    _P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID,
                    "dialogue-food-drink-roleplay",
                    "dialogue_task",
                    "short food and drink dialogue",
                ),
            ]

        if has_order_question and block.word_bank:
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    "answer-id-like",
                    "sentence_pattern",
                    "I'd like ... , please.",
                )
            )
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    "dialogue-food-drink-roleplay",
                    "dialogue_task",
                    "short food and drink dialogue",
                )
            )
            return result

        if block.templates or "role-play" in section_title or "role play" in section_title:
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    "roleplay-ordering",
                    "dialogue_task",
                    "role-play ordering dialogue",
                )
            )
            return result

        if has_id_like:
            result.append(
                _make_target_spec(
                    scope_prefix,
                    page_code,
                    block.block_uid,
                    "pattern-id-like",
                    "sentence_pattern",
                    "I'd like ... , please.",
                )
            )

    return result


def _make_target_spec(
    scope_prefix: str,
    page_code: str,
    block_uid: str,
    suffix: str,
    category: str,
    text: str,
) -> DraftTargetSpec:
    return DraftTargetSpec(
        target_uid=f"LT-{scope_prefix}-{page_code}-{suffix}",
        block_uid=block_uid,
        category=category,
        text=text,
    )


def _refine_target_specs(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    target_specs: list[DraftTargetSpec],
) -> list[DraftTargetSpec]:
    if _pilot_block_type(block) != "vocabulary_core" or not _page_mentions_ordering_language(page):
        return target_specs

    allowed_words = set(_ordering_vocab_target_words(page))
    ordered_specs: list[DraftTargetSpec] = []
    for word in _ordering_vocab_target_words(page):
        spec = next((item for item in target_specs if item.text == word), None)
        if spec is not None:
            ordered_specs.append(spec)

    ordered_specs.extend(
        spec
        for spec in target_specs
        if spec.category != "word" or spec.text in allowed_words
    )
    return _dedupe_target_specs(ordered_specs)


def _build_block_summary(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    focus_vocabulary: list[str],
    core_patterns: list[str],
) -> str:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        prompt = next((item for item in block.prompts if item), "")
        subject = _extract_named_subject(prompt)
        if subject and "like to eat" in prompt.casefold():
            return f"Listen for what {subject} would like to eat and fill the blank from a small word bank."
        if subject:
            return f"Listen for the key words about what {subject} would like and fill the blank from a small word bank."
        return "Listen for the key words and fill the blank from a small word bank."

    if pilot_block_type == "dialogue_core":
        if _has_food_and_drink_questions(block):
            cue_words = [
                item.word
                for item in block.vocabulary
                if item.word in {"hungry", "thirsty"}
            ]
            cue_text = ""
            if cue_words:
                cue_text = f" with {' and '.join(cue_words)} cues"
            dialogue_type = "Family ordering dialogue" if _has_family_speakers(block) else "Ordering dialogue"
            return f"{dialogue_type}{cue_text}, plus two target questions about food and drink."
        return "Core dialogue practice with target questions and short answers."

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        return "Practice asking for food or drink choices with a small word bank and short exchanges."

    if pilot_block_type == "vocabulary_core":
        vocab_words = [item.word for item in block.vocabulary][:5]
        if _scene_mentions_restaurant(block) and vocab_words:
            return "A restaurant scene introduces " + _join_with_and(vocab_words) + "."
        if vocab_words:
            return "The page introduces " + _join_with_and(vocab_words) + "."

    if pilot_block_type == "sentence_pattern_practice":
        item = _extract_order_item(_first_id_like_sentence(block))
        if item:
            return f"Short model dialogue for ordering { _render_item_phrase(item) } with please.".replace("  ", " ")
        return "Short model dialogue for polite ordering with I'd like."

    if pilot_block_type == "roleplay_task":
        if block.templates:
            return "Restaurant role-play with a small order form and food-plus-drink output."
        return "Restaurant role-play with food and drink ordering output."

    parts: list[str] = []
    if block.scene_description:
        parts.append(block.scene_description)
    if core_patterns:
        parts.append("Key patterns: " + "; ".join(core_patterns[:2]))
    elif focus_vocabulary:
        parts.append("Focus vocabulary: " + ", ".join(focus_vocabulary[:5]))
    return " ".join(parts) or f"Draft summary for {block.block_type}."


def _build_focus_vocabulary(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        return _dedupe_strings(block.word_bank)[:5]

    if pilot_block_type == "sentence_pattern_practice":
        model_sentence = _first_id_like_sentence(block)
        anchor_word = _extract_order_item(model_sentence) if model_sentence else None
        focus = ["I'd like"]
        if anchor_word:
            focus.append(anchor_word)
        focus.append("please")
        return _dedupe_strings(focus)[:5]

    if pilot_block_type == "roleplay_task":
        focus = _roleplay_focus_vocabulary(page, block)
        return _dedupe_strings(focus)[:5]

    if pilot_block_type == "vocabulary_core":
        return [item.word for item in block.vocabulary][:5]

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        foods = [word for word in block.word_bank if not _is_drink_word(word)]
        drinks = [word for word in block.word_bank if _is_drink_word(word)]
        return _dedupe_strings(foods[:2] + drinks[:3])[:5]

    if pilot_block_type == "dialogue_core":
        return _dialogue_core_focus_vocabulary(block)

    return [item.word for item in block.vocabulary][:5]


def _build_core_patterns(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        pattern = _blank_prompt_pattern(block)
        return [pattern] if pattern else []

    question_patterns = _question_patterns_from_block(block)

    if pilot_block_type == "dialogue_core":
        answer_pattern = _first_id_like_sentence(block)
        patterns = question_patterns
        if answer_pattern:
            patterns.append(answer_pattern)
        return _dedupe_strings(patterns)[:4]

    if pilot_block_type == "sentence_pattern_practice":
        patterns = question_patterns
        answer_pattern = _first_id_like_sentence(block)
        if answer_pattern:
            patterns.append(answer_pattern)
        return _dedupe_strings(patterns)[:4]

    if pilot_block_type in {"dialogue_practice", "roleplay_task"}:
        patterns = question_patterns
        if question_patterns or block.word_bank or block.templates:
            patterns.append("I'd like ...")
        return _dedupe_strings(patterns)[:4]

    patterns = [pattern.english for pattern in block.patterns]
    if not patterns:
        patterns = [line.english for line in block.dialogue_lines if len(line.english) >= 5]
    return _dedupe_strings(patterns)[:4]


def _canonical_pattern_texts(block: NormalizedTextbookBlock) -> list[str]:
    result: list[str] = []
    source_texts = [pattern.english for pattern in block.patterns]
    source_texts.extend(
        line.english for line in block.dialogue_lines if len(line.english) >= 5
    )

    for text in source_texts:
        normalized = _canonicalize_pattern_text(text)
        if normalized:
            result.append(normalized)
    return _dedupe_strings(result)


def _canonicalize_pattern_text(text: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None
    lowered = normalized.casefold()
    if "what would you like to eat" in lowered:
        return "What would you like to eat?"
    if "what would you like to drink" in lowered:
        return "What would you like to drink?"
    if "i'd like" in lowered:
        return "I'd like ... , please."
    return normalized


def _select_dialogue_core_word_target(block: NormalizedTextbookBlock) -> str | None:
    adjective_like = [
        item.word
        for item in block.vocabulary
        if item.chinese and item.chinese.endswith("的")
    ]
    if adjective_like:
        return adjective_like[0]
    if block.vocabulary:
        return block.vocabulary[0].word
    return None


def _build_allowed_answer_scope(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        return _listening_allowed_answer_scope(block)

    if pilot_block_type == "dialogue_core":
        return _dialogue_core_allowed_answer_scope(block)

    if pilot_block_type == "vocabulary_core":
        return _sort_ordering_words([item.word for item in block.vocabulary])[:6]

    if pilot_block_type == "sentence_pattern_practice":
        return _sentence_pattern_allowed_answer_scope(page, block)

    if pilot_block_type == "roleplay_task":
        return _roleplay_allowed_answer_scope(page, block)

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        return _dialogue_practice_allowed_answer_scope(block)

    answers = [question.answer for question in block.questions if question.answer]
    if not answers:
        answers.extend(block.word_bank)
    return _dedupe_strings(answers)[:6]


def _build_block_probe_questions(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        normalized_answer = _normalized_listening_answer(block)
        if normalized_answer:
            return [f"Can you hear {normalized_answer} clearly?"]

    if pilot_block_type == "dialogue_core":
        probes: list[str] = []
        target_word = _select_dialogue_core_word_target(block)
        if target_word:
            probes.append(f"What does {target_word} mean?")
        first_question = _first_question_pattern(_build_core_patterns(page, block))
        if first_question:
            probes.append(f"Can you repeat: {first_question}")
        return _dedupe_strings(probes)[:2]

    if pilot_block_type == "vocabulary_core":
        sorted_words = _sort_ordering_words([item.word for item in block.vocabulary])
        anchor_word = _page_anchor_word(page)
        review_word = sorted_words[2] if len(sorted_words) >= 3 else (sorted_words[-1] if sorted_words else None)
        probes: list[str] = []
        if review_word:
            probes.append(f"Do you know {review_word}?")
        if anchor_word:
            probes.append(f"Can you read {anchor_word}?")
        return _dedupe_strings(probes)[:2]

    if pilot_block_type == "sentence_pattern_practice":
        model_sentence = _first_id_like_sentence(block)
        if model_sentence:
            return [_render_say_prompt(model_sentence)]

    if pilot_block_type == "roleplay_task":
        return ["If you are the customer, what would you order?"]

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        question_patterns = _question_patterns_from_block(block)
        drink_question = next(
            (pattern for pattern in question_patterns if "drink" in pattern.casefold()),
            None,
        )
        if drink_question:
            return [f"If I ask {_strip_terminal_punctuation(drink_question)}, how do you answer?"]

    probes: list[str] = []
    if block.questions:
        probes.append(block.questions[0].prompt)
    if not probes and block.vocabulary:
        probes.append(f"Do you know {block.vocabulary[0].word}?")
    if not probes:
        core_patterns = _build_core_patterns(page, block)
        if core_patterns:
            first = core_patterns[0]
            prefix = "Can you answer: " if "?" in first else "Can you say: "
            probes.append(f"{prefix}{first}")
    return _dedupe_strings(probes)[:2]


def _build_branchable_topics(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "listening_probe":
        topics = _listening_answer_tokens(block)
        topics.append("listening")
        return _dedupe_strings(topics)[:5]

    if pilot_block_type == "dialogue_core":
        adjective_words = [
            item.word
            for item in block.vocabulary
            if item.chinese and item.chinese.endswith("的")
        ]
        topics = ["food", "drink"]
        if _page_mentions_ordering_language(page):
            topics.append("restaurant")
        topics.extend(adjective_words)
        return _dedupe_strings(topics)[:5]

    if pilot_block_type == "dialogue_practice" and block.word_bank:
        return ["restaurant", "food choice", "drink choice"]

    if pilot_block_type == "sentence_pattern_practice":
        return ["polite order", "restaurant"]

    if pilot_block_type == "roleplay_task":
        return ["restaurant roleplay", "food", "drink"]

    if pilot_block_type == "vocabulary_core":
        sorted_words = _sort_ordering_words([item.word for item in block.vocabulary])
        foods = [word for word in sorted_words if not _is_drink_word(word) and word != "ice cream"]
        drinks = [word for word in sorted_words if _is_drink_word(word)]
        topics = foods[:3]
        if drinks:
            topics.append(drinks[0])
        return _dedupe_strings(topics)[:5]

    topics = [item.word for item in block.vocabulary] or block.word_bank
    if not topics and page.theme:
        topics = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", page.theme)
    return _dedupe_strings(topics)[:5]


def _build_return_anchors(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    core_patterns: list[str],
    allowed_answer_scope: list[str],
) -> list[str]:
    pilot_block_type = _pilot_block_type(block)

    if pilot_block_type == "vocabulary_core":
        anchors: list[str] = ["I'd like ..."]
        first_order_question = next(
            (
                pattern
                for sibling in page.blocks
                for pattern in _question_patterns_from_block(sibling)
                if "what would you like to eat" in pattern.casefold()
            ),
            None,
        )
        if first_order_question:
            anchors.append(first_order_question)
        return _dedupe_strings(anchors)[:3]

    if pilot_block_type == "sentence_pattern_practice":
        anchors = []
        model_sentence = _first_id_like_sentence(block)
        if model_sentence:
            anchors.append(model_sentence)
        anchors.append("I'd like ...")
        return _dedupe_strings(anchors)[:3]

    if pilot_block_type in {"dialogue_practice", "roleplay_task"}:
        anchors = [pattern for pattern in core_patterns if "?" in pattern]
        anchors.append("I'd like ...")
        return _dedupe_strings(anchors)[:3]

    if pilot_block_type == "dialogue_core":
        anchors = [pattern for pattern in core_patterns if "?" in pattern]
        model_sentence = _first_id_like_sentence(block)
        if model_sentence:
            anchors.append(model_sentence)
        return _dedupe_strings(anchors)[:3]

    anchors = [pattern for pattern in core_patterns if "?" in pattern]
    if not anchors:
        anchors = core_patterns[:]
    if not anchors:
        anchors = allowed_answer_scope[:]
    return _dedupe_strings(anchors)[:3]


def _build_priority_block_uids(page: NormalizedTextbookPage) -> list[str]:
    indexed_blocks = list(enumerate(page.blocks))
    indexed_blocks.sort(
        key=lambda pair: (
            _BLOCK_PRIORITY_WEIGHTS.get(_pilot_block_type(pair[1]), 99),
            pair[0],
        )
    )
    ordered = [block.block_uid for _, block in indexed_blocks]
    if (
        page.page_uid == _P24_SPLIT_DIALOGUE_PRACTICE_PAGE_UID
        and _P24_SPLIT_DIALOGUE_PRACTICE_SOURCE_UID in ordered
        and _P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID not in ordered
    ):
        insert_at = ordered.index(_P24_SPLIT_DIALOGUE_PRACTICE_SOURCE_UID) + 1
        ordered.insert(insert_at, _P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID)
    return ordered


def _is_p24_split_dialogue_practice_block(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> bool:
    return (
        page.page_uid == _P24_SPLIT_DIALOGUE_PRACTICE_PAGE_UID
        and block.block_uid == _P24_SPLIT_DIALOGUE_PRACTICE_SOURCE_UID
        and block.block_type == "dialogue_practice"
    )


def _source_block_uid_for_generated_block(block_uid: str) -> str:
    if block_uid == _P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID:
        return _P24_SPLIT_DIALOGUE_PRACTICE_SOURCE_UID
    return block_uid


def _build_p24_split_dialogue_practice_records(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    *,
    priority_block_uids: list[str],
    priority_index: dict[str, int],
) -> list[TeachingBlockRecord]:
    repair_modes = _REPAIR_MODES_BY_BLOCK_TYPE.get("dialogue_practice", ["repeat"])
    specs = [
        {
            "block_uid": block.block_uid,
            "source_refs": [block.block_uid],
            "teaching_goal": "Answer the drink question with a short ordering sentence.",
            "teaching_summary": "Practice drink choices with a small word bank and answer the drink question with I'd like ....",
            "focus_vocabulary": ["water", "tea"],
            "core_patterns": ["What would you like to drink?", "I'd like ..."],
            "allowed_answer_scope": ["I'd like water.", "I'd like some tea."],
            "entry_probe_questions": ["If I ask What would you like to drink, how do you answer?"],
            "branchable_topics": ["restaurant", "drink choice"],
            "return_anchors": ["What would you like to drink?", "I'd like ..."],
        },
        {
            "block_uid": _P24_SPLIT_DIALOGUE_PRACTICE_FOLLOWUP_UID,
            "source_refs": [block.block_uid],
            "teaching_goal": "Answer the food question with a short ordering sentence.",
            "teaching_summary": "Continue the ordering exchange with food choices and answer the eat question with I'd like ....",
            "focus_vocabulary": ["chicken and bread", "rice and vegetables"],
            "core_patterns": ["What would you like to eat?", "I'd like ..."],
            "allowed_answer_scope": [
                "I'd like chicken and bread.",
                "I'd like rice and vegetables.",
            ],
            "entry_probe_questions": ["If I ask What would you like to eat, how do you answer?"],
            "branchable_topics": ["restaurant", "food choice"],
            "return_anchors": ["What would you like to eat?", "I'd like ..."],
        },
    ]
    records: list[TeachingBlockRecord] = []
    for spec in specs:
        block_uid = spec["block_uid"]
        block_index = priority_index.get(block_uid, len(priority_block_uids))
        records.append(
            TeachingBlockRecord(
                block_uid=block_uid,
                page_uid=page.page_uid,
                page_type=page.page_type_hint,
                block_type="dialogue_practice",
                source_refs=spec["source_refs"],
                teaching_goal=spec["teaching_goal"],
                teaching_summary=spec["teaching_summary"],
                focus_vocabulary=spec["focus_vocabulary"],
                core_patterns=spec["core_patterns"],
                allowed_answer_scope=spec["allowed_answer_scope"],
                entry_probe_questions=spec["entry_probe_questions"],
                repair_modes=repair_modes,
                next_block_uids=priority_block_uids[block_index + 1 :],
                learning_target_uids=[],
                branchable_topics=spec["branchable_topics"],
                return_anchors=spec["return_anchors"],
            )
        )
    return records


def _first_block_by_types(
    page: NormalizedTextbookPage,
    block_types: set[str],
) -> NormalizedTextbookBlock | None:
    return next(
        (block for block in page.blocks if _pilot_block_type(block) in block_types),
        None,
    )


def _page_mentions_ordering_language(page: NormalizedTextbookPage) -> bool:
    texts = [
        page.theme or "",
        *[
            text
            for block in page.blocks
            for text in (
                block.scene_description or "",
                *[pattern.english for pattern in block.patterns],
                *[line.english for line in block.dialogue_lines],
                *block.prompts,
            )
        ],
    ]
    haystack = " ".join(texts).casefold()
    return "what would you like" in haystack or "i'd like" in haystack


def _scene_mentions_restaurant(block: NormalizedTextbookBlock) -> bool:
    text = " ".join(filter(None, [block.scene_description, *block.prompts])).casefold()
    return "restaurant" in text or "餐厅" in text


def _has_food_and_drink_questions(block: NormalizedTextbookBlock) -> bool:
    patterns = _question_patterns_from_block(block)
    has_food = any("eat" in pattern.casefold() for pattern in patterns)
    has_drink = any("drink" in pattern.casefold() for pattern in patterns)
    return has_food and has_drink


def _has_family_speakers(block: NormalizedTextbookBlock) -> bool:
    family_names = {"father", "mother", "mom", "mum", "dad", "sarah"}
    speakers = {line.speaker.casefold() for line in block.dialogue_lines if line.speaker}
    return bool(speakers & family_names)


def _block_has_need_state_word(block: NormalizedTextbookBlock) -> bool:
    return any(
        item.chinese and item.chinese.endswith("的")
        for item in block.vocabulary
    )


def _find_word_target_uid(word: str, target_uids: list[str]) -> str | None:
    needle = f"-word-{_slugify(word)}"
    return next(
        (uid for uid in target_uids if uid.casefold().endswith(needle.casefold())),
        None,
    )


def _refine_block_target_uids(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
    target_uids: list[str],
) -> list[str]:
    if _pilot_block_type(block) != "vocabulary_core" or not _page_mentions_ordering_language(page):
        return target_uids

    word_uid_map = {
        item.word: uid
        for item in block.vocabulary
        for uid in target_uids
        if uid.casefold().endswith(f"-word-{_slugify(item.word)}")
    }
    refined = [word_uid_map[word] for word in _ordering_vocab_target_words(page) if word in word_uid_map]
    return refined or target_uids


def _question_patterns_from_block(block: NormalizedTextbookBlock) -> list[str]:
    patterns = []
    for pattern in _canonical_pattern_texts(block):
        if "?" in pattern:
            patterns.append(pattern)
    for line in block.dialogue_lines:
        if "?" in line.english and len(line.english) >= 5:
            normalized = _canonicalize_pattern_text(line.english) or line.english.strip()
            patterns.append(normalized)
    return _dedupe_strings(patterns)


def _first_question_pattern(patterns: list[str]) -> str | None:
    return next((pattern for pattern in patterns if "?" in pattern), None)


def _blank_prompt_pattern(block: NormalizedTextbookBlock) -> str | None:
    prompt = next((question.prompt for question in block.questions if question.prompt), None)
    if not prompt:
        return None
    pattern = re.sub(r"_+", "...", prompt)
    pattern = re.sub(r"\.\.\.\.+", "...", pattern)
    pattern = re.sub(r"\s+", " ", pattern).strip()
    return pattern


def _normalized_listening_answer(block: NormalizedTextbookBlock) -> str | None:
    answer = next((question.answer for question in block.questions if question.answer), None)
    if not answer:
        return None
    tokens = _listening_answer_tokens_from_text(answer)
    if not tokens:
        return answer.strip()
    if len(tokens) == 1:
        return tokens[0]
    return " and ".join(tokens)


def _listening_allowed_answer_scope(block: NormalizedTextbookBlock) -> list[str]:
    normalized_answer = _normalized_listening_answer(block)
    if not normalized_answer:
        return _dedupe_strings(block.word_bank)[:3]

    scope = [normalized_answer]
    prompt = next((question.prompt for question in block.questions if question.prompt), None)
    if prompt:
        filled = _fill_blank_prompt(prompt, normalized_answer)
        if filled:
            scope.append(filled)
    return _dedupe_strings(scope)[:4]


def _listening_answer_tokens(block: NormalizedTextbookBlock) -> list[str]:
    normalized_answer = _normalized_listening_answer(block)
    if not normalized_answer:
        return list(block.word_bank[:2])
    return _listening_answer_tokens_from_text(normalized_answer)


def _listening_answer_tokens_from_text(text: str) -> list[str]:
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s*(?:,|and)\s*", text) if part.strip()]
    return parts


def _fill_blank_prompt(prompt: str, answer: str) -> str | None:
    normalized = prompt.strip()
    if not normalized:
        return None
    parts = _listening_answer_tokens_from_text(answer)
    if not parts:
        parts = [answer.strip()]
    for part in parts:
        normalized = re.sub(r"_+", part, normalized, count=1)
    normalized = re.sub(r"_+", answer, normalized, count=1)
    return re.sub(r"\s+", " ", normalized).strip()


def _dialogue_core_allowed_answer_scope(block: NormalizedTextbookBlock) -> list[str]:
    direct_answers: list[str] = []
    like_answers: list[str] = []
    need_state_variants: list[str] = []
    for line in block.dialogue_lines:
        normalized = line.english.casefold().strip()
        if "?" in line.english or normalized in _SKIP_DIALOGUE_ANSWERS:
            continue
        first_sentence = _first_sentence(line.english)
        if not first_sentence or len(first_sentence) < 5:
            continue
        lowered = first_sentence.casefold()
        if lowered.startswith("i'm "):
            expanded = "I am " + first_sentence[4:]
            need_state_variants.extend([expanded, first_sentence])
            continue
        if lowered.startswith("i am "):
            need_state_variants.extend([first_sentence, "I'm " + first_sentence[5:]])
            continue
        if "i'd like" in lowered:
            like_answers.append(first_sentence)
            continue
        direct_answers.append(first_sentence)
    return _dedupe_strings(direct_answers + like_answers + need_state_variants)[:6]


def _dialogue_core_focus_vocabulary(block: NormalizedTextbookBlock) -> list[str]:
    words = [item.word for item in block.vocabulary]
    trailing_foods = [word for word in words if word == "sandwich" or _looks_like_food_phrase(word)]
    remaining = [word for word in words if word not in trailing_foods]
    return _dedupe_strings(remaining + trailing_foods)[:5]


def _sentence_pattern_allowed_answer_scope(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    model_sentence = _first_id_like_sentence(block)
    scope: list[str] = []
    if model_sentence:
        scope.append(model_sentence)

    words = _sort_ordering_words(_page_vocab_words(page))
    anchor_word = _extract_order_item(model_sentence) if model_sentence else None
    extra_food = next(
        (word for word in words if word != anchor_word and not _is_drink_word(word)),
        None,
    )
    extra_drink = next((word for word in words if _is_drink_word(word)), None)
    for word in (extra_food, extra_drink):
        if not word:
            continue
        scope.append(_render_id_like_sentence(word))
    return _dedupe_strings(scope)[:4]


def _roleplay_allowed_answer_scope(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    food_words = [word for word in _sort_ordering_words(_page_vocab_words(page)) if not _is_drink_word(word)]
    drink_word = next((word for word in _sort_ordering_words(_page_vocab_words(page)) if _is_drink_word(word)), None)
    if not drink_word:
        return []
    scope = []
    for food in food_words[:2]:
        scope.append(f"I'd like {_render_item_phrase(food)} and {_render_item_phrase(drink_word)}.")
    return _dedupe_strings(scope)[:4]


def _dialogue_practice_allowed_answer_scope(block: NormalizedTextbookBlock) -> list[str]:
    drinks = [word for word in block.word_bank if _is_drink_word(word)]
    foods = [word for word in block.word_bank if not _is_drink_word(word)]
    scope: list[str] = []

    if "water" in drinks:
        scope.append("I'd like water.")
    elif drinks:
        scope.append(f"I'd like {_render_item_phrase(drinks[0])}.")

    second_drink = "tea" if "tea" in drinks else next(
        (word for word in drinks if word != "water"),
        None,
    )
    if second_drink:
        scope.append(f"I'd like {_render_item_phrase(second_drink)}.")

    first_food = foods[0] if foods else None
    if first_food:
        scope.append(f"I'd like {first_food}.")

    return _dedupe_strings(scope)[:4]


def _page_vocab_words(page: NormalizedTextbookPage) -> list[str]:
    vocabulary_core = _first_block_by_types(page, {"vocabulary_core"})
    if vocabulary_core is None:
        return []
    return [item.word for item in vocabulary_core.vocabulary]


def _page_anchor_word(page: NormalizedTextbookPage) -> str | None:
    sentence_pattern = _first_block_by_types(page, {"sentence_pattern_practice"})
    model_sentence = _first_id_like_sentence(sentence_pattern) if sentence_pattern else None
    return _extract_order_item(model_sentence) if model_sentence else None


def _ordering_vocab_target_words(page: NormalizedTextbookPage) -> list[str]:
    anchor_word = _page_anchor_word(page)
    drink_word = next((word for word in _page_vocab_words(page) if _is_drink_word(word)), None)
    food_words = [
        word
        for word in _page_vocab_words(page)
        if not _is_drink_word(word) and not _is_dessert_word(word)
    ]

    ordered_words: list[str] = []
    if anchor_word and anchor_word in food_words:
        ordered_words.append(anchor_word)
    ordered_words.extend(reversed([word for word in food_words if word != anchor_word]))
    if drink_word:
        ordered_words.append(drink_word)
    return _dedupe_strings(ordered_words)


def _sort_ordering_words(words: list[str]) -> list[str]:
    foods = [word for word in words if not _is_drink_word(word) and word != "ice cream"]
    desserts = [word for word in words if word == "ice cream"]
    drinks = [word for word in words if _is_drink_word(word)]
    return _dedupe_strings(foods + desserts + drinks)


def _roleplay_focus_vocabulary(
    page: NormalizedTextbookPage,
    block: NormalizedTextbookBlock,
) -> list[str]:
    focus = []
    speaker_names = [
        line.speaker.casefold()
        for line in block.dialogue_lines
        if line.speaker
    ]
    if "waiter" in speaker_names:
        focus.append("waiter")
    if "customer" in speaker_names:
        focus.append("customer")
    words = _sort_ordering_words(_page_vocab_words(page))
    drink_word = next((word for word in words if _is_drink_word(word)), None)
    food_words = [word for word in words if not _is_drink_word(word)]
    if drink_word:
        focus.append(drink_word)
    focus.extend(food_words[:2])
    return _dedupe_strings(focus)


def _first_id_like_sentence(block: NormalizedTextbookBlock | None) -> str | None:
    if block is None:
        return None
    for line in block.dialogue_lines:
        sentence = _first_sentence(line.english)
        if sentence and "i'd like" in sentence.casefold():
            return sentence
    return None


def _extract_named_subject(text: str | None) -> str | None:
    if not text:
        return None
    match = re.match(r"\s*([A-Z][a-z]+)\b", text.strip())
    if match:
        return match.group(1)
    return None


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"[^.!?]+[.!?]", text.strip())
    if match:
        return match.group(0).strip()
    normalized = text.strip()
    return normalized or None


def _extract_order_item(sentence: str | None) -> str | None:
    if not sentence:
        return None
    match = re.search(r"i'd like\s+(?:a|an|some)\s+([^,.!?]+)", sentence, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _render_id_like_sentence(item: str) -> str:
    return f"I'd like {_render_item_phrase(item)}, please."


def _render_say_prompt(text: str) -> str:
    normalized = text.strip()
    if normalized.endswith("?"):
        return f"Can you say: {normalized}"
    normalized = re.sub(r"[.!]+$", "", normalized)
    return f"Can you say: {normalized}?"


def _strip_terminal_punctuation(text: str) -> str:
    return re.sub(r"[?!.,]+$", "", text.strip())


def _join_with_and(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _render_item_phrase(item: str) -> str:
    normalized = item.strip()
    if normalized.casefold() in _SOME_WORDS:
        return f"some {normalized}"
    if normalized.endswith("s"):
        return normalized
    return f"a {normalized}"


def _is_drink_word(word: str) -> bool:
    return word.casefold() in _DRINK_WORDS


def _looks_like_food_phrase(word: str) -> bool:
    lowered = word.casefold()
    if _is_drink_word(word):
        return False
    return any(
        token in lowered
        for token in ("bread", "sandwich", "noodle", "hamburger", "salad", "chicken", "rice", "vegetable")
    )


def _is_dessert_word(word: str) -> bool:
    return word.casefold() in {"ice cream"}


def _dedupe_target_specs(target_specs: list[DraftTargetSpec]) -> list[DraftTargetSpec]:
    seen: set[str] = set()
    result: list[DraftTargetSpec] = []
    for spec in target_specs:
        if spec.target_uid in seen:
            continue
        seen.add(spec.target_uid)
        result.append(spec)
    return result


def _mastery_signal_examples(
    target_uid: str,
    category: str,
    text: str,
) -> dict[str, str]:
    target_key = target_uid.casefold()

    specific_examples = {
        "listening-food-keywords": {
            "mastered": "Learner catches both target words from the word bank.",
            "shaky": "Learner catches one target word only.",
            "not_mastered": "Learner cannot identify the food words.",
        },
        "pattern-what-would-you-like-to-eat": {
            "mastered": "Learner can ask the full question independently.",
            "shaky": "Learner needs prompting or drops part of the sentence.",
            "not_mastered": "Learner cannot form the question even after a model.",
        },
        "pattern-what-would-you-like-to-drink": {
            "mastered": "Learner can ask and understand the drink question.",
            "shaky": "Learner recognizes the sentence but cannot say it smoothly.",
            "not_mastered": "Learner confuses drink with eat or cannot repeat the line.",
        },
        "word-hungry": {
            "mastered": "Learner understands the meaning and says the word clearly.",
            "shaky": "Learner understands the meaning but pronunciation is unstable.",
            "not_mastered": "Learner does not know the meaning or cannot repeat the word.",
        },
        "answer-id-like": {
            "mastered": "Learner answers with I'd like ... independently.",
            "shaky": "Learner answers with a noun only or needs a sentence frame.",
            "not_mastered": "Learner cannot answer the preference question.",
        },
        "dialogue-food-drink-roleplay": {
            "mastered": "Learner completes one short food-drink exchange.",
            "shaky": "Learner can complete half the exchange with support.",
            "not_mastered": "Learner cannot sustain the exchange.",
        },
        "word-sandwich": {
            "mastered": "Learner can read and use sandwich in a short order sentence.",
            "shaky": "Learner knows the meaning but misreads the word.",
            "not_mastered": "Learner cannot recognize or pronounce the word.",
        },
        "word-salad": {
            "mastered": "Learner can identify and say salad correctly.",
            "shaky": "Learner recognizes the picture but pronunciation is unstable.",
            "not_mastered": "Learner does not know the word.",
        },
        "word-hamburger": {
            "mastered": "Learner says hamburger clearly in context.",
            "shaky": "Learner says part of the word only.",
            "not_mastered": "Learner cannot identify the item.",
        },
        "word-tea": {
            "mastered": "Learner knows tea and can use it as a drink answer.",
            "shaky": "Learner knows the meaning but not the full answer pattern.",
            "not_mastered": "Learner cannot connect the word to the drink concept.",
        },
        "pattern-id-like": {
            "mastered": "Learner uses I'd like ... politely and independently.",
            "shaky": "Learner drops please or needs a prompt after I'd like.",
            "not_mastered": "Learner cannot build the sentence.",
        },
        "roleplay-ordering": {
            "mastered": "Learner completes a basic waiter-customer exchange.",
            "shaky": "Learner completes one turn but not the whole exchange.",
            "not_mastered": "Learner cannot role-play without full imitation.",
        },
    }
    for suffix, examples in specific_examples.items():
        if target_key.endswith(suffix):
            return examples

    if category == "word":
        return {
            "mastered": f"Learner can understand and say {text} independently.",
            "shaky": f"Learner recognizes {text} but still needs prompting or repair.",
            "not_mastered": f"Learner cannot recognize or say {text} yet.",
        }
    if category == "sentence_pattern":
        if "?" in text:
            return {
                "mastered": f"Learner can ask {text} independently.",
                "shaky": f"Learner recognizes {text} but cannot say it smoothly.",
                "not_mastered": f"Learner cannot form {text} yet.",
            }
        return {
            "mastered": f"Learner can use {text} independently.",
            "shaky": f"Learner starts {text} but still needs prompting to finish it.",
            "not_mastered": f"Learner cannot build {text} yet.",
        }
    if category == "dialogue_task":
        return {
            "mastered": "Learner completes the short exchange independently.",
            "shaky": "Learner completes part of the exchange with support.",
            "not_mastered": "Learner cannot sustain the exchange yet.",
        }
    if category == "listening_task":
        return {
            "mastered": "Learner catches the key words from the listening task.",
            "shaky": "Learner catches part of the key information only.",
            "not_mastered": "Learner cannot identify the key listening words yet.",
        }
    return {
        "mastered": "Learner completes the target independently.",
        "shaky": "Learner completes the target with support.",
        "not_mastered": "Learner cannot complete the target yet.",
    }


def _lookup_word_gloss(word: str, pages: list[NormalizedTextbookPage]) -> str | None:
    explicit_glosses = {
        "hungry": "feeling like you need food",
        "sandwich": "a sandwich item",
        "salad": "a salad item",
        "hamburger": "a hamburger item",
        "tea": "a drink item",
    }
    if word.casefold() in explicit_glosses:
        return explicit_glosses[word.casefold()]

    for page in pages:
        for block in page.blocks:
            for item in block.vocabulary:
                if item.word.casefold() == word.casefold():
                    if _is_drink_word(word):
                        return "a drink item"
                    if _looks_like_food_phrase(word):
                        return f"a {word} item"
                    return item.chinese or f"curriculum word: {word}"
    return f"curriculum word: {word}"


def _linked_blocks_for_word(
    word: str,
    teaching_blocks: list[TeachingBlockRecord],
) -> list[str]:
    word_lower = word.casefold()
    anchor_words_by_page = {
        block.page_uid: _teaching_block_anchor_word(block)
        for block in teaching_blocks
        if block.block_type == "sentence_pattern_practice"
    }
    result: list[str] = []
    for block in teaching_blocks:
        if _teaching_block_links_word(
            block,
            word_lower,
            anchor_words_by_page.get(block.page_uid),
        ):
            result.append(block.block_uid)
    return _dedupe_strings(result)


def _teaching_block_anchor_word(block: TeachingBlockRecord) -> str | None:
    if block.block_type != "sentence_pattern_practice":
        return None
    for entry in block.allowed_answer_scope:
        anchor_word = _extract_order_item(entry)
        if anchor_word:
            return anchor_word
    for entry in block.focus_vocabulary:
        lowered = entry.casefold()
        if lowered not in {"i'd like", "please"}:
            return entry
    return None


def _teaching_block_links_word(
    block: TeachingBlockRecord,
    word_lower: str,
    page_anchor_word: str | None,
) -> bool:
    focus_words = [item.casefold() for item in block.focus_vocabulary]
    if block.block_type in {"dialogue_core", "vocabulary_core", "sentence_pattern_practice"}:
        return word_lower in focus_words
    if block.block_type == "roleplay_task":
        if page_anchor_word and word_lower == page_anchor_word.casefold():
            return False
        allowed_text = " ".join(block.allowed_answer_scope).casefold()
        return word_lower in focus_words or word_lower in allowed_text
    return False


def _block_mentions_word(
    block: NormalizedTextbookBlock,
    teaching_blocks: list[TeachingBlockRecord],
    word_lower: str,
) -> bool:
    texts = [
        block.scene_description or "",
        *[item.word for item in block.vocabulary],
        *[pattern.english for pattern in block.patterns],
        *[line.english for line in block.dialogue_lines],
        *[question.prompt for question in block.questions],
        *[answer.answer for answer in block.questions if answer.answer],
        *block.word_bank,
        *block.prompts,
        *block.templates,
    ]
    texts.extend(
        field
        for teaching_block in teaching_blocks
        if teaching_block.block_uid == block.block_uid
        for field in (
            *teaching_block.focus_vocabulary,
            *teaching_block.core_patterns,
            *teaching_block.allowed_answer_scope,
        )
    )
    haystack = " \n".join(filter(None, texts)).casefold()
    return word_lower in haystack


def _linked_blocks_for_pattern(
    pattern: str,
    teaching_blocks: list[TeachingBlockRecord],
) -> list[str]:
    pattern_lower = pattern.casefold()
    result: list[str] = []
    for block in teaching_blocks:
        if _teaching_block_links_pattern(block, pattern_lower):
            result.append(block.block_uid)
    return _dedupe_strings(result)


def _teaching_block_links_pattern(
    block: TeachingBlockRecord,
    pattern_lower: str,
) -> bool:
    core_patterns = [pattern.casefold() for pattern in block.core_patterns]
    if pattern_lower == "i'd like ... , please.":
        texts = [*core_patterns, *[entry.casefold() for entry in block.allowed_answer_scope]]
        return any("i'd like" in text for text in texts)
    return pattern_lower in core_patterns


def _block_mentions_pattern(
    block: NormalizedTextbookBlock,
    teaching_blocks: list[TeachingBlockRecord],
    pattern_lower: str,
) -> bool:
    if pattern_lower == "i'd like ... , please.".casefold():
        probes = ["i'd like"]
    else:
        probes = [pattern_lower]

    texts = [
        *[pattern.english for pattern in block.patterns],
        *[line.english for line in block.dialogue_lines],
        *block.word_bank,
        *block.prompts,
        *block.templates,
    ]
    texts.extend(
        field
        for teaching_block in teaching_blocks
        if teaching_block.block_uid == block.block_uid
        for field in (
            *teaching_block.core_patterns,
            *teaching_block.allowed_answer_scope,
        )
    )
    haystack = " \n".join(filter(None, texts)).casefold()
    return any(probe in haystack for probe in probes)


def _dedupe_strings(entries) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _scope_prefix(page: NormalizedTextbookPage) -> str:
    unit = page.unit or "U0"
    return f"{page.grade}{page.semester}{unit}"


def _page_code(page_uid: str) -> str:
    match = re.search(r"-(P\d+)$", page_uid)
    if match:
        return match.group(1)
    return "P0"


def _pattern_suffix(pattern: str) -> str:
    lowered = pattern.casefold()
    if "i'd like" in lowered:
        return "pattern-id-like"
    return f"pattern-{_slugify(pattern)}"


def _atom_pattern_suffix(pattern: str) -> str:
    lowered = pattern.casefold()
    if lowered == "what would you like to eat?":
        return "pattern-order-eat"
    if lowered == "what would you like to drink?":
        return "pattern-order-drink"
    return _pattern_suffix(pattern)


def _slugify(text: str) -> str:
    lowered = text.casefold().replace("i'd", "id")
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return normalized or "item"


def _default_repo_root() -> Path:
    current = Path(__file__).resolve()
    matches: list[Path] = []
    for ancestor in current.parents:
        if (ancestor / "app/knowledge").exists():
            matches.append(ancestor)
    if matches:
        return matches[-1]
    raise FileNotFoundError("Unable to locate repository root containing app/knowledge")


def _normalize_unit_ref(unit: str | None) -> str | None:
    if not unit:
        return None
    match = re.fullmatch(r"U(\d+)", unit)
    if match:
        return f"unit{match.group(1)}"
    return re.sub(r"[^A-Za-z0-9]+", "-", unit.strip().lower()).strip("-") or None
