from collections.abc import Callable
from datetime import datetime

from parking_chatbot.chatbot.guardrails import GuardrailViolation, check_message
from parking_chatbot.chatbot.intents import Intent, detect_intent
from parking_chatbot.chatbot.reservation import Reservation
from parking_chatbot.chatbot.reservation_session import ReservationSession
from parking_chatbot.chatbot.reservation_validation import (
    ReservationValidationError,
)


def answer_question(question: str) -> str:
    from parking_chatbot.rag import answer_question as answer_rag_question

    return answer_rag_question(question)


class ParkingChatbot:
    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.active_session: ReservationSession | None = None
        self.pending_reservation: Reservation | None = None
        self._now = now

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

        if intent is Intent.RESERVATION:
            self.active_session = ReservationSession(now=self._now)
            prompt = self.active_session.current_prompt()
            if prompt is None:
                raise RuntimeError("new reservation session has no prompt")
            return prompt
        if intent is Intent.GREETING:
            return "Hello! How can I help you with your parking today?"
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
        return (
            "Reservation collected: "
            f"{reservation.first_name} {reservation.last_name}, "
            f"car {reservation.car_number}, "
            f"parking type {reservation.parking_type}, "
            f"from {reservation.start_datetime} to {reservation.end_datetime}. "
            "Administrator approval is still required."
        )


_chatbot = ParkingChatbot()


def chat(message: str) -> str:
    return _chatbot.chat(message)
