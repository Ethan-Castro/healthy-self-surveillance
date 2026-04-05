import json
from unittest.mock import patch

from focus_catcher.adapters import OllamaGemmaAdapter
from focus_catcher.models import ReviewInput, SessionConfig


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_ollama_adapter_strips_data_urls_and_parses_json() -> None:
    adapter = OllamaGemmaAdapter(model_name="gemma4:e2b")
    review_input = ReviewInput(
        camera_image_b64="data:image/jpeg;base64,abc123",
        screen_image_b64="data:image/jpeg;base64,xyz456",
        include_screen_analysis=True,
    )

    captured_payload: dict[str, object] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        del timeout
        captured_payload.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "label": "distracted",
                            "confidence": 0.87,
                            "reasons": ["screen_off_task", "phone_visible"],
                            "note": "Screen appears off task.",
                        }
                    )
                }
            }
        )

    with patch("focus_catcher.adapters.request.urlopen", side_effect=fake_urlopen):
        result = adapter.review_live(
            review_input,
            config=SessionConfig(include_screen_analysis=True),
            recent_reviews=[],
            current_label="focused",
        )

    assert captured_payload["keep_alive"] == "10m"
    message = captured_payload["messages"][1]
    assert message["images"] == ["abc123", "xyz456"]
    assert result.model_name == "gemma4:e2b"
    assert result.label.value == "distracted"
    assert set(result.reasons) == {"screen_off_task", "phone_visible"}
