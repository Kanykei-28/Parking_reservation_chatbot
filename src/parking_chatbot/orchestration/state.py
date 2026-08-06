from typing import Literal, TypedDict

WorkflowRoute = Literal["end", "administrator", "recording"]
WorkflowOperation = Literal["user_turn", "refresh_approval"]
CheckpointApprovalStatus = Literal["pending", "approved", "rejected"]
RecordingStatus = Literal["recorded", "already_recorded", "failed"]


class ReservationCheckpointData(TypedDict):
    first_name: str
    last_name: str
    car_number: str
    parking_type: str
    start_datetime: str
    end_datetime: str


class OrchestrationState(TypedDict, total=False):
    operation: WorkflowOperation
    user_message: str
    response: str
    route: WorkflowRoute
    reservation: ReservationCheckpointData
    approval_request_id: str
    approval_status: CheckpointApprovalStatus
    approval_time: str
    administrator_comment: str
    recording_status: RecordingStatus
    error: str | None
