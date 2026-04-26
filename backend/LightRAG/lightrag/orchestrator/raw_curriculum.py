"""Helpers for auditing and loading raw PepTutor curriculum assets."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from json_repair import repair_json
from pydantic import BaseModel, ConfigDict, Field


class RawAssetRecord(BaseModel):
    """One raw asset with inferred type and audit metadata."""

    model_config = ConfigDict(extra="forbid")

    path: str
    kind: str
    extension: str
    size_bytes: int
    is_zero_byte: bool = False


class RawAssetAudit(BaseModel):
    """Summary of the current raw curriculum tree."""

    model_config = ConfigDict(extra="forbid")

    root: str
    total_files: int
    extension_counts: dict[str, int]
    kind_counts: dict[str, int]
    zero_byte_paths: list[str] = Field(default_factory=list)
    assets: list[RawAssetRecord] = Field(default_factory=list)


class RawPageMetadata(BaseModel):
    """Normalized metadata for one raw textbook page."""

    model_config = ConfigDict(extra="allow")

    grade: str
    semester: str
    unit: str | None = None
    page: int | None = None
    uid: str
    book: str | None = None
    theme: str | None = None


class RawContentBlock(BaseModel):
    """Minimal typed content block for textbook-source normalization."""

    model_config = ConfigDict(extra="allow")

    type: str
    uid: str
    section_title: str | None = None


class RawTextbookPage(BaseModel):
    """Typed entrypoint for textbook page sources from raw `.js`/`.json` files."""

    model_config = ConfigDict(extra="allow")

    metadata: RawPageMetadata
    content_blocks: list[RawContentBlock] = Field(default_factory=list)


class NormalizedVocabularyItem(BaseModel):
    """Normalized bilingual vocabulary item extracted from a raw content block."""

    model_config = ConfigDict(extra="forbid")

    word: str
    chinese: str | None = None


class NormalizedPattern(BaseModel):
    """Normalized bilingual sentence pattern or passage segment."""

    model_config = ConfigDict(extra="forbid")

    english: str
    chinese: str | None = None


class NormalizedDialogueTurn(BaseModel):
    """Normalized dialogue line with optional speaker metadata."""

    model_config = ConfigDict(extra="forbid")

    english: str
    chinese: str | None = None
    speaker: str | None = None


class NormalizedQuestion(BaseModel):
    """Normalized exercise question with an optional answer."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    answer: str | None = None


class NormalizedTextbookBlock(BaseModel):
    """Stable block-level signals extracted from a raw textbook page."""

    model_config = ConfigDict(extra="forbid")

    page_uid: str
    block_uid: str
    block_type: str
    section_title: str | None = None
    scene_description: str | None = None
    source_fields: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    vocabulary: list[NormalizedVocabularyItem] = Field(default_factory=list)
    patterns: list[NormalizedPattern] = Field(default_factory=list)
    dialogue_lines: list[NormalizedDialogueTurn] = Field(default_factory=list)
    prose_passages: list[NormalizedPattern] = Field(default_factory=list)
    questions: list[NormalizedQuestion] = Field(default_factory=list)
    word_bank: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)


class NormalizedTextbookPage(BaseModel):
    """Stable page-level record for downstream PageLesson/TeachingBlock conversion."""

    model_config = ConfigDict(extra="forbid")

    page_uid: str
    grade: str
    semester: str
    unit: str | None = None
    page: int | None = None
    book: str | None = None
    theme: str | None = None
    source_path: str | None = None
    source_kind: str | None = None
    source_format: str | None = None
    page_type_hint: str
    block_types: list[str] = Field(default_factory=list)
    blocks: list[NormalizedTextbookBlock] = Field(default_factory=list)


class NormalizedWordListEntry(BaseModel):
    """Normalized word-list row extracted from markdown tables."""

    model_config = ConfigDict(extra="forbid")

    unit: str
    word: str
    phonetic: str | None = None
    chinese: str
    emphasized: bool = False


class NormalizedWordListSection(BaseModel):
    """One unit section from a word-list markdown asset."""

    model_config = ConfigDict(extra="forbid")

    unit: str
    entries: list[NormalizedWordListEntry] = Field(default_factory=list)


class NormalizedUsefulExpressionEntry(BaseModel):
    """Normalized useful-expression row extracted from markdown tables."""

    model_config = ConfigDict(extra="forbid")

    unit: str
    english: str
    chinese: str
    page_ref: str | None = None
    emphasized: bool = False


