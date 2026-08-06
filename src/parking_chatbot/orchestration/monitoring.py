from collections.abc import Callable
from threading import Event, Lock, Thread, current_thread
from typing import Protocol

from parking_chatbot.orchestration.state import OrchestrationState

SAFE_MONITOR_ERROR = (
    "Reservation status monitoring stopped because the workflow could not be "
    "refreshed safely."
)


class ApprovalRefresher(Protocol):
    def refresh_approval(self, thread_id: str) -> OrchestrationState: ...


class ApprovalMonitor:
    """Poll pending workflows and publish a terminal result exactly once."""

    def __init__(
        self,
        orchestration: ApprovalRefresher,
        output: Callable[[str], None],
        *,
        interval_seconds: float = 2.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("monitor interval must be positive")
        self._orchestration = orchestration
        self._output = output
        self._interval_seconds = interval_seconds
        self._lock = Lock()
        self._monitors: dict[str, tuple[Thread, Event]] = {}
        self._closed = False

    def start(self, thread_id: str) -> bool:
        with self._lock:
            current = self._monitors.get(thread_id)
            if self._closed or (current is not None and current[0].is_alive()):
                return False
            stop_event = Event()
            thread = Thread(
                target=self._run,
                args=(thread_id, stop_event),
                name=f"approval-monitor-{thread_id}",
                daemon=True,
            )
            self._monitors[thread_id] = (thread, stop_event)
            thread.start()
            return True

    def stop(self, thread_id: str) -> None:
        with self._lock:
            monitored = self._monitors.get(thread_id)
        if monitored is None:
            return
        thread, stop_event = monitored
        stop_event.set()
        if thread is not current_thread():
            thread.join()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            monitored = list(self._monitors.values())
        for _thread, stop_event in monitored:
            stop_event.set()
        for thread, _stop_event in monitored:
            if thread is not current_thread():
                thread.join()

    def is_monitoring(self, thread_id: str) -> bool:
        with self._lock:
            monitored = self._monitors.get(thread_id)
            return monitored is not None and monitored[0].is_alive()

    def _run(self, thread_id: str, stop_event: Event) -> None:
        try:
            while not stop_event.wait(self._interval_seconds):
                try:
                    state = self._orchestration.refresh_approval(thread_id)
                except Exception:
                    self._output(SAFE_MONITOR_ERROR)
                    return
                if state.get("error"):
                    self._output(SAFE_MONITOR_ERROR)
                    return
                if state.get("approval_status") == "pending":
                    continue
                if state.get("approval_status") == "rejected":
                    self._output(state["response"])
                    return
                if state.get("recording_status") in {
                    "recorded",
                    "already_recorded",
                }:
                    self._output(state["response"])
                    return
        finally:
            stop_event.set()
