import pytest

from focus_catcher.models import SessionConfig


def test_session_config_rejects_slower_active_review_cadence() -> None:
    with pytest.raises(ValueError, match="active review cadence"):
        SessionConfig(
            focused_review_cadence_ms=1000,
            active_review_cadence_ms=1500,
        )
