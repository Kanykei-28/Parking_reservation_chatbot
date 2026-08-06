from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.integration import ReservationApprovalIntegration
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import ParkingChatbot, Reservation
from parking_chatbot.orchestration.serialization import (
    OrchestrationCheckpointError,
    approval_status_to_checkpoint,
    datetime_from_checkpoint,
    datetime_to_checkpoint,
    reservation_from_checkpoint,
    reservation_to_checkpoint,
    uuid_from_checkpoint,
    uuid_to_checkpoint,
)
from parking_chatbot.orchestration.state import (
    OrchestrationState,
)


def _workflow_response(message: str, state: OrchestrationState) -> str:
    details: list[str] = []
    request_id = state.get("approval_request_id")
    if request_id is not None:
        details.append(f"Request ID: {request_id}.")
    comment = state.get("administrator_comment")
    if comment:
        details.append(f"Administrator comment: {comment}")
    return " ".join((message, *details))


class ChatbotInteraction(Protocol):
    active_session: object | None
    pending_reservation: Reservation | None

    def chat(self, message: str) -> str: ...


class ApprovalCoordinator(Protocol):
    def submit(self, reservation: Reservation) -> ApprovalRequestResponse: ...

    def refresh(self) -> ApprovalRequestResponse: ...


class ConfirmedReservationRecorder(Protocol):
    def record(
        self,
        reservation: Reservation,
        approval_request_id: UUID,
        approval_time: datetime,
    ) -> bool: ...


class UserInteractionNode:
    def __init__(self, chatbot: ChatbotInteraction | ParkingChatbot) -> None:
        self._chatbot = chatbot

    def __call__(self, state: OrchestrationState) -> OrchestrationState:
        previous_reservation = self._chatbot.pending_reservation
        previous_session = self._chatbot.active_session
        response = self._chatbot.chat(state.get("user_message", ""))
        if state.get("approval_status") == "pending" and (
            previous_session is not None or self._chatbot.active_session is not None
        ):
            self._chatbot.active_session = None
            return {
                "response": (
                    "Your current reservation is still waiting for administrator "
                    "approval. Please wait for a decision before starting another "
                    "reservation."
                ),
                "route": "end",
            }
        completed_reservation = self._chatbot.pending_reservation
        update: OrchestrationState = {
            "response": response,
            "route": "end",
        }
        if (
            completed_reservation is not None
            and completed_reservation is not previous_reservation
            and self._chatbot.active_session is None
        ):
            try:
                update["reservation"] = reservation_to_checkpoint(completed_reservation)
                update["route"] = "administrator"
            except OrchestrationCheckpointError:
                update["error"] = "completed reservation data is invalid"
        return update


class AdministratorNode:
    def __init__(
        self,
        approval: ApprovalCoordinator | ReservationApprovalIntegration,
    ) -> None:
        self._approval = approval

    def __call__(self, state: OrchestrationState) -> OrchestrationState:
        reservation_data = state.get("reservation")
        if reservation_data is None:
            return {
                "route": "end",
                "error": "completed reservation is unavailable",
            }
        try:
            reservation = reservation_from_checkpoint(reservation_data)
            if state.get("approval_request_id") is None:
                result = self._approval.submit(reservation)
            else:
                result = self._approval.refresh()
        except OrchestrationCheckpointError:
            return {
                "route": "end",
                "error": "completed reservation data is invalid",
            }
        except RuntimeError:
            return {
                "route": "end",
                "error": "administrator approval is unavailable",
            }

        update: OrchestrationState = {
            "approval_request_id": uuid_to_checkpoint(result.request_id),
            "approval_status": approval_status_to_checkpoint(result.status),
            "route": (
                "recording" if result.status is ApprovalStatus.APPROVED else "end"
            ),
            "error": None,
        }
        if result.decision_at is not None:
            try:
                update["approval_time"] = datetime_to_checkpoint(result.decision_at)
            except OrchestrationCheckpointError:
                return {
                    "route": "end",
                    "error": "administrator approval data is invalid",
                }
        if result.administrator_comment is not None:
            update["administrator_comment"] = result.administrator_comment
        response_state = cast(OrchestrationState, {**state, **update})
        if result.status is ApprovalStatus.PENDING:
            update["response"] = _workflow_response(
                "Your reservation is waiting for administrator approval.",
                response_state,
            )
        elif result.status is ApprovalStatus.REJECTED:
            update["response"] = _workflow_response(
                "Your reservation was rejected.",
                response_state,
            )
        return update


class RecordingNode:
    def __init__(self, recorder: ConfirmedReservationRecorder) -> None:
        self._recorder = recorder

    def __call__(self, state: OrchestrationState) -> OrchestrationState:
        reservation_data = state.get("reservation")
        request_id_data = state.get("approval_request_id")
        approval_time_data = state.get("approval_time")
        if (
            reservation_data is None
            or request_id_data is None
            or approval_time_data is None
        ):
            return {
                "route": "end",
                "recording_status": "failed",
                "error": "approved reservation data is incomplete",
            }
        try:
            reservation = reservation_from_checkpoint(reservation_data)
            request_id = uuid_from_checkpoint(request_id_data)
            approval_time = datetime_from_checkpoint(approval_time_data)
            stored = self._recorder.record(
                reservation,
                request_id,
                approval_time,
            )
        except (OrchestrationCheckpointError, RuntimeError):
            return {
                "route": "end",
                "recording_status": "failed",
                "error": "confirmed reservation recording failed",
                "response": _workflow_response(
                    "Your reservation has been approved, but it could not be "
                    "saved to confirmed reservation storage. Please try checking "
                    "again later.",
                    state,
                ),
            }
        update: OrchestrationState = {
            "route": "end",
            "recording_status": ("recorded" if stored else "already_recorded"),
            "error": None,
        }
        update["response"] = _workflow_response(
            "Your reservation has been approved and recorded.",
            cast(OrchestrationState, {**state, **update}),
        )
        return update
