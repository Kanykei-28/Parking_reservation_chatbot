from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from parking_chatbot.chatbot.reservation import Reservation
from parking_chatbot.chatbot.reservation_validation import (
    validate_car_number,
    validate_end_datetime,
    validate_first_name,
    validate_last_name,
    validate_parking_type,
    validate_start_datetime,
)


class ReservationSession:
    _STEPS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("first_name", "What is your first name?"),
        ("last_name", "What is your last name?"),
        ("car_number", "What is your car number?"),
        ("parking_type", "What parking type would you like: standard, covered, or EV?"),
        (
            "start_datetime",
            "What is the reservation start date and time? "
            "For example, 2026-08-02 08:00 or August 2, 2026 8:00 AM.",
        ),
        (
            "end_datetime",
            "What is the reservation end date and time? "
            "For example, 2026-08-02 09:00 or August 2, 2026 9:00 AM.",
        ),
    )

    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.reservation = Reservation()
        self._current_step = 0
        self._now = now or datetime.now

    def current_prompt(self) -> str | None:
        if self.is_complete:
            return None
        return self._STEPS[self._current_step][1]

    def accept_answer(self, answer: str) -> None:
        if self.is_complete:
            raise RuntimeError("reservation session is already complete")

        field_name = self._STEPS[self._current_step][0]
        normalized_answer = self._validate_answer(field_name, answer)
        setattr(self.reservation, field_name, normalized_answer)
        self._current_step += 1

    @property
    def is_complete(self) -> bool:
        return self._current_step == len(self._STEPS)

    def completed_reservation(self) -> Reservation:
        if not self.is_complete:
            raise RuntimeError("reservation session is not complete")
        return self.reservation

    def _validate_answer(self, field_name: str, answer: str) -> str:
        if field_name == "first_name":
            return validate_first_name(answer)
        if field_name == "last_name":
            return validate_last_name(answer)
        if field_name == "car_number":
            return validate_car_number(answer)
        if field_name == "parking_type":
            return validate_parking_type(answer)
        if field_name == "start_datetime":
            return validate_start_datetime(answer, self._now())
        if field_name == "end_datetime":
            start_datetime = self.reservation.start_datetime
            if start_datetime is None:
                raise RuntimeError("reservation start is missing")
            return validate_end_datetime(answer, start_datetime)
        raise RuntimeError(f"unknown reservation field: {field_name}")
