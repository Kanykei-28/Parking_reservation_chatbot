from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from parking_chatbot.admin.api import ApprovalRequestResponse, create_admin_app
from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.admin.integration import (
    ConfirmedReservationProcessingError,
    ReservationApprovalIntegration,
)
from parking_chatbot.admin.models import ApprovalRequest, ApprovalStatus
from parking_chatbot.admin.processing import ApprovedReservationProcessor
from parking_chatbot.admin.repository import InMemoryApprovalRequestRepository
from parking_chatbot.chatbot import ParkingChatbot, Reservation
from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPClient,
    ConfirmedReservationMCPError,
    ConfirmedReservationWriteResult,
)

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")
DECISION_AT = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)


def reservation() -> Reservation:
    return Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-05T09:00",
        end_datetime="2026-08-05T17:00",
    )


def approval(
    status: ApprovalStatus,
    comment: str | None = None,
) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(
        {
            "request_id": REQUEST_ID,
            "reservation": reservation(),
            "status": status,
            "created_at": datetime(2026, 8, 4, 9, 0, tzinfo=UTC),
            "decision_at": (None if status is ApprovalStatus.PENDING else DECISION_AT),
            "administrator_comment": comment,
        }
    )


def configured_integration(
    status: ApprovalStatus,
    mcp_client: ConfirmedReservationMCPClient,
) -> tuple[ReservationApprovalIntegration, MagicMock]:
    gateway = MagicMock(spec=ApprovalGateway)
    gateway.submit.return_value = approval(ApprovalStatus.PENDING)
    gateway.check.return_value = approval(status)
    integration = ReservationApprovalIntegration(gateway, mcp_client)
    integration.submit(reservation())
    return integration, gateway


def successful_mcp_client() -> MagicMock:
    client = MagicMock(spec=ConfirmedReservationMCPClient)
    client.write_confirmed_reservation_sync.return_value = (
        ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=True,
            message="confirmed reservation stored",
        )
    )
    return client


def event_processing_client(
    mcp_client: ConfirmedReservationMCPClient,
) -> tuple[TestClient, InMemoryApprovalRequestRepository]:
    repository = InMemoryApprovalRequestRepository(now=lambda: DECISION_AT)
    processor = ApprovedReservationProcessor(mcp_client)
    return (
        TestClient(
            create_admin_app(
                repository,
                approved_reservation_processor=processor,
            )
        ),
        repository,
    )


def test_approved_result_sends_exact_data_to_mcp_once() -> None:
    client = successful_mcp_client()
    integration, _gateway = configured_integration(ApprovalStatus.APPROVED, client)

    integration.refresh()
    integration.refresh()

    client.write_confirmed_reservation_sync.assert_called_once()
    confirmed = client.write_confirmed_reservation_sync.call_args.args[0]
    assert confirmed.approval_request_id == REQUEST_ID
    assert confirmed.approval_time == DECISION_AT
    assert confirmed.first_name == "Ada"
    assert confirmed.last_name == "Lovelace"
    assert confirmed.car_number == "ABC-123"
    assert confirmed.start_datetime == "2026-08-05T09:00"
    assert confirmed.end_datetime == "2026-08-05T17:00"
    assert client.write_confirmed_reservation_sync.call_args.kwargs == {
        "approval_status": "approved"
    }


def test_approval_endpoint_processes_authoritative_request_immediately() -> None:
    mcp_client = successful_mcp_client()
    api_client, repository = event_processing_client(mcp_client)
    request = repository.create(reservation())
    mcp_client.write_confirmed_reservation_sync.return_value = (
        ConfirmedReservationWriteResult(
            approval_request_id=request.request_id,
            stored=True,
            message="confirmed reservation stored",
        )
    )

    response = api_client.post(f"/approval-requests/{request.request_id}/approve")

    assert response.status_code == 200
    confirmed = mcp_client.write_confirmed_reservation_sync.call_args.args[0]
    assert confirmed.approval_request_id == request.request_id
    assert confirmed.approval_time == DECISION_AT
    assert confirmed.first_name == "Ada"
    assert confirmed.last_name == "Lovelace"
    assert confirmed.car_number == "ABC-123"
    assert confirmed.start_datetime == "2026-08-05T09:00"
    assert confirmed.end_datetime == "2026-08-05T17:00"
    assert mcp_client.write_confirmed_reservation_sync.call_args.kwargs == {
        "approval_status": "approved"
    }


