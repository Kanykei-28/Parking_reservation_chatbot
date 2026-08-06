from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from parking_chatbot.admin.errors import ConfirmedReservationProcessingError
from parking_chatbot.chatbot.guardrails import GuardrailViolation, check_message
from parking_chatbot.chatbot.intents import Intent, detect_intent
from parking_chatbot.chatbot.reservation import Reservation
from parking_chatbot.chatbot.reservation_session import ReservationSession
from parking_chatbot.chatbot.reservation_validation import (
    ReservationValidationError,
)

if TYPE_CHECKING:
    from parking_chatbot.admin.api import ApprovalRequestResponse
    from parking_chatbot.admin.integration import ReservationApprovalIntegration


def answer_question(question: str) -> str:
    from parking_chatbot.rag import answer_question as answer_rag_question

    return answer_rag_question(question)


class ParkingChatbot:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
        approval_integration: ReservationApprovalIntegration | None = None,
    ) -> None:
        self.active_session: ReservationSession | None = None
        self.pending_reservation: Reservation | None = None
        self._now = now
        self._approval_integration = approval_integration

    def submit_pending_reservation_for_approval(self) -> ApprovalRequestResponse:
        if self.pending_reservation is None:
            raise RuntimeError("no completed reservation is pending approval")
        if self._approval_integration is None:
            raise RuntimeError("administrator approval integration is not configured")
        return self._approval_integration.submit(self.pending_reservation)

    def check_pending_reservation_approval(self) -> ApprovalRequestResponse:
        if self._approval_integration is None:
            raise RuntimeError("administrator approval integration is not configured")
        return self._approval_integration.refresh()

    def _approval_status_response(self) -> str:
        integration = self._approval_integration
        if integration is None or integration.request_id is None:
            return "There is no submitted reservation to check."
        try:
            approval = integration.refresh()
        except ConfirmedReservationProcessingError:
            message = (
                "Your reservation has been approved, but it could not be saved to "
                "confirmed reservation storage. Please try checking again later."
            )
            if integration.request_id is not None:
                message += f" Request ID: {integration.request_id}."
            if integration.administrator_comment:
                message += (
                    f" Administrator comment: {integration.administrator_comment}"
                )
            return message
        except RuntimeError:
            return (
                "The administrator approval service is currently unavailable. "
                "Please try checking again later."
            )

        if approval.status.value == "pending":
            message = "Your reservation is still waiting for administrator approval."
        elif approval.status.value == "approved":
            message = "Your reservation has been approved."
        else:
            message = "Your reservation was rejected."
        message = f"{message} Request ID: {approval.request_id}."
        if approval.administrator_comment:
            message += f" Administrator comment: {approval.administrator_comment}"
        return message

    def chat(self, message: str) -> str:
        if self.active_session is not None:
            return self._continue_reservation(message)

        if not message.strip():
            raise ValueError("message must not be empty")

        try:
            check_message(message)
        except GuardrailViolation as error:
            return str(error)
        intent = detect_intent(message)

        if intent is Intent.APPROVAL_STATUS:
            return self._approval_status_response()
        if intent is Intent.RESERVATION:
            self.active_session = ReservationSession(now=self._now)
            prompt = self.active_session.current_prompt()
            if prompt is None:
                raise RuntimeError("new reservation session has no prompt")
            return prompt
        if intent is Intent.GREETING:
            return "Hello! How can I help you with your parking today?"
        if intent is Intent.ACKNOWLEDGEMENT:
            return "You're welcome."
        if intent is Intent.UNKNOWN:
            return (
                "I'm only able to answer questions related to the parking "
                "reservation service."
            )

        return answer_question(message)

    def _continue_reservation(self, message: str) -> str:
        session = self.active_session
        if session is None:
            raise RuntimeError("no active reservation session")

        try:
            session.accept_answer(message)
        except ReservationValidationError as error:
            prompt = session.current_prompt()
            if prompt is None:
                raise RuntimeError(
                    "invalid answer left reservation session without a prompt"
                ) from error
            return f"{error}\n{prompt}"
        if not session.is_complete:
            prompt = session.current_prompt()
            if prompt is None:
                raise RuntimeError("incomplete reservation session has no prompt")
            return prompt

        reservation = session.completed_reservation()
        self.pending_reservation = reservation
        self.active_session = None
        details = (
            f"{reservation.first_name} {reservation.last_name}, "
            f"car {reservation.car_number}, "
            f"parking type {reservation.parking_type}, "
            f"from {reservation.start_datetime} to {reservation.end_datetime}. "
        )
        if self._approval_integration is None:
            return (
                "Reservation collected: "
                + details
                + "Administrator approval is still required."
            )
        try:
            approval = self.submit_pending_reservation_for_approval()
        except RuntimeError:
            return (
                "Reservation collected: "
                + details
                + "The administrator approval service is currently unavailable. "
                "Your reservation details have been kept; please try again later."
            )
        return (
            "Reservation collected and sent to the administrator. "
            + details
            + f"Request ID: {approval.request_id}. "
            f"Current status: {approval.status.value}."
        )


_chatbot = ParkingChatbot()


def chat(message: str) -> str:
    return _chatbot.chat(message)
