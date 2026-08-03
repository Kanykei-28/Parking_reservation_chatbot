from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from parking_chatbot.admin import agent
from parking_chatbot.admin.agent import (
    create_administrator_agent,
    create_approval_tools,
)
from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.client import AdministratorApprovalClient


def pending_response(request_id: UUID) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(
        {
            "request_id": request_id,
            "reservation": {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "car_number": "ABC-123",
                "parking_type": "covered",
                "start_datetime": "2026-08-04T09:00",
                "end_datetime": "2026-08-04T17:00",
            },
            "status": "pending",
            "created_at": "2026-08-03T10:00:00Z",
            "decision_at": None,
            "administrator_comment": None,
        }
    )


@pytest.fixture
def mocked_client() -> MagicMock:
    return MagicMock(spec=AdministratorApprovalClient)


def tools_by_name(client: AdministratorApprovalClient) -> dict[str, BaseTool]:
    return {tool.name: tool for tool in create_approval_tools(client)}


def test_submission_tool_calls_client_with_reservation(
    mocked_client: MagicMock,
) -> None:
    request_id = uuid4()
    mocked_client.submit_reservation.return_value = pending_response(request_id)
    tool = tools_by_name(mocked_client)["submit_reservation_for_approval"]

    result = tool.invoke(
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "car_number": "ABC-123",
            "parking_type": "covered",
            "start_datetime": "2026-08-04T09:00",
            "end_datetime": "2026-08-04T17:00",
        }
    )

    reservation = mocked_client.submit_reservation.call_args.args[0]
    assert reservation.first_name == "Ada"
    assert reservation.end_datetime == "2026-08-04T17:00"
    assert result["request_id"] == str(request_id)
    assert result["status"] == "pending"


def test_status_tool_calls_client_with_request_id(mocked_client: MagicMock) -> None:
    request_id = uuid4()
    mocked_client.get_approval_request.return_value = pending_response(request_id)
    tool = tools_by_name(mocked_client)["check_approval_status"]

    result = tool.invoke({"request_id": str(request_id)})

    mocked_client.get_approval_request.assert_called_once_with(request_id)
    assert result["status"] == "pending"


def test_tools_expose_useful_names_descriptions_and_schemas(
    mocked_client: MagicMock,
) -> None:
    tools = create_approval_tools(mocked_client)

    assert {tool.name for tool in tools} == {
        "submit_reservation_for_approval",
        "check_approval_status",
    }
    assert all(tool.description for tool in tools)
    assert all(tool.args_schema is not None for tool in tools)
    assert "first_name" in tools[0].get_input_jsonschema()["properties"]
    assert "request_id" in tools[1].get_input_jsonschema()["properties"]


def test_agent_is_constructed_with_only_approval_communication_tools(
    mocked_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    create_agent_mock = MagicMock(return_value=sentinel)
    monkeypatch.setattr(agent, "langchain_create_agent", create_agent_mock)
    model = cast(BaseChatModel, MagicMock())

    result = create_administrator_agent(model, mocked_client)

    assert result is sentinel
    arguments = cast(dict[str, Any], create_agent_mock.call_args.kwargs)
    assert arguments["model"] is model
    assert arguments["name"] == "administrator_approval_agent"
    assert "Never approve or reject" in arguments["system_prompt"]
    assert {tool.name for tool in arguments["tools"]} == {
        "submit_reservation_for_approval",
        "check_approval_status",
    }
    assert all("/approve" not in tool.name for tool in arguments["tools"])
    assert all("/reject" not in tool.name for tool in arguments["tools"])
