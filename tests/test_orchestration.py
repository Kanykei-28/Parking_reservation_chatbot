from datetime import UTC, datetime
from uuid import UUID

import pytest

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import Reservation
from parking_chatbot.orchestration import (
    AdministratorNode,
    UserInteractionNode,
    create_orchestration_graph,
)
from parking_chatbot.orchestration.graph import (
    OrchestrationGraph,
    route_after_administrator,
    route_after_user,
)

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")
DECISION_AT = datetime(2026, 8, 5, 10, 30, tzinfo=UTC)


def reservation() -> Reservation:
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
            "reservation": reservation(),
            "status": status,
            "created_at": datetime(2026, 8, 5, 10, 0, tzinfo=UTC),
            "decision_at": (None if status is ApprovalStatus.PENDING else DECISION_AT),
            "administrator_comment": (
                "Use space 42" if status is ApprovalStatus.APPROVED else None
            ),
        }
    )


class FakeChatbot:
    def __init__(
        self, *, completes_reservation: bool, incomplete: bool = False
    ) -> None:
        self.pending_reservation: Reservation | None = None
        self.active_session: object | None = object() if incomplete else None
        self.completes_reservation = completes_reservation
        self.messages: list[str] = []

    def chat(self, message: str) -> str:
        self.messages.append(message)
        if self.completes_reservation:
            self.pending_reservation = reservation()
            self.active_session = None
        return "existing chatbot response"


class FakeApprovalCoordinator:
    def __init__(self, status: ApprovalStatus) -> None:
        self.result = approval_response(status)
        self.submitted: list[Reservation] = []
        self.refresh_count = 0

    def submit(self, completed_reservation: Reservation) -> ApprovalRequestResponse:
        self.submitted.append(completed_reservation)
        return self.result

    def refresh(self) -> ApprovalRequestResponse:
        self.refresh_count += 1
        return self.result


class FakeRecorder:
    def __init__(self, stored: bool = True) -> None:
        self.stored = stored
        self.calls: list[tuple[Reservation, UUID, datetime]] = []

    def record(
        self,
        completed_reservation: Reservation,
        approval_request_id: UUID,
        approval_time: datetime,
    ) -> bool:
        self.calls.append((completed_reservation, approval_request_id, approval_time))
        return self.stored


def build_graph(
    *,
    completes_reservation: bool,
    approval_status: ApprovalStatus = ApprovalStatus.PENDING,
    incomplete: bool = False,
) -> tuple[
    OrchestrationGraph,
    FakeChatbot,
    FakeApprovalCoordinator,
    FakeRecorder,
]:
    chatbot = FakeChatbot(
        completes_reservation=completes_reservation,
        incomplete=incomplete,
    )
    approval = FakeApprovalCoordinator(approval_status)
    recorder = FakeRecorder()
    graph = create_orchestration_graph(
        UserInteractionNode(chatbot),
        AdministratorNode(approval),
        recorder,
    )
    return graph, chatbot, approval, recorder


def test_graph_contains_expected_nodes_and_edges() -> None:
    graph, _chatbot, _approval, _recorder = build_graph(completes_reservation=False)

    drawable = graph.get_graph()
    assert set(drawable.nodes) == {
        "__start__",
        "user_interaction",
        "administrator",
        "recording",
        "__end__",
    }
    edge_pairs = {(edge.source, edge.target) for edge in drawable.edges}
    assert ("__start__", "user_interaction") in edge_pairs
    assert ("user_interaction", "administrator") in edge_pairs
    assert ("administrator", "recording") in edge_pairs
    assert ("recording", "__end__") in edge_pairs


def test_conditional_routes_are_explicit() -> None:
    assert route_after_user({"route": "administrator"}) == "administrator"
    assert route_after_user({"route": "end"}) == "end"
    assert route_after_administrator({"route": "recording"}) == "recording"
    assert route_after_administrator({"route": "end"}) == "end"


def test_information_path_ends_after_existing_chatbot_node() -> None:
    graph, chatbot, approval, recorder = build_graph(completes_reservation=False)

    result = graph.invoke({"user_message": "Hello"})

    assert result["response"] == "existing chatbot response"
    assert result["route"] == "end"
    assert chatbot.messages == ["Hello"]
    assert approval.submitted == []
    assert recorder.calls == []


def test_incomplete_reservation_ends_for_current_turn() -> None:
    graph, _chatbot, approval, recorder = build_graph(
        completes_reservation=False,
        incomplete=True,
    )

    result = graph.invoke({"user_message": "Ada"})

    assert result["route"] == "end"
    assert approval.submitted == []
    assert recorder.calls == []


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.PENDING, ApprovalStatus.REJECTED],
)
def test_non_approved_reservation_stops_without_recording(
    status: ApprovalStatus,
) -> None:
    graph, _chatbot, approval, recorder = build_graph(
        completes_reservation=True,
        approval_status=status,
    )

    result = graph.invoke({"user_message": "complete"})

    assert len(approval.submitted) == 1
    assert result["approval_status"] == status.value
    assert result["route"] == "end"
    assert recorder.calls == []


def test_approved_reservation_reaches_recording_node_with_existing_data() -> None:
    graph, chatbot, approval, recorder = build_graph(
        completes_reservation=True,
        approval_status=ApprovalStatus.APPROVED,
    )

    result = graph.invoke({"user_message": "complete"})

    assert chatbot.messages == ["complete"]
    assert approval.submitted == [reservation()]
    assert recorder.calls == [(reservation(), REQUEST_ID, DECISION_AT)]
    assert result["approval_request_id"] == str(REQUEST_ID)
    assert result["administrator_comment"] == "Use space 42"
    assert result["recording_status"] == "recorded"
    assert result["route"] == "end"


def test_administrator_node_uses_refresh_for_existing_request() -> None:
    approval = FakeApprovalCoordinator(ApprovalStatus.APPROVED)
    node = AdministratorNode(approval)

    result = node(
        {
            "reservation": {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "car_number": "ABC-123",
                "parking_type": "covered",
                "start_datetime": "2026-08-06T09:00",
                "end_datetime": "2026-08-06T17:00",
            },
            "approval_request_id": str(REQUEST_ID),
        }
    )

    assert approval.refresh_count == 1
    assert approval.submitted == []
    assert result["route"] == "recording"
