import importlib.util
import json
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_script(name: str):
    script_path = _repo_root() / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture_structured_root(tmp_path: Path) -> tuple[Path, Path]:
    structured = tmp_path / "structured"
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / "fixture.md").write_text("# fixture", encoding="utf-8")
    _write_json(
        structured / "curriculum-map.json",
        {
            "books": [
                {
                    "book_id": "G6S1",
                    "grade": "G6",
                    "semester": "S1",
                    "source_refs": ["app/knowledge/raw/fixture.md"],
                    "units": [
                        {
                            "unit": "U1",
                            "unit_theme": "locations",
                            "pages": [4, 5],
                            "core_vocabulary": [
                                {"word": "museum shop", "chinese": "博物馆商店"},
                            ],
                        }
                    ],
                },
                {
                    "book_id": "G5S2",
                    "grade": "G5",
                    "semester": "S2",
                    "units": [{"unit": "U1", "pages": [6], "core_vocabulary": []}],
                },
            ]
        },
    )
    _write_json(
        structured / "general" / "general-manifest.json",
        {"generated_files": ["app/knowledge/structured/general/g6s1u1-general.json"]},
    )
    _write_json(
        structured / "general" / "g6s1u1-general.json",
        {
            "scope": {"grade": "G6", "semester": "S1", "unit": "U1", "pages": [4, 5]},
            "source_files": ["app/knowledge/raw/fixture.md"],
            "page_lessons": [
                {
                    "page_uid": "TB-G6S1U1-P4",
                    "page_type": "dialogue",
                    "priority_blocks": ["TB-G6S1U1-P4-D1", "TB-G6S1U1-P4-D2"],
                },
                {
                    "page_uid": "TB-G6S1U1-P5",
                    "page_type": "reading",
                    "priority_blocks": ["TB-G6S1U1-P5-D1"],
                },
            ],
            "teaching_blocks": [
                {
                    "page_uid": "TB-G6S1U1-P4",
                    "block_uid": "TB-G6S1U1-P4-D1",
                    "page_type": "dialogue",
                    "block_type": "dialogue_core",
                    "teaching_goal": "Ask and answer where a place is.",
                    "focus_vocabulary": ["museum shop"],
                    "core_patterns": ["Where is the museum shop?", "It's near the door."],
                    "allowed_answer_scope": ["It's near the door."],
                    "return_anchors": ["Try to say: Where is the museum shop?"],
                },
                {
                    "page_uid": "TB-G6S1U1-P4",
                    "block_uid": "TB-G6S1U1-P4-D2",
                    "page_type": "dialogue",
                    "block_type": "dialogue_core",
                    "teaching_goal": "Ask another location question.",
                    "focus_vocabulary": ["post office"],
                    "core_patterns": ["Where is the post office?"],
                    "allowed_answer_scope": [],
                    "return_anchors": [],
                },
                {
                    "page_uid": "TB-G6S1U1-P5",
                    "block_uid": "TB-G6S1U1-P5-D1",
                    "page_type": "reading",
                    "block_type": "story_reading",
                    "teaching_goal": "Read a story.",
                    "core_patterns": ["Zoom wants a salad."],
                    "allowed_answer_scope": ["Zoom would like a salad."],
                    "return_anchors": [],
                },
            ],
            "learning_targets": [],
            "wordlist_entries": [],
        },
    )
    _write_json(
        structured / "general" / "g5s2u1-general.json",
        {
            "scope": {"grade": "G5", "semester": "S2", "unit": "U1", "pages": [6]},
            "page_lessons": [
                {
                    "page_uid": "TB-G5S2U1-P6",
                    "page_type": "phonics",
                    "priority_blocks": ["TB-G5S2U1-P6-D1"],
                }
            ],
            "teaching_blocks": [
                {
                    "page_uid": "TB-G5S2U1-P6",
                    "block_uid": "TB-G5S2U1-P6-D1",
                    "page_type": "phonics",
                    "block_type": "phonics",
                    "teaching_goal": "Practice cl.",
                    "core_patterns": ["Learn the consonant blend 'cl' as in 'clean'."],
                    "allowed_answer_scope": ["clean"],
                    "return_anchors": ["clean"],
                }
            ],
            "learning_targets": [],
            "wordlist_entries": [],
        },
    )
    return structured, raw


