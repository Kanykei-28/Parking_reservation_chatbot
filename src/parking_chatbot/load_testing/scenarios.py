import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from parking_chatbot.admin.api import ApprovalRequestResponse, create_admin_app
from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.admin.repository import InMemoryApprovalRequestRepository
from parking_chatbot.chatbot import Reservation
from parking_chatbot.load_testing.metrics import ScenarioMetrics
from parking_chatbot.mcp_server.server import create_reservation_mcp_server
from parking_chatbot.orchestration import OrchestrationService
from parking_chatbot.processing import (
    ConfirmedReservation,
    ConfirmedReservationFileRepository,
)

Operation = Callable[[int], bool]


def _run_concurrently(
    scenario: str,
    operations: int,
    workers: int,
    operation: Operation,
) -> ScenarioMetrics:
    if operations <= 0 or workers <= 0:
        raise ValueError("operations and workers must be positive")

    def measured(index: int) -> tuple[float, bool]:
        started = perf_counter()
        try:
            successful = operation(index)
        except Exception:
            successful = False
        return perf_counter() - started, successful

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        outcomes = list(executor.map(measured, range(operations)))
    elapsed = perf_counter() - started
    return ScenarioMetrics.calculate(
        scenario,
        [latency for latency, _successful in outcomes],
        [successful for _latency, successful in outcomes],
        elapsed,
    )


class _EchoChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def chat(self, message: str) -> str:
        return f"handled:{message}"


class _UnusedApproval:
    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        raise RuntimeError("unexpected approval submission")

    def refresh(self) -> ApprovalRequestResponse:
        raise RuntimeError("unexpected approval refresh")


class _UnusedRecorder:
    def record(
        self,
        reservation: Reservation,
        approval_request_id: UUID,
        approval_time: datetime,
    ) -> bool:
        raise RuntimeError("unexpected recording")


def run_chatbot_scenario(
    operations: int = 20,
    workers: int = 4,
) -> ScenarioMetrics:
    service = OrchestrationService(_EchoChatbot, _UnusedApproval, _UnusedRecorder())

    def interact(index: int) -> bool:
        thread_id = f"chatbot-{index}"
        message = f"message-{index}"
        state = service.start_or_continue(thread_id, message)
        return (
            state.get("user_message") == message
            and state.get("response") == f"handled:{message}"
            and service.get_state(thread_id).get("user_message") == message
        )

    return _run_concurrently("Chatbot", operations, workers, interact)


def _reservation_payload(index: int) -> dict[str, str]:
    return {
        "first_name": f"User{index}",
        "last_name": "LoadTest",
        "car_number": f"LOAD-{index:05d}",
        "parking_type": "covered",
        "start_datetime": "2026-08-06T09:00",
        "end_datetime": "2026-08-06T17:00",
    }


def run_administrator_scenario(
    operations: int = 20,
    workers: int = 4,
) -> ScenarioMetrics:
    repository = InMemoryApprovalRequestRepository()
    app = create_admin_app(repository)
    request_ids: set[str] = set()
    request_ids_lock = Lock()

    def submit_decide_retrieve(index: int) -> bool:
        with TestClient(app) as client:
            created = client.post(
                "/approval-requests",
                json=_reservation_payload(index),
            )
            if created.status_code != 201:
                return False
            request_id = created.json()["request_id"]
            decision = client.post(
                f"/approval-requests/{request_id}/approve",
                json={"administrator_comment": f"approved-{index}"},
            )
            retrieved = client.get(f"/approval-requests/{request_id}")
        with request_ids_lock:
            if request_id in request_ids:
                return False
            request_ids.add(request_id)
        return bool(
            decision.status_code == 200
            and retrieved.status_code == 200
            and retrieved.json()["status"] == "approved"
            and retrieved.json()["administrator_comment"] == f"approved-{index}"
        )

    metrics = _run_concurrently(
        "Administrator",
        operations,
        workers,
        submit_decide_retrieve,
    )
    if len(request_ids) != metrics.successful_operations:
        raise RuntimeError("administrator scenario request IDs were not isolated")
    return metrics


def _confirmed_reservation(index: int, request_id: UUID) -> ConfirmedReservation:
    return ConfirmedReservation(
        approval_request_id=request_id,
        first_name=f"User{index}",
        last_name="LoadTest",
        car_number=f"LOAD-{index:05d}",
        start_datetime="2026-08-06T09:00",
        end_datetime="2026-08-06T17:00",
        approval_time=datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
    )


