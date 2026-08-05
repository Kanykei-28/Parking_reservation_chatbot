from parking_chatbot.admin.errors import ConfirmedReservationProcessingError
from parking_chatbot.admin.models import ApprovalRequest, ApprovalStatus
from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPClient,
    ConfirmedReservationMCPError,
)
from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationValidationError,
)


class ApprovedReservationProcessor:
    def __init__(self, client: ConfirmedReservationMCPClient) -> None:
        self._client = client

    def process(self, request: ApprovalRequest) -> None:
        if request.status is not ApprovalStatus.APPROVED or request.decision_at is None:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            )

        reservation = request.reservation
        values = (
            reservation.first_name,
            reservation.last_name,
            reservation.car_number,
            reservation.start_datetime,
            reservation.end_datetime,
        )
        if any(value is None for value in values):
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            )
        assert reservation.first_name is not None
        assert reservation.last_name is not None
        assert reservation.car_number is not None
        assert reservation.start_datetime is not None
        assert reservation.end_datetime is not None

        try:
            confirmed = ConfirmedReservation(
                approval_request_id=request.request_id,
                first_name=reservation.first_name,
                last_name=reservation.last_name,
                car_number=reservation.car_number,
                start_datetime=reservation.start_datetime,
                end_datetime=reservation.end_datetime,
                approval_time=request.decision_at,
            )
            result = self._client.write_confirmed_reservation_sync(
                confirmed,
                approval_status=request.status.value,
            )
        except (
            ConfirmedReservationMCPError,
            ConfirmedReservationValidationError,
        ) as error:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            ) from error

        if result.approval_request_id != request.request_id:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            )