def test_pending_and_rejected_api_requests_do_not_invoke_processor() -> None:
    mcp_client = successful_mcp_client()
    api_client, repository = event_processing_client(mcp_client)
    pending_request = repository.create(reservation())
    rejected_request = repository.create(reservation())

    rejection = api_client.post(
        f"/approval-requests/{rejected_request.request_id}/reject"
    )

    assert rejection.status_code == 200
    assert repository.get(pending_request.request_id).status is ApprovalStatus.PENDING
    mcp_client.write_confirmed_reservation_sync.assert_not_called()


def test_approval_stays_approved_when_immediate_processing_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "/private/confirmed-reservations.txt"
    mcp_client = successful_mcp_client()
    mcp_client.write_confirmed_reservation_sync.side_effect = (
        ConfirmedReservationMCPError(private_detail)
    )
    api_client, repository = event_processing_client(mcp_client)
    request = repository.create(reservation())

    response = api_client.post(f"/approval-requests/{request.request_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert repository.get(request.request_id).status is ApprovalStatus.APPROVED
    assert "Approved reservation processing failed" in caplog.text
    assert private_detail not in caplog.text


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.PENDING, ApprovalStatus.REJECTED],
)
def test_non_approved_result_never_calls_mcp(status: ApprovalStatus) -> None:
    client = successful_mcp_client()
    integration, _gateway = configured_integration(status, client)

    result = integration.refresh()

    assert result.status is status
    client.write_confirmed_reservation_sync.assert_not_called()


def test_mcp_failure_is_safe_and_remains_retryable() -> None:
    private_detail = "/private/confirmed-reservations.txt"
    client = successful_mcp_client()
    client.write_confirmed_reservation_sync.side_effect = [
        ConfirmedReservationMCPError(private_detail),
        ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=False,
            message="confirmed reservation already stored",
        ),
    ]
    integration, _gateway = configured_integration(ApprovalStatus.APPROVED, client)

    with pytest.raises(
        ConfirmedReservationProcessingError,
        match="^approved reservation could not be stored$",
    ) as caught:
        integration.refresh()

    assert private_detail not in str(caught.value)
    result = integration.refresh()
    assert result.status is ApprovalStatus.APPROVED
    assert client.write_confirmed_reservation_sync.call_count == 2


def test_chatbot_reports_processing_failure_accurately_and_retries() -> None:
    private_detail = "/private/confirmed-reservations.txt"
    client = successful_mcp_client()
    client.write_confirmed_reservation_sync.side_effect = [
        ConfirmedReservationMCPError(private_detail),
        ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=True,
            message="confirmed reservation stored",
        ),
    ]
    integration, gateway = configured_integration(ApprovalStatus.APPROVED, client)
    gateway.check.return_value = approval(
        ApprovalStatus.APPROVED,
        "Use space 42",
    )
    chatbot = ParkingChatbot(approval_integration=integration)

    first_message = chatbot.chat("Check my reservation status")
    second_message = chatbot.chat("Check my reservation status")

    assert "has been approved, but it could not be saved" in first_message
    assert (
        "administrator approval service is currently unavailable" not in first_message
    )
    assert private_detail not in first_message
    assert f"Request ID: {REQUEST_ID}" in first_message
    assert "Administrator comment: Use space 42" in first_message
    assert "Your reservation has been approved." in second_message
    assert client.write_confirmed_reservation_sync.call_count == 2


