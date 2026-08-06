from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock, RLock
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.admin.integration import ReservationApprovalIntegration
from parking_chatbot.chatbot import ParkingChatbot
from parking_chatbot.chatbot.intents import Intent, detect_intent
from parking_chatbot.mcp_client import ConfirmedReservationMCPClient
from parking_chatbot.orchestration.graph import (
    OrchestrationGraph,
    create_orchestration_graph,
)
from parking_chatbot.orchestration.nodes import (
    AdministratorNode,
    ApprovalCoordinator,
    ChatbotInteraction,
    ConfirmedReservationRecorder,
    UserInteractionNode,
)
from parking_chatbot.orchestration.recording import MCPConfirmedReservationRecorder
from parking_chatbot.orchestration.state import (
    OrchestrationState,
)


class OrchestrationWorkflowError(RuntimeError):
    """A safe error for invalid orchestration lifecycle operations."""


@dataclass
class _ThreadWorkflow:
    chatbot: ChatbotInteraction | ParkingChatbot
    graph: OrchestrationGraph
    generation: int
    lock: RLock
    latest_completed: OrchestrationState | None = None

    def checkpoint_thread_id(self, public_thread_id: str) -> str:
        return f"{public_thread_id}:reservation:{self.generation}"


class OrchestrationService:
    """Run and resume isolated checkpointed reservation workflows."""

    def __init__(
        self,
        chatbot_factory: Callable[[], ChatbotInteraction | ParkingChatbot],
        approval_factory: Callable[[], ApprovalCoordinator],
        recorder: ConfirmedReservationRecorder,
        *,
        checkpointer: InMemorySaver | None = None,
    ) -> None:
        self._chatbot_factory = chatbot_factory
        self._approval_factory = approval_factory
        self._recorder = recorder
        self._checkpointer = checkpointer or InMemorySaver()
        self._workflows: dict[str, _ThreadWorkflow] = {}
        self._registry_lock = Lock()

    def start_or_continue(
        self,
        thread_id: str,
        message: str,
    ) -> OrchestrationState:
        normalized_id = self._normalize_thread_id(thread_id)
        workflow = self._workflow(normalized_id)
        with workflow.lock:
            current_state = self._state(workflow, normalized_id)
            if detect_intent(message) is Intent.APPROVAL_STATUS:
                status_state = (
                    current_state
                    if current_state.get("approval_request_id") is not None
                    else workflow.latest_completed
                )
                if status_state is not None:
                    return self._with_status_response(status_state)
            if self._is_terminal(current_state):
                workflow.latest_completed = current_state
                self._rotate_workflow(workflow)
            result = cast(
                OrchestrationState,
                workflow.graph.invoke(
                    {
                        "operation": "user_turn",
                        "user_message": message,
                    },
                    config=self._config(workflow.checkpoint_thread_id(normalized_id)),
                ),
            )
            if self._is_terminal(result):
                workflow.latest_completed = result
            return result

    def refresh_approval(self, thread_id: str) -> OrchestrationState:
        normalized_id = self._normalize_thread_id(thread_id)
        workflow = self._get_workflow(normalized_id)
        if workflow is None:
            raise OrchestrationWorkflowError("approval workflow does not exist")
        with workflow.lock:
            if self._state(workflow, normalized_id).get("approval_request_id") is None:
                raise OrchestrationWorkflowError("approval workflow does not exist")
            result = cast(
                OrchestrationState,
                workflow.graph.invoke(
                    {"operation": "refresh_approval"},
                    config=self._config(workflow.checkpoint_thread_id(normalized_id)),
                ),
            )
            if self._is_terminal(result):
                workflow.latest_completed = result
            return result

    def get_state(self, thread_id: str) -> OrchestrationState:
        normalized_id = self._normalize_thread_id(thread_id)
        workflow = self._get_workflow(normalized_id)
        if workflow is None:
            raise OrchestrationWorkflowError("workflow does not exist")
        with workflow.lock:
            return self._state(workflow, normalized_id)

    def _workflow(self, thread_id: str) -> _ThreadWorkflow:
        with self._registry_lock:
            workflow = self._workflows.get(thread_id)
            if workflow is None:
                chatbot = self._chatbot_factory()
                workflow = _ThreadWorkflow(
                    chatbot=chatbot,
                    graph=self._create_graph(chatbot),
                    generation=1,
                    lock=RLock(),
                )
                self._workflows[thread_id] = workflow
            return workflow

    def _get_workflow(self, thread_id: str) -> _ThreadWorkflow | None:
        with self._registry_lock:
            return self._workflows.get(thread_id)

    def _create_graph(
        self,
        chatbot: ChatbotInteraction | ParkingChatbot,
    ) -> OrchestrationGraph:
        return create_orchestration_graph(
            UserInteractionNode(chatbot),
            AdministratorNode(self._approval_factory()),
            self._recorder,
            checkpointer=self._checkpointer,
        )

    def _rotate_workflow(self, workflow: _ThreadWorkflow) -> None:
        workflow.generation += 1
        workflow.graph = self._create_graph(workflow.chatbot)

    def _state(
        self,
        workflow: _ThreadWorkflow,
        public_thread_id: str,
    ) -> OrchestrationState:
        return cast(
            OrchestrationState,
            dict(
                workflow.graph.get_state(
                    self._config(workflow.checkpoint_thread_id(public_thread_id))
                ).values
            ),
        )

    @staticmethod
    def _is_terminal(state: OrchestrationState) -> bool:
        return state.get("approval_status") == "rejected" or state.get(
            "recording_status"
        ) in {"recorded", "already_recorded"}

    @staticmethod
    def _with_status_response(state: OrchestrationState) -> OrchestrationState:
        result = cast(OrchestrationState, dict(state))
        if state.get("recording_status") in {"recorded", "already_recorded"}:
            message = "Your reservation has been approved and recorded."
        elif state.get("approval_status") == "rejected":
            message = "Your reservation was rejected."
        elif state.get("approval_status") == "pending":
            message = "Your reservation is waiting for administrator approval."
        else:
            return result
        request_id = state.get("approval_request_id")
        if request_id:
            message += f" Request ID: {request_id}."
        comment = state.get("administrator_comment")
        if comment:
            message += f" Administrator comment: {comment}"
        result["response"] = message
        return result

    @staticmethod
    def _normalize_thread_id(thread_id: str) -> str:
        normalized_id = thread_id.strip()
        if not normalized_id:
            raise ValueError("thread_id must not be empty")
        return normalized_id

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}


def create_orchestration_service(
    chatbot_factory: Callable[[], ChatbotInteraction | ParkingChatbot],
    approval_gateway_factory: Callable[[], ApprovalGateway],
    confirmed_reservation_client: ConfirmedReservationMCPClient,
    *,
    checkpointer: InMemorySaver | None = None,
) -> OrchestrationService:
    """Compose Stage 4 with Stage 2 approval and graph-owned MCP recording."""
    return OrchestrationService(
        chatbot_factory,
        lambda: ReservationApprovalIntegration(approval_gateway_factory()),
        MCPConfirmedReservationRecorder(confirmed_reservation_client),
        checkpointer=checkpointer,
    )
