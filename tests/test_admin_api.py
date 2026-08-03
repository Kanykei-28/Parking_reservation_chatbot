from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from parking_chatbot.admin import InMemoryApprovalRequestRepository
from parking_chatbot.admin.api import create_admin_app
from parking_chatbot.chatbot import Reservation


@pytest.fixture
def repository() -> InMemoryApprovalRequestRepository:
    decided_at = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    return InMemoryApprovalRequestRepository(now=lambda: decided_at)


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


@pytest.fixture
def client(repository: InMemoryApprovalRequestRepository) -> TestClient:
    return TestClient(create_admin_app(repository))


def test_creates_pending_approval_request(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
) -> None:
    reservation_data = {
        "first_name": "Grace",
        "last_name": "Hopper",
        "car_number": "XYZ-789",
        "parking_type": "ev",
        "start_datetime": "2026-08-05T08:00",
        "end_datetime": "2026-08-05T10:00",
    }

    response = client.post("/approval-requests", json=reservation_data)

    assert response.status_code == 201
    response_data = response.json()
    request_id = UUID(response_data["request_id"])
    assert response_data["status"] == "pending"
    assert response_data["reservation"] == reservation_data

    stored_request = repository.get(request_id)
    assert stored_request.request_id == request_id
    assert stored_request.status.value == "pending"
    assert stored_request.reservation == Reservation(**reservation_data)


def test_create_approval_request_requires_all_reservation_fields(
    client: TestClient,
) -> None:
    response = client.post(
        "/approval-requests",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "car_number": "XYZ-789",
            "parking_type": "ev",
            "start_datetime": "2026-08-05T08:00",
        },
    )

    assert response.status_code == 422


def test_lists_approval_requests(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    first_request = repository.create(reservation)
    second_request = repository.create(reservation)

    response = client.get("/approval-requests")

    assert response.status_code == 200
    assert [item["request_id"] for item in response.json()] == [
        str(first_request.request_id),
        str(second_request.request_id),
    ]


def test_filters_pending_approval_requests(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    pending_request = repository.create(reservation)
    approved_request = repository.create(reservation)
    repository.approve(approved_request.request_id)

    response = client.get("/approval-requests", params={"status": "pending"})

    assert response.status_code == 200
    assert [item["request_id"] for item in response.json()] == [
        str(pending_request.request_id)
    ]


def test_retrieves_approval_request_by_id(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    request = repository.create(reservation)

    response = client.get(f"/approval-requests/{request.request_id}")

    assert response.status_code == 200
    assert response.json() == {
        "request_id": str(request.request_id),
        "reservation": {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "car_number": "ABC-123",
            "parking_type": "covered",
            "start_datetime": "2026-08-04T09:00",
            "end_datetime": "2026-08-04T17:00",
        },
        "status": "pending",
        "created_at": request.created_at.isoformat().replace("+00:00", "Z"),
        "decision_at": None,
        "administrator_comment": None,
    }


def test_nonexistent_approval_request_returns_404(client: TestClient) -> None:
    response = client.get("/approval-requests/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"].endswith("does not exist")


def test_approves_pending_request(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    request = repository.create(reservation)

    response = client.post(f"/approval-requests/{request.request_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["decision_at"] == "2026-08-03T12:00:00Z"
    assert repository.get(request.request_id).status.value == "approved"


def test_rejects_pending_request(
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    request = repository.create(reservation)

    response = client.post(f"/approval-requests/{request.request_id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert repository.get(request.request_id).status.value == "rejected"


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_administrator_comment_is_preserved(
    decision: str,
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    request = repository.create(reservation)

    response = client.post(
        f"/approval-requests/{request.request_id}/{decision}",
        json={"administrator_comment": "Reviewed by the parking administrator"},
    )

    assert response.status_code == 200
    assert (
        response.json()["administrator_comment"]
        == "Reviewed by the parking administrator"
    )
    assert (
        repository.get(request.request_id).administrator_comment
        == "Reviewed by the parking administrator"
    )


@pytest.mark.parametrize("second_decision", ["approve", "reject"])
def test_deciding_already_decided_request_returns_409(
    second_decision: str,
    client: TestClient,
    repository: InMemoryApprovalRequestRepository,
    reservation: Reservation,
) -> None:
    request = repository.create(reservation)
    repository.approve(request.request_id)

    response = client.post(f"/approval-requests/{request.request_id}/{second_decision}")

    assert response.status_code == 409
    assert response.json()["detail"].endswith("is already approved")


def test_malformed_request_id_is_rejected(client: TestClient) -> None:
    response = client.get("/approval-requests/not-a-uuid")

    assert response.status_code == 422


def test_invalid_status_filter_is_rejected(client: TestClient) -> None:
    response = client.get("/approval-requests", params={"status": "unknown"})

    assert response.status_code == 422
