import subprocess
import sys
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import Reservation
from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPError,
    ConfirmedReservationWriteResult,
)
from parking_chatbot.orchestration import (
    AdministratorNode,
    MCPConfirmedReservationRecorder,
    OrchestrationCheckpointError,
    OrchestrationRecordingError,
    OrchestrationService,
    create_orchestration_service,
    datetime_from_checkpoint,
    datetime_to_checkpoint,
    reservation_from_checkpoint,
    reservation_to_checkpoint,
    uuid_from_checkpoint,
    uuid_to_checkpoint,
)
from parking_chatbot.processing import ConfirmedReservation

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")
SECOND_REQUEST_ID = UUID("87654321-4321-8765-4321-876543218765")
APPROVAL_TIME = datetime(2026, 8, 6, 10, 30, tzinfo=UTC)


def reservation(name: str = "Ada") -> Reservation:
    return Reservation(
        first_name=name,
        last_name="Lovelace",
        car_number="ABC-123",
        parking_type="covered",
        start_datetime="2026-08-06T09:00",
        end_datetime="2026-08-06T17:00",
    )


def response(
    status: ApprovalStatus,
    *,
    request_id: UUID = REQUEST_ID,
    comment: str | None = None,
) -> ApprovalRequestResponse:
    return ApprovalRequestResponse.model_validate(
        {
            "request_id": request_id,
            "reservation": reservation(),
            "status": status,
            "created_at": datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
            "decision_at": None if status is ApprovalStatus.PENDING else APPROVAL_TIME,
            "administrator_comment": comment,
        }
    )


class CompletingChatbot:
    def __init__(self, completed: Reservation) -> None:
        self.active_session: object | None = object()
        self.pending_reservation: Reservation | None = None
        self.completed = completed
        self.messages: list[str] = []

    def chat(self, message: str) -> str:
        self.messages.append(message)
        self.pending_reservation = self.completed
        self.active_session = None
        return "reservation complete"


class SequencedApproval:
    def __init__(self, results: list[ApprovalRequestResponse]) -> None:
        self.results = results
        self.submissions = 0
        self.refreshes = 0

    def submit(self, completed_reservation: Reservation) -> ApprovalRequestResponse:
        self.submissions += 1
        return self.results[0]

    def refresh(self) -> ApprovalRequestResponse:
        self.refreshes += 1
        return self.results[min(self.refreshes, len(self.results) - 1)]


