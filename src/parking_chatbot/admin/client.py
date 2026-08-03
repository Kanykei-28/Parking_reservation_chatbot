from dataclasses import asdict
from uuid import UUID

import httpx
from pydantic import ValidationError

from parking_chatbot.admin.api import ApprovalRequestResponse
from parking_chatbot.chatbot.reservation import Reservation


class AdministratorServiceError(RuntimeError):
    pass


class ApprovalRequestNotFoundClientError(AdministratorServiceError):
    pass


class AdministratorApprovalClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            transport=transport,
            timeout=timeout,
        )

    def submit_reservation(
        self,
        reservation: Reservation,
    ) -> ApprovalRequestResponse:
        return self._request(
            "POST",
            "/approval-requests",
            json=asdict(reservation),
        )

    def get_approval_request(self, request_id: UUID) -> ApprovalRequestResponse:
        return self._request("GET", f"/approval-requests/{request_id}")

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, str | None] | None = None,
    ) -> ApprovalRequestResponse:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as error:
            raise AdministratorServiceError(
                f"administrator approval service request failed: {error}"
            ) from error

        if response.status_code == 404:
            raise ApprovalRequestNotFoundClientError(
                "approval request was not found by the administrator service"
            )
        if response.is_error:
            raise AdministratorServiceError(
                "administrator approval service returned "
                f"HTTP {response.status_code}: {response.text}"
            )

        try:
            return ApprovalRequestResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise AdministratorServiceError(
                "administrator approval service returned an invalid response"
            ) from error
