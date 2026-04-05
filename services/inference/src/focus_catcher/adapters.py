from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from .models import GemmaDecision, ReviewEntry, ReviewInput, SessionConfig, SetupStatus

ALLOWED_REASONS = [
    "looking_away",
    "phone_visible",
    "screen_off_task",
    "stepped_away",
    "restless",
    "multitasking",
    "unclear",
]


class GemmaAdapter(Protocol):
    def check_setup(self) -> SetupStatus: ...

    def review_live(
        self,
        review_input: ReviewInput,
        config: SessionConfig,
        recent_reviews: list[ReviewEntry],
        current_label: str,
    ) -> GemmaDecision: ...

    def review_rescan(
        self,
        image_b64: str,
        config: SessionConfig,
        live_reviews: list[ReviewEntry],
    ) -> GemmaDecision: ...


@dataclass(slots=True)
class MockGemmaAdapter:
    model_name: str = "gemma4:e2b"

    def check_setup(self) -> SetupStatus:
        return SetupStatus(
            ready=True,
            model_name=self.model_name,
            mode="mock",
            message="Mock mode enabled for development.",
        )

    def review_live(
        self,
        review_input: ReviewInput,
        config: SessionConfig,
        recent_reviews: list[ReviewEntry],
        current_label: str,
    ) -> GemmaDecision:
        del config, recent_reviews, current_label
        if not review_input.camera_image_b64:
            raise ValueError("camera frame is required for live review")
        return GemmaDecision(
            label="focused",
            confidence=0.74,
            reasons=[],
            note="You look settled on the task right now.",
            model_name=self.model_name,
        )

    def review_rescan(
        self,
        image_b64: str,
        config: SessionConfig,
        live_reviews: list[ReviewEntry],
    ) -> GemmaDecision:
        del image_b64, config, live_reviews
        return GemmaDecision(
            label="focused",
            confidence=0.81,
            reasons=[],
            note="The saved frame still looks on task.",
            model_name=self.model_name,
        )