class Recorder:
    def __init__(self, outcomes: list[bool | Exception] | None = None) -> None:
        self.outcomes = outcomes or [True]
        self.calls: list[tuple[Reservation, UUID, datetime]] = []

    def record(
        self,
        completed_reservation: Reservation,
        request_id: UUID,
        approval_time: datetime,
    ) -> bool:
        self.calls.append((completed_reservation, request_id, approval_time))
        outcome = self.outcomes[min(len(self.calls) - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def service_with(
    approval: SequencedApproval,
    recorder: Recorder,
    *,
    chatbot: CompletingChatbot | None = None,
) -> tuple[OrchestrationService, CompletingChatbot]:
    workflow_chatbot = chatbot or CompletingChatbot(reservation())
    service = OrchestrationService(
        lambda: workflow_chatbot,
        lambda: approval,
        recorder,
    )
    return service, workflow_chatbot


def test_pending_state_survives_and_refresh_skips_user_interaction() -> None:
    approval = SequencedApproval(
        [response(ApprovalStatus.PENDING), response(ApprovalStatus.PENDING)]
    )
    service, chatbot = service_with(approval, Recorder())

    initial = service.start_or_continue("workflow-1", "complete reservation")
    refreshed = service.refresh_approval("workflow-1")

    assert initial["approval_request_id"] == str(REQUEST_ID)
    assert initial["response"].startswith(
        "Your reservation is waiting for administrator approval."
    )
    assert refreshed["approval_status"] == "pending"
    assert chatbot.messages == ["complete reservation"]
    assert approval.submissions == 1
    assert approval.refreshes == 1


def test_unique_thread_ids_have_isolated_state() -> None:
    chatbots = iter(
        [CompletingChatbot(reservation("Ada")), CompletingChatbot(reservation("Grace"))]
    )
    approvals = iter(
        [
            SequencedApproval([response(ApprovalStatus.PENDING)]),
            SequencedApproval(
                [response(ApprovalStatus.PENDING, request_id=SECOND_REQUEST_ID)]
            ),
        ]
    )
    service = OrchestrationService(
        lambda: next(chatbots), lambda: next(approvals), Recorder()
    )

    first = service.start_or_continue("first", "one")
    second = service.start_or_continue("second", "two")

    assert first["approval_request_id"] == str(REQUEST_ID)
    assert second["approval_request_id"] == str(SECOND_REQUEST_ID)
    assert first["reservation"]["first_name"] == "Ada"
    assert second["reservation"]["first_name"] == "Grace"


def test_rejected_refresh_finishes_without_recording() -> None:
    approval = SequencedApproval(
        [
            response(ApprovalStatus.PENDING),
            response(ApprovalStatus.REJECTED, comment="No spaces"),
        ]
    )
    recorder = Recorder()
    service, _ = service_with(approval, recorder)
    service.start_or_continue("rejected", "complete")

    result = service.refresh_approval("rejected")

    assert result["response"].startswith("Your reservation was rejected.")
    assert str(REQUEST_ID) in result["response"]
    assert "No spaces" in result["response"]
    assert recorder.calls == []


def test_approved_refresh_records_once_and_preserves_authoritative_data() -> None:
    approval = SequencedApproval(
        [
            response(ApprovalStatus.PENDING),
            response(ApprovalStatus.APPROVED, comment="Use space 42"),
        ]
    )
    recorder = Recorder()
    service, chatbot = service_with(approval, recorder)
    service.start_or_continue("approved", "complete")

    result = service.refresh_approval("approved")
    repeated = service.refresh_approval("approved")

    assert recorder.calls == [(chatbot.completed, REQUEST_ID, APPROVAL_TIME)]
    assert result["recording_status"] == "recorded"
    assert result["response"].startswith(
        "Your reservation has been approved and recorded."
    )
    assert repeated["recording_status"] == "recorded"
    assert approval.refreshes == 1


def test_idempotent_mcp_result_is_successful() -> None:
    approval = SequencedApproval(
        [response(ApprovalStatus.PENDING), response(ApprovalStatus.APPROVED)]
    )
    service, _ = service_with(approval, Recorder([False]))
    service.start_or_continue("idempotent", "complete")

    result = service.refresh_approval("idempotent")

    assert result["recording_status"] == "already_recorded"
    assert result["response"].startswith(
        "Your reservation has been approved and recorded."
    )


def test_recording_failure_is_safe_and_retryable() -> None:
    private_detail = "/private/confirmed.txt: subprocess stderr secret"
    approval = SequencedApproval(
        [response(ApprovalStatus.PENDING), response(ApprovalStatus.APPROVED)]
    )
    recorder = Recorder([RuntimeError(private_detail), True])
    service, _ = service_with(approval, recorder)
    service.start_or_continue("retry", "complete")

    failed = service.refresh_approval("retry")
    retried = service.refresh_approval("retry")

    assert failed["recording_status"] == "failed"
    assert private_detail not in failed["response"]
    assert failed["error"] == "confirmed reservation recording failed"
    assert retried["recording_status"] == "recorded"
    assert len(recorder.calls) == 2


class FakeMCPClient:
    def __init__(
        self, *, stored: bool = True, failure: Exception | None = None
    ) -> None:
        self.stored = stored
        self.failure = failure
        self.calls: list[tuple[ConfirmedReservation, str]] = []

    def write_confirmed_reservation_sync(
        self, confirmed: ConfirmedReservation, approval_status: str = "approved"
    ) -> ConfirmedReservationWriteResult:
        self.calls.append((confirmed, approval_status))
        if self.failure is not None:
            raise self.failure
        return ConfirmedReservationWriteResult(
            approval_request_id=REQUEST_ID,
            stored=self.stored,
            message="stored",
        )


@pytest.mark.parametrize("stored", [True, False])
def test_concrete_recorder_uses_mcp_client_and_accepts_idempotency(
    stored: bool,
) -> None:
    client = FakeMCPClient(stored=stored)
    recorder = MCPConfirmedReservationRecorder(client)  # type: ignore[arg-type]

    result = recorder.record(reservation(), REQUEST_ID, APPROVAL_TIME)

    assert result is stored
    confirmed, status = client.calls[0]
    assert status == "approved"
    assert confirmed.approval_request_id == REQUEST_ID
    assert confirmed.approval_time == APPROVAL_TIME
    assert confirmed.first_name == "Ada"


def test_concrete_recorder_maps_mcp_failure_safely() -> None:
    private_detail = "/private/output.txt secret stderr"
    client = FakeMCPClient(failure=ConfirmedReservationMCPError(private_detail))
    recorder = MCPConfirmedReservationRecorder(client)  # type: ignore[arg-type]

    with pytest.raises(OrchestrationRecordingError) as captured:
        recorder.record(reservation(), REQUEST_ID, APPROVAL_TIME)

    assert private_detail not in str(captured.value)


class Gateway:
    def __init__(self) -> None:
        self.request = response(ApprovalStatus.PENDING)

    def submit(self, completed_reservation: Reservation) -> ApprovalRequestResponse:
        return self.request

    def check(self, request_id: UUID) -> ApprovalRequestResponse:
        return self.request


def test_orchestration_uses_stage2_integration_without_immediate_mcp() -> None:
    gateway = Gateway()
    mcp_client = FakeMCPClient()
    service = create_orchestration_service(
        lambda: CompletingChatbot(reservation()),
        lambda: gateway,
        mcp_client,  # type: ignore[arg-type]
    )

    result = service.start_or_continue("stage-2", "complete")

    assert result["approval_status"] == "pending"
    assert mcp_client.calls == []


class ConcurrentChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def __init__(self) -> None:
        self.first_entered = Event()
        self.release_first = Event()
        self._counter_lock = Lock()
        self.active_calls = 0
        self.maximum_active_calls = 0

    def chat(self, message: str) -> str:
        with self._counter_lock:
            self.active_calls += 1
            self.maximum_active_calls = max(
                self.maximum_active_calls,
                self.active_calls,
            )
        if message == "first":
            self.first_entered.set()
            assert self.release_first.wait(timeout=1)
        with self._counter_lock:
            self.active_calls -= 1
        return message


def test_same_thread_graph_operations_are_serialized() -> None:
    chatbot = ConcurrentChatbot()
    service = OrchestrationService(
        lambda: chatbot,
        lambda: SequencedApproval([response(ApprovalStatus.PENDING)]),
        Recorder(),
    )
    results: list[object] = []
    first = Thread(
        target=lambda: results.append(service.start_or_continue("shared", "first"))
    )
    second = Thread(
        target=lambda: results.append(service.start_or_continue("shared", "second"))
    )

    first.start()
    assert chatbot.first_entered.wait(timeout=1)
    second.start()
    Event().wait(0.03)
    assert chatbot.maximum_active_calls == 1
    chatbot.release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(results) == 2
    assert chatbot.maximum_active_calls == 1


class SequentialReservationChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def __init__(self) -> None:
        self.completed = [reservation("Ada"), reservation("Grace")]
        self.calls = 0

    def chat(self, message: str) -> str:
        self.pending_reservation = self.completed[self.calls]
        self.calls += 1
        return "reservation complete"


def test_two_sequential_reservations_get_independent_approval_workflows() -> None:
    chatbot = SequentialReservationChatbot()
    approvals = iter(
        [
            SequencedApproval([response(ApprovalStatus.APPROVED)]),
            SequencedApproval(
                [
                    response(
                        ApprovalStatus.APPROVED,
                        request_id=SECOND_REQUEST_ID,
                    )
                ]
            ),
        ]
    )
    recorder = Recorder([True, True])
    service = OrchestrationService(lambda: chatbot, lambda: next(approvals), recorder)

    first = service.start_or_continue("conversation", "reservation A")
    second = service.start_or_continue("conversation", "reservation B")

    assert first["approval_request_id"] == str(REQUEST_ID)
    assert second["approval_request_id"] == str(SECOND_REQUEST_ID)
    assert first["reservation"]["first_name"] == "Ada"
    assert second["reservation"]["first_name"] == "Grace"
    assert second["recording_status"] == "recorded"
    assert [call[1] for call in recorder.calls] == [REQUEST_ID, SECOND_REQUEST_ID]


class PendingThenNewReservationChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, message: str) -> str:
        self.calls += 1
        if self.calls == 1:
            self.pending_reservation = reservation("Ada")
            return "reservation complete"
        self.active_session = object()
        return "First name?"


def test_second_reservation_is_blocked_while_first_is_pending() -> None:
    chatbot = PendingThenNewReservationChatbot()
    approval = SequencedApproval([response(ApprovalStatus.PENDING)])
    service = OrchestrationService(lambda: chatbot, lambda: approval, Recorder())
    service.start_or_continue("conversation", "reservation A")

    result = service.start_or_continue("conversation", "reservation B")

    assert result["response"] == (
        "Your current reservation is still waiting for administrator approval. "
        "Please wait for a decision before starting another reservation."
    )
    assert result["approval_request_id"] == str(REQUEST_ID)
    assert result["approval_status"] == "pending"
    assert approval.submissions == 1
    assert chatbot.active_session is None


def test_approved_status_question_returns_latest_result_without_side_effects() -> None:
    chatbot = SequentialReservationChatbot()
    approval = SequencedApproval(
        [response(ApprovalStatus.APPROVED, comment="Use space 42")]
    )
    recorder = Recorder()
    service = OrchestrationService(lambda: chatbot, lambda: approval, recorder)
    service.start_or_continue("status", "reserve parking")

    result = service.start_or_continue("status", "Is my reservation approved?")

    assert result["response"] == (
        "Your reservation has been approved and recorded. "
        f"Request ID: {REQUEST_ID}. Administrator comment: Use space 42"
    )
    assert chatbot.calls == 1
    assert approval.submissions == 1
    assert len(recorder.calls) == 1


def test_rejected_status_question_returns_latest_result_without_new_reservation() -> (
    None
):
    chatbot = SequentialReservationChatbot()
    approval = SequencedApproval(
        [response(ApprovalStatus.REJECTED, comment="Lot full")]
    )
    recorder = Recorder()
    service = OrchestrationService(lambda: chatbot, lambda: approval, recorder)
    service.start_or_continue("status", "reserve parking")

    result = service.start_or_continue("status", "Was my booking rejected?")

    assert result["response"] == (
        f"Your reservation was rejected. Request ID: {REQUEST_ID}. "
        "Administrator comment: Lot full"
    )
    assert chatbot.calls == 1
    assert approval.submissions == 1
    assert recorder.calls == []


def test_pending_status_question_returns_state_without_new_submission() -> None:
    chatbot = SequentialReservationChatbot()
    approval = SequencedApproval([response(ApprovalStatus.PENDING)])
    recorder = Recorder()
    service = OrchestrationService(lambda: chatbot, lambda: approval, recorder)
    service.start_or_continue("status", "reserve parking")

    result = service.start_or_continue(
        "status",
        "What is the status of my reservation?",
    )

    assert result["response"] == (
        "Your reservation is waiting for administrator approval. "
        f"Request ID: {REQUEST_ID}."
    )
    assert chatbot.calls == 1
    assert approval.submissions == 1
    assert approval.refreshes == 0
    assert recorder.calls == []


class CompleteThenConverseChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, message: str) -> str:
        self.calls += 1
        if self.calls == 1:
            self.pending_reservation = reservation()
            return "reservation complete"
        return "Hello!"


