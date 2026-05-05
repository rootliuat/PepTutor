#!/usr/bin/env python3
"""Plan read-only curriculum data tightening candidates from graph-audit findings."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
DEFAULT_DOCS_DIR = Path("docs")
PLAN_SCHEMA_VERSION = "curriculum_data_tightening_plan_v1"
ANCHOR_PAGE_UIDS = {
    "TB-G5S1U3-P22",
    "TB-G6S1U1-P4",
    "TB-G6S2U1-P4",
    "TB-G5S1U3-P31",
    "TB-G5S2U1-P6",
    "TB-G6S2U2-P13",
}
P13_PAGE_UID = "TB-G6S2U2-P13"
P6_PAGE_UID = "TB-G5S2U1-P6"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root() / path).resolve()


def rel_path(path: Path) -> str:
    resolved = resolve_path(path)
    try:
        return str(resolved.relative_to(repo_root()))
    except ValueError:
        return str(resolved)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def datestamp() -> str:
    return datetime.now().strftime("%Y%m%d")


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).strip()


def _load_script(name: str) -> Any:
    script_path = repo_root() / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _latest_artifact(pattern: str, artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path | None:
    reports = sorted(
        resolve_path(artifact_dir).glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def load_audit(path: Path | None) -> tuple[dict[str, Any], Path | None]:
    if path:
        resolved = resolve_path(path)
        return json.loads(resolved.read_text(encoding="utf-8")), resolved
    latest = _latest_artifact("curriculum_graph_audit_*.json")
    if latest:
        return json.loads(latest.read_text(encoding="utf-8")), latest

    builder = _load_script("build_curriculum_graph")
    auditor = _load_script("audit_curriculum_graph")
    graph = builder.build_curriculum_graph(
        structured_dir=repo_root() / "app/knowledge/structured",
        raw_dir=repo_root() / "app/knowledge/raw",
    )
    return auditor.audit_curriculum_graph(graph), None


def load_graph(path: Path | None) -> tuple[dict[str, Any] | None, Path | None]:
    if path:
        resolved = resolve_path(path)
        return json.loads(resolved.read_text(encoding="utf-8")), resolved
    latest = _latest_artifact("curriculum_graph_*.json")
    if latest:
        return json.loads(latest.read_text(encoding="utf-8")), latest
    return None, None


def _node_index(graph: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not graph:
        return {}
    return {node["id"]: node for node in graph.get("nodes", [])}


def _edges_by_source(graph: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    edges: dict[str, list[dict[str, Any]]] = {}
    if not graph:
        return edges
    for edge in graph.get("edges", []):
        edges.setdefault(edge.get("source", ""), []).append(edge)
    return edges


def _targets(
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: dict[str, dict[str, Any]],
    source: str,
    edge_type: str,
    node_type: str | None = None,
) -> list[dict[str, Any]]:
    result = []
    for edge in edge_map.get(source, []):
        if edge.get("type") != edge_type:
            continue
        node = nodes.get(edge.get("target", ""))
        if node and (node_type is None or node.get("type") == node_type):
            result.append(node)
    return result


def _labels(nodes: list[dict[str, Any]]) -> list[str]:
    return sorted({clean_text(node.get("label")) for node in nodes if clean_text(node.get("label"))})


def _block_context(
    finding: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    block_uid = clean_text(finding.get("block_uid"))
    block = nodes.get(f"Block:{block_uid}") if block_uid else None
    if not block:
        return {
            "current_allowed_answer_scope": finding.get("evidence", {}).get("allowed_answer_scope", []),
            "detected_question_targets": finding.get("evidence", {}).get("questions", []),
            "detected_answer_frames": [],
            "detected_return_anchors": [],
        }

    block_id = block["id"]
    props = block.get("properties", {})
    question_nodes = _targets(by_source, nodes, block_id, "block_has_question_target", "QuestionTarget")
    story_questions = _targets(by_source, nodes, block_id, "story_has_question", "StoryQuestion")
    answer_targets = _targets(by_source, nodes, block_id, "block_has_answer_target")
    return_anchors = _targets(by_source, nodes, block_id, "vocab_returns_to_anchor", "ReturnAnchor")
    answer_frames: list[dict[str, Any]] = []
    for question in [*question_nodes, *story_questions]:
        answer_frames.extend(_targets(by_source, nodes, question["id"], "question_expects_answer_frame", "AnswerFrame"))

    return {
        "current_allowed_answer_scope": props.get("allowed_answer_scope")
        or finding.get("evidence", {}).get("allowed_answer_scope", []),
        "detected_question_targets": _labels([*question_nodes, *story_questions])
        or finding.get("evidence", {}).get("questions", []),
        "detected_answer_frames": _labels([*answer_frames, *answer_targets]),
        "detected_return_anchors": _labels(return_anchors),
    }


def _candidate_class(finding: dict[str, Any]) -> str:
    rule = finding.get("rule", "")
    if rule == "answer_scope_ambiguous":
        return "answer_scope_tightening_candidate"
    if rule in {"phonics_without_pattern", "phonics_without_exemplar"}:
        return "phonics_graph_inheritance_candidate"
    if rule in {"suspicious_return_anchor", "vocab_without_return_anchor", "module_choice_leak_risk"}:
        return "return_anchor_wrapper_candidate"
    if rule in {"story_without_question", "story_without_answer_frame"}:
        return "false_positive_rule_refinement_candidate"
    return "defer_low_priority_candidate"


def _priority(finding: dict[str, Any], candidate_class: str) -> str:
    page_uid = finding.get("page_uid", "")
    rule = finding.get("rule", "")
    if page_uid == P13_PAGE_UID or rule == "answer_scope_ambiguous":
        return "P0"
    if page_uid == P6_PAGE_UID or candidate_class == "phonics_graph_inheritance_candidate":
        return "P1"
    if page_uid in ANCHOR_PAGE_UIDS:
        return "P1"
    if candidate_class in {"return_anchor_wrapper_candidate", "false_positive_rule_refinement_candidate"}:
        return "P2"
    return "P3"


def _suggested_action(finding: dict[str, Any], candidate_class: str) -> str:
    rule = finding.get("rule", "")
    if candidate_class == "answer_scope_tightening_candidate":
        return (
            "Review the block's allowed_answer_scope and replace generic labels with structured acceptable-answer "
            "intent, expected frame, and return-anchor boundaries; do not mutate data without human review."
        )
    if candidate_class == "phonics_graph_inheritance_candidate":
        return (
            "Model page-level phonics pattern/exemplar inheritance so practice blocks can inherit the pattern instead "
            "of requiring every block to repeat it."
        )
    if candidate_class == "return_anchor_wrapper_candidate":
        return (
            "Normalize wrapper-style activity instructions into separate activity labels and durable return anchors."
        )
    if candidate_class == "false_positive_rule_refinement_candidate":
        return (
            "Refine graph builder/audit classification before data edits; distinguish real story questions from reading, "
            "setup, or practice blocks."
        )
    if rule == "bare_noun_redirect_risk":
        return "Keep as target-priority risk evidence; do not promote to immediate source edit without runtime evidence."
    return "Defer until higher-risk source/schema gaps are reviewed."


def _owner_layer(candidate_class: str) -> str:
    if candidate_class == "answer_scope_tightening_candidate":
        return "curriculum_data_review"
    if candidate_class == "phonics_graph_inheritance_candidate":
        return "graph_builder_schema"
    if candidate_class == "return_anchor_wrapper_candidate":
        return "curriculum_data_review_or_graph_normalizer"
    if candidate_class == "false_positive_rule_refinement_candidate":
        return "audit_rule_refinement"
    return "triage_backlog"


def _risk_if_changed(candidate_class: str) -> str:
    if candidate_class == "answer_scope_tightening_candidate":
        return "Over-tightening answer scope may reject valid personalized answers or reopen module-choice fallback paths."
    if candidate_class == "phonics_graph_inheritance_candidate":
        return "Incorrect inheritance could attach the wrong phonics pattern to practice blocks."
    if candidate_class == "return_anchor_wrapper_candidate":
        return "Over-normalizing wrappers could remove a valid student action from activity pages."
    if candidate_class == "false_positive_rule_refinement_candidate":
        return "Treating a rule false positive as missing data could invent story prompts not present in the book."
    return "Low immediate risk; premature edits could create noise without improving classroom behavior."


def _reason(finding: dict[str, Any], candidate_class: str) -> str:
    page_uid = finding.get("page_uid", "")
    rule = finding.get("rule", "")
    if page_uid == P13_PAGE_UID:
        return (
            "P13 has only answer_scope_ambiguous evidence in the P8.1 audit; do not classify it as return-anchor or "
            "module-choice risk unless a future audit shows that evidence."
        )
    if page_uid == P6_PAGE_UID:
        return (
            "P6 has no phonics_without_exemplar finding in this audit; current evidence points to phonics pattern "
            "inheritance and wrapper-anchor normalization."
        )
    return f"{rule} maps to {candidate_class} for read-only human review."


def build_candidates(audit: dict[str, Any], graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    nodes = _node_index(graph)
    by_source = _edges_by_source(graph)
    candidates = []
    for index, finding in enumerate(audit.get("findings", []), start=1):
        candidate_class = _candidate_class(finding)
        context = _block_context(finding, nodes, by_source)
        candidates.append(
            {
                "candidate_id": f"CDT-{index:04d}",
                "class": candidate_class,
                "severity": finding.get("severity", "warning"),
                "page_uid": finding.get("page_uid", ""),
                "block_uid": finding.get("block_uid", ""),
                "source_files": finding.get("source_files", []),
                "current_issue_rule": finding.get("rule", ""),
                "current_evidence": finding.get("evidence", {}),
                "current_allowed_answer_scope": context["current_allowed_answer_scope"],
                "detected_question_targets": context["detected_question_targets"],
                "detected_answer_frames": context["detected_answer_frames"],
                "detected_return_anchors": context["detected_return_anchors"],
                "suggested_action": _suggested_action(finding, candidate_class),
                "suggested_owner_layer": _owner_layer(candidate_class),
                "should_mutate_data_now": False,
                "risk_if_changed": _risk_if_changed(candidate_class),
                "priority": _priority(finding, candidate_class),
                "reason": _reason(finding, candidate_class),
            }
        )
    return candidates


def build_plan(
    audit: dict[str, Any],
    *,
    audit_path: Path | None = None,
    graph: dict[str, Any] | None = None,
    graph_path: Path | None = None,
) -> dict[str, Any]:
    candidates = build_candidates(audit, graph)
    class_counts = Counter(candidate["class"] for candidate in candidates)
    priority_counts = Counter(candidate["priority"] for candidate in candidates)
    p13_candidates = [candidate for candidate in candidates if candidate["page_uid"] == P13_PAGE_UID]
    p6_candidates = [candidate for candidate in candidates if candidate["page_uid"] == P6_PAGE_UID]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_audit_path": rel_path(audit_path) if audit_path else "",
        "source_graph_path": rel_path(graph_path) if graph_path else "",
        "summary": {
            "finding_count": len(audit.get("findings", [])),
            "candidate_count": len(candidates),
            "candidate_counts_by_class": dict(sorted(class_counts.items())),
            "candidate_counts_by_priority": dict(sorted(priority_counts.items())),
            "p13_candidate_classes": sorted({candidate["class"] for candidate in p13_candidates}),
            "p13_has_return_anchor_or_module_choice_candidate": any(
                candidate["current_issue_rule"] in {"suspicious_return_anchor", "module_choice_leak_risk"}
                for candidate in p13_candidates
            ),
            "p6_candidate_classes": sorted({candidate["class"] for candidate in p6_candidates}),
            "p6_has_phonics_without_exemplar": any(
                candidate["current_issue_rule"] == "phonics_without_exemplar" for candidate in p6_candidates
            ),
            "recommended_next_slices": [
                "P8.3a answer-scope data tightening review with human approval before source edits.",
                "P8.3b phonics graph inheritance / rule refinement.",
            ],
        },
        "candidates": candidates,
    }


def write_plan_json(plan: dict[str, Any], out_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curriculum_data_tightening_candidates_{timestamp()}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _top_candidates(candidates: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(
        candidates,
        key=lambda item: (
            priority_rank.get(item["priority"], 9),
            item["page_uid"],
            item["block_uid"],
            item["current_issue_rule"],
            item["candidate_id"],
        ),
    )[:limit]


def render_markdown(plan: dict[str, Any], *, json_path: Path | None = None) -> str:
    summary = plan["summary"]
    class_counts = summary["candidate_counts_by_class"]
    priority_counts = summary["candidate_counts_by_priority"]
    candidates = plan["candidates"]
    lines = [
        "# Curriculum Data Tightening Candidates",
        "",
        f"Generated from: `{plan.get('source_audit_path') or 'in-memory audit'}`",
    ]
    if plan.get("source_graph_path"):
        lines.append(f"Graph context: `{plan['source_graph_path']}`")
    if json_path:
        lines.append(f"Generated candidate JSON: `{rel_path(json_path)}`")
    lines.extend(
        [
            "",
            "This is a read-only candidate plan. It does not edit structured curriculum data.",
            "",
            "## Summary",
            "",
            f"- finding_count: {summary['finding_count']}",
            f"- candidate_count: {summary['candidate_count']}",
            f"- P13 candidate classes: {', '.join(summary['p13_candidate_classes']) or 'none'}",
            "- P13 return-anchor/module-choice candidate: "
            f"{summary['p13_has_return_anchor_or_module_choice_candidate']}",
            f"- P6 candidate classes: {', '.join(summary['p6_candidate_classes']) or 'none'}",
            f"- P6 has phonics_without_exemplar: {summary['p6_has_phonics_without_exemplar']}",
            "",
            "## Candidate Counts By Class",
            "",
            "| Class | Count |",
            "|---|---:|",
        ]
    )
    for key, value in sorted(class_counts.items()):
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "## Candidate Counts By Priority", "", "| Priority | Count |", "|---|---:|"])
    for key, value in sorted(priority_counts.items()):
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Recommended Next Slices",
            "",
            "1. P8.3a: answer-scope data tightening review. Human approval is still required before data edits.",
            "2. P8.3b: phonics graph inheritance / rule refinement.",
            "",
            "## Top Review Candidates",
            "",
            "| ID | Priority | Class | Page | Block | Rule | Suggested action |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for candidate in _top_candidates(candidates):
        action = candidate["suggested_action"].replace("|", "\\|")
        lines.append(
            "| "
            f"`{candidate['candidate_id']}` | `{candidate['priority']}` | `{candidate['class']}` | "
            f"`{candidate['page_uid']}` | `{candidate['block_uid']}` | "
            f"`{candidate['current_issue_rule']}` | {action} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- `should_mutate_data_now` is `false` for every candidate.",
            "- P13 is not classified as return-anchor or module-choice risk unless the audit finding explicitly says so.",
            "- P6 is not classified as `phonics_without_exemplar` because the P8.1 audit emitted no such P6 finding.",
            "- Low-priority target-selection risks remain documented but are not promoted into immediate data edits.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_markdown(plan: dict[str, Any], path: Path, *, json_path: Path | None = None) -> Path:
    output = resolve_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(plan, json_path=json_path), encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, help="Existing curriculum_graph_audit_*.json.")
    parser.add_argument("--graph", type=Path, help="Optional curriculum_graph_*.json for richer context.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument(
        "--docs-output",
        type=Path,
        default=DEFAULT_DOCS_DIR / f"curriculum-data-tightening-candidates-{datestamp()}.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit, audit_path = load_audit(args.audit)
    graph, graph_path = load_graph(args.graph)
    plan = build_plan(audit, audit_path=audit_path, graph=graph, graph_path=graph_path)
    json_path = write_plan_json(plan, args.out_dir)
    docs_path = write_markdown(plan, args.docs_output, json_path=json_path)
    print(json_path)
    print(docs_path)


if __name__ == "__main__":
    main()
