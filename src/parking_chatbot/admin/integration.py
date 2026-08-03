from uuid import UUID

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot.reservation import Reservation


class ReservationApprovalIntegration:
    """Connect one completed reservation workflow to administrator approval."""

    def __init__(self, gateway: ApprovalGateway) -> None:
        self._gateway = gateway
        self._reservation: Reservation | None = None
        self._approval: ApprovalRequestResponse | None = None

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
        return self._approval

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
