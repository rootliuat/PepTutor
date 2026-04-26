"""Exact lesson evidence lookup before scoped semantic retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LessonEvidenceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: str
    semester: str
    unit: str
    pages: list[int] = Field(default_factory=list)


class LessonEvidencePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_uid: str
    page_type: str
    page_intro_cn: str
    priority_block_uids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    confidence: str


class LessonEvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_uid: str
    page_uid: str
    page_type: str
    block_type: str
    teaching_goal: str
    teaching_summary: str
    focus_vocabulary: list[str] = Field(default_factory=list)
    core_patterns: list[str] = Field(default_factory=list)
    allowed_answer_scope: list[str] = Field(default_factory=list)
    entry_probe_questions: list[str] = Field(default_factory=list)
    repair_modes: list[str] = Field(default_factory=list)
    learning_target_uids: list[str] = Field(default_factory=list)
    branchable_topics: list[str] = Field(default_factory=list)
    return_anchors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "block_uid": self.block_uid,
            "page_uid": self.page_uid,
            "block_type": self.block_type,
            "teaching_goal": self.teaching_goal,
            "teaching_summary": self.teaching_summary,
            "focus_vocabulary": self.focus_vocabulary[:8],
            "core_patterns": self.core_patterns[:8],
            "allowed_answer_scope": self.allowed_answer_scope[:8],
            "source_refs": self.source_refs,
        }


class LessonEvidence(BaseModel):
    """UID-first page and block evidence for one lesson turn."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "peptutor-lesson-evidence-v1"
    lookup_strategy: list[str] = Field(
        default_factory=lambda: [
            "exact_page_uid",
            "exact_block_uid",
            "same_page_scope",
            "same_unit_scope",
        ]
    )
    scope: LessonEvidenceScope
    exact_page: LessonEvidencePage
    exact_block: LessonEvidenceBlock | None = None
    same_page_blocks: list[LessonEvidenceBlock] = Field(default_factory=list)
    same_unit_blocks: list[LessonEvidenceBlock] = Field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lookup_strategy": self.lookup_strategy,
            "scope": self.scope.model_dump(mode="json"),
            "exact_page": self.exact_page.model_dump(mode="json"),
            "exact_block": (
                self.exact_block.to_prompt_payload() if self.exact_block else None
            ),
            "same_page_support": [
                block.to_prompt_payload() for block in self.same_page_blocks
            ],
            "same_unit_support": [
                block.to_prompt_payload() for block in self.same_unit_blocks
            ],
        }


@dataclass(frozen=True)
class _CurriculumPageMeta:
    page_uid: str
    page_type: str
    confidence: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class _OverlayRecord:
    payload: dict[str, Any]
    source_ref: str


