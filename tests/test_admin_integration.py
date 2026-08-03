from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage

from parking_chatbot.admin import gateway
from parking_chatbot.admin.agent import create_approval_tools
from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.admin.gateway import ApprovalGateway, LangChainApprovalGateway
from parking_chatbot.admin.integration import ReservationApprovalIntegration
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import ParkingChatbot, Reservation


def approval_response(
    request_id: UUID,
    reservation: Reservation,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    comment: str | None = None,
) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(
        {
            "request_id": request_id,
            "reservation": reservation,
            "status": status,
            "created_at": datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
            "decision_at": (
                datetime(2026, 8, 3, 12, 30, tzinfo=UTC)
                if status is not ApprovalStatus.PENDING
                else None
            ),
            "administrator_comment": comment,
        }
    )


def complete_reservation() -> Reservation:
    return Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-04T09:00",
        end_datetime="2026-08-04T17:00",
    )


def test_complete_chatbot_reservation_is_escalated_with_all_fields() -> None:
    reservation = complete_reservation()
    request_id = uuid4()
    approval_gateway = MagicMock(spec=ApprovalGateway)
    approval_gateway.submit.return_value = approval_response(request_id, reservation)
    integration = ReservationApprovalIntegration(approval_gateway)
    chatbot = ParkingChatbot(
        now=lambda: datetime(2026, 8, 3, 8, 0),
        approval_integration=integration,
    )

    final_message = chatbot.chat("Reserve parking")
    for answer in (
        "Ada",
        "Lovelace",
        "ABC-123",
        "covered",
        "2026-08-04T09:00",
        "2026-08-04T17:00",
    ):
        final_message = chatbot.chat(answer)

    submitted = approval_gateway.submit.call_args.args[0]
    assert submitted == reservation
    assert submitted.first_name == "Ada"
    assert submitted.last_name == "Lovelace"
    assert submitted.car_number == "ABC-123"
    assert submitted.parking_type == "covered"
    assert submitted.start_datetime == "2026-08-04T09:00"
    assert submitted.end_datetime == "2026-08-04T17:00"
    assert integration.request_id == request_id
    assert integration.status is ApprovalStatus.PENDING
    assert "sent to the administrator" in final_message
    assert f"Request ID: {request_id}" in final_message
    assert "Current status: pending" in final_message


def test_repeated_submission_reuses_existing_approval_request() -> None:
    reservation = complete_reservation()
    request_id = uuid4()
    approval_gateway = MagicMock(spec=ApprovalGateway)
    approval_gateway.submit.return_value = approval_response(request_id, reservation)
    integration = ReservationApprovalIntegration(approval_gateway)

    first_result = integration.submit(reservation)
    second_result = integration.submit(reservation)

    assert first_result is second_result
    assert second_result.request_id == request_id
    approval_gateway.submit.assert_called_once_with(reservation)


@pytest.mark.parametrize(
    ("status", "comment"),
    [
        (ApprovalStatus.APPROVED, "Space 42 assigned"),
        (ApprovalStatus.REJECTED, "Parking is full"),
    ],
)
def test_status_and_administrator_comment_are_refreshed(
    status: ApprovalStatus,
    comment: str,
) -> None:
    reservation = complete_reservation()
    request_id = uuid4()
    approval_gateway = MagicMock(spec=ApprovalGateway)
    approval_gateway.submit.return_value = approval_response(request_id, reservation)
    approval_gateway.check.return_value = approval_response(
        request_id,
        reservation,
        status,
        comment,
    )
    integration = ReservationApprovalIntegration(approval_gateway)
    integration.submit(reservation)

    result = integration.refresh()

    approval_gateway.check.assert_called_once_with(request_id)
    assert result.status is status
    assert integration.status is status
    assert integration.administrator_comment == comment


