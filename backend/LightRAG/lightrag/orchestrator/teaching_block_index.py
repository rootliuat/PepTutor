"""Offline TeachingBlock indexing helpers for future Qdrant ingestion."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lightrag.orchestrator.lesson_runtime import (
    PilotLessonCatalog,
    TeachingBlockRecord,
    _extract_page_number,
)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


class IndexedTeachingBlock(BaseModel):
    """Normalized record ready for external embedding and vector upsert."""

    model_config = ConfigDict(extra="forbid")

    point_id: str
    embedding_text: str
    payload: dict


def build_embedding_text(block: TeachingBlockRecord) -> str:
    """Build compact, teaching-oriented text for embeddings."""
    parts = _dedupe_preserve_order(
        [
            block.teaching_goal,
            block.teaching_summary,
            *block.core_patterns,
            *block.focus_vocabulary,
            *block.allowed_answer_scope,
        ]
    )
    return " | ".join(parts)


def build_payload(
    catalog: PilotLessonCatalog,
    block: TeachingBlockRecord,
) -> dict:
    """Build the metadata payload recommended by the teaching-runtime design."""
    scope = catalog.get_scope_for_page(block.page_uid)
    return {
        "block_uid": block.block_uid,
        "page_uid": block.page_uid,
        "grade": scope.grade,
        "semester": scope.semester,
        "unit": scope.unit,
        "page": _extract_page_number(block.page_uid),
        "page_type": block.page_type,
        "block_type": block.block_type,
        "teaching_goal": block.teaching_goal,
        "teaching_summary": block.teaching_summary,
        "focus_vocabulary": block.focus_vocabulary,
        "core_patterns": block.core_patterns,
        "allowed_answer_scope": block.allowed_answer_scope,
        "repair_modes": block.repair_modes,
        "learning_target_uids": block.learning_target_uids,
        "next_block_uids": block.next_block_uids,
        "branchable_topics": block.branchable_topics,
        "return_anchors": block.return_anchors,
    }


def build_index_record(
    catalog: PilotLessonCatalog,
    block: TeachingBlockRecord,
) -> IndexedTeachingBlock:
    """Create a normalized teaching-block record for later vector upsert."""
    return IndexedTeachingBlock(
        point_id=block.block_uid,
        embedding_text=build_embedding_text(block),
        payload=build_payload(catalog, block),
    )


def build_unit_index_records(catalog: PilotLessonCatalog) -> list[IndexedTeachingBlock]:
    """Convert the loaded pilot catalog into deterministic index records."""
    return [
        build_index_record(catalog, block)
        for _, block in sorted(catalog.blocks.items(), key=lambda item: item[0])
    ]
