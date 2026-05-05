import importlib.util
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_client_module():
    script_path = _repo_root() / "scripts/lib/ragflow_client.py"
    name = "ragflow_client"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_health_check_disabled_is_graceful():
    ragflow = _load_client_module()

    client = ragflow.RAGFlowClient(ragflow.RAGFlowConfig(enabled=False))

    result = client.health_check()
    assert result["reachable"] is False
    assert result["api_auth_ok"] is False
    assert "not enabled" in result["warning"]


def test_list_datasets_uses_bearer_auth_and_parses_items():
    ragflow = _load_client_module()
    calls = []

    def transport(method, url, *, headers, data, timeout):
        calls.append((method, url, headers, data, timeout))
        return 200, {}, json.dumps({"code": 0, "data": [{"id": "ds1", "name": "PepTutor"}]}).encode()

    config = ragflow.RAGFlowConfig(
        base_url="http://ragflow.local",
        api_key="secret",
        dataset_id="ds1",
        timeout_seconds=3,
        enabled=True,
    )
    client = ragflow.RAGFlowClient(config, transport=transport)

    datasets = client.list_datasets()

    assert datasets == [{"id": "ds1", "name": "PepTutor"}]
    assert calls[0][0] == "GET"
    assert calls[0][1].startswith("http://ragflow.local/api/v1/datasets")
    assert calls[0][2]["Authorization"] == "Bearer secret"
    assert calls[0][4] == 3


def test_export_chunks_lists_documents_and_chunks():
    ragflow = _load_client_module()

    def transport(method, url, *, headers, data, timeout):
        if url.endswith("/documents?page=1&page_size=1024"):
            return 200, {}, json.dumps({"code": 0, "data": [{"id": "doc1", "name": "book.md"}]}).encode()
        if "/chunks?page=1&page_size=1024" in url:
            return 200, {}, json.dumps({"code": 0, "data": {"chunks": [{"id": "c1", "content": "TB-G5S2U1-P6 clean"}]}}).encode()
        raise AssertionError(url)

    config = ragflow.RAGFlowConfig("http://ragflow.local", "secret", "ds1", 3, True)
    client = ragflow.RAGFlowClient(config, transport=transport)

    chunks = client.export_chunks()

    assert chunks[0]["id"] == "c1"
    assert chunks[0]["document_id"] == "doc1"
    assert chunks[0]["document_name"] == "book.md"


def test_retrieve_posts_question_and_dataset_ids():
    ragflow = _load_client_module()
    captured = {}

    def transport(method, url, *, headers, data, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json.loads(data.decode())
        return 200, {}, json.dumps({"code": 0, "data": {"chunks": []}}).encode()

    config = ragflow.RAGFlowConfig("http://ragflow.local", "secret", "ds1", 3, True)
    client = ragflow.RAGFlowClient(config, transport=transport)

    response = client.retrieve("Where is the museum shop?", top_k=4)

    assert response["code"] == 0
    assert captured["method"] == "POST"
    assert captured["url"] == "http://ragflow.local/api/v1/retrieval"
    assert captured["body"]["dataset_ids"] == ["ds1"]
    assert captured["body"]["top_k"] == 4
