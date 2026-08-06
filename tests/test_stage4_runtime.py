from datetime import UTC, datetime
from threading import Event
from time import monotonic
from uuid import UUID

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import Reservation
from parking_chatbot.mcp_client import ConfirmedReservationWriteResult
from parking_chatbot.orchestration import (
    ApprovalMonitor,
    OrchestrationState,
    create_orchestration_service,
)
from parking_chatbot.orchestration.monitoring import SAFE_MONITOR_ERROR
from parking_chatbot.processing import ConfirmedReservation

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")
APPROVAL_TIME = datetime(2026, 8, 6, 10, 30, tzinfo=UTC)


def wait_until(predicate: object, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if callable(predicate) and predicate():
            return
        Event().wait(0.005)
    raise AssertionError("condition was not met before timeout")


class RefreshSequence:
    def __init__(self, states: list[OrchestrationState | Exception]) -> None:
        self.states = states
        self.calls = 0

    def refresh_approval(self, thread_id: str) -> OrchestrationState:
        outcome = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_monitor_skips_pending_and_prints_approved_once() -> None:
    response = (
        f"Your reservation has been approved and recorded. Request ID: {REQUEST_ID}. "
        "Administrator comment: Use space 42"
    )
    service = RefreshSequence(
        [
            {"approval_status": "pending"},
            {
                "approval_status": "approved",
                "recording_status": "recorded",
                "response": response,
            },
        ]
    )
    output: list[str] = []
    monitor = ApprovalMonitor(service, output.append, interval_seconds=0.01)

    assert monitor.start("workflow") is True
    assert monitor.start("workflow") is False
    wait_until(lambda: output)
    Event().wait(0.03)
    monitor.close()

    assert output == [response]
    assert service.calls == 2
    assert not monitor.is_monitoring("workflow")


def test_monitor_prints_rejection_once_with_comment_and_request_id() -> None:
    response = (
        f"Your reservation was rejected. Request ID: {REQUEST_ID}. "
        "Administrator comment: Lot full"
    )
    service = RefreshSequence(
        [
            {
                "approval_status": "rejected",
                "response": response,
            }
        ]
    )
    output: list[str] = []
    monitor = ApprovalMonitor(service, output.append, interval_seconds=0.01)

    monitor.start("workflow")
    wait_until(lambda: output)
    monitor.close()

    assert output == [response]
    assert service.calls == 1


def test_monitor_closes_while_pending_without_output() -> None:
    service = RefreshSequence([{"approval_status": "pending"}])
    output: list[str] = []
    monitor = ApprovalMonitor(service, output.append, interval_seconds=0.01)
    monitor.start("workflow")
    wait_until(lambda: service.calls > 0)

    monitor.close()
    calls_after_close = service.calls
    Event().wait(0.03)

    assert output == []
    assert service.calls == calls_after_close
    assert not monitor.is_monitoring("workflow")


def test_monitor_failure_is_safe_and_stops() -> None:
    private_detail = "/private/output.txt stderr secret"
    service = RefreshSequence([RuntimeError(private_detail)])
    output: list[str] = []
    monitor = ApprovalMonitor(service, output.append, interval_seconds=0.01)

    monitor.start("workflow")
    wait_until(lambda: output)
    monitor.close()

    assert output == [SAFE_MONITOR_ERROR]
    assert private_detail not in output[0]
    assert service.calls == 1


def completed_reservation() -> Reservation:
    return Reservation(
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-06T09:00",
        end_datetime="2026-08-06T17:00",
    )


def approval_response(status: ApprovalStatus) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(
        {
            "request_id": REQUEST_ID,
            "reservation": completed_reservation(),
            "status": status,
            "created_at": datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
            "decision_at": (
                APPROVAL_TIME if status is ApprovalStatus.APPROVED else None
            ),
            "administrator_comment": (
                "Use space 42" if status is ApprovalStatus.APPROVED else None
            ),
        }
    )


class CompletingChatbot:
    active_session: object | None = object()
    pending_reservation: Reservation | None = None

    def chat(self, message: str) -> str:
        self.pending_reservation = completed_reservation()
        self.active_session = None
        return "reservation completed"


class PendingThenApprovedGateway:
    def __init__(self) -> None:
        self.checks = 0

    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        return approval_response(ApprovalStatus.PENDING)

    def check(self, request_id: UUID) -> ApprovalRequestResponse:
        self.checks += 1
        return approval_response(ApprovalStatus.APPROVED)


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[ConfirmedReservation] = []

    def write_confirmed_reservation_sync(
        self,
        reservation: ConfirmedReservation,
        approval_status: str = "approved",
    ) -> ConfirmedReservationWriteResult:
        self.calls.append(reservation)
        return ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=True,
            message="stored",
        )


def test_real_graph_is_automatically_refreshed_recorded_and_notified() -> None:
    gateway = PendingThenApprovedGateway()
    mcp_client = FakeMCPClient()
    service = create_orchestration_service(
        CompletingChatbot,
        lambda: gateway,
        mcp_client,  # type: ignore[arg-type]
    )
    output: list[str] = []
    monitor = ApprovalMonitor(service, output.append, interval_seconds=0.01)

    initial = service.start_or_continue("integration", "complete")
    assert initial["approval_status"] == "pending"
    monitor.start("integration")
    wait_until(lambda: output)
    monitor.close()

    assert output == [
        f"Your reservation has been approved and recorded. Request ID: {REQUEST_ID}. "
        "Administrator comment: Use space 42"
    ]
    assert gateway.checks == 1
    assert len(mcp_client.calls) == 1
