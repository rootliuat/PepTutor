import importlib.util
import json
import subprocess
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


def _query_set() -> dict:
    return {
        "schema_version": "curriculum_agentic_query_set_v1",
        "queries": [
            {
                "query_id": "museum_shop_question",
                "text": "Where is the museum shop?",
                "page_uid": "TB-G6S1U1-P4",
                "review_focus": "location question target preservation",
            },
            {
                "query_id": "p13_answer_scope",
                "text": "TB-G6S2U2-P13 answer scope",
                "page_uid": "TB-G6S2U2-P13",
                "review_focus": "answer-scope boundary review",
            },
        ],
    }


def _evidence_index() -> dict:
    return {
        "entries": [
            {
                "source": "structured",
                "source_ref": "QuestionTarget:museum",
                "page_uid": "TB-G6S1U1-P4",
                "block_uid": "TB-G6S1U1-P4-D2",
                "evidence_type": "QuestionTarget",
                "text": "Where is the museum shop?",
            },
            {
                "source": "audit",
                "source_ref": "answer_scope_ambiguous",
                "page_uid": "TB-G6S2U2-P13",
                "block_uid": "TB-G6S2U2-P13-D1",
                "evidence_type": "answer_scope_ambiguous",
                "text": "Allowed answer scope needs review.",
            },
        ]
    }


def test_default_provider_none_generates_prompts_without_provider_calls():
    harness = _load_script("run_agentic_curriculum_harness")

    result = harness.run_harness(query_set=_query_set(), evidence_index=_evidence_index(), provider="none")

    assert result["provider"] == "none"
    assert result["runtime_connected"] is False
    assert result["summary"]["query_count"] == 2
    assert result["summary"]["provider_call_count"] == 0
    assert "Where is the museum shop?" in result["results"][0]["prompt"]
    assert result["results"][0]["provider_log"]["called"] is False


def test_fake_provider_call_is_logged_with_command_and_output():
    harness = _load_script("run_agentic_curriculum_harness")
    calls = []

    def fake_runner(command: str, timeout_seconds: float | None):
        calls.append((command, timeout_seconds))
        return subprocess.CompletedProcess(command, 0, stdout="fake answer", stderr="")

    result = harness.run_harness(
        query_set=_query_set(),
        evidence_index=_evidence_index(),
        provider="generic",
        provider_command="cat {prompt_file}",
        timeout_seconds=3,
        runner=fake_runner,
    )

    assert len(calls) == 2
    provider_log = result["results"][0]["provider_log"]
    assert provider_log["called"] is True
    assert provider_log["command"].startswith("cat ")
    assert provider_log["exit_code"] == 0
    assert provider_log["stdout"] == "fake answer"
    assert provider_log["stderr"] == ""
    assert isinstance(provider_log["duration"], float)
    assert isinstance(provider_log["duration_seconds"], float)


def test_query_set_contains_required_queries():
    query_path = _repo_root() / "docs" / "curriculum-agentic-query-set-20260505.json"
    query_set = json.loads(query_path.read_text(encoding="utf-8"))
    query_text = "\n".join(query["text"] for query in query_set["queries"])

    for required in [
        "Where is the museum shop?",
        "It's near ...",
        "How tall is it?",
        "TB-G6S2U2-P13 answer scope",
        "cl as in clean",
        "What's your favourite food?",
        "story scaffold P31",
    ]:
        assert required in query_text


def test_retrieval_comparison_and_review_queue_are_review_only(tmp_path):
    harness = _load_script("run_agentic_curriculum_harness")
    comparison_script = _load_script("run_curriculum_retrieval_comparison")
    queue_script = _load_script("build_curriculum_evidence_review_queue")

    harness_result = harness.run_harness(query_set=_query_set(), evidence_index=_evidence_index(), provider="none")
    comparison = comparison_script.build_comparison(harness_result)
    comparison_json = comparison_script.write_comparison_json(comparison, tmp_path / "artifacts")
    comparison_md = comparison_script.write_markdown(comparison, tmp_path / "docs" / "comparison.md")
    queue = queue_script.build_review_queue(comparison)
    queue_json = queue_script.write_queue_json(queue, tmp_path / "artifacts")
    queue_md = queue_script.write_markdown(queue, tmp_path / "docs" / "queue.md")

    assert json.loads(comparison_json.read_text(encoding="utf-8"))["schema_version"] == (
        "curriculum_retrieval_comparison_v1"
    )
    assert "prompt_only_needs_human_review" in comparison_md.read_text(encoding="utf-8")
    parsed_queue = json.loads(queue_json.read_text(encoding="utf-8"))
    assert parsed_queue["schema_version"] == "curriculum_evidence_review_queue_v1"
    assert parsed_queue["summary"]["should_mutate_data_now_count"] == 0
    assert "should_mutate_data_now: False" in queue_md.read_text(encoding="utf-8")
