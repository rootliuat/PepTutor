#!/usr/bin/env python3
"""Build a read-only curriculum graph from PepTutor structured textbook data."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


GRAPH_SCHEMA_VERSION = "curriculum_graph_v1"
DEFAULT_STRUCTURED_DIR = Path("app/knowledge/structured")
DEFAULT_RAW_DIR = Path("app/knowledge/raw")
DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")

ANCHOR_PAGE_UIDS = (
    "TB-G5S1U3-P22",
    "TB-G6S1U1-P4",
    "TB-G6S2U1-P4",
    "TB-G5S1U3-P31",
    "TB-G5S2U1-P6",
    "TB-G6S2U2-P13",
)
NODE_TYPES = (
    "Book",
    "Unit",
    "Page",
    "Block",
    "TeachingTarget",
    "QuestionTarget",
    "AnswerTarget",
    "AnswerFrame",
    "VocabItem",
    "PhonicsPattern",
    "PhonicsExemplar",
    "StoryQuestion",
    "StoryCharacter",
    "RolePlayPair",
    "AnswerScope",
    "ReturnAnchor",
    "SourceFile",
)
EDGE_TYPES = (
    "book_contains_unit",
    "unit_contains_page",
    "page_contains_block",
    "block_has_target",
    "block_has_question_target",
    "block_has_answer_target",
    "question_expects_answer_frame",
    "block_has_answer_scope",
    "block_has_vocab",
    "vocab_returns_to_anchor",
    "phonics_uses_pattern",
    "phonics_uses_exemplar",
    "story_has_question",
    "story_has_character",
    "roleplay_has_pair",
    "node_from_source_file",
)

QUESTION_PREFIXES = (
    "what ",
    "what's ",
    "what is ",
    "where ",
    "when ",
    "who ",
    "whose ",
    "which ",
    "why ",
    "how ",
    "do ",
    "does ",
    "did ",
    "can ",
    "is ",
    "are ",
)
DECLARATIVE_PREFIXES = (
    "it's ",
    "it is ",
    "i'm ",
    "i am ",
    "i'd ",
    "i would ",
    "zoom would ",
    "yes, ",
    "no, ",
)
PHONICS_PATTERN_RE = re.compile(
    r"(?:blend|sound)\s+['\"]?(?P<pattern>[a-z]{1,4})['\"]?\s+as\s+in\s+['\"]?(?P<word>[a-z][a-z -]*)['\"]?",
    re.I,
)
WORD_RE = re.compile(r"^[A-Za-z][A-Za-z' -]{0,40}$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root() / path).resolve()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).strip()


def normalized_text(value: Any) -> str:
    return clean_text(value).strip("。！？!?.").casefold()


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned[:96] or "empty"


def stable_id(node_type: str, *parts: str) -> str:
    return f"{node_type}:{':'.join(slug(part) for part in parts if part)}"


def rel_path(path: Path) -> str:
    path = resolve_path(path)
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def looks_like_question(value: Any) -> bool:
    text = clean_text(value)
    normalized = normalized_text(text)
    if not text or normalized.startswith(DECLARATIVE_PREFIXES):
        return False
    return text.endswith("?") or normalized.startswith(QUESTION_PREFIXES)


def looks_like_answer(value: Any) -> bool:
    text = clean_text(value)
    normalized = normalized_text(text)
    if not text:
        return False
    return normalized.startswith(DECLARATIVE_PREFIXES) or not looks_like_question(text)


def is_probable_vocab(value: Any) -> bool:
    text = clean_text(value)
    if not text or looks_like_question(text):
        return False
    return bool(WORD_RE.match(text)) and len(text.split()) <= 4


def infer_book_id(scope: dict[str, Any], page_uid: str = "") -> str:
    grade = clean_text(scope.get("grade"))
    semester = clean_text(scope.get("semester"))
    if grade and semester:
        return f"{grade}{semester}"
    match = re.match(r"TB-(G\d)(S\d)", page_uid)
    if match:
        return "".join(match.groups())
    return ""


def infer_unit_id(scope: dict[str, Any], page_uid: str = "") -> str:
    unit = clean_text(scope.get("unit"))
    if unit:
        return unit
    match = re.match(r"TB-G\dS\d(.*?)-P\d+", page_uid)
    if match:
        return match.group(1)
    return ""


def infer_answer_frame(question: str, allowed_answers: list[str]) -> str:
    normalized = normalized_text(question)
    answers = [clean_text(answer) for answer in allowed_answers if clean_text(answer)]
    if normalized.startswith("where "):
        if any(normalized_text(answer).startswith("it's near") for answer in answers):
            return "It's near ..."
        return "It's ..."
    if normalized.startswith("how tall is it"):
        return "It's ... metres tall."
    if normalized.startswith("how tall are you"):
        return "I'm ... metres tall."
    if normalized.startswith("what's your favourite food") or normalized.startswith("what is your favourite food"):
        return "My favourite food is ..."
    if normalized.startswith("what would zoom like to eat"):
        return "Zoom would like ..."
    if normalized.startswith("what would you like"):
        return "I'd like ..."
    if normalized.startswith("what did you do last weekend"):
        return "I ..."
    if normalized.startswith("did you "):
        return "Yes, I did. / No, I didn't."
    if normalized.startswith("who "):
        return "... is ..."
    return ""


class CurriculumGraphBuilder:
    def __init__(self, *, structured_dir: Path, raw_dir: Path) -> None:
        self.structured_dir = structured_dir
        self.raw_dir = raw_dir
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.page_priority: dict[str, list[str]] = {}
        self.page_to_book_unit: dict[str, tuple[str, str]] = {}
        self.structured_files: set[str] = set()
        self.raw_files: set[str] = set()

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        *,
        source_file: Path | str = "",
        book_id: str = "",
        unit_id: str = "",
        page_uid: str = "",
        block_uid: str = "",
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = rel_path(Path(source_file)) if source_file else ""
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "id": node_id,
                "type": node_type,
                "label": label,
                "book_id": book_id,
                "unit_id": unit_id,
                "page_uid": page_uid,
                "block_uid": block_uid,
                "source_files": [source] if source else [],
                "properties": properties or {},
            }
        else:
            node = self.nodes[node_id]
            if source and source not in node["source_files"]:
                node["source_files"].append(source)
            for key, value in {
                "book_id": book_id,
                "unit_id": unit_id,
                "page_uid": page_uid,
                "block_uid": block_uid,
            }.items():
                if value and not node.get(key):
                    node[key] = value
            node["properties"].update(
                {key: value for key, value in (properties or {}).items() if value not in ("", [], {})}
            )
        if source and node_type != "SourceFile":
            source_id = self.add_source_file(source)["id"]
            self.add_edge("node_from_source_file", node_id, source_id, page_uid=page_uid, block_uid=block_uid)
        return self.nodes[node_id]

    def add_source_file(self, source: str | Path) -> dict[str, Any]:
        source_text = rel_path(Path(source)) if isinstance(source, Path) else clean_text(source)
        source_id = stable_id("SourceFile", source_text)
        return self.add_node(
            source_id,
            "SourceFile",
            source_text,
            properties={"path": source_text},
        )

    def add_edge(
        self,
        edge_type: str,
        source: str,
        target: str,
        *,
        page_uid: str = "",
        block_uid: str = "",
        properties: dict[str, Any] | None = None,
    ) -> None:
        if source not in self.nodes or target not in self.nodes:
            return
        edge_id = f"{edge_type}:{source}->{target}"
        self.edges[edge_id] = {
            "id": edge_id,
            "type": edge_type,
            "source": source,
            "target": target,
            "page_uid": page_uid,
            "block_uid": block_uid,
            "properties": properties or {},
        }

    def build(self) -> dict[str, Any]:
        self._add_raw_source_files()
        self._add_curriculum_map()
        self._add_general_manifest()
        for source_file in self._structured_content_files():
            self._load_structured_content(source_file)
        return self._graph()

    def _add_raw_source_files(self) -> None:
        for path in sorted(self.raw_dir.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                source = rel_path(path)
                self.raw_files.add(source)
                self.add_source_file(source)

    def _add_curriculum_map(self) -> None:
        map_path = self.structured_dir / "curriculum-map.json"
        if not map_path.exists():
            return
        data = self._load_json(map_path)
        if not isinstance(data, dict):
            return
        self.structured_files.add(rel_path(map_path))
        self.add_source_file(map_path)
        for book in data.get("books") or []:
            book_id = clean_text(book.get("book_id")) or f"{clean_text(book.get('grade'))}{clean_text(book.get('semester'))}"
            if not book_id:
                continue
            book_node_id = f"Book:{book_id}"
            self.add_node(
                book_node_id,
                "Book",
                book_id,
                source_file=map_path,
                book_id=book_id,
                properties={
                    "grade": clean_text(book.get("grade")),
                    "semester": clean_text(book.get("semester")),
                    "source_refs": book.get("source_refs") or [],
                },
            )
            for source_ref in book.get("source_refs") or []:
                self.add_source_file(clean_text(source_ref))
            for unit in book.get("units") or []:
                unit_id = clean_text(unit.get("unit"))
                if not unit_id:
                    continue
                unit_node_id = f"Unit:{book_id}:{unit_id}"
                self.add_node(
                    unit_node_id,
                    "Unit",
                    f"{book_id} {unit_id}",
                    source_file=map_path,
                    book_id=book_id,
                    unit_id=unit_id,
                    properties={
                        "unit": unit_id,
                        "unit_theme": clean_text(unit.get("unit_theme")),
                        "pages": unit.get("pages") or [],
                    },
                )
                self.add_edge("book_contains_unit", book_node_id, unit_node_id)
                for page_no in unit.get("pages") or []:
                    page_uid = f"TB-{book_id}{unit_id}-P{page_no}"
                    self.page_to_book_unit[page_uid] = (book_id, unit_id)
                    page_node_id = f"Page:{page_uid}"
                    self.add_node(
                        page_node_id,
                        "Page",
                        page_uid,
                        source_file=map_path,
                        book_id=book_id,
                        unit_id=unit_id,
                        page_uid=page_uid,
                        properties={"page_number": page_no},
                    )
                    self.add_edge("unit_contains_page", unit_node_id, page_node_id, page_uid=page_uid)
                for vocab in unit.get("core_vocabulary") or []:
                    self._add_vocab_from_map(vocab, map_path, book_id, unit_id)

    def _add_general_manifest(self) -> None:
        manifest_path = self.structured_dir / "general" / "general-manifest.json"
        if not manifest_path.exists():
            return
        data = self._load_json(manifest_path)
        if not isinstance(data, dict):
            return
        self.structured_files.add(rel_path(manifest_path))
        self.add_source_file(manifest_path)
        for key in ("generated_files", "scopes", "reports"):
            for item in data.get(key) or []:
                if isinstance(item, str):
                    self.add_source_file(item)
                elif isinstance(item, dict):
                    for value_key in ("path", "file", "output_path", "manifest_path"):
                        value = clean_text(item.get(value_key))
                        if value:
                            self.add_source_file(value)

    def _add_vocab_from_map(self, entry: dict[str, Any], source_file: Path, book_id: str, unit_id: str) -> None:
        word = clean_text(entry.get("word"))
        if not word:
            return
        vocab_id = stable_id("VocabItem", word)
        self.add_node(
            vocab_id,
            "VocabItem",
            word,
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            properties={
                "chinese": clean_text(entry.get("chinese")),
                "phonetic": clean_text(entry.get("phonetic")),
                "emphasized": bool(entry.get("emphasized")),
                "source": "curriculum_map.core_vocabulary",
                "source_refs": entry.get("source_refs") or [],
            },
        )
        for source_ref in entry.get("source_refs") or []:
            self.add_source_file(clean_text(source_ref))

    def _structured_content_files(self) -> list[Path]:
        files: list[Path] = []
        general_dir = self.structured_dir / "general"
        files.extend(sorted(general_dir.glob("*.json")))
        files.extend(sorted(self.structured_dir.glob("*pilot*.json")))
        return [
            path
            for path in files
            if path.name not in {"general-manifest.json", "general-build-report.json"}
            and not path.name.endswith("manifest.json")
        ]

    def _load_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _load_structured_content(self, source_file: Path) -> None:
        data = self._load_json(source_file)
        if not isinstance(data, dict):
            return
        if not any(key in data for key in ("page_lessons", "teaching_blocks", "learning_targets", "wordlist_entries")):
            return
        self.structured_files.add(rel_path(source_file))
        self.add_source_file(source_file)
        scope = data.get("scope") or {}
        book_id = infer_book_id(scope)
        unit_id = infer_unit_id(scope)
        self._ensure_book_unit(book_id, unit_id, source_file, scope)
        self._add_pages(data.get("page_lessons") or [], source_file, scope)
        self._add_blocks(data.get("teaching_blocks") or [], source_file, scope)
        self._add_learning_targets(data.get("learning_targets") or [], source_file, scope)
        self._add_wordlist_entries(data.get("wordlist_entries") or [], source_file, scope)

    def _ensure_book_unit(self, book_id: str, unit_id: str, source_file: Path, scope: dict[str, Any]) -> None:
        if not book_id:
            return
        book_node_id = f"Book:{book_id}"
        self.add_node(
            book_node_id,
            "Book",
            book_id,
            source_file=source_file,
            book_id=book_id,
            properties={"grade": clean_text(scope.get("grade")), "semester": clean_text(scope.get("semester"))},
        )
        if unit_id:
            unit_node_id = f"Unit:{book_id}:{unit_id}"
            self.add_node(
                unit_node_id,
                "Unit",
                f"{book_id} {unit_id}",
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                properties={"unit": unit_id, "pages": scope.get("pages") or []},
            )
            self.add_edge("book_contains_unit", book_node_id, unit_node_id)

    def _book_unit_for_page(self, page_uid: str, scope: dict[str, Any]) -> tuple[str, str]:
        if page_uid in self.page_to_book_unit:
            return self.page_to_book_unit[page_uid]
        book_id = infer_book_id(scope, page_uid)
        unit_id = infer_unit_id(scope, page_uid)
        if book_id and unit_id:
            self.page_to_book_unit[page_uid] = (book_id, unit_id)
        return book_id, unit_id

    def _add_pages(self, pages: list[dict[str, Any]], source_file: Path, scope: dict[str, Any]) -> None:
        for page in pages:
            page_uid = clean_text(page.get("page_uid"))
            if not page_uid:
                continue
            book_id, unit_id = self._book_unit_for_page(page_uid, scope)
            self._ensure_book_unit(book_id, unit_id, source_file, scope)
            priority_blocks = [clean_text(item) for item in page.get("priority_blocks") or [] if clean_text(item)]
            self.page_priority[page_uid] = priority_blocks
            page_node_id = f"Page:{page_uid}"
            self.add_node(
                page_node_id,
                "Page",
                page_uid,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                properties={
                    "page_type": clean_text(page.get("page_type")),
                    "page_intro_cn": clean_text(page.get("page_intro_cn")),
                    "entry_probe_questions": page.get("entry_probe_questions") or [],
                    "priority_blocks": priority_blocks,
                    "assumed_prior_knowledge": page.get("assumed_prior_knowledge") or [],
                },
            )
            if book_id and unit_id:
                self.add_edge("unit_contains_page", f"Unit:{book_id}:{unit_id}", page_node_id, page_uid=page_uid)

    def _add_blocks(self, blocks: list[dict[str, Any]], source_file: Path, scope: dict[str, Any]) -> None:
        for block in blocks:
            block_uid = clean_text(block.get("block_uid"))
            page_uid = clean_text(block.get("page_uid"))
            if not block_uid:
                self._add_malformed_block(block, source_file, scope)
                continue
            if not page_uid:
                page_uid = "-".join(block_uid.split("-")[:4]) if block_uid.startswith("TB-") else ""
            book_id, unit_id = self._book_unit_for_page(page_uid, scope)
            self._ensure_book_unit(book_id, unit_id, source_file, scope)
            priority_index = self._priority_index(page_uid, block_uid)
            block_node_id = f"Block:{block_uid}"
            self.add_node(
                block_node_id,
                "Block",
                block_uid,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={
                    "page_type": clean_text(block.get("page_type")),
                    "block_type": clean_text(block.get("block_type")),
                    "teaching_goal": clean_text(block.get("teaching_goal")),
                    "teaching_summary": clean_text(block.get("teaching_summary")),
                    "focus_vocabulary": block.get("focus_vocabulary") or [],
                    "core_patterns": block.get("core_patterns") or [],
                    "allowed_answer_scope": block.get("allowed_answer_scope") or [],
                    "entry_probe_questions": block.get("entry_probe_questions") or [],
                    "repair_modes": block.get("repair_modes") or [],
                    "return_anchors": block.get("return_anchors") or [],
                    "priority_index": priority_index,
                    "next_block_uids": block.get("next_block_uids") or [],
                    "learning_target_uids": block.get("learning_target_uids") or [],
                },
            )
            if page_uid:
                page_node_id = f"Page:{page_uid}"
                self.add_node(
                    page_node_id,
                    "Page",
                    page_uid,
                    source_file=source_file,
                    book_id=book_id,
                    unit_id=unit_id,
                    page_uid=page_uid,
                )
                self.add_edge(
                    "page_contains_block",
                    page_node_id,
                    block_node_id,
                    page_uid=page_uid,
                    block_uid=block_uid,
                    properties={"priority_index": priority_index},
                )
            self._add_block_contract_nodes(block, block_node_id, source_file, book_id, unit_id)

    def _add_malformed_block(self, block: dict[str, Any], source_file: Path, scope: dict[str, Any]) -> None:
        book_id = infer_book_id(scope)
        unit_id = infer_unit_id(scope)
        node_id = stable_id("Block", rel_path(source_file), clean_text(block.get("page_uid")) or "missing-block-uid")
        self.add_node(
            node_id,
            "Block",
            "missing block_uid",
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=clean_text(block.get("page_uid")),
            properties={"missing_block_uid": True, "raw_block": block},
        )

    def _priority_index(self, page_uid: str, block_uid: str) -> int | None:
        try:
            return self.page_priority.get(page_uid, []).index(block_uid)
        except ValueError:
            return None

    def _add_block_contract_nodes(
        self,
        block: dict[str, Any],
        block_node_id: str,
        source_file: Path,
        book_id: str,
        unit_id: str,
    ) -> None:
        page_uid = clean_text(block.get("page_uid"))
        block_uid = clean_text(block.get("block_uid"))
        allowed_answers = [clean_text(item) for item in block.get("allowed_answer_scope") or [] if clean_text(item)]
        core_patterns = [clean_text(item) for item in block.get("core_patterns") or [] if clean_text(item)]
        focus_vocabulary = [clean_text(item) for item in block.get("focus_vocabulary") or [] if clean_text(item)]
        return_anchors = [clean_text(item) for item in block.get("return_anchors") or [] if clean_text(item)]

        for text in core_patterns:
            target_id = stable_id("TeachingTarget", block_uid, text)
            self.add_node(
                target_id,
                "TeachingTarget",
                text,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={"source": "core_patterns"},
            )
            self.add_edge("block_has_target", block_node_id, target_id, page_uid=page_uid, block_uid=block_uid)
            if looks_like_question(text):
                self._add_question_target(text, source_file, book_id, unit_id, page_uid, block_uid, block_node_id, allowed_answers)
            elif looks_like_answer(text):
                self._add_answer_target(text, source_file, book_id, unit_id, page_uid, block_uid, block_node_id)
            self._maybe_add_phonics_nodes(text, source_file, book_id, unit_id, page_uid, block_uid, block_node_id)

        for answer in allowed_answers:
            if looks_like_answer(answer):
                self._add_answer_target(answer, source_file, book_id, unit_id, page_uid, block_uid, block_node_id)

        scope_id = f"AnswerScope:{block_uid}"
        self.add_node(
            scope_id,
            "AnswerScope",
            f"{block_uid} answer scope",
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=page_uid,
            block_uid=block_uid,
            properties={"allowed_answer_scope": allowed_answers},
        )
        self.add_edge("block_has_answer_scope", block_node_id, scope_id, page_uid=page_uid, block_uid=block_uid)

        for vocab in focus_vocabulary:
            if not is_probable_vocab(vocab):
                continue
            vocab_id = stable_id("VocabItem", vocab)
            self.add_node(
                vocab_id,
                "VocabItem",
                vocab,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={"source": "focus_vocabulary"},
            )
            self.add_edge("block_has_vocab", block_node_id, vocab_id, page_uid=page_uid, block_uid=block_uid)
            self.add_edge("block_has_target", block_node_id, vocab_id, page_uid=page_uid, block_uid=block_uid)

        for anchor in return_anchors:
            anchor_id = stable_id("ReturnAnchor", block_uid, anchor)
            self.add_node(
                anchor_id,
                "ReturnAnchor",
                anchor,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={"source": "return_anchors"},
            )
            self.add_edge("vocab_returns_to_anchor", block_node_id, anchor_id, page_uid=page_uid, block_uid=block_uid)
            if looks_like_question(anchor):
                self._add_question_target(anchor, source_file, book_id, unit_id, page_uid, block_uid, block_node_id, allowed_answers)

        self._maybe_add_story_nodes(block, block_node_id, source_file, book_id, unit_id, core_patterns, allowed_answers)

    def _add_question_target(
        self,
        text: str,
        source_file: Path,
        book_id: str,
        unit_id: str,
        page_uid: str,
        block_uid: str,
        block_node_id: str,
        allowed_answers: list[str],
    ) -> None:
        question = clean_text(text)
        question_id = stable_id("QuestionTarget", block_uid, question)
        self.add_node(
            question_id,
            "QuestionTarget",
            question,
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=page_uid,
            block_uid=block_uid,
            properties={"source": "core_patterns_or_return_anchor"},
        )
        self.add_edge("block_has_question_target", block_node_id, question_id, page_uid=page_uid, block_uid=block_uid)
        frame = infer_answer_frame(question, allowed_answers)
        if frame:
            frame_id = stable_id("AnswerFrame", block_uid, frame)
            self.add_node(
                frame_id,
                "AnswerFrame",
                frame,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={"inferred_from_question": question},
            )
            self.add_edge("question_expects_answer_frame", question_id, frame_id, page_uid=page_uid, block_uid=block_uid)
            self.add_edge("block_has_answer_target", block_node_id, frame_id, page_uid=page_uid, block_uid=block_uid)

    def _add_answer_target(
        self,
        text: str,
        source_file: Path,
        book_id: str,
        unit_id: str,
        page_uid: str,
        block_uid: str,
        block_node_id: str,
    ) -> None:
        answer = clean_text(text)
        answer_id = stable_id("AnswerTarget", block_uid, answer)
        self.add_node(
            answer_id,
            "AnswerTarget",
            answer,
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=page_uid,
            block_uid=block_uid,
            properties={"source": "core_patterns_or_answer_scope"},
        )
        self.add_edge("block_has_answer_target", block_node_id, answer_id, page_uid=page_uid, block_uid=block_uid)

    def _maybe_add_phonics_nodes(
        self,
        text: str,
        source_file: Path,
        book_id: str,
        unit_id: str,
        page_uid: str,
        block_uid: str,
        block_node_id: str,
    ) -> None:
        match = PHONICS_PATTERN_RE.search(text)
        if not match:
            return
        pattern = clean_text(match.group("pattern")).lower()
        exemplar = clean_text(match.group("word")).strip(".")
        pattern_id = stable_id("PhonicsPattern", block_uid, pattern)
        exemplar_id = stable_id("PhonicsExemplar", block_uid, exemplar)
        self.add_node(
            pattern_id,
            "PhonicsPattern",
            pattern,
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=page_uid,
            block_uid=block_uid,
            properties={"source": "core_patterns"},
        )
        self.add_node(
            exemplar_id,
            "PhonicsExemplar",
            exemplar,
            source_file=source_file,
            book_id=book_id,
            unit_id=unit_id,
            page_uid=page_uid,
            block_uid=block_uid,
            properties={"pattern": pattern},
        )
        self.add_edge("block_has_target", block_node_id, pattern_id, page_uid=page_uid, block_uid=block_uid)
        self.add_edge("phonics_uses_pattern", block_node_id, pattern_id, page_uid=page_uid, block_uid=block_uid)
        self.add_edge("phonics_uses_exemplar", pattern_id, exemplar_id, page_uid=page_uid, block_uid=block_uid)

    def _maybe_add_story_nodes(
        self,
        block: dict[str, Any],
        block_node_id: str,
        source_file: Path,
        book_id: str,
        unit_id: str,
        core_patterns: list[str],
        allowed_answers: list[str],
    ) -> None:
        page_type = clean_text(block.get("page_type"))
        block_type = clean_text(block.get("block_type"))
        summary = clean_text(block.get("teaching_summary"))
        if page_type != "reading" and "story" not in summary.casefold() and "story" not in block_type.casefold():
            return
        page_uid = clean_text(block.get("page_uid"))
        block_uid = clean_text(block.get("block_uid"))
        story_questions = [pattern for pattern in core_patterns if looks_like_question(pattern)]
        for question in story_questions:
            story_id = stable_id("StoryQuestion", block_uid, question)
            self.add_node(
                story_id,
                "StoryQuestion",
                question,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={"source": "core_patterns"},
            )
            self.add_edge("story_has_question", block_node_id, story_id, page_uid=page_uid, block_uid=block_uid)
            frame = infer_answer_frame(question, allowed_answers)
            if frame:
                frame_id = stable_id("AnswerFrame", block_uid, frame)
                self.add_node(
                    frame_id,
                    "AnswerFrame",
                    frame,
                    source_file=source_file,
                    book_id=book_id,
                    unit_id=unit_id,
                    page_uid=page_uid,
                    block_uid=block_uid,
                    properties={"inferred_from_story_question": question},
                )
                self.add_edge("question_expects_answer_frame", story_id, frame_id, page_uid=page_uid, block_uid=block_uid)
        all_text = " ".join([summary, " ".join(core_patterns), " ".join(allowed_answers)]).casefold()
        for character in ("Zoom", "Zip", "Robin", "Wu Binbin", "Mike", "John", "Zhang Peng"):
            if character.casefold() not in all_text:
                continue
            char_id = stable_id("StoryCharacter", block_uid, character)
            self.add_node(
                char_id,
                "StoryCharacter",
                character,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
            )
            self.add_edge("story_has_character", block_node_id, char_id, page_uid=page_uid, block_uid=block_uid)
        for question in story_questions:
            answer = next((item for item in allowed_answers if looks_like_answer(item)), "")
            if not answer:
                continue
            label = f"{question} -> {answer}"
            pair_id = stable_id("RolePlayPair", block_uid, label)
            self.add_node(
                pair_id,
                "RolePlayPair",
                label,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
            )
            self.add_edge("roleplay_has_pair", block_node_id, pair_id, page_uid=page_uid, block_uid=block_uid)

    def _add_learning_targets(self, targets: list[dict[str, Any]], source_file: Path, scope: dict[str, Any]) -> None:
        for target in targets:
            target_uid = clean_text(target.get("target_uid"))
            block_uid = clean_text(target.get("block_uid"))
            if not target_uid:
                continue
            page_uid = "-".join(block_uid.split("-")[:4]) if block_uid.startswith("TB-") else ""
            book_id, unit_id = self._book_unit_for_page(page_uid, scope)
            node_id = f"TeachingTarget:{target_uid}"
            self.add_node(
                node_id,
                "TeachingTarget",
                clean_text(target.get("text")) or target_uid,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                page_uid=page_uid,
                block_uid=block_uid,
                properties={
                    "target_uid": target_uid,
                    "category": clean_text(target.get("category")),
                    "text": clean_text(target.get("text")),
                },
            )
            block_node_id = f"Block:{block_uid}"
            if block_node_id in self.nodes:
                self.add_edge("block_has_target", block_node_id, node_id, page_uid=page_uid, block_uid=block_uid)

    def _add_wordlist_entries(self, entries: list[dict[str, Any]], source_file: Path, scope: dict[str, Any]) -> None:
        for entry in entries:
            word = clean_text(entry.get("word"))
            if not word:
                continue
            book_id = infer_book_id(scope)
            unit_id = infer_unit_id(scope)
            vocab_id = stable_id("VocabItem", word)
            self.add_node(
                vocab_id,
                "VocabItem",
                word,
                source_file=source_file,
                book_id=book_id,
                unit_id=unit_id,
                properties={
                    "unit": clean_text(entry.get("unit")),
                    "phonetic": clean_text(entry.get("phonetic")),
                    "chinese": clean_text(entry.get("chinese")),
                    "emphasized": bool(entry.get("emphasized")),
                    "source": "wordlist_entries",
                },
            )
            for block_uid in entry.get("linked_block_uids") or []:
                block_uid = clean_text(block_uid)
                page_uid = "-".join(block_uid.split("-")[:4]) if block_uid.startswith("TB-") else ""
                block_node_id = f"Block:{block_uid}"
                if block_node_id in self.nodes:
                    self.add_edge("block_has_vocab", block_node_id, vocab_id, page_uid=page_uid, block_uid=block_uid)
                    self.add_edge("block_has_target", block_node_id, vocab_id, page_uid=page_uid, block_uid=block_uid)

    def _graph(self) -> dict[str, Any]:
        node_counts = dict(sorted(Counter(node["type"] for node in self.nodes.values()).items()))
        edge_counts = dict(sorted(Counter(edge["type"] for edge in self.edges.values()).items()))
        pages_by_book = dict(sorted(Counter(node.get("book_id") or "__unknown__" for node in self.nodes.values() if node["type"] == "Page").items()))
        blocks_by_book = dict(sorted(Counter(node.get("book_id") or "__unknown__" for node in self.nodes.values() if node["type"] == "Block").items()))
        represented = sorted(page_uid for page_uid in ANCHOR_PAGE_UIDS if f"Page:{page_uid}" in self.nodes)
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": {
                "structured_dir": rel_path(self.structured_dir),
                "raw_dir": rel_path(self.raw_dir),
                "structured_files": sorted(self.structured_files),
                "raw_files": sorted(self.raw_files),
            },
            "metadata": {
                "book_count": node_counts.get("Book", 0),
                "unit_count": node_counts.get("Unit", 0),
                "page_count": node_counts.get("Page", 0),
                "block_count": node_counts.get("Block", 0),
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "node_type_counts": node_counts,
                "edge_type_counts": edge_counts,
                "pages_by_book": pages_by_book,
                "blocks_by_book": blocks_by_book,
                "anchor_pages": {
                    "requested": list(ANCHOR_PAGE_UIDS),
                    "present": represented,
                    "missing": sorted(set(ANCHOR_PAGE_UIDS) - set(represented)),
                },
                "methodology_note": (
                    "Offline deterministic graph extraction inspired by graph extraction/reward-eval "
                    "workflows; no GRPO training or runtime connection is introduced."
                ),
            },
            "node_types": list(NODE_TYPES),
            "edge_types": list(EDGE_TYPES),
            "nodes": sorted(self.nodes.values(), key=lambda node: (node["type"], node["id"])),
            "edges": sorted(self.edges.values(), key=lambda edge: (edge["type"], edge["id"])),
        }


def build_curriculum_graph(
    *,
    structured_dir: Path = DEFAULT_STRUCTURED_DIR,
    raw_dir: Path = DEFAULT_RAW_DIR,
) -> dict[str, Any]:
    return CurriculumGraphBuilder(
        structured_dir=resolve_path(structured_dir),
        raw_dir=resolve_path(raw_dir),
    ).build()


def write_graph(graph: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curriculum_graph_{timestamp()}.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structured-dir", type=Path, default=DEFAULT_STRUCTURED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    graph = build_curriculum_graph(structured_dir=args.structured_dir, raw_dir=args.raw_dir)
    print(write_graph(graph, args.out_dir))


if __name__ == "__main__":
    main()
