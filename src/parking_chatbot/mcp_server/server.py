import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationConflictError,
    ConfirmedReservationFileRepository,
    ConfirmedReservationStorageError,
    ConfirmedReservationValidationError,
)

DEFAULT_OUTPUT_PATH = Path("data/dynamic/confirmed_reservations.txt")


class WriteConfirmedReservationResult(BaseModel):
    approval_request_id: UUID
    stored: bool
    message: str


class _ConfirmedReservationToolHandler:
    def __init__(self, repository: ConfirmedReservationFileRepository) -> None:
        self._repository = repository

    def write_confirmed_reservation(
        self,
        approval_request_id: UUID,
        approval_status: str,
        first_name: str,
        last_name: str,
        car_number: str,
        start_datetime: str,
        end_datetime: str,
        approval_time: datetime,
    ) -> WriteConfirmedReservationResult:
        if approval_status != "approved":
            raise ToolError("reservation status must be approved")

        try:
            reservation = ConfirmedReservation(
                approval_request_id=approval_request_id,
                first_name=first_name,
                last_name=last_name,
                car_number=car_number,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                approval_time=approval_time,
            )
        except ConfirmedReservationValidationError as error:
            raise ToolError("confirmed reservation is invalid") from error

        try:
            stored = self._repository.append(reservation)
        except ConfirmedReservationConflictError as error:
            raise ToolError(
                "approval request conflicts with a stored reservation"
            ) from error
        except ConfirmedReservationStorageError as error:
            raise ToolError("could not store confirmed reservation") from error

        message = (
            "confirmed reservation stored"
            if stored
            else "confirmed reservation already stored"
        )
        return WriteConfirmedReservationResult(
            approval_request_id=approval_request_id,
            stored=stored,
            message=message,
        )


def create_reservation_mcp_server(
    repository: ConfirmedReservationFileRepository,
) -> FastMCP[None]:
    server = FastMCP("Confirmed Parking Reservations")
    handler = _ConfirmedReservationToolHandler(repository)

    @server.tool(name="write_confirmed_reservation", structured_output=True)
    def write_confirmed_reservation(
        approval_request_id: UUID,
        approval_status: str,
        first_name: str,
        last_name: str,
        car_number: str,
        start_datetime: str,
        end_datetime: str,
        approval_time: datetime,
    ) -> WriteConfirmedReservationResult:
        """Store a human-approved parking reservation."""
        return handler.write_confirmed_reservation(
            approval_request_id=approval_request_id,
            approval_status=approval_status,
            first_name=first_name,
            last_name=last_name,
            car_number=car_number,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            approval_time=approval_time,
        )

    return server


def main() -> None:
    output_path = Path(
        os.environ.get("CONFIRMED_RESERVATIONS_PATH", str(DEFAULT_OUTPUT_PATH))
    )
    repository = ConfirmedReservationFileRepository(output_path)
    server = create_reservation_mcp_server(repository)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
