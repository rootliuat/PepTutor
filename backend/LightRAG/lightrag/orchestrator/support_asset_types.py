"""Shared Pydantic models for structured support assets."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SupportScopeInfo(BaseModel):
    """Minimal unit scope for support assets."""

    model_config = ConfigDict(extra="forbid")

    grade: str
    semester: str
    unit: str
    pages: list[int] = Field(default_factory=list)


class LexiconEntryRecord(BaseModel):
    """One stable lexicon item derived from the unit word list."""

    model_config = ConfigDict(extra="forbid")

    entry_uid: str
    entry_type: str
    english: str
    chinese: str
    phonetic: str | None = None
    emphasized: bool = False
    source_refs: list[str] = Field(default_factory=list)
    page_refs: list[str] = Field(default_factory=list)
    linked_page_uids: list[str] = Field(default_factory=list)
    linked_block_uids: list[str] = Field(default_factory=list)


class ExpressionEntryRecord(BaseModel):
    """One stable useful-expression record linked back to page and block scope."""

    model_config = ConfigDict(extra="forbid")

    entry_uid: str
    english: str
    chinese: str
    page_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    linked_page_uids: list[str] = Field(default_factory=list)
    linked_block_uids: list[str] = Field(default_factory=list)


class SupportAssetFile(BaseModel):
    """Unit-level structured support assets for lexicon and useful expressions."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    scope: SupportScopeInfo
    source_files: list[str] = Field(default_factory=list)
    lexicon_entries: list[LexiconEntryRecord] = Field(default_factory=list)
    expression_entries: list[ExpressionEntryRecord] = Field(default_factory=list)
