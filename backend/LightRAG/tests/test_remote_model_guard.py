import argparse

import pytest

from lightrag.api import config as config_module


@pytest.fixture(autouse=True)
def _reset_remote_model_guard_state(monkeypatch):
    original_initialized = config_module._initialized
    original_global_args = config_module._global_args

    for key in (
        "PEPTUTOR_REQUIRE_REMOTE_MODELS",
        "LLM_BINDING_API_KEY",
        "EMBEDDING_BINDING_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_EMBEDDING_API_KEY",
        "GEMINI_API_KEY",
        "JINA_API_KEY",
        "AZURE_EMBEDDING_ENDPOINT",
        "JINA_API_BASE",
    ):
        monkeypatch.delenv(key, raising=False)

    config_module._initialized = False
    config_module._global_args = None

    yield

    config_module._initialized = original_initialized
    config_module._global_args = original_global_args


def _build_args(**overrides):
    args = argparse.Namespace(
        llm_binding="openai",
        embedding_binding="openai",
        llm_binding_host="https://api.openai.com/v1",
        embedding_binding_host="https://api.openai.com/v1",
        llm_binding_api_key="sk-llm",
        embedding_binding_api_key="sk-embed",
        llm_model="gpt-4.1-mini",
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_remote_model_guard_accepts_hosted_api_bindings(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_REQUIRE_REMOTE_MODELS", "1")
    args = _build_args()

    resolved = config_module.enforce_remote_model_configuration(args)

    assert resolved is args
    assert args.peptutor_require_remote_models is True


def test_remote_model_guard_rejects_local_bindings(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_REQUIRE_REMOTE_MODELS", "1")

    with pytest.raises(ValueError) as exc_info:
        config_module.enforce_remote_model_configuration(
            _build_args(
                llm_binding="ollama",
                embedding_binding="ollama",
                llm_binding_host="http://localhost:11434",
                embedding_binding_host="http://localhost:11434",
            )
        )

    message = str(exc_info.value)
    assert "LLM_BINDING=ollama is a local-model binding" in message
    assert "EMBEDDING_BINDING=ollama is a local-model binding" in message


def test_remote_model_guard_rejects_local_api_hosts(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_REQUIRE_REMOTE_MODELS", "1")

    with pytest.raises(ValueError) as exc_info:
        config_module.enforce_remote_model_configuration(
            _build_args(
                llm_binding_host="http://127.0.0.1:8000/v1",
                embedding_binding_host="http://localhost:8001/v1",
            )
        )

    message = str(exc_info.value)
    assert "LLM_BINDING_HOST resolves to a local endpoint" in message
    assert "EMBEDDING_BINDING_HOST resolves to a local endpoint" in message


def test_remote_model_guard_requires_remote_credentials(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_REQUIRE_REMOTE_MODELS", "1")

    with pytest.raises(ValueError) as exc_info:
        config_module.enforce_remote_model_configuration(
            _build_args(llm_binding_api_key="", embedding_binding_api_key="")
        )

    message = str(exc_info.value)
    assert "LLM binding openai requires remote credentials" in message
    assert "Embedding binding openai requires remote credentials" in message


def test_initialize_config_applies_remote_model_guard(monkeypatch):
    monkeypatch.setenv("PEPTUTOR_REQUIRE_REMOTE_MODELS", "1")

    with pytest.raises(ValueError, match="local-model binding"):
        config_module.initialize_config(
            _build_args(llm_binding="ollama", llm_binding_host="http://localhost:11434"),
            force=True,
        )

    assert config_module._initialized is False