def run_mcp_storage_scenario(
    operations: int = 20,
    workers: int = 4,
    *,
    output_path: Path | None = None,
) -> ScenarioMetrics:
    temporary_directory: TemporaryDirectory[str] | None = None
    if output_path is None:
        temporary_directory = TemporaryDirectory()
        output_path = Path(temporary_directory.name) / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    server = create_reservation_mcp_server(repository)

    def store(index: int) -> bool:
        confirmed = _confirmed_reservation(index, uuid4())
        arguments = {
            "approval_request_id": confirmed.approval_request_id,
            "approval_status": "approved",
            "first_name": confirmed.first_name,
            "last_name": confirmed.last_name,
            "car_number": confirmed.car_number,
            "start_datetime": confirmed.start_datetime,
            "end_datetime": confirmed.end_datetime,
            "approval_time": confirmed.approval_time,
        }

        def call_tool() -> dict[str, object]:
            result = asyncio.run(
                server.call_tool("write_confirmed_reservation", arguments)
            )
            structured = result[1] if isinstance(result, tuple) else result
            if not isinstance(structured, dict):
                raise RuntimeError("MCP storage scenario returned invalid data")
            return cast(dict[str, object], structured)

        return call_tool().get("stored") is True and call_tool().get("stored") is False

    try:
        metrics = _run_concurrently("MCP Storage", operations, workers, store)
        line_count = (
            len(output_path.read_text(encoding="utf-8").splitlines())
            if output_path.exists()
            else 0
        )
        if line_count != metrics.successful_operations:
            raise RuntimeError("MCP storage scenario produced unexpected records")
        return metrics
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()


class _CompletingChatbot:
    active_session: object | None = None
    pending_reservation: Reservation | None = None

    def __init__(self, reservation: Reservation) -> None:
        self._reservation = reservation

    def chat(self, message: str) -> str:
        self.pending_reservation = self._reservation
        return "reservation complete"


class _ApprovingCoordinator:
    def __init__(self) -> None:
        self._request_id = uuid4()

    def submit(self, reservation: Reservation) -> ApprovalRequestResponse:
        return ApprovalRequestResponse.model_validate(
            {
                "request_id": self._request_id,
                "reservation": reservation,
                "status": ApprovalStatus.APPROVED,
                "created_at": datetime.now(UTC),
                "decision_at": datetime.now(UTC),
                "administrator_comment": "load-test approved",
            }
        )

    def refresh(self) -> ApprovalRequestResponse:
        raise RuntimeError("unexpected approval refresh")


class _FileRecorder:
    def __init__(self, repository: ConfirmedReservationFileRepository) -> None:
        self._repository = repository

    def record(
        self,
        reservation: Reservation,
        approval_request_id: UUID,
        approval_time: datetime,
    ) -> bool:
        assert reservation.first_name is not None
        assert reservation.last_name is not None
        assert reservation.car_number is not None
        assert reservation.start_datetime is not None
        assert reservation.end_datetime is not None
        return self._repository.append(
            ConfirmedReservation(
                approval_request_id=approval_request_id,
                first_name=reservation.first_name,
                last_name=reservation.last_name,
                car_number=reservation.car_number,
                start_datetime=reservation.start_datetime,
                end_datetime=reservation.end_datetime,
                approval_time=approval_time,
            )
        )


def run_end_to_end_scenario(
    operations: int = 20,
    workers: int = 4,
    *,
    output_path: Path | None = None,
) -> ScenarioMetrics:
    temporary_directory: TemporaryDirectory[str] | None = None
    if output_path is None:
        temporary_directory = TemporaryDirectory()
        output_path = Path(temporary_directory.name) / "orchestrated.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    factory_lock = Lock()
    next_index = 0

    def chatbot_factory() -> _CompletingChatbot:
        nonlocal next_index
        with factory_lock:
            index = next_index
            next_index += 1
        return _CompletingChatbot(Reservation(**_reservation_payload(index)))

    service = OrchestrationService(
        chatbot_factory,
        _ApprovingCoordinator,
        _FileRecorder(repository),
    )
    request_ids: set[str] = set()
    ids_lock = Lock()

    def orchestrate(index: int) -> bool:
        state = service.start_or_continue(f"end-to-end-{index}", "reserve")
        request_id = state.get("approval_request_id")
        if request_id is None:
            return False
        with ids_lock:
            if request_id in request_ids:
                return False
            request_ids.add(request_id)
        return (
            state.get("approval_status") == "approved"
            and state.get("recording_status") == "recorded"
            and state.get("reservation", {}).get("car_number") is not None
        )

    try:
        metrics = _run_concurrently("End-to-End", operations, workers, orchestrate)
        line_count = (
            len(output_path.read_text(encoding="utf-8").splitlines())
            if output_path.exists()
            else 0
        )
        if line_count != metrics.successful_operations:
            raise RuntimeError("end-to-end scenario produced unexpected records")
        return metrics
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()


def run_all_scenarios(
    operations: int = 20,
    workers: int = 4,
) -> list[ScenarioMetrics]:
    return [
        run_chatbot_scenario(operations, workers),
        run_administrator_scenario(operations, workers),
        run_mcp_storage_scenario(operations, workers),
        run_end_to_end_scenario(operations, workers),
    ]
