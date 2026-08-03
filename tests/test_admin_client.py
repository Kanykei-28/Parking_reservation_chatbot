from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from parking_chatbot.admin.client import (
    AdministratorApprovalClient,
    AdministratorServiceError,
    ApprovalRequestNotFoundClientError,
)
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import Reservation


def approval_response(request_id: UUID) -> dict[str, object]:
    return {
        "request_id": str(request_id),
        "reservation": {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "car_number": "ABC-123",
            "parking_type": "covered",
            "start_datetime": "2026-08-04T09:00",
            "end_datetime": "2026-08-04T17:00",
        },
        "status": "pending",
        "created_at": datetime(2026, 8, 3, 10, 0, tzinfo=UTC).isoformat(),
        "decision_at": None,
        "administrator_comment": None,
    }


def test_client_submits_all_reservation_fields_and_parses_response() -> None:
    request_id = uuid4()
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(201, json=approval_response(request_id))

    client = AdministratorApprovalClient(
        "https://admin.example.test",
        transport=httpx.MockTransport(handler),
    )
    reservation = Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-04T09:00",
        end_datetime="2026-08-04T17:00",
    )

    result = client.submit_reservation(reservation)

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert captured_request.url == "https://admin.example.test/approval-requests"
    assert captured_request.read().decode() == (
        '{"first_name":"Ada","last_name":"Lovelace","car_number":"ABC-123",'
        '"parking_type":"covered","start_datetime":"2026-08-04T09:00",'
        '"end_datetime":"2026-08-04T17:00"}'
    )
    assert result.request_id == request_id
    assert result.status is ApprovalStatus.PENDING
    assert result.reservation.first_name == "Ada"


def test_client_retrieves_approval_request() -> None:
    request_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/approval-requests/{request_id}"
        return httpx.Response(200, json=approval_response(request_id))

    client = AdministratorApprovalClient(
        "https://admin.example.test/",
        transport=httpx.MockTransport(handler),
    )

    result = client.get_approval_request(request_id)

    assert result.request_id == request_id
    assert result.status is ApprovalStatus.PENDING


def test_client_maps_not_found_response_to_clear_error() -> None:
    client = AdministratorApprovalClient(
        "https://admin.example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"detail": "not found"})
        ),
    )

    with pytest.raises(ApprovalRequestNotFoundClientError, match="not found"):
        client.get_approval_request(uuid4())


def test_client_maps_network_failure_to_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = AdministratorApprovalClient(
        "https://admin.example.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AdministratorServiceError, match="service request failed"):
        client.get_approval_request(uuid4())
