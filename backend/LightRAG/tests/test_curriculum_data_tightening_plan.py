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


def _fixture_audit() -> dict:
    return {
        "schema_version": "curriculum_graph_audit_v1",
        "summary": {"finding_count": 5},
        "findings": [
            {
                "rule": "answer_scope_ambiguous",
                "severity": "warning",
                "page_uid": "TB-G6S2U2-P13",
                "block_uid": "TB-G6S2U2-P13-D1",
                "source_files": ["app/knowledge/structured/general/g6s2u2-general.json"],
                "evidence": {"allowed_answer_scope": ["Last weekend"]},
            },
            {
                "rule": "phonics_without_pattern",
                "severity": "error",
                "page_uid": "TB-G5S2U1-P6",
                "block_uid": "TB-G5S2U1-P6-D2",
                "source_files": ["app/knowledge/structured/general/g5s2u1-general.json"],
                "evidence": {"core_patterns": ["Class, clock, plate, eggplant, clean, play."]},
            },
            {
                "rule": "suspicious_return_anchor",
                "severity": "warning",
                "page_uid": "TB-G5S2U1-P6",
                "block_uid": "TB-G5S2U1-P6-D1",
                "source_files": ["app/knowledge/structured/general/g5s2u1-general.json"],
                "evidence": {"return_anchor": "Learn the consonant blend 'cl' as in 'clean'."},
            },
            {
                "rule": "story_without_question",
                "severity": "warning",
                "page_uid": "TB-G5S1U1-P9",
                "block_uid": "TB-G5S1U1-P9-D1",
                "source_files": ["app/knowledge/structured/general/g5s1u1-general.json"],
                "evidence": {},
            },
            {
                "rule": "bare_noun_redirect_risk",
                "severity": "warning",
                "page_uid": "TB-G5S1U3-P22",
                "block_uid": "TB-G5S1U3-P22-D1",
                "source_files": ["app/knowledge/structured/general/g5s1u3-general.json"],
                "evidence": {"vocab": "favourite food", "questions": ["What's your favourite food?"]},
            },
        ],
    }


def _fixture_graph() -> dict:
    return {
        "schema_version": "curriculum_graph_v1",
        "nodes": [
            {
                "id": "Block:TB-G6S2U2-P13-D1",
                "type": "Block",
                "page_uid": "TB-G6S2U2-P13",
                "block_uid": "TB-G6S2U2-P13-D1",
                "properties": {"allowed_answer_scope": ["Last weekend"]},
            },
            {
                "id": "QuestionTarget:p13",
                "type": "QuestionTarget",
                "label": "What did you do last weekend?",
            },
            {"id": "AnswerFrame:p13", "type": "AnswerFrame", "label": "I ..."},
            {"id": "ReturnAnchor:p13", "type": "ReturnAnchor", "label": "What did you do last weekend?"},
            {
                "id": "Block:TB-G5S2U1-P6-D2",
                "type": "Block",
                "page_uid": "TB-G5S2U1-P6",
                "block_uid": "TB-G5S2U1-P6-D2",
                "properties": {"allowed_answer_scope": ["clean"]},
            },
        ],
        "edges": [
            {
                "source": "Block:TB-G6S2U2-P13-D1",
                "target": "QuestionTarget:p13",
                "type": "block_has_question_target",
            },
            {
                "source": "QuestionTarget:p13",
                "target": "AnswerFrame:p13",
                "type": "question_expects_answer_frame",
            },
            {
                "source": "Block:TB-G6S2U2-P13-D1",
                "target": "ReturnAnchor:p13",
                "type": "vocab_returns_to_anchor",
            },
        ],
    }


def test_answer_scope_ambiguous_becomes_tightening_candidate():
    planner = _load_script("plan_curriculum_data_tightening")

    plan = planner.build_plan(_fixture_audit(), graph=_fixture_graph())

    p13 = [candidate for candidate in plan["candidates"] if candidate["page_uid"] == "TB-G6S2U2-P13"]
    assert len(p13) == 1
    assert p13[0]["class"] == "answer_scope_tightening_candidate"
    assert p13[0]["current_allowed_answer_scope"] == ["Last weekend"]
    assert p13[0]["detected_question_targets"] == ["What did you do last weekend?"]
    assert p13[0]["detected_answer_frames"] == ["I ..."]
    assert p13[0]["should_mutate_data_now"] is False


def test_p13_without_return_anchor_or_module_choice_findings_is_not_misclassified():
    planner = _load_script("plan_curriculum_data_tightening")

    plan = planner.build_plan(_fixture_audit(), graph=_fixture_graph())

    summary = plan["summary"]
    assert summary["p13_candidate_classes"] == ["answer_scope_tightening_candidate"]
    assert summary["p13_has_return_anchor_or_module_choice_candidate"] is False


def test_phonics_without_pattern_becomes_graph_inheritance_candidate():
    planner = _load_script("plan_curriculum_data_tightening")

    plan = planner.build_plan(_fixture_audit(), graph=_fixture_graph())

    p6 = [candidate for candidate in plan["candidates"] if candidate["page_uid"] == "TB-G5S2U1-P6"]
    assert {candidate["class"] for candidate in p6} == {
        "phonics_graph_inheritance_candidate",
        "return_anchor_wrapper_candidate",
    }
    assert plan["summary"]["p6_has_phonics_without_exemplar"] is False


def test_output_json_and_docs_are_valid(tmp_path):
    planner = _load_script("plan_curriculum_data_tightening")
    audit_path = tmp_path / "curriculum_graph_audit_fixture.json"
    graph_path = tmp_path / "curriculum_graph_fixture.json"
    audit_path.write_text(json.dumps(_fixture_audit(), ensure_ascii=False), encoding="utf-8")
    graph_path.write_text(json.dumps(_fixture_graph(), ensure_ascii=False), encoding="utf-8")

    audit, loaded_audit_path = planner.load_audit(audit_path)
    graph, loaded_graph_path = planner.load_graph(graph_path)
    plan = planner.build_plan(audit, audit_path=loaded_audit_path, graph=graph, graph_path=loaded_graph_path)
    json_path = planner.write_plan_json(plan, tmp_path / "artifacts")
    doc_path = planner.write_markdown(plan, tmp_path / "docs" / "candidates.md", json_path=json_path)

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "curriculum_data_tightening_plan_v1"
    assert parsed["summary"]["candidate_count"] == 5
    assert "P8.3a: answer-scope data tightening review" in doc_path.read_text(encoding="utf-8")


def test_planner_does_not_modify_structured_curriculum_data(tmp_path):
    planner = _load_script("plan_curriculum_data_tightening")
    structured_file = tmp_path / "app" / "knowledge" / "structured" / "fixture.json"
    structured_file.parent.mkdir(parents=True)
    structured_file.write_text('{"unchanged": true}\n', encoding="utf-8")
    before = structured_file.read_text(encoding="utf-8")

    plan = planner.build_plan(_fixture_audit(), graph=_fixture_graph())
    planner.write_plan_json(plan, tmp_path / "artifacts")
    planner.write_markdown(plan, tmp_path / "docs" / "candidates.md")

    assert structured_file.read_text(encoding="utf-8") == before
