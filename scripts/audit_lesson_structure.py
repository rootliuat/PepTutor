#!/usr/bin/env python3
"""Audit lesson block structure and classroom pacing from a fixed smoke report."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from lightrag.orchestrator.lesson_runtime import (
    PilotLessonCatalog,
    TeachingBlockRecord,
)
from lightrag.orchestrator.page_overview_skill import PageOverviewSkill


Verdict = Literal["pass", "suspicious", "broken"]
RiskLevel = Literal["low", "medium", "high"]
Severity = Literal["minor", "major", "critical"]

DEFAULT_MANIFEST = (
    Path("app/knowledge/structured/general/general-with-pilot-overrides-manifest.json")
)
DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")
EXPECTED_PAGE_COUNT = 20
EXPECTED_TURNS_PER_PAGE = 8
REPORT_KIND = "peptutor_lesson_structure_audit"

_VERDICT_RANK: dict[Verdict, int] = {"pass": 0, "suspicious": 1, "broken": 2}
_SEVERITY_TO_VERDICT: dict[Severity, Verdict] = {
    "minor": "suspicious",
    "major": "suspicious",
    "critical": "broken",
}
_FIX_SCOPE_ORDER = (
    "adjust_priority_blocks",
    "adjust_next_block_uids",
    "split_block",
    "narrow_answer_scope",
    "widen_open_slot_scope",
    "align_page_overview",
    "add_regression_case",
    "no_change",
)
_OPEN_SLOT_RE = re.compile(r"\.\.\.|___+|_{2,}")
_ENGLISH_ANCHOR_RE = re.compile(
    r"[A-Za-z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){1,7}[.!?]?"
)
_BLOCK_NUMBER_RE = re.compile(r"-D(\d+)$")
_SECOND_MODULE_RE = re.compile(r"(?:第二块|第2块|second\s+(?:block|module))", re.I)


@dataclass(frozen=True)
class Finding:
    id: str
    severity: Severity
    title: str
    evidence: str
    recommended_fix_scope: str
    block_uid: str | None = None
    step: str | None = None

    @property
    def verdict(self) -> Verdict:
        return _SEVERITY_TO_VERDICT[self.severity]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "evidence": self.evidence,
            "recommended_fix_scope": self.recommended_fix_scope,
        }
        if self.block_uid:
            payload["block_uid"] = self.block_uid
        if self.step:
            payload["step"] = self.step
        return payload


@dataclass
class PageAudit:
    page_uid: str
    book: str = ""
    label: str = ""
    smoke_risk: str = ""
    verdict: Verdict = "pass"
    risk_level: RiskLevel = "low"
    primary_issue: str = "none"
    block_count_static: int = 0
    block_count_smoke: int | None = None
    priority_blocks: list[str] = field(default_factory=list)
    overview_modules: list[dict[str, Any]] = field(default_factory=list)
    block_findings: list[Finding] = field(default_factory=list)
    edge_findings: list[Finding] = field(default_factory=list)
    runtime_evidence: list[Finding] = field(default_factory=list)
    recommended_fix_scope: list[str] = field(default_factory=list)

    def add(self, finding: Finding, *, bucket: str) -> None:
        if bucket == "block":
            self.block_findings.append(finding)
        elif bucket == "edge":
            self.edge_findings.append(finding)
        else:
            self.runtime_evidence.append(finding)
        if _VERDICT_RANK[finding.verdict] > _VERDICT_RANK[self.verdict]:
            self.verdict = finding.verdict
        self.risk_level = _risk_for_verdict(self.verdict)

    def finalize(self) -> None:
        all_findings = [
            *self.block_findings,
            *self.edge_findings,
            *self.runtime_evidence,
        ]
        if all_findings:
            self.primary_issue = sorted(
                all_findings,
                key=lambda item: (
                    _VERDICT_RANK[item.verdict],
                    {"critical": 3, "major": 2, "minor": 1}[item.severity],
                ),
                reverse=True,
            )[0].title
        scopes = [finding.recommended_fix_scope for finding in all_findings]
        if not scopes:
            scopes = ["no_change"]
        self.recommended_fix_scope = _ordered_unique_scopes(scopes)

    def to_payload(self) -> dict[str, Any]:
        return {
            "page_uid": self.page_uid,
            "book": self.book,
            "label": self.label,
            "smoke_risk": self.smoke_risk,
            "verdict": self.verdict,
            "risk_level": self.risk_level,
            "primary_issue": self.primary_issue,
            "block_count_static": self.block_count_static,
            "block_count_smoke": self.block_count_smoke,
            "priority_blocks": self.priority_blocks,
            "overview_modules": self.overview_modules,
            "block_findings": [
                finding.to_payload() for finding in self.block_findings
            ],
            "edge_findings": [
                finding.to_payload() for finding in self.edge_findings
            ],
            "runtime_evidence": [
                finding.to_payload() for finding in self.runtime_evidence
            ],
            "recommended_fix_scope": self.recommended_fix_scope,
        }


def _risk_for_verdict(verdict: Verdict) -> RiskLevel:
    return {"pass": "low", "suspicious": "medium", "broken": "high"}[verdict]


def _add_priority_order_finding(
    audit: PageAudit,
    *,
    priority_blocks: list[str],
) -> None:
    audit.add(
        Finding(
            id="priority_order_differs_from_block_numbering",
            severity="minor",
            title="classroom entry order differs from block numbering",
            evidence=(
                f"priority_blocks={priority_blocks}; "
                f"numbered_order={_numbered_order(priority_blocks)}"
            ),
            recommended_fix_scope="add_regression_case",
        ),
        bucket="edge",
    )


def _ordered_unique_scopes(scopes: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for scope in _FIX_SCOPE_ORDER:
        if scope in scopes and scope not in seen:
            ordered.append(scope)
            seen.add(scope)
    for scope in scopes:
        if scope not in seen:
            ordered.append(scope)
            seen.add(scope)
    return ordered


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


def _load_smoke_report(path: Path) -> dict[str, Any]:
    resolved = _resolve_path(path)
    return json.loads(resolved.read_text(encoding="utf-8"))


def _group_turns(smoke_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for turn in smoke_report.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        page_uid = str(turn.get("page_uid") or "").strip()
        if not page_uid:
            continue
        grouped.setdefault(page_uid, []).append(turn)
    return grouped


def _smoke_pages(smoke_report: dict[str, Any]) -> list[dict[str, Any]]:
    pages = smoke_report.get("pages")
    if isinstance(pages, list) and pages:
        return [page for page in pages if isinstance(page, dict)]
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for turn in smoke_report.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        page_uid = str(turn.get("page_uid") or "").strip()
        if not page_uid or page_uid in seen:
            continue
        seen.add(page_uid)
        result.append({"page_uid": page_uid})
    return result


def audit_structure(
    *,
    manifest_path: Path,
    smoke_report_path: Path,
) -> dict[str, Any]:
    manifest = _resolve_path(manifest_path)
    smoke_path = _resolve_path(smoke_report_path)
    smoke_report = _load_smoke_report(smoke_path)
    catalog = PilotLessonCatalog(manifest_path=manifest)
    overview_skill = PageOverviewSkill()
    turns_by_page = _group_turns(smoke_report)

    audits: list[PageAudit] = []
    for page_info in _smoke_pages(smoke_report):
        page_uid = str(page_info.get("page_uid") or "")
        audit = PageAudit(
            page_uid=page_uid,
            book=str(page_info.get("book") or ""),
            label=str(page_info.get("label") or ""),
            smoke_risk=str(page_info.get("risk") or ""),
            block_count_smoke=(
                int(page_info["block_count"])
                if isinstance(page_info.get("block_count"), int)
                else None
            ),
        )
        _audit_static_page(
            audit=audit,
            catalog=catalog,
            overview_skill=overview_skill,
        )
        _audit_runtime_page(
            audit=audit,
            turns=turns_by_page.get(page_uid, []),
        )
        audit.finalize()
        audits.append(audit)

    summary = _summary(audits, smoke_report)
    report = {
        "kind": REPORT_KIND,
        "audit_id": f"lesson-structure-{_timestamp()}",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest),
        "smoke_report_path": str(smoke_path),
        "smoke_regression_set_id": smoke_report.get("regression_set_id"),
        "expected_page_count": EXPECTED_PAGE_COUNT,
        "expected_turns_per_page": EXPECTED_TURNS_PER_PAGE,
        "summary": summary,
        "pages": [audit.to_payload() for audit in audits],
    }
    return report


def _audit_static_page(
    *,
    audit: PageAudit,
    catalog: PilotLessonCatalog,
    overview_skill: PageOverviewSkill,
) -> None:
    try:
        page = catalog.get_page(audit.page_uid)
    except KeyError:
        audit.add(
            Finding(
                id="manifest_page_missing",
                severity="critical",
                title="page is missing from lesson manifest",
                evidence=f"{audit.page_uid} is present in smoke report but not in manifest.",
                recommended_fix_scope="adjust_priority_blocks",
            ),
            bucket="edge",
        )
        return

    blocks = catalog.blocks_for_page(audit.page_uid)
    block_uids = [block.block_uid for block in blocks]
    audit.block_count_static = len(blocks)
    audit.priority_blocks = list(page.priority_blocks)

    if audit.block_count_smoke is not None and audit.block_count_smoke != len(blocks):
        audit.add(
            Finding(
                id="smoke_block_count_mismatch",
                severity="major",
                title="smoke matrix block_count does not match manifest",
                evidence=(
                    f"smoke block_count={audit.block_count_smoke}; "
                    f"manifest blocks={len(blocks)}."
                ),
                recommended_fix_scope="add_regression_case",
            ),
            bucket="edge",
        )

    if not page.priority_blocks:
        audit.add(
            Finding(
                id="priority_blocks_missing",
                severity="critical",
                title="page has no priority_blocks",
                evidence="No classroom entry order is available for this page.",
                recommended_fix_scope="adjust_priority_blocks",
            ),
            bucket="edge",
        )
    else:
        missing_priority = [
            block_uid for block_uid in page.priority_blocks if block_uid not in block_uids
        ]
        if missing_priority:
            audit.add(
                Finding(
                    id="priority_block_missing",
                    severity="critical",
                    title="priority_blocks references blocks outside this page",
                    evidence=f"missing or cross-page priority blocks={missing_priority}",
                    recommended_fix_scope="adjust_priority_blocks",
                ),
                bucket="edge",
            )
        if len(set(page.priority_blocks)) != len(page.priority_blocks):
            audit.add(
                Finding(
                    id="priority_blocks_duplicate",
                    severity="major",
                    title="priority_blocks contains duplicate entries",
                    evidence=f"priority_blocks={page.priority_blocks}",
                    recommended_fix_scope="adjust_priority_blocks",
                ),
                bucket="edge",
            )

    unprioritized = [block_uid for block_uid in block_uids if block_uid not in page.priority_blocks]
    if unprioritized:
        audit.add(
            Finding(
                id="blocks_not_in_priority_order",
                severity="major",
                title="some teaching blocks are not reachable from priority_blocks",
                evidence=f"unprioritized blocks={unprioritized}",
                recommended_fix_scope="adjust_priority_blocks",
            ),
            bucket="edge",
        )

    priority_order_differs = (
        _numbered_order(page.priority_blocks) != page.priority_blocks
        and len(page.priority_blocks) > 1
    )

    block_by_uid = {block.block_uid: block for block in blocks}
    priority_index = {block_uid: index for index, block_uid in enumerate(page.priority_blocks)}
    for block in blocks:
        _audit_block_scope(audit, block, same_page_blocks=blocks)
        _audit_next_edges(
            audit=audit,
            block=block,
            block_by_uid=block_by_uid,
            priority_index=priority_index,
            priority_blocks=list(page.priority_blocks),
        )

    overview = overview_skill.build(page=page, blocks=blocks)
    if overview is None:
        if priority_order_differs:
            _add_priority_order_finding(audit, priority_blocks=page.priority_blocks)
        if len(blocks) > 1:
            audit.add(
                Finding(
                    id="page_overview_missing_for_multi_block_page",
                    severity="major",
                    title="multi-block page has no page overview modules",
                    evidence=f"block_count={len(blocks)}; priority_blocks={page.priority_blocks}",
                    recommended_fix_scope="align_page_overview",
                ),
                bucket="edge",
            )
        return

    audit.overview_modules = [
        {
            "label": module.label,
            "block_uids": list(module.block_uids),
            "summary": module.summary,
        }
        for module in overview.modules
    ]
    overview_blocks = [
        block_uid
        for module in overview.modules
        for block_uid in module.block_uids
    ]
    if priority_order_differs and overview_blocks != page.priority_blocks:
        _add_priority_order_finding(audit, priority_blocks=page.priority_blocks)
    unknown_overview_blocks = [
        block_uid for block_uid in overview_blocks if block_uid not in block_by_uid
    ]
    missing_overview_priority_blocks = [
        block_uid for block_uid in page.priority_blocks if block_uid not in overview_blocks
    ]
    if unknown_overview_blocks:
        audit.add(
            Finding(
                id="page_overview_unknown_block",
                severity="critical",
                title="page overview references unknown blocks",
                evidence=f"unknown overview blocks={unknown_overview_blocks}",
                recommended_fix_scope="align_page_overview",
            ),
            bucket="edge",
        )
    if missing_overview_priority_blocks:
        audit.add(
            Finding(
                id="page_overview_omits_priority_blocks",
                severity="major",
                title="page overview omits blocks from the classroom entry order",
                evidence=(
                    f"missing priority blocks={missing_overview_priority_blocks}; "
                    f"overview_blocks={overview_blocks}"
                ),
                recommended_fix_scope="align_page_overview",
            ),
            bucket="edge",
        )
    if len(blocks) > 1 and len(overview.modules) == 1:
        audit.add(
            Finding(
                id="page_overview_collapsed_multi_block_page",
                severity="major",
                title="page overview collapses a multi-block page into one module",
                evidence=f"module_count=1; block_count={len(blocks)}",
                recommended_fix_scope="align_page_overview",
            ),
            bucket="edge",
        )


def _audit_block_scope(
    audit: PageAudit,
    block: TeachingBlockRecord,
    *,
    same_page_blocks: list[TeachingBlockRecord],
) -> None:
    text = _block_scope_text(block)
    has_food = _has_food_target(text)
    has_drink = _has_drink_target(text)
    if has_food and has_drink and (
        len(block.core_patterns) > 1 or len(block.allowed_answer_scope) > 2
    ) and not _is_intentional_food_drink_mix(block, same_page_blocks):
        audit.add(
            Finding(
                id="block_mixes_food_and_drink_targets",
                severity="major",
                title="block mixes food and drink teaching targets",
                evidence=(
                    f"core_patterns={block.core_patterns}; "
                    f"allowed_answer_scope={block.allowed_answer_scope[:5]}"
                ),
                recommended_fix_scope="split_block",
                block_uid=block.block_uid,
            ),
            bucket="block",
        )

    open_slot_values = [
        value
        for value in [*block.core_patterns, *block.allowed_answer_scope]
        if _OPEN_SLOT_RE.search(value)
    ]
    closed_examples = [
        value
        for value in block.allowed_answer_scope
        if value and not _OPEN_SLOT_RE.search(value)
    ]
    if open_slot_values and 0 < len(closed_examples) <= 2:
        audit.add(
            Finding(
                id="open_slot_has_narrow_examples",
                severity="minor",
                title="open-slot block has a narrow example list",
                evidence=(
                    f"open_slot_values={open_slot_values[:3]}; "
                    f"allowed_answer_scope={block.allowed_answer_scope[:4]}"
                ),
                recommended_fix_scope="widen_open_slot_scope",
                block_uid=block.block_uid,
            ),
            bucket="block",
        )

    block_type = block.block_type.casefold()
    dense_non_dialogue_type = not _block_type_allows_many_core_patterns(block_type)
    dense_multi_block_dialogue = (
        block_type == "dialogue_core"
        and audit.block_count_static > 1
        and len(block.core_patterns) >= 8
    )
    if len(block.core_patterns) >= 4 and (
        dense_non_dialogue_type or dense_multi_block_dialogue
    ):
        audit.add(
            Finding(
                id="block_has_many_core_patterns",
                severity="minor",
                title="block contains many core patterns for one classroom step",
                evidence=f"core_patterns={block.core_patterns[:6]}",
                recommended_fix_scope="split_block",
                block_uid=block.block_uid,
            ),
            bucket="block",
        )


def _block_type_allows_many_core_patterns(block_type: str) -> bool:
    return block_type in {
        "dialogue_core",
        "dialogue_practice",
        "grammar_point",
        "listening_task",
        "practice_fill_blank",
        "practice_write",
        "reading_passage",
        "story",
        "story_block",
        "summary_wrap_up",
    }


def _block_scope_text(block: TeachingBlockRecord) -> str:
    return " ".join(
        [
            block.block_type,
            block.teaching_goal,
            block.teaching_summary,
            *block.focus_vocabulary,
            *block.core_patterns,
            *block.allowed_answer_scope,
            *block.branchable_topics,
        ]
    ).casefold()


def _has_food_target(text: str) -> bool:
    return any(
        token in text
        for token in ("food", "eat", "sandwich", "hamburger", "salad", "想吃")
    )


def _has_drink_target(text: str) -> bool:
    return any(
        token in text
        for token in ("drink", "water", "tea", "juice", "thirsty", "想喝", "口渴")
    )


def _is_intentional_food_drink_mix(
    block: TeachingBlockRecord,
    same_page_blocks: list[TeachingBlockRecord],
) -> bool:
    block_type = block.block_type.casefold()
    text = _block_scope_text(block)
    if block_type == "vocabulary_core":
        return True

    if block_type == "roleplay_task":
        return "roleplay" in text or "role-play" in text or "角色扮演" in text

    if block_type == "picture_scene":
        has_category_task = any(
            token in text
            for token in ("classify", "category", "categories", "分类", "分组")
        )
        has_supplies = any(token in text for token in ("supplies", "party supplies", "用品"))
        return has_category_task and has_supplies

    if block_type != "dialogue_core":
        return False

    other_texts = [
        _block_scope_text(candidate)
        for candidate in same_page_blocks
        if candidate.block_uid != block.block_uid
    ]
    has_food_followup = any(
        _has_food_target(text) and not _has_drink_target(text)
        for text in other_texts
    )
    has_drink_followup = any(
        _has_drink_target(text) and not _has_food_target(text)
        for text in other_texts
    )
    return has_food_followup and has_drink_followup


def _audit_next_edges(
    *,
    audit: PageAudit,
    block: TeachingBlockRecord,
    block_by_uid: dict[str, TeachingBlockRecord],
    priority_index: dict[str, int],
    priority_blocks: list[str],
) -> None:
    for target_uid in block.next_block_uids:
        target = block_by_uid.get(target_uid)
        if target is None:
            audit.add(
                Finding(
                    id="next_block_target_missing",
                    severity="critical",
                    title="next_block_uids points outside this page or manifest",
                    evidence=f"{block.block_uid} -> {target_uid}",
                    recommended_fix_scope="adjust_next_block_uids",
                    block_uid=block.block_uid,
                ),
                bucket="edge",
            )
            continue
        if target.page_uid != block.page_uid:
            audit.add(
                Finding(
                    id="next_block_cross_page",
                    severity="critical",
                    title="next_block_uids crosses page boundary",
                    evidence=f"{block.block_uid} -> {target_uid}",
                    recommended_fix_scope="adjust_next_block_uids",
                    block_uid=block.block_uid,
                ),
                bucket="edge",
            )

    index = priority_index.get(block.block_uid)
    if index is None:
        return
    immediate_next = (
        priority_blocks[index + 1] if index + 1 < len(priority_blocks) else None
    )
    if immediate_next and immediate_next not in block.next_block_uids:
        audit.add(
            Finding(
                id="next_block_skips_immediate_priority_block",
                severity="major",
                title="next edge does not include the next priority block",
                evidence=(
                    f"{block.block_uid} next_block_uids={block.next_block_uids}; "
                    f"expected immediate next={immediate_next}"
                ),
                recommended_fix_scope="adjust_next_block_uids",
                block_uid=block.block_uid,
            ),
            bucket="edge",
        )
    if immediate_next is None and block.next_block_uids:
        audit.add(
            Finding(
                id="terminal_priority_block_has_next_edges",
                severity="minor",
                title="last priority block still has next edges",
                evidence=f"{block.block_uid} next_block_uids={block.next_block_uids}",
                recommended_fix_scope="adjust_next_block_uids",
                block_uid=block.block_uid,
            ),
            bucket="edge",
        )


def _audit_runtime_page(
    *,
    audit: PageAudit,
    turns: list[dict[str, Any]],
) -> None:
    if not turns:
        audit.add(
            Finding(
                id="smoke_page_missing_turns",
                severity="critical",
                title="page has no turns in smoke transcript",
                evidence="The specified smoke report does not contain turns for this page.",
                recommended_fix_scope="add_regression_case",
            ),
            bucket="runtime",
        )
        return

    if len(turns) != EXPECTED_TURNS_PER_PAGE:
        audit.add(
            Finding(
                id="smoke_turn_count_unexpected",
                severity="major",
                title="page does not have the expected smoke turn count",
                evidence=f"turn_count={len(turns)}; expected={EXPECTED_TURNS_PER_PAGE}",
                recommended_fix_scope="add_regression_case",
            ),
            bucket="runtime",
        )

    known_blocks = set(audit.priority_blocks)
    second_module_blocks = _second_module_blocks(audit.overview_modules)
    for turn in turns:
        step = str(turn.get("step") or "")
        learner_input = str(turn.get("learner_input") or "")
        response = str(turn.get("teacher_response") or "")
        state_page_uid = str(turn.get("state_page_uid") or "")
        state_block_uid = str(turn.get("state_block_uid") or "")

        if int(turn.get("http_status") or 0) != 200 or turn.get("error"):
            audit.add(
                Finding(
                    id="runtime_turn_failed",
                    severity="critical",
                    title="smoke turn failed",
                    evidence=(
                        f"{step} input={learner_input!r}; "
                        f"status={turn.get('http_status')} error={turn.get('error')}"
                    ),
                    recommended_fix_scope="add_regression_case",
                    step=step,
                ),
                bucket="runtime",
            )
        if state_page_uid and state_page_uid != audit.page_uid:
            audit.add(
                Finding(
                    id="runtime_state_page_drift",
                    severity="critical",
                    title="runtime state drifted to another page",
                    evidence=f"{step} state_page_uid={state_page_uid}",
                    recommended_fix_scope="adjust_next_block_uids",
                    step=step,
                ),
                bucket="runtime",
            )
        if state_block_uid and known_blocks and state_block_uid not in known_blocks:
            audit.add(
                Finding(
                    id="runtime_state_block_outside_priority",
                    severity="critical",
                    title="runtime entered a block outside priority_blocks",
                    evidence=f"{step} state_block_uid={state_block_uid}",
                    recommended_fix_scope="adjust_priority_blocks",
                    step=step,
                ),
                bucket="runtime",
            )
        if turn.get("fallbackused") is True or turn.get("teacherresponsesource") == "fallback":
            audit.add(
                Finding(
                    id="runtime_fallback_used",
                    severity="critical",
                    title="runtime fell back during structure smoke",
                    evidence=(
                        f"{step} input={learner_input!r}; "
                        f"reason={turn.get('fallback_reason')} route={turn.get('route')}"
                    ),
                    recommended_fix_scope="add_regression_case",
                    step=step,
                ),
                bucket="runtime",
            )
        for flag in turn.get("quality_flags") or []:
            if flag in {
                "broken_mixed_english",
                "next_page_copy",
                "generic_praise",
                "phonics_tautology",
                "traditional_chinese",
            }:
                audit.add(
                    Finding(
                        id=f"runtime_quality_flag_{flag}",
                        severity="minor" if flag == "generic_praise" else "major",
                        title="runtime response quality flag may be structure-induced",
                        evidence=(
                            f"{step} input={learner_input!r}; "
                            f"flag={flag}; reply={response[:180]}"
                        ),
                        recommended_fix_scope="add_regression_case",
                        step=step,
                    ),
                    bucket="runtime",
                )
        if (
            _SECOND_MODULE_RE.search(learner_input)
            and second_module_blocks
            and state_block_uid
            and state_block_uid not in second_module_blocks
        ):
            audit.add(
                Finding(
                    id="runtime_module_choice_landed_elsewhere",
                    severity="critical",
                    title="second-module request did not land in the second module",
                    evidence=(
                        f"{step} input={learner_input!r}; "
                        f"state_block_uid={state_block_uid}; "
                        f"second_module_blocks={sorted(second_module_blocks)}"
                    ),
                    recommended_fix_scope="align_page_overview",
                    step=step,
                ),
                bucket="runtime",
            )
        if _reply_looks_overloaded(response, step=step):
            audit.add(
                Finding(
                    id="runtime_reply_overloaded",
                    severity="minor",
                    title="teacher reply may be doing too many classroom actions",
                    evidence=f"{step} reply={response[:220]}",
                    recommended_fix_scope="split_block",
                    step=step,
                ),
                bucket="runtime",
            )


def _reply_looks_overloaded(response: str, *, step: str) -> bool:
    if not response or step == "page_entry":
        return False
    anchors = [
        match.group(0).strip()
        for match in _ENGLISH_ANCHOR_RE.finditer(response)
        if _anchor_is_contentful(match.group(0))
    ]
    if len(anchors) >= 4:
        return True
    action_cues = sum(
        1
        for cue in ("先", "然后", "再", "跟我读", "回答", "试着", "现在")
        if cue in response
    )
    return action_cues >= 4 and len(response) > 180


def _anchor_is_contentful(text: str) -> bool:
    compact = re.sub(r"[^a-z]", "", text.casefold())
    return len(compact) >= 5 and compact not in {
        "peptutor",
        "lesson",
        "teacher",
    }


def _second_module_blocks(overview_modules: list[dict[str, Any]]) -> set[str]:
    if len(overview_modules) < 2:
        return set()
    block_uids = overview_modules[1].get("block_uids")
    if not isinstance(block_uids, list):
        return set()
    return {str(block_uid) for block_uid in block_uids if block_uid}


def _numbered_order(block_uids: list[str]) -> list[str]:
    return sorted(block_uids, key=lambda block_uid: (_block_number(block_uid), block_uid))


def _block_number(block_uid: str) -> int:
    match = _BLOCK_NUMBER_RE.search(block_uid)
    return int(match.group(1)) if match else 9999


def _summary(
    audits: list[PageAudit],
    smoke_report: dict[str, Any],
) -> dict[str, Any]:
    verdict_counts = {"pass": 0, "suspicious": 0, "broken": 0}
    fix_scope_counts: dict[str, int] = {}
    finding_counts: dict[str, int] = {}
    for audit in audits:
        verdict_counts[audit.verdict] += 1
        for scope in audit.recommended_fix_scope:
            fix_scope_counts[scope] = fix_scope_counts.get(scope, 0) + 1
        for finding in [
            *audit.block_findings,
            *audit.edge_findings,
            *audit.runtime_evidence,
        ]:
            finding_counts[finding.id] = finding_counts.get(finding.id, 0) + 1

    coverage_complete = len(audits) == EXPECTED_PAGE_COUNT and all(
        len(smoke_report_turns) == EXPECTED_TURNS_PER_PAGE
        for smoke_report_turns in _group_turns(smoke_report).values()
    )
    return {
        "page_count": len(audits),
        "coverage_complete": coverage_complete,
        "verdict_counts": verdict_counts,
        "fix_scope_counts": dict(sorted(fix_scope_counts.items())),
        "finding_counts": dict(sorted(finding_counts.items())),
        "broken_pages": [
            audit.page_uid for audit in audits if audit.verdict == "broken"
        ],
        "suspicious_pages": [
            audit.page_uid for audit in audits if audit.verdict == "suspicious"
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Lesson Structure Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Manifest: `{report['manifest_path']}`",
        f"Smoke report: `{report['smoke_report_path']}`",
        f"Regression set: `{report.get('smoke_regression_set_id')}`",
        "",
        "## Summary",
        "",
    ]
    summary = report["summary"]
    lines.append(f"- page_count: `{summary['page_count']}`")
    lines.append(f"- coverage_complete: `{summary['coverage_complete']}`")
    lines.append(f"- verdict_counts: `{summary['verdict_counts']}`")
    lines.append(f"- fix_scope_counts: `{summary['fix_scope_counts']}`")
    lines.append("")
    lines.append("## Pages")
    lines.append("")
    for page in report["pages"]:
        lines.append(
            f"### {page['verdict'].upper()} `{page['page_uid']}` "
            f"{page.get('book', '')} {page.get('label', '')}".rstrip()
        )
        lines.append(f"- risk_level: `{page['risk_level']}`")
        lines.append(f"- primary_issue: {page['primary_issue']}")
        lines.append(f"- recommended_fix_scope: `{page['recommended_fix_scope']}`")
        lines.append(f"- priority_blocks: `{page['priority_blocks']}`")
        if page.get("overview_modules"):
            module_text = "; ".join(
                f"{module['label']}={module['block_uids']}"
                for module in page["overview_modules"]
            )
            lines.append(f"- overview_modules: `{module_text}`")
        findings = [
            ("block", page["block_findings"]),
            ("edge", page["edge_findings"]),
            ("runtime", page["runtime_evidence"]),
        ]
        has_findings = any(items for _, items in findings)
        if not has_findings:
            lines.append("- findings: none")
        else:
            for bucket, items in findings:
                for item in items:
                    suffix = f" ({item['block_uid']})" if item.get("block_uid") else ""
                    if item.get("step"):
                        suffix += f" [{item['step']}]"
                    lines.append(
                        f"- {bucket}/{item['severity']} `{item['id']}`{suffix}: "
                        f"{item['title']} | fix={item['recommended_fix_scope']} | "
                        f"{item['evidence']}"
                    )
        lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    resolved_out = _resolve_path(out_dir)
    resolved_out.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    json_path = resolved_out / f"lesson_structure_audit_{stamp}.json"
    md_path = resolved_out / f"lesson_structure_audit_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Lesson manifest to audit.",
    )
    parser.add_argument(
        "--smoke-report",
        type=Path,
        required=True,
        help="Existing scripts/smoke_lesson_matrix.py JSON report to consume.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for JSON and Markdown audit artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_structure(
        manifest_path=args.manifest,
        smoke_report_path=args.smoke_report,
    )
    json_path, md_path = write_report(report, args.out_dir)
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "summary": report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