def infer_raw_asset_kind(path: Path) -> str:
    """Infer a stable raw asset kind from the current source filename convention."""
    name = path.name
    if name.endswith("语料.js"):
        return "textbook_source_js"
    if name.endswith("语料.json"):
        return "textbook_source_json"
    if "单词表" in name and path.suffix.lower() == ".md":
        return "word_list_markdown"
    if "Useful expressions" in name and path.suffix.lower() == ".md":
        return "useful_expressions_markdown"
    if "Irregular verbs" in name and path.suffix.lower() == ".md":
        return "irregular_verbs_markdown"
    if "pronunciation patterns" in name and path.suffix.lower() == ".json":
        return "pronunciation_patterns_json"
    return "unknown"


def audit_raw_assets(raw_root: Path) -> RawAssetAudit:
    """Audit raw curriculum files and flag obvious normalization blockers."""
    root = raw_root.resolve()
    assets: list[RawAssetRecord] = []
    extension_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    zero_byte_paths: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        extension = path.suffix.lower() or "<noext>"
        kind = infer_raw_asset_kind(path)
        size_bytes = path.stat().st_size
        relative_path = path.relative_to(root).as_posix()
        is_zero_byte = size_bytes == 0

        extension_counts[extension] = extension_counts.get(extension, 0) + 1
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if is_zero_byte:
            zero_byte_paths.append(relative_path)

        assets.append(
            RawAssetRecord(
                path=relative_path,
                kind=kind,
                extension=extension,
                size_bytes=size_bytes,
                is_zero_byte=is_zero_byte,
            )
        )

    return RawAssetAudit(
        root=str(root),
        total_files=len(assets),
        extension_counts=extension_counts,
        kind_counts=kind_counts,
        zero_byte_paths=zero_byte_paths,
        assets=assets,
    )


def load_textbook_source(path: Path) -> list[RawTextbookPage]:
    """Load textbook page sources from either raw `.json` arrays or legacy `.js` object streams."""
    source_path = path.resolve()
    text = source_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Raw textbook source is empty: {source_path}")

    suffix = source_path.suffix.lower()
    if suffix == ".json":
        payload = _load_json_with_repair(text)
    elif suffix == ".js":
        payload = _load_json_with_repair(_wrap_js_object_stream(text))
    else:
        raise ValueError(f"Unsupported textbook source suffix: {source_path.suffix}")

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected textbook source shape in {source_path}")

    return [RawTextbookPage.model_validate(item) for item in payload]


def normalize_textbook_source(path: Path) -> list[NormalizedTextbookPage]:
    """Convert one raw textbook source file into normalized page records."""
    source_path = path.resolve()
    source_kind = infer_raw_asset_kind(source_path)
    source_format = source_path.suffix.lower().lstrip(".") or None

    return [
        normalize_textbook_page(
            page,
            source_path=source_path,
            source_kind=source_kind,
            source_format=source_format,
        )
        for page in load_textbook_source(source_path)
    ]


def normalize_word_list_markdown(path: Path) -> list[NormalizedWordListSection]:
    """Parse current raw word-list markdown assets into unit sections."""
    source_path = path.resolve()
    current_unit: str | None = None
    sections: dict[str, list[NormalizedWordListEntry]] = {}

    for line in source_path.read_text(encoding="utf-8").splitlines():
        unit_match = re.match(r"^\s*##\s+(Unit\s+\d+)\s*$", line)
        if unit_match:
            current_unit = unit_match.group(1)
            sections.setdefault(current_unit, [])
            continue

        cells = _parse_markdown_table_cells(line)
        if cells is None or len(cells) < 3 or current_unit is None:
            continue
        if _is_markdown_alignment_row(cells):
            continue
        if "单词" in cells[0] and "中文" in cells[2]:
            continue

        raw_word = cells[0]
        word = _strip_markdown_emphasis(raw_word)
        if not word:
            continue

        sections[current_unit].append(
            NormalizedWordListEntry(
                unit=current_unit,
                word=word,
                phonetic=cells[1] or None,
                chinese=cells[2],
                emphasized=raw_word != word,
            )
        )

    return [
        NormalizedWordListSection(unit=unit, entries=entries)
        for unit, entries in sections.items()
    ]


