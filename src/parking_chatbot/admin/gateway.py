import json
from typing import Any, Protocol, cast
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from parking_chatbot.admin.agent import create_administrator_agent
from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.chatbot.reservation import Reservation


class ApprovalGateway(Protocol):
    def submit(self, reservation: Reservation) -> ApprovalRequestResponse: ...

    def check(self, request_id: UUID) -> ApprovalRequestResponse: ...


class ApprovalGatewayError(RuntimeError):
    pass


class DirectApprovalGateway:
    """Deterministic gateway for tests or workflows that do not require an LLM."""

    def __init__(self, client: AdministratorApprovalClient) -> None:
        self._client = client

    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        return self._client.submit_reservation(reservation)

    def check(self, request_id: UUID) -> ApprovalRequestResponse:
        return self._client.get_approval_request(request_id)


class LangChainApprovalGateway:
    """Gateway that communicates through the administrator LangChain agent."""

    def __init__(self, agent: Runnable[Any, Any]) -> None:
        self._agent = agent

    @classmethod
    def from_model_and_client(
        cls,
        model: BaseChatModel,
        client: AdministratorApprovalClient,
    ) -> "LangChainApprovalGateway":
        agent = create_administrator_agent(model, client)
        return cls(cast(Runnable[Any, Any], agent))

    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        payload = {
            "first_name": reservation.first_name,
            "last_name": reservation.last_name,
            "car_number": reservation.car_number,
            "parking_type": reservation.parking_type,
            "start_datetime": reservation.start_datetime,
            "end_datetime": reservation.end_datetime,
        }
        return self._invoke_tool(
            "submit_reservation_for_approval",
            "Call submit_reservation_for_approval exactly once with this completed "
            f"reservation: {json.dumps(payload)}",
        )

    def check(self, request_id: UUID) -> ApprovalRequestResponse:
        return self._invoke_tool(
            "check_approval_status",
            "Call check_approval_status exactly once with approval request ID "
            f"{request_id}.",
        )

    def _invoke_tool(
        self,
        tool_name: str,
        instruction: str,
    ) -> ApprovalRequestResponse:
        try:
            result = self._agent.invoke(
                {"messages": [{"role": "user", "content": instruction}]}
            )
        except Exception as error:
            raise ApprovalGatewayError(
                "administrator approval agent could not complete the request"
            ) from error

        if not isinstance(result, dict):
            raise ApprovalGatewayError(
                "administrator approval agent returned an invalid result"
            )
        messages = result.get("messages")
        if not isinstance(messages, list):
            raise ApprovalGatewayError(
                "administrator approval agent returned no tool messages"
            )

        for message in reversed(messages):
            if isinstance(message, ToolMessage) and message.name == tool_name:
                return self._parse_tool_result(message.content)
        raise ApprovalGatewayError(
            f"administrator approval agent did not call {tool_name}"
        )

    @staticmethod
    def _parse_tool_result(
        content: str | list[str | dict[str, Any]],
    ) -> ApprovalRequestResponse:
        if not isinstance(content, str):
            raise ApprovalGatewayError(
                "administrator approval tool returned an invalid result"
            )
        try:
            payload = json.loads(content)
            return ApprovalRequestResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as error:
            raise ApprovalGatewayError(
                "administrator approval tool returned an invalid result"
            ) from error
