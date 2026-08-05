from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationConflictError,
    ConfirmedReservationFileRepository,
    ConfirmedReservationStorageError,
    ConfirmedReservationValidationError,
)

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")


def confirmed_reservation(
    *,
    request_id: UUID = REQUEST_ID,
    car_number: str = "ABC-123",
    approval_time: datetime | None = None,
) -> ConfirmedReservation:
    return ConfirmedReservation(
        approval_request_id=request_id,
        first_name=" Ada ",
        last_name=" Lovelace ",
        car_number=car_number,
        start_datetime=" 2026-08-05T09:00 ",
        end_datetime=" 2026-08-05T17:00 ",
        approval_time=approval_time or datetime(2026, 8, 4, 10, 30, tzinfo=UTC),
    )


def test_model_formats_exact_single_line() -> None:
    reservation = confirmed_reservation()

    assert reservation.to_file_line() == (
        "Ada Lovelace | ABC-123 | 2026-08-05T09:00–2026-08-05T17:00 | "
        "2026-08-04T10:30:00+00:00\n"
    )
    assert not reservation.to_file_line().endswith("\n\n")


def test_model_normalizes_approval_time_to_utc() -> None:
    approval_time = datetime(
        2026,
        8,
        4,
        16,
        30,
        tzinfo=timezone(timedelta(hours=6)),
    )

    reservation = confirmed_reservation(approval_time=approval_time)

    assert reservation.to_file_line().endswith("2026-08-04T10:30:00+00:00\n")


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("first_name", "Ada\nInjected"),
        ("last_name", "Love\rlace"),
        ("car_number", "ABC|123"),
        ("start_datetime", "2026-08-05|09:00"),
        ("end_datetime", "\n"),
    ],
)
def test_model_rejects_empty_or_format_corrupting_text(
    field_name: str,
    value: str,
) -> None:
    values = {
        "approval_request_id": REQUEST_ID,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "car_number": "ABC-123",
        "start_datetime": "2026-08-05T09:00",
        "end_datetime": "2026-08-05T17:00",
        "approval_time": datetime(2026, 8, 4, 10, 30, tzinfo=UTC),
    }
    values[field_name] = value

    with pytest.raises(ConfirmedReservationValidationError):
        ConfirmedReservation(**values)  # type: ignore[arg-type]


def test_model_rejects_naive_approval_time() -> None:
    with pytest.raises(
        ConfirmedReservationValidationError,
        match="approval_time must be timezone-aware",
    ):
        confirmed_reservation(approval_time=datetime(2026, 8, 4, 10, 30))


def test_repository_creates_parent_and_appends_records(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    first = confirmed_reservation()
    second = confirmed_reservation(
        request_id=UUID("87654321-4321-8765-4321-876543218765"),
        car_number="XYZ-789",
    )

    assert repository.append(first)
    assert repository.append(second)

    assert output_path.read_text(encoding="utf-8") == (
        first.to_file_line() + second.to_file_line()
    )


def test_repository_makes_identical_duplicate_idempotent(tmp_path: Path) -> None:
    output_path = tmp_path / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    reservation = confirmed_reservation()

    assert repository.append(reservation)
    assert not repository.append(reservation)
    assert output_path.read_text(encoding="utf-8") == reservation.to_file_line()


def test_repository_detects_duplicate_conflict_across_instances(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "confirmed.txt"
    ConfirmedReservationFileRepository(output_path).append(confirmed_reservation())
    second_repository = ConfirmedReservationFileRepository(output_path)

    with pytest.raises(
        ConfirmedReservationConflictError,
        match="already has different data",
    ):
        second_repository.append(confirmed_reservation(car_number="DIFFERENT"))

    assert (
        output_path.read_text(encoding="utf-8")
        == confirmed_reservation().to_file_line()
    )


def test_repository_recovers_from_index_update_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "private-location" / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    reservation = confirmed_reservation()

    with monkeypatch.context() as patch:
        patch.setattr(
            repository,
            "_write_index_atomically",
            lambda _index: (_ for _ in ()).throw(OSError(str(output_path))),
        )
        with pytest.raises(
            ConfirmedReservationStorageError,
            match="^could not store confirmed reservation$",
        ) as caught:
            repository.append(reservation)

    assert str(tmp_path) not in str(caught.value)
    assert not output_path.exists()
    assert repository.append(reservation)
    assert output_path.read_text(encoding="utf-8") == reservation.to_file_line()


def test_repository_recovers_from_append_failure_without_duplicate_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "private-location" / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    reservation = confirmed_reservation()

    with monkeypatch.context() as patch:
        patch.setattr(
            repository,
            "_append_line",
            lambda _line: (_ for _ in ()).throw(OSError(str(output_path))),
        )
        with pytest.raises(
            ConfirmedReservationStorageError,
            match="^could not store confirmed reservation$",
        ) as caught:
            repository.append(reservation)

    assert str(tmp_path) not in str(caught.value)
    assert repository.append(reservation)
    assert output_path.read_text(encoding="utf-8") == reservation.to_file_line()
