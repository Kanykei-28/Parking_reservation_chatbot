from datetime import datetime
from typing import cast
from uuid import UUID

from parking_chatbot.admin.models import ApprovalStatus
from parking_chatbot.chatbot import Reservation
from parking_chatbot.orchestration.state import (
    CheckpointApprovalStatus,
    ReservationCheckpointData,
)


class OrchestrationCheckpointError(RuntimeError):
    """A safe error raised for invalid checkpoint data."""


def reservation_to_checkpoint(
    reservation: Reservation,
) -> ReservationCheckpointData:
    values = {
        "first_name": reservation.first_name,
        "last_name": reservation.last_name,
        "car_number": reservation.car_number,
        "parking_type": reservation.parking_type,
        "start_datetime": reservation.start_datetime,
        "end_datetime": reservation.end_datetime,
    }
    if any(not isinstance(value, str) for value in values.values()):
        raise OrchestrationCheckpointError("reservation checkpoint data is invalid")
    return cast(ReservationCheckpointData, values)


def reservation_from_checkpoint(data: object) -> Reservation:
    if not isinstance(data, dict):
        raise OrchestrationCheckpointError("reservation checkpoint data is invalid")
    field_names = (
        "first_name",
        "last_name",
        "car_number",
        "parking_type",
        "start_datetime",
        "end_datetime",
    )
    if set(data) != set(field_names) or any(
        not isinstance(data.get(field_name), str) or not data[field_name].strip()
        for field_name in field_names
    ):
        raise OrchestrationCheckpointError("reservation checkpoint data is invalid")
    try:
        return Reservation(**{name: data[name] for name in field_names})
    except (TypeError, ValueError) as error:
        raise OrchestrationCheckpointError(
            "reservation checkpoint data is invalid"
        ) from error


def uuid_to_checkpoint(value: UUID) -> str:
    return str(value)


def uuid_from_checkpoint(value: object) -> UUID:
    if not isinstance(value, str):
        raise OrchestrationCheckpointError("approval request ID is invalid")
    try:
        return UUID(value)
    except ValueError as error:
        raise OrchestrationCheckpointError("approval request ID is invalid") from error


def datetime_to_checkpoint(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OrchestrationCheckpointError("approval timestamp is invalid")
    return value.isoformat()


def datetime_from_checkpoint(value: object) -> datetime:
    if not isinstance(value, str):
        raise OrchestrationCheckpointError("approval timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise OrchestrationCheckpointError("approval timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrchestrationCheckpointError("approval timestamp is invalid")
    return parsed


def approval_status_to_checkpoint(
    status: ApprovalStatus,
) -> CheckpointApprovalStatus:
    return status.value


def approval_status_from_checkpoint(value: object) -> ApprovalStatus:
    if not isinstance(value, str):
        raise OrchestrationCheckpointError("approval status is invalid")
    try:
        return ApprovalStatus(value)
    except ValueError as error:
        raise OrchestrationCheckpointError("approval status is invalid") from error