def test_chatbot_keeps_administrator_service_failure_message() -> None:
    client = successful_mcp_client()
    integration, gateway = configured_integration(ApprovalStatus.APPROVED, client)
    gateway.check.side_effect = RuntimeError("administrator endpoint unavailable")
    chatbot = ParkingChatbot(approval_integration=integration)

    message = chatbot.chat("Check my reservation status")

    assert message == (
        "The administrator approval service is currently unavailable. "
        "Please try checking again later."
    )
    client.write_confirmed_reservation_sync.assert_not_called()


def test_failed_immediate_processing_is_retried_by_status_refresh() -> None:
    mcp_client = successful_mcp_client()
    mcp_client.write_confirmed_reservation_sync.side_effect = [
        ConfirmedReservationMCPError("private immediate failure"),
        ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=True,
            message="confirmed reservation stored",
        ),
    ]
    repository = InMemoryApprovalRequestRepository(now=lambda: DECISION_AT)
    request = ApprovalRequest(reservation=reservation(), request_id=REQUEST_ID)
    repository.add(request)
    api_client = TestClient(
        create_admin_app(
            repository,
            approved_reservation_processor=ApprovedReservationProcessor(mcp_client),
        )
    )

    response = api_client.post(f"/approval-requests/{REQUEST_ID}/approve")
    gateway = MagicMock(spec=ApprovalGateway)
    gateway.submit.return_value = approval(ApprovalStatus.PENDING)
    gateway.check.return_value = ApprovalRequestResponse.model_validate(request)
    integration = ReservationApprovalIntegration(gateway, mcp_client)
    integration.submit(reservation())

    refreshed = integration.refresh()

    assert response.json()["status"] == "approved"
    assert refreshed.status is ApprovalStatus.APPROVED
    assert mcp_client.write_confirmed_reservation_sync.call_count == 2


def test_successful_immediate_processing_stays_idempotent_on_status_refresh(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "confirmed.txt"
    mcp_client = ConfirmedReservationMCPClient(
        environment={"CONFIRMED_RESERVATIONS_PATH": str(output_path)}
    )
    repository = InMemoryApprovalRequestRepository(now=lambda: DECISION_AT)
    request = repository.create(reservation())
    api_client = TestClient(
        create_admin_app(
            repository,
            approved_reservation_processor=ApprovedReservationProcessor(mcp_client),
        )
    )

    response = api_client.post(f"/approval-requests/{request.request_id}/approve")
    approved_response = ApprovalRequestResponse.model_validate(request)
    gateway = MagicMock(spec=ApprovalGateway)
    gateway.submit.return_value = approval(ApprovalStatus.PENDING).model_copy(
        update={"request_id": request.request_id}
    )
    gateway.check.return_value = approved_response
    integration = ReservationApprovalIntegration(gateway, mcp_client)
    integration.submit(reservation())
    integration.refresh()

    assert response.status_code == 200
    assert output_path.read_text(encoding="utf-8").count("\n") == 1
    mcp_client.close()


def test_real_approve_endpoint_writes_through_stdio_mcp_server(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "confirmed.txt"
    mcp_client = ConfirmedReservationMCPClient(
        environment={"CONFIRMED_RESERVATIONS_PATH": str(output_path)}
    )
    api_client, repository = event_processing_client(mcp_client)
    request = repository.create(reservation())

    response = api_client.post(f"/approval-requests/{request.request_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert output_path.read_text(encoding="utf-8") == (
        "Ada Lovelace | ABC-123 | 2026-08-05T09:00–2026-08-05T17:00 | "
        "2026-08-04T10:30:00+00:00\n"
    )
    mcp_client.close()


def test_real_approved_flow_writes_through_stdio_mcp_server(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "confirmed.txt"
    client = ConfirmedReservationMCPClient(
        environment={"CONFIRMED_RESERVATIONS_PATH": str(output_path)}
    )
    integration, _gateway = configured_integration(ApprovalStatus.APPROVED, client)

    result = integration.refresh()

    assert result.status is ApprovalStatus.APPROVED
    assert output_path.read_text(encoding="utf-8") == (
        "Ada Lovelace | ABC-123 | 2026-08-05T09:00–2026-08-05T17:00 | "
        "2026-08-04T10:30:00+00:00\n"
    )
