from focus_catcher.adapters import MockGemmaAdapter, OllamaGemmaAdapter, build_gemma_adapter
from focus_catcher.models import RuntimeProfile


def test_build_gemma_adapter_defaults_to_ollama(monkeypatch) -> None:
    monkeypatch.delenv("FOCUS_CATCHER_GEMMA_BACKEND", raising=False)
    adapter = build_gemma_adapter()
    assert isinstance(adapter, OllamaGemmaAdapter)


def test_mock_gemma_adapter_reports_ready_setup() -> None:
    setup = MockGemmaAdapter().check_setup()
    assert setup.ready is True
    assert setup.mode == "mock"
    assert setup.runtime_profile == RuntimeProfile.STANDARD