def normalize_useful_expressions_markdown(path: Path) -> list[NormalizedUsefulExpressionEntry]:
    """Parse current useful-expression markdown assets into normalized rows."""
    source_path = path.resolve()
    current_unit: str | None = None
    result: list[NormalizedUsefulExpressionEntry] = []

    for line in source_path.read_text(encoding="utf-8").splitlines():
        cells = _parse_markdown_table_cells(line)
        if cells is None or len(cells) < 4:
            continue
        if _is_markdown_alignment_row(cells):
            continue
        if "Useful expressions" in cells[1] or "英文表达" in cells[1]:
            continue

        raw_unit = cells[0]
        parsed_unit = _strip_markdown_emphasis(raw_unit)
        if parsed_unit:
            current_unit = parsed_unit
        if current_unit is None:
            continue

        english = _strip_markdown_emphasis(cells[1])
        chinese = cells[2]
        page_ref = cells[3] or None
        if not english or not chinese:
            continue

        result.append(
            NormalizedUsefulExpressionEntry(
                unit=current_unit,
                english=english,
                chinese=chinese,
                page_ref=page_ref,
                emphasized=raw_unit != parsed_unit,
            )
        )

    return result


def normalize_textbook_page(
    page: RawTextbookPage,
    *,
    source_path: Path | None = None,
    source_kind: str | None = None,
    source_format: str | None = None,
) -> NormalizedTextbookPage:
    """Extract stable page and block signals from one raw textbook page."""
    blocks = [
        normalize_textbook_block(page.metadata.uid, block) for block in page.content_blocks
    ]
    block_types = [block.block_type for block in blocks]

    return NormalizedTextbookPage(
        page_uid=page.metadata.uid,
        grade=page.metadata.grade,
        semester=page.metadata.semester,
        unit=page.metadata.unit,
        page=page.metadata.page,
        book=page.metadata.book,
        theme=page.metadata.theme,
        source_path=str(source_path) if source_path is not None else None,
        source_kind=source_kind,
        source_format=source_format,
        page_type_hint=_infer_page_type_hint(block_types),
        block_types=block_types,
        blocks=blocks,
    )


def normalize_textbook_block(
    page_uid: str,
    block: RawContentBlock,
) -> NormalizedTextbookBlock:
    """Extract the stable raw signals we need before generating lesson-specific schema."""
    payload = block.model_dump(exclude_none=True)
    source_fields = sorted(
        key
        for key in payload
        if key not in {"type", "uid", "section_title", "scene_description"}
    )

    return NormalizedTextbookBlock(
        page_uid=page_uid,
        block_uid=block.uid,
        block_type=block.type,
        section_title=block.section_title,
        scene_description=_clean_text(payload.get("scene_description")),
        source_fields=source_fields,
        skills=_extract_string_list(payload.get("skills")),
        vocabulary=_extract_vocabulary(payload),
        patterns=_extract_patterns(payload),
        dialogue_lines=_extract_dialogue_lines(payload.get("dialogues")),
        prose_passages=_extract_bilingual_pairs(payload.get("paragraphs")),
        questions=_extract_questions(payload.get("questions")),
        word_bank=_extract_word_bank(payload.get("word_bank")),
        prompts=_extract_prompts(payload),
        templates=_extract_templates(payload),
    )


def _wrap_js_object_stream(text: str) -> str:
    """Convert legacy JS textbook sources into a JSON array string."""
    stripped = text.strip()
    if stripped.startswith("["):
        return stripped
    return f"[{stripped}]"


def _load_json_with_repair(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return repair_json(text, return_objects=True)


def _infer_page_type_hint(block_types: list[str]) -> str:
    if "vocabulary_core" in block_types:
        return "vocabulary"
    if "grammar_point" in block_types:
        return "grammar"
    if "dialogue_core" in block_types or "dialogue_practice" in block_types:
        return "dialogue"
    if "reading_passage" in block_types or "story_time" in block_types:
        return "reading"
    if "phonics" in block_types:
        return "phonics"
    if "writing_prompt" in block_types or "practice_write" in block_types:
        return "writing"
    if "listening_exercise" in block_types:
        return "listening"
    if "assessment_quiz" in block_types:
        return "assessment"
    if "picture_scene" in block_types:
        return "picture"
    if "table_of_contents" in block_types or "proverbs_list" in block_types:
        return "reference"
    if any(block_type.startswith("practice_") for block_type in block_types):
        return "practice"
    if not block_types:
        return "unknown"
    prefix, _, _ = block_types[0].partition("_")
    return prefix or block_types[0]


def _extract_vocabulary(payload: dict[str, Any]) -> list[NormalizedVocabularyItem]:
    seen: set[tuple[str, str | None]] = set()
    result: list[NormalizedVocabularyItem] = []

    for field in ("focus_vocabulary", "items", "related_vocabulary"):
        entries = payload.get(field)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str):
                word = _clean_text(entry)
                chinese = None
            elif isinstance(entry, dict):
                word = _clean_text(
                    entry.get("word")
                    or entry.get("english")
                    or entry.get("title_english")
                )
                chinese = _clean_text(
                    entry.get("chinese")
                    or entry.get("title_chinese")
                    or entry.get("translation")
                )
            else:
                continue

            if not word:
                continue
            key = (word, chinese)
            if key in seen:
                continue
            seen.add(key)
            result.append(NormalizedVocabularyItem(word=word, chinese=chinese))

    return result


