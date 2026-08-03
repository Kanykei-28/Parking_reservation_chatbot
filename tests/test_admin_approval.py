from datetime import UTC, datetime
from uuid import uuid4

import pytest

from parking_chatbot.admin import (
    ApprovalAlreadyDecidedError,
    ApprovalRequest,
    ApprovalRequestNotFoundError,
    ApprovalStatus,
    InMemoryApprovalRequestRepository,
)
from parking_chatbot.chatbot import Reservation


@pytest.fixture
def reservation() -> Reservation:
    return Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-04T09:00",
        end_datetime="2026-08-04T17:00",
    )


def test_new_request_defaults_to_pending(reservation: Reservation) -> None:
    request = ApprovalRequest(reservation)

    assert request.status is ApprovalStatus.PENDING
    assert request.decision_at is None
    assert request.administrator_comment is None
    assert request.created_at.tzinfo is not None
    assert request.created_at.utcoffset() is not None


def test_automatically_generated_request_ids_are_unique(
    reservation: Reservation,
) -> None:
    first_request = ApprovalRequest(reservation)
    second_request = ApprovalRequest(reservation)

    assert first_request.request_id != second_request.request_id


def test_reservation_data_is_preserved(reservation: Reservation) -> None:
    request = ApprovalRequest(reservation)

    assert request.reservation is reservation
    assert request.reservation == reservation


def test_repository_retrieves_request_by_id(reservation: Reservation) -> None:
    repository = InMemoryApprovalRequestRepository()
    request = repository.create(reservation)

    assert repository.get(request.request_id) is request


def test_repository_lists_requests(reservation: Reservation) -> None:
    repository = InMemoryApprovalRequestRepository()
    first_request = repository.create(reservation)
    second_request = repository.create(reservation)

    assert repository.list() == [first_request, second_request]


def test_repository_can_store_existing_request(reservation: Reservation) -> None:
    repository = InMemoryApprovalRequestRepository()
    request = ApprovalRequest(reservation)

    repository.add(request)

    assert repository.get(request.request_id) is request


def test_approving_request_records_comment_and_decision_timestamp(
    reservation: Reservation,
) -> None:
    decided_at = datetime(2026, 8, 3, 10, 30, tzinfo=UTC)
    repository = InMemoryApprovalRequestRepository(now=lambda: decided_at)
    request = repository.create(reservation)

    result = repository.approve(request.request_id, "Space is available")

    assert result is request
    assert request.status is ApprovalStatus.APPROVED
    assert request.administrator_comment == "Space is available"
    assert request.decision_at == decided_at


def test_rejecting_request_records_comment_and_decision_timestamp(
    reservation: Reservation,
) -> None:
    decided_at = datetime(2026, 8, 3, 11, 0, tzinfo=UTC)
    repository = InMemoryApprovalRequestRepository(now=lambda: decided_at)
    request = repository.create(reservation)

    repository.reject(request.request_id, "Parking is full")

    assert request.status is ApprovalStatus.REJECTED
    assert request.administrator_comment == "Parking is full"
    assert request.decision_at == decided_at


def test_get_raises_for_nonexistent_request() -> None:
    repository = InMemoryApprovalRequestRepository()
    missing_id = uuid4()

    with pytest.raises(
        ApprovalRequestNotFoundError,
        match=f"approval request {missing_id} does not exist",
    ):
        repository.get(missing_id)


def test_decision_raises_for_nonexistent_request() -> None:
    repository = InMemoryApprovalRequestRepository()
    missing_id = uuid4()

    with pytest.raises(ApprovalRequestNotFoundError):
        repository.approve(missing_id)


def test_request_cannot_be_decided_twice(reservation: Reservation) -> None:
    repository = InMemoryApprovalRequestRepository()
    request = repository.create(reservation)
    repository.approve(request.request_id)

    with pytest.raises(
        ApprovalAlreadyDecidedError,
        match="is already approved",
    ):
        repository.reject(request.request_id, "Changed my mind")

    assert request.status is ApprovalStatus.APPROVED
    assert request.administrator_comment is None
