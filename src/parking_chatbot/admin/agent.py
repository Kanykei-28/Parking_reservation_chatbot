from typing import Any
from uuid import UUID

from langchain.agents import create_agent as langchain_create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.chatbot.reservation import Reservation

ADMINISTRATOR_AGENT_PROMPT = """You communicate with the human administrator's
parking-reservation approval service. You may submit a completed reservation for
approval or check an existing approval request's status. Never approve or reject a
request yourself. The human administrator exclusively owns that decision."""


class SubmitReservationInput(BaseModel):
    first_name: str
    last_name: str
    car_number: str
    parking_type: str
    start_datetime: str
    end_datetime: str


class CheckApprovalStatusInput(BaseModel):
    request_id: UUID


def create_approval_tools(client: AdministratorApprovalClient) -> list[BaseTool]:
    def submit_reservation_for_approval(
        first_name: str,
        last_name: str,
        car_number: str,
        parking_type: str,
        start_datetime: str,
        end_datetime: str,
    ) -> dict[str, Any]:
        """Submit a completed parking reservation for human administrator approval."""
        reservation = Reservation(
            first_name=first_name,
            last_name=last_name,
            car_number=car_number,
            parking_type=parking_type,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )
        response = client.submit_reservation(reservation)
        return response.model_dump(mode="json")

    def check_approval_status(request_id: UUID) -> dict[str, Any]:
        """Get the current pending, approved, or rejected status of a request."""
        response = client.get_approval_request(request_id)
        return response.model_dump(mode="json")

    return [
        StructuredTool.from_function(
            submit_reservation_for_approval,
            name="submit_reservation_for_approval",
            description=(
                "Submit all fields of a completed parking reservation to the human "
                "administrator and return its approval request ID and pending status."
            ),
            args_schema=SubmitReservationInput,
        ),
        StructuredTool.from_function(
            check_approval_status,
            name="check_approval_status",
            description=(
                "Retrieve the current status and administrator comment for an existing "
                "approval request ID."
            ),
            args_schema=CheckApprovalStatusInput,
        ),
    ]


def create_administrator_agent(
    model: BaseChatModel,
    client: AdministratorApprovalClient,
) -> Any:
    return langchain_create_agent(
        model=model,
        tools=create_approval_tools(client),
        system_prompt=ADMINISTRATOR_AGENT_PROMPT,
        name="administrator_approval_agent",
    )