def test_latest_completed_result_survives_later_conversation() -> None:
    chatbot = CompleteThenConverseChatbot()
    approval = SequencedApproval([response(ApprovalStatus.APPROVED)])
    recorder = Recorder()
    service = OrchestrationService(lambda: chatbot, lambda: approval, recorder)
    service.start_or_continue("status", "reserve parking")
    service.start_or_continue("status", "hello")

    result = service.start_or_continue("status", "Was my reservation recorded?")

    assert result["response"] == (
        f"Your reservation has been approved and recorded. Request ID: {REQUEST_ID}."
    )
    assert chatbot.calls == 2
    assert approval.submissions == 1
    assert len(recorder.calls) == 1


def assert_primitive_checkpoint_value(value: object) -> None:
    assert not isinstance(value, (Enum, UUID, datetime, Reservation))
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for nested in value.values():
            assert_primitive_checkpoint_value(nested)
        return
    if isinstance(value, list):
        for nested in value:
            assert_primitive_checkpoint_value(nested)
        return
    raise AssertionError(f"non-primitive checkpoint value: {type(value)!r}")


def test_strict_checkpoint_contains_only_primitive_workflow_state() -> None:
    checkpointer = InMemorySaver(
        serde=JsonPlusSerializer(
            pickle_fallback=False,
            allowed_msgpack_modules=(),
        )
    )
    approval = SequencedApproval(
        [response(ApprovalStatus.PENDING), response(ApprovalStatus.APPROVED)]
    )
    service = OrchestrationService(
        lambda: CompletingChatbot(reservation()),
        lambda: approval,
        Recorder(),
        checkpointer=checkpointer,
    )

    pending = service.start_or_continue("primitive", "complete")
    resumed = service.refresh_approval("primitive")
    checkpoint = checkpointer.get_tuple(
        {"configurable": {"thread_id": "primitive:reservation:1"}}
    )

    assert pending["approval_status"] == "pending"
    assert resumed["recording_status"] == "recorded"
    assert checkpoint is not None
    assert_primitive_checkpoint_value(checkpoint.checkpoint["channel_values"])


