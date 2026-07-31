from datetime import datetime
from unittest.mock import MagicMock

import pytest

from parking_chatbot.chatbot import ParkingChatbot, chatbot
from parking_chatbot.chatbot.intents import Intent


def fixed_now() -> datetime:
    return datetime(2026, 7, 30, 12, 0)


@pytest.fixture
def mocked_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock]:
    detect_intent = MagicMock()
    answer_question = MagicMock()
    monkeypatch.setattr(chatbot, "detect_intent", detect_intent)
    monkeypatch.setattr(chatbot, "answer_question", answer_question)
    monkeypatch.setattr(chatbot, "_chatbot", ParkingChatbot())
    return detect_intent, answer_question


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (
            Intent.GREETING,
            "Hello! How can I help you with your parking today?",
        ),
        (
            Intent.RESERVATION,
            "What is your first name?",
        ),
        (
            Intent.UNKNOWN,
            "I'm only able to answer questions related to the parking "
            "reservation service.",
        ),
    ],
)
def test_non_information_intents_do_not_use_rag(
    intent: Intent,
    expected: str,
    mocked_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    detect_intent, answer_question = mocked_dependencies
    detect_intent.return_value = intent

    assert chatbot.chat("test message") == expected
    detect_intent.assert_called_once_with("test message")
    answer_question.assert_not_called()


def test_information_intent_uses_rag_pipeline(
    mocked_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    detect_intent, answer_question = mocked_dependencies
    detect_intent.return_value = Intent.INFORMATION
    answer_question.return_value = "Parking is open daily."

    result = chatbot.chat("What are the parking hours?")

    assert result == "Parking is open daily."
    answer_question.assert_called_once_with("What are the parking hours?")


def test_reservation_collection_advances_through_each_prompt() -> None:
    parking_chatbot = ParkingChatbot(now=fixed_now)

    assert parking_chatbot.chat("I want to reserve parking") == (
        "What is your first name?"
    )
    assert parking_chatbot.chat("Ada") == "What is your last name?"
    assert parking_chatbot.chat("Lovelace") == "What is your car number?"
    assert parking_chatbot.chat("ABC-123") == (
        "What parking type would you like: standard, covered, or EV?"
    )
    assert parking_chatbot.chat("covered") == (
        "What is the reservation start date and time? "
        "For example, 2026-08-02 08:00 or August 2, 2026 8:00 AM."
    )
    assert parking_chatbot.chat("2026-08-01T09:00:00") == (
        "What is the reservation end date and time? "
        "For example, 2026-08-02 09:00 or August 2, 2026 9:00 AM."
    )

    confirmation = parking_chatbot.chat("2026-08-01T17:00:00")

    assert "Ada Lovelace" in confirmation
    assert "ABC-123" in confirmation
    assert "covered" in confirmation
    assert "2026-08-01T09:00" in confirmation
    assert "2026-08-01T17:00" in confirmation
    assert "Administrator approval is still required" in confirmation


def test_completed_reservation_becomes_pending_and_clears_session() -> None:
    parking_chatbot = ParkingChatbot(now=fixed_now)
    parking_chatbot.chat("Book parking")

    for answer in (
        "Ada",
        "Lovelace",
        "ABC-123",
        "covered",
        "2026-08-01T09:00:00",
        "2026-08-01T17:00:00",
    ):
        parking_chatbot.chat(answer)

    assert parking_chatbot.active_session is None
    assert parking_chatbot.pending_reservation is not None
    assert parking_chatbot.pending_reservation.first_name == "Ada"
    assert parking_chatbot.pending_reservation.last_name == "Lovelace"
    assert parking_chatbot.pending_reservation.car_number == "ABC-123"
    assert parking_chatbot.pending_reservation.parking_type == "covered"
    assert parking_chatbot.pending_reservation.start_datetime == "2026-08-01T09:00"
    assert parking_chatbot.pending_reservation.end_datetime == "2026-08-01T17:00"


def test_separate_chatbot_instances_do_not_share_reservation_state() -> None:
    first_chatbot = ParkingChatbot()
    second_chatbot = ParkingChatbot()

    first_chatbot.chat("Reserve a parking space")
    first_chatbot.chat("Ada")

    assert first_chatbot.active_session is not None
    assert first_chatbot.active_session.reservation.first_name == "Ada"
    assert second_chatbot.active_session is None
    assert second_chatbot.pending_reservation is None
    assert second_chatbot.chat("hello") == (
        "Hello! How can I help you with your parking today?"
    )


@pytest.mark.parametrize("message", ["", "   ", "\t\n"])
def test_parking_chatbot_rejects_empty_messages(message: str) -> None:
    parking_chatbot = ParkingChatbot()

    with pytest.raises(ValueError, match="^message must not be empty$"):
        parking_chatbot.chat(message)


def test_empty_message_does_not_advance_active_session() -> None:
    parking_chatbot = ParkingChatbot()
    parking_chatbot.chat("Reserve parking")

    assert parking_chatbot.chat(" ") == (
        "First name must not be empty.\nWhat is your first name?"
    )

    assert parking_chatbot.active_session is not None
    assert parking_chatbot.active_session.reservation.first_name is None
    assert parking_chatbot.active_session.current_prompt() == (
        "What is your first name?"
    )


def test_validation_error_keeps_active_reservation_prompt() -> None:
    parking_chatbot = ParkingChatbot(now=fixed_now)
    parking_chatbot.chat("Reserve parking")

    response = parking_chatbot.chat("   ")

    assert response == ("First name must not be empty.\nWhat is your first name?")
    assert parking_chatbot.active_session is not None
    assert parking_chatbot.active_session.current_prompt() == (
        "What is your first name?"
    )


def test_validated_reservation_collection_normalizes_values() -> None:
    parking_chatbot = ParkingChatbot(now=fixed_now)
    messages = (
        "Reserve parking",
        "  Ada  ",
        "  Lovelace ",
        " ABC-123 ",
        " CoVeReD ",
        "2026-08-01 09:00",
        "2026-08-01 17:00",
    )

    responses = [parking_chatbot.chat(message) for message in messages]

    assert responses[-1].endswith("Administrator approval is still required.")
    assert parking_chatbot.pending_reservation is not None
    assert parking_chatbot.pending_reservation.first_name == "Ada"
    assert parking_chatbot.pending_reservation.last_name == "Lovelace"
    assert parking_chatbot.pending_reservation.car_number == "ABC-123"
    assert parking_chatbot.pending_reservation.parking_type == "covered"
    assert parking_chatbot.pending_reservation.start_datetime == "2026-08-01T09:00"
    assert parking_chatbot.pending_reservation.end_datetime == "2026-08-01T17:00"
