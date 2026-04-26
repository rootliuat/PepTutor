from __future__ import annotations

from lightrag.api import speech_proxy_config as config_module


def test_speech_proxy_env_reads_repo_root_fallback(tmp_path, monkeypatch):
    backend_env = tmp_path / "backend.env"
    repo_env = tmp_path / "repo.env"
    backend_env.write_text("", encoding="utf-8")
    repo_env.write_text(
        "VITE_PEPTUTOR_TTS_APP_ID=repo-app\nVITE_PEPTUTOR_TTS_API_KEY=repo-key\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("VITE_PEPTUTOR_TTS_APP_ID", raising=False)
    monkeypatch.delenv("VITE_PEPTUTOR_TTS_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "_BACKEND_ENV_PATH", backend_env)
    monkeypatch.setattr(config_module, "_REPO_ENV_PATH", repo_env)
    config_module.load_speech_proxy_env_fallbacks.cache_clear()

    assert config_module.get_env_with_fallback("VITE_PEPTUTOR_TTS_APP_ID") == "repo-app"
    assert config_module.get_env_with_fallback("VITE_PEPTUTOR_TTS_API_KEY") == "repo-key"


def test_speech_proxy_env_prefers_backend_over_repo_root(tmp_path, monkeypatch):
    backend_env = tmp_path / "backend.env"
    repo_env = tmp_path / "repo.env"
    backend_env.write_text("VITE_PEPTUTOR_TTS_APP_ID=backend-app\n", encoding="utf-8")
    repo_env.write_text("VITE_PEPTUTOR_TTS_APP_ID=repo-app\n", encoding="utf-8")

    monkeypatch.delenv("VITE_PEPTUTOR_TTS_APP_ID", raising=False)
    monkeypatch.setattr(config_module, "_BACKEND_ENV_PATH", backend_env)
    monkeypatch.setattr(config_module, "_REPO_ENV_PATH", repo_env)
    config_module.load_speech_proxy_env_fallbacks.cache_clear()

    assert config_module.get_env_with_fallback("VITE_PEPTUTOR_TTS_APP_ID") == "backend-app"

