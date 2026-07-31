from parking_chatbot.chatbot import Reservation


def test_reservation_defaults_all_fields_to_none() -> None:
    reservation = Reservation()

    assert reservation.first_name is None
    assert reservation.last_name is None
    assert reservation.car_number is None
    assert reservation.parking_type is None
    assert reservation.start_datetime is None
    assert reservation.end_datetime is None


def test_reservation_assigns_provided_values() -> None:
    reservation = Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-01T09:00:00",
        end_datetime="2026-08-01T17:00:00",
    )

    assert reservation.first_name == "Ada"
    assert reservation.last_name == "Lovelace"
    assert reservation.car_number == "ABC-123"
    assert reservation.parking_type == "covered"
    assert reservation.start_datetime == "2026-08-01T09:00:00"
    assert reservation.end_datetime == "2026-08-01T17:00:00"
