import asyncio
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ValidationError

from parking_chatbot.processing import ConfirmedReservation

WRITE_TOOL_NAME = "write_confirmed_reservation"
INVALID_RESULT_MESSAGE = "confirmed reservation server returned an invalid result"

TransportFactory = Callable[..., AbstractAsyncContextManager[tuple[Any, Any]]]
SessionFactory = Callable[..., AbstractAsyncContextManager[Any]]


class ConfirmedReservationWriteResult(BaseModel):
    approval_request_id: UUID
    stored: bool
    message: str


class ConfirmedReservationMCPError(RuntimeError):
    pass


class ConfirmedReservationMCPClient:
    def __init__(
        self,
        *,
        command: str | None = None,
        arguments: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None,
        transport_factory: TransportFactory = stdio_client,
        session_factory: SessionFactory = ClientSession,
    ) -> None:
        self._closed = False
        self._server_parameters = StdioServerParameters(
            command=command or sys.executable,
            args=list(arguments or ("-m", "parking_chatbot.mcp_server.server")),
            env=dict(environment) if environment is not None else None,
        )
        self._transport_factory = transport_factory
        self._session_factory = session_factory

    async def write_confirmed_reservation(
        self,
        reservation: ConfirmedReservation,
        approval_status: str = "approved",
    ) -> ConfirmedReservationWriteResult:
        if self._closed:
            raise ConfirmedReservationMCPError(
                "confirmed reservation MCP client is closed"
            )
        arguments = {
            "approval_request_id": str(reservation.approval_request_id),
            "approval_status": approval_status,
            "first_name": reservation.first_name,
            "last_name": reservation.last_name,
            "car_number": reservation.car_number,
            "start_datetime": reservation.start_datetime,
            "end_datetime": reservation.end_datetime,
            "approval_time": reservation.approval_time.isoformat(),
        }
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as server_stderr:
            try:
                async with (
                    self._transport_factory(
                        self._server_parameters,
                        errlog=server_stderr,
                    ) as streams,
                    self._session_factory(*streams) as session,
                ):
                    await session.initialize()
                    tools = await session.list_tools()
                    if not any(tool.name == WRITE_TOOL_NAME for tool in tools.tools):
                        raise ConfirmedReservationMCPError(
                            "confirmed reservation server is missing its write tool"
                        )

                    result = await session.call_tool(WRITE_TOOL_NAME, arguments)
                    if result.isError:
                        raise ConfirmedReservationMCPError(
                            "confirmed reservation server rejected the request"
                        )
                    if result.structuredContent is None:
                        raise ConfirmedReservationMCPError(INVALID_RESULT_MESSAGE)
                    try:
                        return ConfirmedReservationWriteResult.model_validate(
                            result.structuredContent
                        )
                    except ValidationError as error:
                        raise ConfirmedReservationMCPError(
                            INVALID_RESULT_MESSAGE
                        ) from error
            except ConfirmedReservationMCPError:
                raise
            except Exception as error:
                raise ConfirmedReservationMCPError(
                    "could not communicate with confirmed reservation server"
                ) from error

    def write_confirmed_reservation_sync(
        self,
        reservation: ConfirmedReservation,
        approval_status: str = "approved",
    ) -> ConfirmedReservationWriteResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.write_confirmed_reservation(reservation, approval_status)
            )
        raise ConfirmedReservationMCPError(
            "synchronous confirmed reservation processing is unavailable"
        )

    def close(self) -> None:
        self._closed = True