class LessonEvidenceLookup:
    """Build compact evidence from exact page/block metadata first."""

    def __init__(
        self,
        catalog: Any,
        *,
        curriculum_map_path: Path | None = None,
    ):
        self.catalog = catalog
        self.curriculum_map_path = (
            curriculum_map_path.resolve()
            if curriculum_map_path is not None
            else _default_curriculum_map_path_for_catalog(catalog)
        )
        self.repo_root = (
            _find_repo_root(self.curriculum_map_path)
            if self.curriculum_map_path is not None
            else None
        )
        self._page_meta: dict[str, _CurriculumPageMeta] = {}
        self._target_source_refs_by_block_uid: dict[str, list[str]] = {}
        self._overlay_source_refs: set[str] = set()
        self._overlay_pages: dict[str, _OverlayRecord] = {}
        self._overlay_blocks: dict[str, _OverlayRecord] = {}
        if self.curriculum_map_path is not None and self.curriculum_map_path.exists():
            self._load_curriculum_map()
            self._load_overlay_records()

    def lookup(
        self,
        *,
        page_uid: str,
        block_uid: str | None = None,
        same_page_limit: int = 4,
        same_unit_limit: int = 8,
    ) -> LessonEvidence:
        scope = self.catalog.get_scope_for_page(page_uid)
        evidence_scope = LessonEvidenceScope(
            grade=scope.grade,
            semester=scope.semester,
            unit=scope.unit,
            pages=list(scope.pages),
        )
        page_record = self._page_record(page_uid)
        exact_page = self._build_page_evidence(page_record)
        exact_block = None
        if block_uid is not None:
            block_record = self._block_record(block_uid)
            actual_page_uid = _record_value(block_record, "page_uid")
            if actual_page_uid != page_uid:
                raise ValueError(
                    f"Block {block_uid} belongs to page {actual_page_uid}, "
                    f"not requested page {page_uid}"
                )
            exact_block = self._build_block_evidence(block_record)

        same_page_blocks = [
            self._build_block_evidence(record)
            for record in self._blocks_for_page(page_uid, exclude_block_uid=block_uid)[
                : max(same_page_limit, 0)
            ]
        ]
        same_unit_records = self.catalog.blocks_for_unit(
            page_uid,
            exclude_page_uid=page_uid,
        )[: max(same_unit_limit, 0)]
        same_unit_blocks = [
            self._build_block_evidence(self._block_record(_record_value(record, "block_uid")))
            for record in same_unit_records
        ]
        self._assert_same_scope(
            reference_scope=evidence_scope,
            blocks=same_unit_blocks,
            support_name="same_unit_blocks",
        )
        return LessonEvidence(
            scope=evidence_scope,
            exact_page=exact_page,
            exact_block=exact_block,
            same_page_blocks=same_page_blocks,
            same_unit_blocks=same_unit_blocks,
        )

    def _load_curriculum_map(self) -> None:
        if self.curriculum_map_path is None:
            return
        payload = json.loads(self.curriculum_map_path.read_text(encoding="utf-8"))
        for book in payload.get("books", []):
            for unit in book.get("units", []):
                for page in unit.get("page_types", []):
                    page_uid = page.get("page_uid")
                    if not isinstance(page_uid, str):
                        continue
                    source_refs = tuple(
                        ref
                        for ref in page.get("source_refs", [])
                        if isinstance(ref, str)
                    )
                    self._page_meta[page_uid] = _CurriculumPageMeta(
                        page_uid=page_uid,
                        page_type=str(page.get("page_type") or ""),
                        confidence=str(page.get("confidence") or "unknown"),
                        source_refs=source_refs,
                    )
                    for source_ref in source_refs:
                        if self._is_overlay_source_ref(source_ref):
                            self._overlay_source_refs.add(source_ref)
                for target in unit.get("learning_targets", []):
                    block_uid = target.get("block_uid")
                    if not isinstance(block_uid, str):
                        continue
                    self._target_source_refs_by_block_uid.setdefault(
                        block_uid,
                        [],
                    ).extend(
                        ref
                        for ref in target.get("source_refs", [])
                        if isinstance(ref, str)
                    )

    def _load_overlay_records(self) -> None:
        for source_ref in sorted(self._overlay_source_refs):
            source_path = self._resolve_source_ref(source_ref)
            if source_path is None or not source_path.exists():
                continue
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            for page in payload.get("page_lessons", []):
                page_uid = page.get("page_uid")
                if isinstance(page_uid, str) and page_uid in self._page_meta:
                    self._overlay_pages[page_uid] = _OverlayRecord(
                        payload=page,
                        source_ref=source_ref,
                    )
            for block in payload.get("teaching_blocks", []):
                block_uid = block.get("block_uid")
                if isinstance(block_uid, str):
                    self._overlay_blocks[block_uid] = _OverlayRecord(
                        payload=block,
                        source_ref=source_ref,
                    )

    def _page_record(self, page_uid: str) -> Any:
        overlay = self._overlay_pages.get(page_uid)
        if overlay is not None:
            return overlay
        return self.catalog.get_page(page_uid)

    def _block_record(self, block_uid: str) -> Any:
        overlay = self._overlay_blocks.get(block_uid)
        if overlay is not None:
            return overlay
        return self.catalog.get_block(block_uid)

    def _blocks_for_page(
        self,
        page_uid: str,
        *,
        exclude_block_uid: str | None = None,
    ) -> list[Any]:
        page = self._page_record(page_uid)
        ordered_uids = [
            block_uid
            for block_uid in _record_value(page, "priority_blocks", [])
            if block_uid != exclude_block_uid
        ]
        seen = set(ordered_uids)
        for block in self.catalog.blocks_for_page(page_uid):
            block_uid = _record_value(block, "block_uid")
            if block_uid == exclude_block_uid or block_uid in seen:
                continue
            ordered_uids.append(block_uid)
            seen.add(block_uid)
        return [self._block_record(block_uid) for block_uid in ordered_uids]

    def _build_page_evidence(self, record: Any) -> LessonEvidencePage:
        data = _record_data(record)
        page_uid = str(data["page_uid"])
        meta = self._page_meta.get(page_uid)
        source_refs = _unique_strings(
            [
                page_uid,
                *_record_source_refs(record),
                *(meta.source_refs if meta else ()),
            ]
        )
        return LessonEvidencePage(
            page_uid=page_uid,
            page_type=(meta.page_type if meta and meta.page_type else data["page_type"]),
            page_intro_cn=str(data.get("page_intro_cn") or ""),
            priority_block_uids=list(data.get("priority_blocks") or []),
            source_refs=source_refs,
            confidence=meta.confidence if meta else "catalog",
        )

    def _build_block_evidence(self, record: Any) -> LessonEvidenceBlock:
        data = _record_data(record)
        block_uid = str(data["block_uid"])
        source_refs = _unique_strings(
            [
                block_uid,
                *_record_source_refs(record),
                *(
                    self._target_source_refs_by_block_uid.get(block_uid)
                    or []
                ),
            ]
        )
        return LessonEvidenceBlock(
            block_uid=block_uid,
            page_uid=str(data["page_uid"]),
            page_type=str(data.get("page_type") or ""),
            block_type=str(data.get("block_type") or ""),
            teaching_goal=str(data.get("teaching_goal") or ""),
            teaching_summary=str(data.get("teaching_summary") or ""),
            focus_vocabulary=list(data.get("focus_vocabulary") or []),
            core_patterns=list(data.get("core_patterns") or []),
            allowed_answer_scope=list(data.get("allowed_answer_scope") or []),
            entry_probe_questions=list(data.get("entry_probe_questions") or []),
            repair_modes=list(data.get("repair_modes") or []),
            learning_target_uids=list(data.get("learning_target_uids") or []),
            branchable_topics=list(data.get("branchable_topics") or []),
            return_anchors=list(data.get("return_anchors") or []),
            source_refs=source_refs,
        )

    def _assert_same_scope(
        self,
        *,
        reference_scope: LessonEvidenceScope,
        blocks: list[LessonEvidenceBlock],
        support_name: str,
    ) -> None:
        expected = (
            reference_scope.grade,
            reference_scope.semester,
            reference_scope.unit,
        )
        for block in blocks:
            scope = self.catalog.get_scope_for_page(block.page_uid)
            actual = (scope.grade, scope.semester, scope.unit)
            if actual != expected:
                raise ValueError(
                    f"{support_name} leaked {block.block_uid} from {actual}; "
                    f"expected {expected}"
                )

    def _is_overlay_source_ref(self, source_ref: str) -> bool:
        return (
            source_ref.endswith(".json")
            and "/structured/" in source_ref
            and "/structured/general/" not in source_ref
        )

    def _resolve_source_ref(self, source_ref: str) -> Path | None:
        source_path = Path(source_ref)
        if source_path.is_absolute():
            return source_path
        if self.repo_root is None:
            return None
        return self.repo_root / source_path


