from datetime import datetime

import pytest

from parking_chatbot.chatbot import (
    Reservation,
    ReservationSession,
    ReservationValidationError,
)


def fixed_now() -> datetime:
    return datetime(2026, 7, 30, 12, 0)


def test_session_collects_reservation_fields_in_order() -> None:
    session = ReservationSession(now=fixed_now)
    steps = [
        ("What is your first name?", "Ada", "first_name", "Ada"),
        ("What is your last name?", "Lovelace", "last_name", "Lovelace"),
        ("What is your car number?", "ABC-123", "car_number", "ABC-123"),
        (
            "What parking type would you like: standard, covered, or EV?",
            "covered",
            "parking_type",
            "covered",
        ),
        (
            "What is the reservation start date and time? "
            "For example, 2026-08-02 08:00 or August 2, 2026 8:00 AM.",
            "2026-08-01T09:00:00",
            "start_datetime",
            "2026-08-01T09:00",
        ),
        (
            "What is the reservation end date and time? "
            "For example, 2026-08-02 09:00 or August 2, 2026 9:00 AM.",
            "2026-08-01T17:00:00",
            "end_datetime",
            "2026-08-01T17:00",
        ),
    ]

    for prompt, answer, field_name, expected_value in steps:
        assert session.current_prompt() == prompt
        assert not session.is_complete

        session.accept_answer(answer)

        assert getattr(session.reservation, field_name) == expected_value

    assert session.is_complete
    assert session.current_prompt() is None


def test_completed_reservation_returns_collected_reservation() -> None:
    session = ReservationSession(now=fixed_now)
    answers = (
        "Ada",
        "Lovelace",
        "ABC-123",
        "covered",
        "2026-08-01T09:00:00",
        "2026-08-01T17:00:00",
    )

    for answer in answers:
        session.accept_answer(answer)

    assert session.completed_reservation() is session.reservation
    assert session.completed_reservation() == Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-01T09:00",
        end_datetime="2026-08-01T17:00",
    )


def test_completed_reservation_rejects_incomplete_session() -> None:
    session = ReservationSession(now=fixed_now)

    with pytest.raises(RuntimeError, match="reservation session is not complete"):
        session.completed_reservation()


def test_session_rejects_answers_after_completion() -> None:
    session = ReservationSession(now=fixed_now)

    for answer in (
        "Ada",
        "Lovelace",
        "ABC-123",
        "covered",
        "2026-08-01T09:00",
        "2026-08-01T17:00",
    ):
        session.accept_answer(answer)

    with pytest.raises(
        RuntimeError,
        match="reservation session is already complete",
    ):
        session.accept_answer("extra answer")


def test_invalid_answer_keeps_current_prompt() -> None:
    session = ReservationSession(now=fixed_now)

    with pytest.raises(ReservationValidationError, match="must not be empty"):
        session.accept_answer("")

    assert session.reservation.first_name is None
    assert session.current_prompt() == "What is your first name?"