def test_build_curriculum_graph_from_fixture_has_required_schema(tmp_path):
    builder = _load_script("build_curriculum_graph")
    structured, raw = _fixture_structured_root(tmp_path)

    graph = builder.build_curriculum_graph(structured_dir=structured, raw_dir=raw)

    assert graph["schema_version"] == "curriculum_graph_v1"
    node_types = {node["type"] for node in graph["nodes"]}
    edge_types = {edge["type"] for edge in graph["edges"]}
    assert {
        "Book",
        "Unit",
        "Page",
        "Block",
        "QuestionTarget",
        "AnswerFrame",
        "PhonicsPattern",
        "PhonicsExemplar",
        "SourceFile",
    } <= node_types
    assert {
        "book_contains_unit",
        "unit_contains_page",
        "page_contains_block",
        "node_from_source_file",
        "phonics_uses_pattern",
        "phonics_uses_exemplar",
    } <= edge_types
    assert any("general-manifest.json" in item for item in graph["source"]["structured_files"])


def test_audit_curriculum_graph_reports_required_summary_and_rules(tmp_path):
    builder = _load_script("build_curriculum_graph")
    auditor = _load_script("audit_curriculum_graph")
    structured, raw = _fixture_structured_root(tmp_path)
    graph = builder.build_curriculum_graph(structured_dir=structured, raw_dir=raw)

    audit = auditor.audit_curriculum_graph(graph)

    summary = audit["summary"]
    for key in {
        "book_count",
        "unit_count",
        "page_count",
        "block_count",
        "node_count",
        "edge_count",
        "pages_by_book",
        "blocks_by_book",
        "pages_with_issues",
        "blocks_with_issues",
        "issue_counts_by_rule",
        "issue_counts_by_severity",
        "top_issue_pages",
        "six_anchor_pages_present",
        "six_anchor_pages_issue_summary",
    }:
        assert key in summary
    rule_counts = summary["issue_counts_by_rule"]
    assert rule_counts["question_without_answer_frame"] >= 1
    assert rule_counts["story_without_question"] >= 1
    assert rule_counts["suspicious_return_anchor"] >= 1
    assert rule_counts["bare_noun_redirect_risk"] >= 1
    assert rule_counts["module_choice_leak_risk"] >= 1
    assert summary["issue_counts_by_severity"]["warning"] >= 1


def test_full_structured_curriculum_represents_anchor_pages():
    builder = _load_script("build_curriculum_graph")

    graph = builder.build_curriculum_graph(
        structured_dir=_repo_root() / "app/knowledge/structured",
        raw_dir=_repo_root() / "app/knowledge/raw",
    )

    assert graph["metadata"]["page_count"] > 6
    assert graph["metadata"]["block_count"] > 6
    anchors = graph["metadata"]["anchor_pages"]
    assert not anchors["missing"]
    assert set(anchors["present"]) == set(builder.ANCHOR_PAGE_UIDS)
    page_ids = {node["id"] for node in graph["nodes"] if node["type"] == "Page"}
    for page_uid in builder.ANCHOR_PAGE_UIDS:
        assert f"Page:{page_uid}" in page_ids


def test_write_graph_and_audit_outputs_valid_json(tmp_path):
    builder = _load_script("build_curriculum_graph")
    auditor = _load_script("audit_curriculum_graph")
    structured, raw = _fixture_structured_root(tmp_path)
    graph = builder.build_curriculum_graph(structured_dir=structured, raw_dir=raw)

    graph_path = builder.write_graph(graph, tmp_path / "artifacts")
    audit = auditor.audit_curriculum_graph(json.loads(graph_path.read_text(encoding="utf-8")))
    audit_path = auditor.write_audit(audit, tmp_path / "artifacts")

    assert json.loads(graph_path.read_text(encoding="utf-8"))["schema_version"] == "curriculum_graph_v1"
    assert json.loads(audit_path.read_text(encoding="utf-8"))["schema_version"] == "curriculum_graph_audit_v1"
