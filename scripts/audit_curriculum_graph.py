#!/usr/bin/env python3
"""Audit PepTutor curriculum graph structure for target/anchor quality risks."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


AUDIT_SCHEMA_VERSION = "curriculum_graph_audit_v1"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")
ANCHOR_PAGE_UIDS = (
    "TB-G5S1U3-P22",
    "TB-G6S1U1-P4",
    "TB-G6S2U1-P4",
    "TB-G5S1U3-P31",
    "TB-G5S2U1-P6",
    "TB-G6S2U2-P13",
)
RULES = (
    "missing_page_uid",
    "missing_block_uid",
    "missing_block_target",
    "missing_question_target",
    "question_without_answer_frame",
    "answer_frame_without_question",
    "phonics_without_pattern",
    "phonics_without_exemplar",
    "story_without_question",
    "story_without_answer_frame",
    "vocab_without_return_anchor",
    "suspicious_return_anchor",
    "answer_scope_missing",
    "answer_scope_ambiguous",
    "multi_target_block_without_priority",
    "target_role_unknown",
    "bare_noun_redirect_risk",
    "module_choice_leak_risk",
    "source_file_missing_or_unknown",
)
SEVERITY_BY_RULE = {
    "missing_page_uid": "error",
    "missing_block_uid": "error",
    "missing_block_target": "error",
    "phonics_without_pattern": "error",
    "phonics_without_exemplar": "error",
    "source_file_missing_or_unknown": "error",
}
WRAPPER_ANCHOR_RE = re.compile(
    r"^(can you say:|try to say:|say after me:|learn the consonant blend|listen and|choose|answer the questions)",
    re.I,
)
EMPTY_SLOT_RE = re.compile(r"\b(where|what|when|who|how)\s+(?:is|are|do|does|did)?\s*the\s+\?", re.I)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_root() / path).resolve()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_build_module() -> Any:
    module_path = repo_root() / "scripts" / "build_curriculum_graph.py"
    spec = importlib.util.spec_from_file_location("build_curriculum_graph", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).strip()


def normalized_text(value: Any) -> str:
    return clean_text(value).strip("。！？!?.").casefold()


def latest_graph_path(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        resolve_path(artifact_dir).glob("curriculum_graph_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No curriculum_graph_*.json found in {artifact_dir}")
    return reports[0]


def _node_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in graph.get("nodes", [])}


def _edges_by_source(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        edges[edge.get("source", "")].append(edge)
    return edges


def _edges_by_target(graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        edges[edge.get("target", "")].append(edge)
    return edges


def _targets_of_type(
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: dict[str, dict[str, Any]],
    source: str,
    edge_type: str,
    node_type: str | None = None,
) -> list[dict[str, Any]]:
    targets = []
    for edge in edge_map.get(source, []):
        if edge.get("type") != edge_type:
            continue
        node = nodes.get(edge.get("target", ""))
        if node and (node_type is None or node.get("type") == node_type):
            targets.append(node)
    return targets


def _sources_of_type(
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: dict[str, dict[str, Any]],
    target: str,
    edge_type: str,
    node_type: str | None = None,
) -> list[dict[str, Any]]:
    sources = []
    for edge in edge_map.get(target, []):
        if edge.get("type") != edge_type:
            continue
        node = nodes.get(edge.get("source", ""))
        if node and (node_type is None or node.get("type") == node_type):
            sources.append(node)
    return sources


def _severity(rule: str) -> str:
    return SEVERITY_BY_RULE.get(rule, "warning")


def _finding(
    rule: str,
    node: dict[str, Any],
    message: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": _severity(rule),
        "page_uid": node.get("page_uid", ""),
        "block_uid": node.get("block_uid", ""),
        "node_id": node.get("id", ""),
        "node_type": node.get("type", ""),
        "source_files": node.get("source_files", []),
        "message": message,
        "evidence": evidence or {},
    }


def _target_role(
    block: dict[str, Any],
    questions: list[dict[str, Any]],
    phonics_patterns: list[dict[str, Any]],
) -> str:
    props = block.get("properties", {})
    page_type = normalized_text(props.get("page_type"))
    block_type = normalized_text(props.get("block_type"))
    summary = normalized_text(props.get("teaching_summary"))
    if phonics_patterns or page_type == "phonics" or block_type == "phonics":
        return "phonics"
    if page_type in {"reading", "story"} or "story" in summary or "story" in block_type:
        return "story"
    if questions:
        return "question"
    if props.get("core_patterns") or props.get("allowed_answer_scope"):
        return "phrase"
    return "unknown"


def _labels(nodes: list[dict[str, Any]], *, limit: int = 20) -> list[str]:
    return [clean_text(node.get("label")) for node in nodes[:limit] if clean_text(node.get("label"))]


def _top_counts(counts: Counter[str], *, limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"id": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _answer_scope_nodes(
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: dict[str, dict[str, Any]],
    block_id: str,
) -> list[dict[str, Any]]:
    return _targets_of_type(edge_map, nodes, block_id, "block_has_answer_scope", "AnswerScope")


def _question_has_frame(
    edge_map: dict[str, list[dict[str, Any]]],
    nodes: dict[str, dict[str, Any]],
    question: dict[str, Any],
) -> bool:
    return bool(_targets_of_type(edge_map, nodes, question["id"], "question_expects_answer_frame", "AnswerFrame"))


def _audit_source_files(nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in nodes.values():
        if node.get("type") == "SourceFile":
            path = clean_text(node.get("properties", {}).get("path"))
            if not path:
                findings.append(
                    _finding(
                        "source_file_missing_or_unknown",
                        node,
                        "SourceFile node has no path property.",
                    )
                )
            continue
        if not node.get("source_files"):
            findings.append(
                _finding(
                    "source_file_missing_or_unknown",
                    node,
                    "Curriculum node has no source-file provenance.",
                )
            )
    return findings


def _audit_block(
    block: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    by_source: dict[str, list[dict[str, Any]]],
    page_priority_counts: dict[str, int],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    props = block.get("properties", {})
    block_id = block["id"]
    target_nodes = _targets_of_type(by_source, nodes, block_id, "block_has_target")
    question_nodes = _targets_of_type(by_source, nodes, block_id, "block_has_question_target", "QuestionTarget")
    answer_targets = _targets_of_type(by_source, nodes, block_id, "block_has_answer_target")
    phonics_patterns = _targets_of_type(by_source, nodes, block_id, "phonics_uses_pattern", "PhonicsPattern")
    return_anchors = _targets_of_type(by_source, nodes, block_id, "vocab_returns_to_anchor", "ReturnAnchor")
    answer_scopes = _answer_scope_nodes(by_source, nodes, block_id)
    role = _target_role(block, question_nodes, phonics_patterns)

    if not block.get("page_uid"):
        findings.append(_finding("missing_page_uid", block, "Block has no page_uid."))
    if not block.get("block_uid") or props.get("missing_block_uid"):
        findings.append(_finding("missing_block_uid", block, "Block has no block_uid."))
    if not target_nodes and not props.get("teaching_goal"):
        findings.append(_finding("missing_block_target", block, "Block has no target node or teaching goal."))
    if role == "unknown":
        findings.append(
            _finding("target_role_unknown", block, "Could not infer block target role from page/block data.")
        )

    if props.get("block_type") == "dialogue_core" and not question_nodes:
        findings.append(_finding("missing_question_target", block, "Dialogue core block has no question target."))

    if role == "phonics":
        if not phonics_patterns:
            findings.append(
                _finding(
                    "phonics_without_pattern",
                    block,
                    "Phonics block has no extracted phonics pattern edge.",
                    evidence={"core_patterns": props.get("core_patterns") or []},
                )
            )
        for pattern in phonics_patterns:
            exemplars = _targets_of_type(by_source, nodes, pattern["id"], "phonics_uses_exemplar", "PhonicsExemplar")
            if not exemplars:
                findings.append(
                    _finding(
                        "phonics_without_exemplar",
                        pattern,
                        "Phonics pattern has no exemplar word.",
                        evidence={"pattern": pattern.get("label")},
                    )
                )

    if role == "story":
        story_questions = _targets_of_type(by_source, nodes, block_id, "story_has_question", "StoryQuestion")
        if not story_questions:
            findings.append(_finding("story_without_question", block, "Story block has no story question."))
        if story_questions and not any(_question_has_frame(by_source, nodes, question) for question in story_questions):
            findings.append(_finding("story_without_answer_frame", block, "Story question has no answer frame."))

    if props.get("focus_vocabulary") and not return_anchors:
        findings.append(
            _finding(
                "vocab_without_return_anchor",
                block,
                "Block has focus vocabulary but no return anchor.",
                evidence={"focus_vocabulary": props.get("focus_vocabulary") or []},
            )
        )

    for anchor in return_anchors:
        label = clean_text(anchor.get("label"))
        if WRAPPER_ANCHOR_RE.search(label) or EMPTY_SLOT_RE.search(label):
            findings.append(
                _finding(
                    "suspicious_return_anchor",
                    anchor,
                    "Return anchor looks like an instruction wrapper or incomplete target.",
                    evidence={"return_anchor": label},
                )
            )

    if not answer_scopes:
        findings.append(_finding("answer_scope_missing", block, "Block has no AnswerScope node."))
    elif role in {"question", "story"} and not any(
        scope.get("properties", {}).get("allowed_answer_scope") for scope in answer_scopes
    ):
        findings.append(_finding("answer_scope_missing", block, "Question/story block has empty answer scope."))

    allowed_scope = [clean_text(item) for item in props.get("allowed_answer_scope") or []]
    ambiguous = [
        item
        for item in allowed_scope
        if normalized_text(item) in {"personalized answer", "answer the questions", "last weekend"}
    ]
    if ambiguous:
        findings.append(
            _finding(
                "answer_scope_ambiguous",
                block,
                "Allowed answer scope contains generic or ambiguous entries.",
                evidence={"allowed_answer_scope": ambiguous},
            )
        )

    if len(props.get("core_patterns") or []) > 3 and props.get("priority_index") is None:
        findings.append(
            _finding(
                "multi_target_block_without_priority",
                block,
                "Multi-target block is not listed in page priority_blocks.",
                evidence={"core_patterns": props.get("core_patterns") or []},
            )
        )

    page_node = nodes.get(f"Page:{block.get('page_uid')}")
    if page_node and page_priority_counts.get(page_node["id"], 0) > 1 and not return_anchors:
        findings.append(
            _finding(
                "module_choice_leak_risk",
                block,
                "Multi-block page block lacks return anchor, increasing module-choice fallback risk.",
                evidence={"page_priority_blocks": page_node.get("properties", {}).get("priority_blocks") or []},
            )
        )

    for vocab in props.get("focus_vocabulary") or []:
        vocab_norm = normalized_text(vocab)
        if any(vocab_norm and vocab_norm in normalized_text(question.get("label")) for question in question_nodes):
            findings.append(
                _finding(
                    "bare_noun_redirect_risk",
                    block,
                    "Focus vocabulary is embedded in a question target and could be over-selected as a bare noun.",
                    evidence={"vocab": vocab, "questions": _labels(question_nodes)},
                )
            )

    if question_nodes and not answer_targets:
        findings.append(
            _finding(
                "question_without_answer_frame",
                block,
                "Question target exists but block has no answer target or answer frame.",
                evidence={"questions": _labels(question_nodes)},
            )
        )

    return findings


def _audit_question_frames(
    nodes: dict[str, dict[str, Any]],
    by_source: dict[str, list[dict[str, Any]]],
    by_target: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in nodes.values():
        if node.get("type") not in {"QuestionTarget", "StoryQuestion"}:
            continue
        if not _question_has_frame(by_source, nodes, node):
            findings.append(_finding("question_without_answer_frame", node, "Question node has no answer frame."))
    for node in nodes.values():
        if node.get("type") != "AnswerFrame":
            continue
        if not _sources_of_type(by_target, nodes, node["id"], "question_expects_answer_frame"):
            findings.append(_finding("answer_frame_without_question", node, "Answer frame is not linked from a question."))
    return findings


def _anchor_summary(
    page_uid: str,
    nodes: dict[str, dict[str, Any]],
    by_source: dict[str, list[dict[str, Any]]],
    page_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    page_node = nodes.get(f"Page:{page_uid}")
    block_nodes = [
        node for node in nodes.values() if node.get("type") == "Block" and node.get("page_uid") == page_uid
    ]
    teaching_targets: list[dict[str, Any]] = []
    question_targets: list[dict[str, Any]] = []
    answer_frames: list[dict[str, Any]] = []
    answer_scopes: list[dict[str, Any]] = []
    for block in block_nodes:
        block_id = block["id"]
        teaching_targets.extend(_targets_of_type(by_source, nodes, block_id, "block_has_target"))
        question_targets.extend(
            _targets_of_type(by_source, nodes, block_id, "block_has_question_target", "QuestionTarget")
        )
        answer_scopes.extend(_answer_scope_nodes(by_source, nodes, block_id))
        for question in question_targets:
            answer_frames.extend(
                _targets_of_type(by_source, nodes, question["id"], "question_expects_answer_frame", "AnswerFrame")
            )
    rules = [finding["rule"] for finding in page_findings]
    return {
        "page_exists": page_node is not None,
        "block_count": len(block_nodes),
        "detected_teaching_targets": sorted(set(_labels(teaching_targets, limit=200))),
        "detected_question_targets": sorted(set(_labels(question_targets, limit=200))),
        "detected_answer_frames": sorted(set(_labels(answer_frames, limit=200))),
        "detected_answer_scope_nodes": sorted(set(node["id"] for node in answer_scopes)),
        "detected_issues": page_findings,
        "bare_noun_redirect_risk": "bare_noun_redirect_risk" in rules,
        "module_choice_leak_risk": "module_choice_leak_risk" in rules,
        "missing_answer_frame_risk": "question_without_answer_frame" in rules
        or "story_without_answer_frame" in rules,
    }


def audit_curriculum_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = _node_index(graph)
    by_source = _edges_by_source(graph)
    by_target = _edges_by_target(graph)
    findings: list[dict[str, Any]] = []

    block_nodes = [node for node in nodes.values() if node.get("type") == "Block"]
    page_nodes = [node for node in nodes.values() if node.get("type") == "Page"]
    page_priority_counts = {
        page["id"]: len(page.get("properties", {}).get("priority_blocks") or []) for page in page_nodes
    }

    for page in page_nodes:
        if not page.get("page_uid"):
            findings.append(_finding("missing_page_uid", page, "Page node has no page_uid."))

    findings.extend(_audit_source_files(nodes))
    for block in block_nodes:
        findings.extend(_audit_block(block, nodes, by_source, page_priority_counts))
    findings.extend(_audit_question_frames(nodes, by_source, by_target))

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings = sorted(
        findings,
        key=lambda item: (
            severity_rank.get(item["severity"], 3),
            item["page_uid"],
            item["block_uid"],
            item["rule"],
            item["node_id"],
        ),
    )
    rule_counts = Counter(finding["rule"] for finding in findings)
    severity_counts = Counter(finding["severity"] for finding in findings)
    by_page = Counter(finding["page_uid"] or "__unknown__" for finding in findings)
    by_block = Counter(finding["block_uid"] or "__unknown__" for finding in findings)
    metadata = graph.get("metadata", {})
    page_findings = defaultdict(list)
    for finding in findings:
        page_findings[finding.get("page_uid", "")].append(finding)
    anchor_present = [page_uid for page_uid in ANCHOR_PAGE_UIDS if f"Page:{page_uid}" in nodes]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "graph_schema_version": graph.get("schema_version"),
        "graph_generated_at": graph.get("generated_at"),
        "rules": list(RULES),
        "summary": {
            "finding_count": len(findings),
            "book_count": metadata.get("book_count", 0),
            "unit_count": metadata.get("unit_count", 0),
            "page_count": metadata.get("page_count", 0),
            "block_count": metadata.get("block_count", 0),
            "node_count": metadata.get("node_count", len(nodes)),
            "edge_count": metadata.get("edge_count", len(graph.get("edges", []))),
            "pages_by_book": metadata.get("pages_by_book", {}),
            "blocks_by_book": metadata.get("blocks_by_book", {}),
            "pages_with_issues": sorted(key for key in by_page if key != "__unknown__"),
            "blocks_with_issues": sorted(key for key in by_block if key != "__unknown__"),
            "issue_counts_by_rule": {rule: rule_counts.get(rule, 0) for rule in RULES},
            "issue_counts_by_severity": {
                severity: severity_counts.get(severity, 0) for severity in ("info", "warning", "error")
            },
            "top_issue_pages": _top_counts(by_page),
            "six_anchor_pages_present": {
                "requested": list(ANCHOR_PAGE_UIDS),
                "present": anchor_present,
                "missing": sorted(set(ANCHOR_PAGE_UIDS) - set(anchor_present)),
                "all_present": len(anchor_present) == len(ANCHOR_PAGE_UIDS),
            },
            "six_anchor_pages_issue_summary": {
                page_uid: _anchor_summary(page_uid, nodes, by_source, page_findings.get(page_uid, []))
                for page_uid in ANCHOR_PAGE_UIDS
            },
        },
        "findings": findings,
        "top_findings": findings[:25],
        "methodology_note": (
            "Offline deterministic graph audit inspired by graph extraction/reward-eval workflows; "
            "no GRPO training or runtime connection is introduced."
        ),
    }


def write_audit(audit: dict[str, Any], out_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    out = resolve_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curriculum_graph_audit_{timestamp()}.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, help="Existing curriculum_graph_*.json to audit.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--structured-dir", type=Path, default=Path("app/knowledge/structured"))
    parser.add_argument("--raw-dir", type=Path, default=Path("app/knowledge/raw"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.graph:
        graph = json.loads(resolve_path(args.graph).read_text(encoding="utf-8"))
    else:
        builder = _load_build_module()
        graph = builder.build_curriculum_graph(structured_dir=args.structured_dir, raw_dir=args.raw_dir)
    audit = audit_curriculum_graph(graph)
    path = write_audit(audit, args.out_dir)
    print(path)


if __name__ == "__main__":
    main()