def _extract_patterns(payload: dict[str, Any]) -> list[NormalizedPattern]:
    patterns = _extract_bilingual_pairs(payload.get("key_points"))

    points = payload.get("points")
    if isinstance(points, list):
        for point in points:
            if not isinstance(point, dict):
                continue
            patterns.extend(_extract_bilingual_pairs(point.get("examples")))

    return _dedupe_patterns(patterns)


def _extract_bilingual_pairs(entries: Any) -> list[NormalizedPattern]:
    result: list[NormalizedPattern] = []
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        english = _clean_text(entry.get("english"))
        chinese = _clean_text(entry.get("chinese"))
        if not english:
            continue
        result.append(NormalizedPattern(english=english, chinese=chinese))

    return result


def _extract_dialogue_lines(entries: Any) -> list[NormalizedDialogueTurn]:
    result: list[NormalizedDialogueTurn] = []
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        english = _clean_text(entry.get("english"))
        if not english:
            continue
        result.append(
            NormalizedDialogueTurn(
                english=english,
                chinese=_clean_text(entry.get("chinese")),
                speaker=_clean_text(entry.get("speaker")),
            )
        )

    return result


def _extract_questions(entries: Any) -> list[NormalizedQuestion]:
    result: list[NormalizedQuestion] = []
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if isinstance(entry, str):
            prompt = _clean_text(entry)
            if prompt:
                result.append(NormalizedQuestion(prompt=prompt))
            continue

        if not isinstance(entry, dict):
            continue

        prompt = _clean_text(
            entry.get("q")
            or entry.get("question")
            or entry.get("prompt")
            or entry.get("english")
        )
        if not prompt:
            continue

        result.append(
            NormalizedQuestion(
                prompt=prompt,
                answer=_clean_text(entry.get("a") or entry.get("answer")),
            )
        )

    return result


def _extract_word_bank(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []

    result: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized = _clean_text(entry)
        elif isinstance(entry, dict):
            normalized = _clean_text(
                entry.get("word") or entry.get("english") or entry.get("title")
            )
        else:
            normalized = None

        if normalized:
            result.append(normalized)

    return _dedupe_strings(result)


def _extract_prompts(payload: dict[str, Any]) -> list[str]:
    prompts = [
        _clean_text(payload.get("instructions")),
        _clean_text(payload.get("extra_content")),
    ]

    points = payload.get("points")
    if isinstance(points, list):
        for point in points:
            if not isinstance(point, dict):
                continue
            prompts.append(_clean_text(point.get("title")))
            prompts.append(_clean_text(point.get("explanation_english")))
            prompts.append(_clean_text(point.get("explanation_chinese")))

    return _dedupe_strings(prompts)


def _extract_templates(payload: dict[str, Any]) -> list[str]:
    return _dedupe_strings(
        [_clean_text(payload.get("student_response_template"))]
    )


def _extract_string_list(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    return _dedupe_strings(
        _clean_text(entry) for entry in entries if isinstance(entry, str)
    )


def _dedupe_patterns(patterns: list[NormalizedPattern]) -> list[NormalizedPattern]:
    seen: set[tuple[str, str | None]] = set()
    result: list[NormalizedPattern] = []
    for pattern in patterns:
        key = (pattern.english, pattern.chinese)
        if key in seen:
            continue
        seen.add(key)
        result.append(pattern)
    return result


def _dedupe_strings(entries) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        if not entry or entry in seen:
            continue
        seen.add(entry)
        result.append(entry)
    return result


def _parse_markdown_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _is_markdown_alignment_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)


def _strip_markdown_emphasis(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"^\*\*(.+)\*\*$", r"\1", normalized)
    return normalized.strip()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
