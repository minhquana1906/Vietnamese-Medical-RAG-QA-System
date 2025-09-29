import pytest
from pydantic import ValidationError


def test_complete_request_basic():
    from backend.src.schema import CompleteRequest

    request = CompleteRequest(user_message="Hello doctor")

    assert request.user_message == "Hello doctor"
    assert request.bot_id == "Meddy"
    assert request.user_id == "user_1"
    assert request.is_sync_request is False


def test_complete_request_full():
    from backend.src.schema import CompleteRequest

    data = {
        "bot_id": "custom_bot",
        "user_id": "doctor_1",
        "user_message": "What is the treatment for hypertension?",
        "is_sync_request": True,
        "metadata": {"source": "web_app"},
    }

    request = CompleteRequest(**data)

    assert request.bot_id == "custom_bot"
    assert request.user_id == "doctor_1"
    assert request.user_message == "What is the treatment for hypertension?"
    assert request.is_sync_request is True
    assert request.metadata == {"source": "web_app"}


def test_complete_request_missing_user_message():
    from backend.src.schema import CompleteRequest

    with pytest.raises(ValidationError) as exc_info:
        CompleteRequest(bot_id="test")

    errors = exc_info.value.errors()
    assert any("user_message" in str(error["loc"]) for error in errors)
