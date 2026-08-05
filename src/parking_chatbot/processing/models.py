from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


class ConfirmedReservationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConfirmedReservation:
    approval_request_id: UUID
    first_name: str
    last_name: str
    car_number: str
    start_datetime: str
    end_datetime: str
    approval_time: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "first_name",
            "last_name",
            "car_number",
            "start_datetime",
            "end_datetime",
        ):
            value = getattr(self, field_name)
            normalized_value = self._validate_text(value, field_name)
            object.__setattr__(self, field_name, normalized_value)

        if self.approval_time.tzinfo is None or self.approval_time.utcoffset() is None:
            raise ConfirmedReservationValidationError(
                "approval_time must be timezone-aware"
            )

    def to_file_line(self) -> str:
        approval_time = self.approval_time.astimezone(UTC).isoformat()
        return (
            f"{self.first_name} {self.last_name} | {self.car_number} | "
            f"{self.start_datetime}–{self.end_datetime} | {approval_time}\n"
        )

    @staticmethod
    def _validate_text(value: str, field_name: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ConfirmedReservationValidationError(f"{field_name} must not be empty")
        if any(character in normalized_value for character in ("\n", "\r", "|")):
            raise ConfirmedReservationValidationError(
                f"{field_name} must not contain newline, carriage-return, or pipe"
            )
        return normalized_value