def test_checkpoint_domain_values_survive_round_trip() -> None:
    original_reservation = reservation()

    assert (
        reservation_from_checkpoint(reservation_to_checkpoint(original_reservation))
        == original_reservation
    )
    assert uuid_from_checkpoint(uuid_to_checkpoint(REQUEST_ID)) == REQUEST_ID
    assert (
        datetime_from_checkpoint(datetime_to_checkpoint(APPROVAL_TIME)) == APPROVAL_TIME
    )


def test_malformed_serialized_reservation_is_handled_safely() -> None:
    approval = SequencedApproval([response(ApprovalStatus.PENDING)])
    node = AdministratorNode(approval)

    result = node(
        {
            "reservation": {  # type: ignore[typeddict-item]
                "first_name": "Ada",
                "last_name": "Lovelace",
            }
        }
    )

    assert result == {
        "route": "end",
        "error": "completed reservation data is invalid",
    }
    assert approval.submissions == 0


@pytest.mark.parametrize(
    "invalid_value",
    ["not-a-uuid", "2026-08-06T10:30:00", {"unexpected": "data"}],
)
def test_invalid_checkpoint_values_raise_safe_errors(invalid_value: object) -> None:
    with pytest.raises(OrchestrationCheckpointError):
        if isinstance(invalid_value, dict):
            reservation_from_checkpoint(invalid_value)
        elif isinstance(invalid_value, str) and "T" in invalid_value:
            datetime_from_checkpoint(invalid_value)
        else:
            uuid_from_checkpoint(invalid_value)


def test_checkpoint_subprocess_has_no_unregistered_type_warning() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = """
from langgraph.checkpoint.memory import InMemorySaver
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.orchestration import OrchestrationService
from tests.test_orchestration_persistence import (
    CompletingChatbot, Recorder, SequencedApproval, reservation, response,
)
saver = InMemorySaver()
service = OrchestrationService(
    lambda: CompletingChatbot(reservation()),
    lambda: SequencedApproval([response(ApprovalStatus.PENDING)]),
    Recorder(),
    checkpointer=saver,
)
service.start_or_continue("smoke", "complete")
service.get_state("smoke")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Deserializing unregistered type" not in result.stderr
