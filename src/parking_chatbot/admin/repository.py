from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from parking_chatbot.admin.models import ApprovalRequest
from parking_chatbot.chatbot.reservation import Reservation


class ApprovalRequestNotFoundError(KeyError):
    pass


class InMemoryApprovalRequestRepository:
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._requests: dict[UUID, ApprovalRequest] = {}
        self._now = now

    def create(self, reservation: Reservation) -> ApprovalRequest:
        request = ApprovalRequest(reservation=reservation)
        self.add(request)
        return request

    def add(self, request: ApprovalRequest) -> None:
        if request.request_id in self._requests:
            raise ValueError(f"approval request {request.request_id} already exists")
        self._requests[request.request_id] = request

    def get(self, request_id: UUID) -> ApprovalRequest:
        try:
            return self._requests[request_id]
        except KeyError as error:
            raise ApprovalRequestNotFoundError(
                f"approval request {request_id} does not exist"
            ) from error

    def list(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    def approve(
        self,
        request_id: UUID,
        administrator_comment: str | None = None,
    ) -> ApprovalRequest:
        request = self.get(request_id)
        request.approve(administrator_comment, decided_at=self._current_time())
        return request

    def reject(
        self,
        request_id: UUID,
        administrator_comment: str | None = None,
    ) -> ApprovalRequest:
        request = self.get(request_id)
        request.reject(administrator_comment, decided_at=self._current_time())
        return request

    def _current_time(self) -> datetime | None:
        return self._now() if self._now is not None else None
