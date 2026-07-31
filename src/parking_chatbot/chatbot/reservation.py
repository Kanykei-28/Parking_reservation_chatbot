from dataclasses import dataclass


@dataclass
class Reservation:
    first_name: str | None = None
    last_name: str | None = None
    car_number: str | None = None
    parking_type: str | None = None
    start_datetime: str | None = None
    end_datetime: str | None = None
