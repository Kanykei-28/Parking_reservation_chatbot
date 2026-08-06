from datetime import datetime
from uuid import UUID

from parking_chatbot.chatbot import Reservation
from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPClient,
    ConfirmedReservationMCPError,
)
from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationValidationError,
)


class OrchestrationRecordingError(RuntimeError):
    """A safe error raised when confirmed-reservation recording fails."""


class MCPConfirmedReservationRecorder:
    """Adapt the orchestration recording boundary to the existing MCP client."""

    def __init__(self, client: ConfirmedReservationMCPClient) -> None:
        self._client = client

    def record(
        self,
        reservation: Reservation,
        approval_request_id: UUID,
        approval_time: datetime,
    ) -> bool:
        try:
            confirmed = ConfirmedReservation(
                approval_request_id=approval_request_id,
                first_name=self._required(reservation.first_name),
                last_name=self._required(reservation.last_name),
                car_number=self._required(reservation.car_number),
                start_datetime=self._required(reservation.start_datetime),
                end_datetime=self._required(reservation.end_datetime),
                approval_time=approval_time,
            )
            result = self._client.write_confirmed_reservation_sync(
                confirmed,
                approval_status="approved",
            )
        except (
            ConfirmedReservationMCPError,
            ConfirmedReservationValidationError,
            ValueError,
        ) as error:
            raise OrchestrationRecordingError(
                "confirmed reservation recording failed"
            ) from error
        if result.approval_request_id != confirmed.approval_request_id:
            raise OrchestrationRecordingError("confirmed reservation recording failed")
        return result.stored

    @staticmethod
    def _required(value: str | None) -> str:
        if value is None:
            raise ValueError("confirmed reservation data is incomplete")
        return value
