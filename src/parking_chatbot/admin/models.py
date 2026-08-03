from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from parking_chatbot.chatbot.reservation import Reservation


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalAlreadyDecidedError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ApprovalRequest:
    reservation: Reservation
    request_id: UUID = field(default_factory=uuid4)
    status: ApprovalStatus = field(default=ApprovalStatus.PENDING, init=False)
    created_at: datetime = field(default_factory=_utc_now)
    decision_at: datetime | None = field(default=None, init=False)
    administrator_comment: str | None = field(default=None, init=False)

    def approve(
        self,
        administrator_comment: str | None = None,
        *,
        decided_at: datetime | None = None,
    ) -> None:
        self._decide(ApprovalStatus.APPROVED, administrator_comment, decided_at)

    def reject(
        self,
        administrator_comment: str | None = None,
        *,
        decided_at: datetime | None = None,
    ) -> None:
        self._decide(ApprovalStatus.REJECTED, administrator_comment, decided_at)

    def _decide(
        self,
        status: ApprovalStatus,
        administrator_comment: str | None,
        decided_at: datetime | None,
    ) -> None:
        if self.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecidedError(
                f"approval request {self.request_id} is already {self.status.value}"
            )

        decision_at = decided_at or _utc_now()
        if decision_at.tzinfo is None or decision_at.utcoffset() is None:
            raise ValueError("decision timestamp must be timezone-aware")

        self.status = status
        self.decision_at = decision_at
        self.administrator_comment = administrator_comment
