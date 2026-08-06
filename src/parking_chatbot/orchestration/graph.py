from typing import Literal
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from parking_chatbot.orchestration.nodes import (
    AdministratorNode,
    ConfirmedReservationRecorder,
    RecordingNode,
    UserInteractionNode,
)
from parking_chatbot.orchestration.state import OrchestrationState


OrchestrationGraph = CompiledStateGraph[
    OrchestrationState,
    None,
    OrchestrationState,
    OrchestrationState,]

def route_at_entry(
    state: OrchestrationState,
) -> Literal["user_interaction", "administrator", "end"]:
    if state.get("operation") != "refresh_approval":
        return "user_interaction"
    if state.get("recording_status") in {
        "recorded",
        "already_recorded",
    }:
        return "end"
    if state.get("approval_status") == "rejected":
        return "end"
    return "administrator"


def route_after_user(
    state: OrchestrationState,
) -> Literal["administrator", "end"]:
    if state.get("route") == "administrator":
        return "administrator"
    return "end"


def route_after_administrator(
    state: OrchestrationState,
) -> Literal["recording", "end"]:
    if state.get("route") == "recording":
        return "recording"
    return "end"


def create_orchestration_graph(
    user_node: UserInteractionNode,
    administrator_node: AdministratorNode,
    recorder: ConfirmedReservationRecorder,
    *,
    checkpointer: InMemorySaver | None = None,
) -> OrchestrationGraph:
    builder = StateGraph(OrchestrationState)
    builder.add_node("user_interaction", user_node)
    builder.add_node("administrator", administrator_node)
    builder.add_node("recording", RecordingNode(recorder))

    builder.add_conditional_edges(
        START,
        route_at_entry,
        {
            "user_interaction": "user_interaction",
            "administrator": "administrator",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "user_interaction",
        route_after_user,
        {"administrator": "administrator", "end": END},
    )
    builder.add_conditional_edges(
        "administrator",
        route_after_administrator,
        {"recording": "recording", "end": END},
    )
    builder.add_edge("recording", END)
    return builder.compile(checkpointer=checkpointer)