def _record_data(record: Any) -> dict[str, Any]:
    if isinstance(record, _OverlayRecord):
        return record.payload
    if hasattr(record, "model_dump"):
        return record.model_dump(mode="json")
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported lesson evidence record: {type(record)!r}")


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    return _record_data(record).get(key, default)


def _record_source_refs(record: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(record, _OverlayRecord):
        refs.append(record.source_ref)
    data = _record_data(record)
    refs.extend(ref for ref in data.get("source_refs", []) if isinstance(ref, str))
    return refs


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _default_curriculum_map_path_for_catalog(catalog: Any) -> Path | None:
    manifest_path = getattr(catalog, "manifest_path", None)
    if manifest_path is None:
        return None
    root = _find_repo_root(Path(__file__))
    resolved_manifest = Path(manifest_path).resolve()
    if not _is_relative_to(resolved_manifest, root):
        return None
    candidate = root / "app" / "knowledge" / "structured" / "curriculum-map.json"
    return candidate if candidate.exists() else None


def _find_repo_root(path: Path) -> Path:
    resolved = path.resolve()
    candidates = [resolved, *resolved.parents]
    for candidate in candidates:
        if (candidate / "app" / "knowledge" / "structured").exists():
            return candidate
    return Path(__file__).resolve().parents[4]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