@dataclass(slots=True)
class OllamaGemmaAdapter:
    model_name: str = "gemma4:e2b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_sec: float = 45.0
    keep_alive: str = "10m"

    def check_setup(self) -> SetupStatus:
        try:
            response = request.urlopen(f"{self.base_url}/api/tags", timeout=5)
            payload = json.loads(response.read().decode("utf-8"))
        except error.URLError:
            return SetupStatus(
                ready=False,
                model_name=self.model_name,
                mode="ollama",
                message="Start Ollama first, then make sure gemma4:e2b is available locally.",
            )

        names = {model["name"] for model in payload.get("models", [])}
        if self.model_name not in names:
            return SetupStatus(
                ready=False,
                model_name=self.model_name,
                mode="ollama",
                message=f"Model {self.model_name} is missing. Run `ollama run {self.model_name}` first.",
            )

        return SetupStatus(
            ready=True,
            model_name=self.model_name,
            mode="ollama",
            message="Gemma is ready for local focus reviews.",
        )

    def review_live(
        self,
        review_input: ReviewInput,
        config: SessionConfig,
        recent_reviews: list[ReviewEntry],
        current_label: str,
    ) -> GemmaDecision:
        if not review_input.camera_image_b64:
            raise ValueError("camera frame is required for live review")

        history = self._history_excerpt(recent_reviews)
        user_prompt = (
            "Review these latest local focus images for one person at a laptop.\n"
            f"current_visible_label={current_label}\n"
            f"include_screen_analysis={config.include_screen_analysis and bool(review_input.screen_image_b64)}\n"
            f"recent_history={history}\n"
            "Classify only the person's focus state right now."
        )
        images = [self._strip_data_url(review_input.camera_image_b64)]
        if config.include_screen_analysis and review_input.screen_image_b64:
            images.append(self._strip_data_url(review_input.screen_image_b64))

        return self._call_ollama(
            prompt_type="live",
            user_prompt=user_prompt,
            images=images,
        )

    def review_rescan(
        self,
        image_b64: str,
        config: SessionConfig,
        live_reviews: list[ReviewEntry],
    ) -> GemmaDecision:
        history = self._history_excerpt(live_reviews)
        user_prompt = (
            "This is a slower second-pass rescan of a saved accountability-buddy keyframe.\n"
            f"include_screen_analysis={config.include_screen_analysis}\n"
            f"live_history={history}\n"
            "Be a bit more careful than the live pass, but still return only the immediate focus state in this frame."
        )
        return self._call_ollama(
            prompt_type="rescan",
            user_prompt=user_prompt,
            images=[self._strip_data_url(image_b64)],
        )

    def _call_ollama(self, prompt_type: str, user_prompt: str, images: list[str]) -> GemmaDecision:
        payload = {
            "model": self.model_name,
            "stream": False,
            "keep_alive": self.keep_alive,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a local focus accountability buddy. "
                        "Return JSON only with keys: label, confidence, reasons, note. "
                        "Allowed labels: focused, drifting, distracted, away. "
                        f"Allowed reasons: {', '.join(ALLOWED_REASONS)}. "
                        "The note must be one short plain-English sentence. "
                        "Use away only when the person appears to have stepped away or is absent. "
                        "Use distracted for clear off-task behavior. Use drifting for softer slippage."
                    ),
                },
                {
                    "role": "user",
                    "content": f"mode={prompt_type}\n{user_prompt}\nReturn JSON only.",
                    "images": images,
                },
            ],
        }

        response = request.urlopen(
            request.Request(
                url=f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=self.timeout_sec,
        )
        raw = json.loads(response.read().decode("utf-8"))
        content = raw["message"]["content"]
        parsed = self._extract_json(content)

        label = str(parsed.get("label", "focused")).strip().lower()
        if label not in {"focused", "drifting", "distracted", "away"}:
            raise ValueError(f"unexpected label from model: {label}")

        confidence = min(1.0, max(0.0, float(parsed.get("confidence", 0.7))))
        reasons = [
            reason
            for reason in parsed.get("reasons", [])
            if isinstance(reason, str) and reason in ALLOWED_REASONS
        ]
        note = str(parsed.get("note", "")).strip() or "I checked again and this looks steady."

        return GemmaDecision(
            label=label,
            confidence=confidence,
            reasons=reasons,
            note=note,
            model_name=self.model_name,
        )

    def _extract_json(self, content: str) -> dict[str, object]:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"model did not return JSON: {content!r}")
        return json.loads(content[start : end + 1])

    def _history_excerpt(self, reviews: list[ReviewEntry]) -> str:
        if not reviews:
            return "[]"
        excerpt = [
            {
                "label": review.label.value,
                "reasons": review.reasons,
                "note": review.note,
            }
            for review in reviews[-4:]
        ]
        return json.dumps(excerpt, separators=(",", ":"))

    def _strip_data_url(self, payload: str | None) -> str:
        if not payload:
            raise ValueError("image payload is required")
        if "," in payload and payload.startswith("data:"):
            return payload.split(",", 1)[1]
        return payload


def build_gemma_adapter() -> GemmaAdapter:
    mode = os.getenv("FOCUS_CATCHER_GEMMA_BACKEND", "ollama").strip().lower() or "ollama"
    model_name = os.getenv("FOCUS_CATCHER_GEMMA_MODEL", "gemma4:e2b").strip() or "gemma4:e2b"
    base_url = os.getenv("FOCUS_CATCHER_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    timeout_sec = float(os.getenv("FOCUS_CATCHER_OLLAMA_TIMEOUT_SEC", "45").strip() or "45")
    keep_alive = os.getenv("FOCUS_CATCHER_OLLAMA_KEEP_ALIVE", "10m").strip() or "10m"

    if mode == "mock":
        return MockGemmaAdapter(model_name=model_name)

    return OllamaGemmaAdapter(
        model_name=model_name,
        base_url=base_url,
        timeout_sec=timeout_sec,
        keep_alive=keep_alive,
    )