def test_chatbot_and_agent_do_not_expose_approval_decisions() -> None:
    client = MagicMock(spec=AdministratorApprovalClient)
    approval_gateway = MagicMock(spec=ApprovalGateway)
    integration = ReservationApprovalIntegration(approval_gateway)
    chatbot = ParkingChatbot(approval_integration=integration)
    tools = create_approval_tools(client)

    assert not hasattr(chatbot, "approve")
    assert not hasattr(chatbot, "reject")
    assert not hasattr(integration, "approve")
    assert not hasattr(integration, "reject")
    assert {tool.name for tool in tools} == {
        "submit_reservation_for_approval",
        "check_approval_status",
    }


def test_status_intent_without_submitted_reservation_is_clear() -> None:
    chatbot = ParkingChatbot()

    assert chatbot.chat("Check my reservation status") == (
        "There is no submitted reservation to check."
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            ApprovalStatus.PENDING,
            "Your reservation is still waiting for administrator approval.",
        ),
        (ApprovalStatus.APPROVED, "Your reservation has been approved."),
        (ApprovalStatus.REJECTED, "Your reservation was rejected."),
    ],
)
def test_chatbot_reports_current_approval_status(
    status: ApprovalStatus,
    expected: str,
) -> None:
    reservation = complete_reservation()
    request_id = uuid4()
    approval_gateway = MagicMock(spec=ApprovalGateway)
    approval_gateway.submit.return_value = approval_response(request_id, reservation)
    approval_gateway.check.return_value = approval_response(
        request_id,
        reservation,
        status,
        "Use the north entrance" if status is ApprovalStatus.APPROVED else None,
    )
    integration = ReservationApprovalIntegration(approval_gateway)
    integration.submit(reservation)
    chatbot = ParkingChatbot(approval_integration=integration)

    message = chatbot.chat("What is the status of my reservation?")

    assert expected in message
    assert f"Request ID: {request_id}" in message
    if status is ApprovalStatus.APPROVED:
        assert "Administrator comment: Use the north entrance" in message


def test_submission_service_failure_keeps_completed_reservation() -> None:
    approval_gateway = MagicMock(spec=ApprovalGateway)
    approval_gateway.submit.side_effect = RuntimeError("service unavailable")
    integration = ReservationApprovalIntegration(approval_gateway)
    chatbot = ParkingChatbot(
        now=lambda: datetime(2026, 8, 3, 8, 0),
        approval_integration=integration,
    )

    chatbot.chat("Reserve parking")
    for answer in (
        "Ada",
        "Lovelace",
        "ABC-123",
        "covered",
        "2026-08-04T09:00",
    ):
        chatbot.chat(answer)
    message = chatbot.chat("2026-08-04T17:00")

    assert "approval service is currently unavailable" in message
    assert "reservation details have been kept" in message
    assert chatbot.pending_reservation == complete_reservation()
    assert chatbot.active_session is None


def test_langchain_gateway_invokes_existing_agent_and_structured_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reservation = complete_reservation()
    request_id = uuid4()
    response = approval_response(request_id, reservation)
    agent = MagicMock()
    agent.invoke.return_value = {
        "messages": [
            ToolMessage(
                content=response.model_dump_json(),
                tool_call_id="submission-call",
                name="submit_reservation_for_approval",
            )
        ]
    }
    create_agent_mock = MagicMock(return_value=agent)
    monkeypatch.setattr(gateway, "create_administrator_agent", create_agent_mock)
    model = cast(BaseChatModel, MagicMock())
    client = MagicMock(spec=AdministratorApprovalClient)
    approval_gateway = LangChainApprovalGateway.from_model_and_client(model, client)

    result = approval_gateway.submit(reservation)

    create_agent_mock.assert_called_once_with(model, client)
    assert result.request_id == request_id
    invocation = cast(dict[str, Any], agent.invoke.call_args.args[0])
    assert "submit_reservation_for_approval" in invocation["messages"][0]["content"]

    agent.invoke.return_value = {
        "messages": [
            ToolMessage(
                content=response.model_dump_json(),
                tool_call_id="status-call",
                name="check_approval_status",
            )
        ]
    }
    assert approval_gateway.check(request_id).status is ApprovalStatus.PENDING
