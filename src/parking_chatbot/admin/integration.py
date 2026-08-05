from uuid import UUID

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.errors import ConfirmedReservationProcessingError
from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot.reservation import Reservation
from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPClient,
    ConfirmedReservationMCPError,
)
from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationValidationError,
)


class ReservationApprovalIntegration:
    """Connect one completed reservation workflow to administrator approval."""

    def __init__(
        self,
        gateway: ApprovalGateway,
        confirmed_reservation_client: ConfirmedReservationMCPClient | None = None,
    ) -> None:
        self._gateway = gateway
        self._confirmed_reservation_client = confirmed_reservation_client
        self._reservation: Reservation | None = None
        self._approval: ApprovalRequestResponse | None = None
        self._processed_request_id: UUID | None = None

    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        self._ensure_complete(reservation)
        if self._approval is not None:
            if reservation != self._reservation:
                raise RuntimeError(
                    "approval workflow is already associated with another reservation"
                )
            return self._approval

        self._reservation = reservation
        self._approval = self._gateway.submit(reservation)
        return self._approval

    def refresh(self) -> ApprovalRequestResponse:
        if self._approval is None:
            raise RuntimeError("reservation has not been submitted for approval")
        self._approval = self._gateway.check(self._approval.request_id)
        self._process_confirmed_reservation(self._approval)
        return self._approval

    def _process_confirmed_reservation(
        self,
        approval: ApprovalRequestResponse,
    ) -> None:
        client = self._confirmed_reservation_client
        if approval.status is not ApprovalStatus.APPROVED or client is None:
            return
        if self._processed_request_id == approval.request_id:
            return
        if self._reservation is None or approval.decision_at is None:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            )

        reservation = self._reservation
        self._ensure_complete(reservation)
        assert reservation.first_name is not None
        assert reservation.last_name is not None
        assert reservation.car_number is not None
        assert reservation.start_datetime is not None
        assert reservation.end_datetime is not None

        try:
            confirmed_reservation = ConfirmedReservation(
                approval_request_id=approval.request_id,
                first_name=reservation.first_name,
                last_name=reservation.last_name,
                car_number=reservation.car_number,
                start_datetime=reservation.start_datetime,
                end_datetime=reservation.end_datetime,
                approval_time=approval.decision_at,
            )
            result = client.write_confirmed_reservation_sync(
                confirmed_reservation,
                approval_status=approval.status.value,
            )
        except (
            ConfirmedReservationMCPError,
            ConfirmedReservationValidationError,
        ) as error:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            ) from error

        if result.approval_request_id != approval.request_id:
            raise ConfirmedReservationProcessingError(
                "approved reservation could not be stored"
            )
        self._processed_request_id = approval.request_id

    @property
    def request_id(self) -> UUID | None:
        return self._approval.request_id if self._approval is not None else None

    @property
    def status(self) -> ApprovalStatus | None:
        return self._approval.status if self._approval is not None else None

    @property
    def administrator_comment(self) -> str | None:
        if self._approval is None:
            return None
        return self._approval.administrator_comment

    @staticmethod
    def _ensure_complete(reservation: Reservation) -> None:
        values = (
            reservation.first_name,
            reservation.last_name,
            reservation.car_number,
            reservation.parking_type,
            reservation.start_datetime,
            reservation.end_datetime,
        )
        if any(value is None for value in values):
            raise ValueError(
                "only a completed reservation can be submitted for approval"
            )
