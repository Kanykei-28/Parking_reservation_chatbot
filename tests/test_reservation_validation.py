from datetime import datetime

import pytest

from parking_chatbot.chatbot.reservation_validation import (
    ReservationValidationError,
    parse_reservation_datetime,
    validate_car_number,
    validate_end_datetime,
    validate_first_name,
    validate_last_name,
    validate_parking_type,
    validate_start_datetime,
)

NOW = datetime(2026, 8, 1, 8, 0)


@pytest.mark.parametrize(
    "validator",
    [validate_first_name, validate_last_name, validate_car_number],
)
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_required_text_rejects_whitespace(
    validator: object,
    value: str,
) -> None:
    with pytest.raises(ReservationValidationError, match="must not be empty"):
        validator(value)  # type: ignore[operator]


def test_names_and_car_number_are_trimmed() -> None:
    assert validate_first_name("  Ada ") == "Ada"
    assert validate_last_name(" Lovelace  ") == "Lovelace"
    assert validate_car_number(" ABC-123 ") == "ABC-123"


@pytest.mark.parametrize("value", ["standard", "COVERED", " Ev "])
def test_parking_type_is_normalized(value: str) -> None:
    assert validate_parking_type(value) == value.strip().lower()


def test_invalid_parking_type_is_rejected() -> None:
    with pytest.raises(
        ReservationValidationError,
        match="must be standard, covered, or ev",
    ):
        validate_parking_type("premium")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-02 08:00", datetime(2026, 8, 2, 8, 0)),
        ("2026-08-02T08:00", datetime(2026, 8, 2, 8, 0)),
        ("August 2, 2026 8:00 AM", datetime(2026, 8, 2, 8, 0)),
        ("August 2 2026 8am", datetime(2026, 8, 2, 8, 0)),
        ("2 August 2026 08:00", datetime(2026, 8, 2, 8, 0)),
    ],
)
def test_datetime_formats_are_accepted(value: str, expected: datetime) -> None:
    assert parse_reservation_datetime(value) == expected


@pytest.mark.parametrize(
    "value",
    ["not-a-date", "2026-08-01", "2026-13-01 09:00"],
)
def test_malformed_datetime_is_rejected(value: str) -> None:
    with pytest.raises(ReservationValidationError, match="absolute date and time"):
        parse_reservation_datetime(value)


@pytest.mark.parametrize(
    "value",
    ["tomorrow at 8am", "next Monday", "in two hours"],
)
def test_relative_datetime_is_rejected(value: str) -> None:
    with pytest.raises(ReservationValidationError, match="absolute date and time"):
        parse_reservation_datetime(value)


def test_ambiguous_numeric_datetime_is_rejected() -> None:
    with pytest.raises(ReservationValidationError, match="absolute date and time"):
        parse_reservation_datetime("02/08/2026 08:00")


@pytest.mark.parametrize(
    "value",
    ["2026-08-02T08:00+06:00", "2026-08-02T02:00Z"],
)
def test_timezone_aware_datetime_is_rejected(value: str) -> None:
    with pytest.raises(ReservationValidationError, match="without a timezone"):
        parse_reservation_datetime(value)


def test_start_datetime_is_normalized() -> None:
    assert validate_start_datetime("2026-08-01 09:00", NOW) == ("2026-08-01T09:00")


@pytest.mark.parametrize(
    "value",
    [
        "August 2, 2026 8:00 AM",
        "August 2 2026 8am",
        "2 August 2026 08:00",
    ],
)
def test_human_readable_start_datetime_is_normalized(value: str) -> None:
    assert validate_start_datetime(value, NOW) == "2026-08-02T08:00"


def test_past_start_is_rejected() -> None:
    with pytest.raises(
        ReservationValidationError,
        match="must not be in the past",
    ):
        validate_start_datetime("2026-08-01 07:59", NOW)


def test_start_more_than_five_days_ahead_is_rejected() -> None:
    with pytest.raises(
        ReservationValidationError,
        match="no more than 5 days",
    ):
        validate_start_datetime("2026-08-06 08:01", NOW)


@pytest.mark.parametrize(
    ("end", "message"),
    [
        ("2026-08-01 06:00", "must be after"),
        ("2026-08-01 06:30", "at least 1 hour"),
        ("2026-08-01 21:01", "must not exceed 15 hours"),
    ],
)
def test_invalid_reservation_durations(end: str, message: str) -> None:
    with pytest.raises(ReservationValidationError, match=message):
        validate_end_datetime(end, "2026-08-01T06:00")


def test_exactly_fifteen_hour_reservation_is_accepted() -> None:
    assert (
        validate_end_datetime(
            "2026-08-01 21:00",
            "2026-08-01T06:00",
        )
        == "2026-08-01T21:00"
    )


@pytest.mark.parametrize(
    ("validator", "value", "message"),
    [
        (validate_start_datetime, "2026-08-01 05:59", "Start time"),
        (validate_start_datetime, "2026-08-01 23:01", "Start time"),
    ],
)
def test_start_outside_opening_hours_is_rejected(
    validator: object,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ReservationValidationError, match=message):
        validator(value, NOW)  # type: ignore[operator]


@pytest.mark.parametrize(
    "value",
    ["2026-08-01 05:59", "2026-08-01 23:01"],
)
def test_end_outside_opening_hours_is_rejected(value: str) -> None:
    with pytest.raises(ReservationValidationError, match="End time"):
        validate_end_datetime(value, "2026-08-01T08:00")
