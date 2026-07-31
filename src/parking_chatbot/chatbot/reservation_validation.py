from datetime import datetime, time, timedelta

_HUMAN_READABLE_DATETIME_FORMATS = (
    "%B %d, %Y %I:%M %p",
    "%B %d %Y %I%p",
    "%d %B %Y %H:%M",
)
_DATETIME_ERROR_MESSAGE = (
    "Enter an absolute date and time, for example 2026-08-02 08:00."
)


class ReservationValidationError(ValueError):
    pass


def validate_first_name(value: str) -> str:
    return _validate_required_text(value, "First name")


def validate_last_name(value: str) -> str:
    return _validate_required_text(value, "Last name")


def validate_car_number(value: str) -> str:
    return _validate_required_text(value, "Car number")


def validate_parking_type(value: str) -> str:
    normalized_value = value.strip().lower()
    if normalized_value not in {"standard", "covered", "ev"}:
        raise ReservationValidationError(
            "Parking type must be standard, covered, or ev."
        )
    return normalized_value


def parse_reservation_datetime(value: str) -> datetime:
    normalized_value = value.strip()
    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError:
        parsed_value = _parse_human_readable_datetime(normalized_value)
    else:
        if "T" not in normalized_value and " " not in normalized_value:
            raise ReservationValidationError(_DATETIME_ERROR_MESSAGE)

    if parsed_value.tzinfo is not None:
        raise ReservationValidationError("Enter the date and time without a timezone.")
    return parsed_value.replace(second=0, microsecond=0)


def _parse_human_readable_datetime(value: str) -> datetime:
    for datetime_format in _HUMAN_READABLE_DATETIME_FORMATS:
        try:
            return datetime.strptime(value, datetime_format)
        except ValueError:
            continue
    raise ReservationValidationError(_DATETIME_ERROR_MESSAGE)


def validate_start_datetime(value: str, current_datetime: datetime) -> str:
    start_datetime = parse_reservation_datetime(value)
    normalized_current_datetime = current_datetime.replace(
        second=0,
        microsecond=0,
    )

    _validate_parking_hours(start_datetime, "Start")
    if start_datetime < normalized_current_datetime:
        raise ReservationValidationError("Reservation start must not be in the past.")
    if start_datetime > normalized_current_datetime + timedelta(days=5):
        raise ReservationValidationError(
            "Reservation start must be no more than 5 days ahead."
        )
    return start_datetime.isoformat(timespec="minutes")


def validate_end_datetime(value: str, start_value: str) -> str:
    start_datetime = parse_reservation_datetime(start_value)
    end_datetime = parse_reservation_datetime(value)

    _validate_parking_hours(end_datetime, "End")
    duration = end_datetime - start_datetime
    if duration <= timedelta(0):
        raise ReservationValidationError("Reservation end must be after the start.")
    if duration < timedelta(hours=1):
        raise ReservationValidationError(
            "Reservation duration must be at least 1 hour."
        )
    if duration > timedelta(hours=15):
        raise ReservationValidationError(
            "Reservation duration must not exceed 15 hours."
        )
    return end_datetime.isoformat(timespec="minutes")


def _validate_required_text(value: str, label: str) -> str:
    normalized_value = value.strip()
    if not normalized_value:
        raise ReservationValidationError(f"{label} must not be empty.")
    return normalized_value


def _validate_parking_hours(value: datetime, label: str) -> None:
    if not time(6, 0) <= value.time() <= time(23, 0):
        raise ReservationValidationError(
            f"{label} time must be within parking hours, 06:00–23:00."
        )
