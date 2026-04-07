from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from .models import (
    GemmaDecision,
    ReviewEntry,
    ReviewInput,
    RuntimeProfile,
    SessionConfig,
    SetupStatus,
)

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
    def check_setup(self, runtime_profile: RuntimeProfile | None = None) -> SetupStatus: ...

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
    higher_accuracy_model_name: str = "gemma4:e4b"
    default_runtime_profile: RuntimeProfile = RuntimeProfile.STANDARD

    def check_setup(self, runtime_profile: RuntimeProfile | None = None) -> SetupStatus:
        selected_profile = runtime_profile or self.default_runtime_profile
        return SetupStatus(
            ready=True,
            model_name=self._model_for_profile(selected_profile),
            runtime_profile=selected_profile,
            available_runtime_profiles=[
                RuntimeProfile.STANDARD,
                RuntimeProfile.HIGHER_ACCURACY,
            ],
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
        del recent_reviews, current_label
        if not review_input.camera_image_b64:
            raise ValueError("camera frame is required for live review")
        return GemmaDecision(
            label="focused",
            confidence=0.74,
            reasons=[],
            note="You look settled on the task right now.",
            model_name=self._model_for_profile(config.runtime_profile),
        )

    def review_rescan(
        self,
        image_b64: str,
        config: SessionConfig,
        live_reviews: list[ReviewEntry],
    ) -> GemmaDecision:
        del image_b64, live_reviews
        return GemmaDecision(
            label="focused",
            confidence=0.81,
            reasons=[],
            note="The saved frame still looks on task.",
            model_name=self._model_for_profile(config.runtime_profile),
        )

    def _model_for_profile(self, runtime_profile: RuntimeProfile) -> str:
        if runtime_profile == RuntimeProfile.HIGHER_ACCURACY:
            return self.higher_accuracy_model_name
        return self.model_name


@dataclass(slots=True)
class OllamaGemmaAdapter:
    model_name: str = "gemma4:e2b"
    higher_accuracy_model_name: str = "gemma4:e4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_sec: float = 45.0
    keep_alive: str = "10m"
    default_runtime_profile: RuntimeProfile = RuntimeProfile.STANDARD

    def check_setup(self, runtime_profile: RuntimeProfile | None = None) -> SetupStatus:
        selected_profile = runtime_profile or self.default_runtime_profile
        try:
            response = request.urlopen(f"{self.base_url}/api/tags", timeout=5)
            payload = json.loads(response.read().decode("utf-8"))
        except error.URLError:
            return SetupStatus(
                ready=False,
                model_name=self._model_for_profile(selected_profile),
                runtime_profile=selected_profile,
                mode="ollama",
                message="Start Ollama first, then make sure the required Gemma model is available locally.",
            )

        names = {model["name"] for model in payload.get("models", [])}
        available_profiles = [
            profile
            for profile in RuntimeProfile
            if self._model_for_profile(profile) in names
        ]
        required_model = self._model_for_profile(selected_profile)
        if required_model not in names:
            if selected_profile == RuntimeProfile.HIGHER_ACCURACY:
                message = (
                    f"Higher-accuracy mode is unavailable. Run `ollama run {required_model}` first."
                )
            else:
                message = f"Model {required_model} is missing. Run `ollama run {required_model}` first."
            return SetupStatus(
                ready=False,
                model_name=required_model,
                runtime_profile=selected_profile,
                available_runtime_profiles=available_profiles,
                mode="ollama",
                message=message,
            )

        message = "Gemma is ready for local focus reviews."
        if (
            selected_profile == RuntimeProfile.STANDARD
            and RuntimeProfile.HIGHER_ACCURACY in available_profiles
        ):
            message = "Gemma is ready for local focus reviews. Higher accuracy is also available."
        if selected_profile == RuntimeProfile.HIGHER_ACCURACY:
            message = "Higher-accuracy Gemma reviews are ready locally."

        return SetupStatus(
            ready=True,
            model_name=required_model,
            runtime_profile=selected_profile,
            available_runtime_profiles=available_profiles,
            mode="ollama",
            message=message,
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
            model_name=self._model_for_profile(config.runtime_profile),
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
            model_name=self._model_for_profile(config.runtime_profile),
            prompt_type="rescan",
            user_prompt=user_prompt,
            images=[self._strip_data_url(image_b64)],
        )

    def _call_ollama(
        self,
        model_name: str,
        prompt_type: str,
        user_prompt: str,
        images: list[str],
    ) -> GemmaDecision:
        payload = {
            "model": model_name,
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
            model_name=model_name,
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

    def _model_for_profile(self, runtime_profile: RuntimeProfile) -> str:
        if runtime_profile == RuntimeProfile.HIGHER_ACCURACY:
            return self.higher_accuracy_model_name
        return self.model_name


def build_gemma_adapter() -> GemmaAdapter:
    mode = os.getenv("FOCUS_CATCHER_GEMMA_BACKEND", "ollama").strip().lower() or "ollama"
    model_name = os.getenv("FOCUS_CATCHER_GEMMA_MODEL", "gemma4:e2b").strip() or "gemma4:e2b"
    higher_accuracy_model_name = (
        os.getenv("FOCUS_CATCHER_GEMMA_HIGHER_ACCURACY_MODEL", "gemma4:e4b").strip()
        or "gemma4:e4b"
    )
    runtime_profile_raw = (
        os.getenv("FOCUS_CATCHER_DEFAULT_RUNTIME_PROFILE", RuntimeProfile.STANDARD.value).strip().lower()
        or RuntimeProfile.STANDARD.value
    )
    base_url = os.getenv("FOCUS_CATCHER_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    timeout_sec = float(os.getenv("FOCUS_CATCHER_OLLAMA_TIMEOUT_SEC", "45").strip() or "45")
    keep_alive = os.getenv("FOCUS_CATCHER_OLLAMA_KEEP_ALIVE", "10m").strip() or "10m"
    try:
        default_runtime_profile = RuntimeProfile(runtime_profile_raw)
    except ValueError:
        default_runtime_profile = RuntimeProfile.STANDARD

    if mode == "mock":
        return MockGemmaAdapter(
            model_name=model_name,
            higher_accuracy_model_name=higher_accuracy_model_name,
            default_runtime_profile=default_runtime_profile,
        )

    return OllamaGemmaAdapter(
        model_name=model_name,
        higher_accuracy_model_name=higher_accuracy_model_name,
        base_url=base_url,
        timeout_sec=timeout_sec,
        keep_alive=keep_alive,
        default_runtime_profile=default_runtime_profile,
    )
