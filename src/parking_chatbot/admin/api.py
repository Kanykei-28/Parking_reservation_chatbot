import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from parking_chatbot.admin.errors import ConfirmedReservationProcessingError
from parking_chatbot.admin.models import (
    ApprovalAlreadyDecidedError,
    ApprovalRequest,
    ApprovalStatus,
)
from parking_chatbot.admin.processing import ApprovedReservationProcessor
from parking_chatbot.admin.repository import (
    ApprovalRequestNotFoundError,
    InMemoryApprovalRequestRepository,
)
from parking_chatbot.chatbot.reservation import Reservation

logger = logging.getLogger(__name__)


class ReservationSubmissionRequest(BaseModel):
    first_name: str
    last_name: str
    car_number: str
    parking_type: str
    start_datetime: str
    end_datetime: str


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str | None
    last_name: str | None
    car_number: str | None
    parking_type: str | None
    start_datetime: str | None
    end_datetime: str | None


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: UUID
    reservation: ReservationResponse
    status: ApprovalStatus
    created_at: datetime
    decision_at: datetime | None
    administrator_comment: str | None


class ApprovalDecisionRequest(BaseModel):
    administrator_comment: str | None = None


def create_admin_app(
    repository: InMemoryApprovalRequestRepository | None = None,
    approved_reservation_processor: ApprovedReservationProcessor | None = None,
) -> FastAPI:
    app = FastAPI(title="Parking Reservation Administration API")
    app_repository = repository or InMemoryApprovalRequestRepository()

    def get_repository() -> InMemoryApprovalRequestRepository:
        return app_repository

    @app.post(
        "/approval-requests",
        response_model=ApprovalRequestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_approval_request(
        reservation_data: ReservationSubmissionRequest,
        repository: Annotated[
            InMemoryApprovalRequestRepository, Depends(get_repository)
        ],
    ) -> ApprovalRequest:
        reservation = Reservation(**reservation_data.model_dump())
        return repository.create(reservation)

    @app.get("/approval-requests", response_model=list[ApprovalRequestResponse])
    def list_approval_requests(
        repository: Annotated[
            InMemoryApprovalRequestRepository, Depends(get_repository)
        ],
        approval_status: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    ) -> list[ApprovalRequest]:
        requests = repository.list()
        if approval_status is None:
            return requests
        return [request for request in requests if request.status is approval_status]

    @app.get(
        "/approval-requests/{request_id}",
        response_model=ApprovalRequestResponse,
    )
    def get_approval_request(
        request_id: UUID,
        repository: Annotated[
            InMemoryApprovalRequestRepository, Depends(get_repository)
        ],
    ) -> ApprovalRequest:
        return _get_request(repository, request_id)

    @app.post(
        "/approval-requests/{request_id}/approve",
        response_model=ApprovalRequestResponse,
    )
    def approve_approval_request(
        request_id: UUID,
        repository: Annotated[
            InMemoryApprovalRequestRepository, Depends(get_repository)
        ],
        decision: ApprovalDecisionRequest | None = None,
    ) -> ApprovalRequest:
        comment = decision.administrator_comment if decision is not None else None
        try:
            approved_request = repository.approve(request_id, comment)
        except ApprovalRequestNotFoundError as error:
            raise _not_found(request_id) from error
        except ApprovalAlreadyDecidedError as error:
            raise _already_decided(error) from error
        if approved_reservation_processor is not None:
            try:
                approved_reservation_processor.process(approved_request)
            except ConfirmedReservationProcessingError:
                logger.error("Approved reservation processing failed")
        return approved_request

    @app.post(
        "/approval-requests/{request_id}/reject",
        response_model=ApprovalRequestResponse,
    )
    def reject_approval_request(
        request_id: UUID,
        repository: Annotated[
            InMemoryApprovalRequestRepository, Depends(get_repository)
        ],
        decision: ApprovalDecisionRequest | None = None,
    ) -> ApprovalRequest:
        comment = decision.administrator_comment if decision is not None else None
        try:
            return repository.reject(request_id, comment)
        except ApprovalRequestNotFoundError as error:
            raise _not_found(request_id) from error
        except ApprovalAlreadyDecidedError as error:
            raise _already_decided(error) from error

    return app


def _get_request(
    repository: InMemoryApprovalRequestRepository,
    request_id: UUID,
) -> ApprovalRequest:
    try:
        return repository.get(request_id)
    except ApprovalRequestNotFoundError as error:
        raise _not_found(request_id) from error


def _not_found(request_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"approval request {request_id} does not exist",
    )


def _already_decided(error: ApprovalAlreadyDecidedError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(error),
    )


app = create_admin_app()
