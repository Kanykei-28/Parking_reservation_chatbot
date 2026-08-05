import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from mcp import StdioServerParameters

from parking_chatbot.mcp_client import (
    ConfirmedReservationMCPClient,
    ConfirmedReservationMCPError,
)
from parking_chatbot.processing import ConfirmedReservation

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")


def confirmed_reservation() -> ConfirmedReservation:
    return ConfirmedReservation(
        approval_request_id=REQUEST_ID,
        first_name="Ada",
        last_name="Lovelace",
        car_number="ABC-123",
        start_datetime="2026-08-05T09:00",
        end_datetime="2026-08-05T17:00",
        approval_time=datetime(2026, 8, 4, 10, 30, tzinfo=UTC),
    )


class FakeSession:
    def __init__(
        self,
        *,
        tool_names: tuple[str, ...] = ("write_confirmed_reservation",),
        structured_content: dict[str, object] | None = None,
        is_error: bool = False,
    ) -> None:
        self.tool_names = tool_names
        self.structured_content = structured_content or {
            "approval_request_id": str(REQUEST_ID),
            "stored": True,
            "message": "confirmed reservation stored",
        }
        self.is_error = is_error
        self.initialized = False
        self.closed = False
        self.called_name: str | None = None
        self.called_arguments: dict[str, object] | None = None

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def initialize(self) -> None:
        self.initialized = True

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(
            tools=[SimpleNamespace(name=name) for name in self.tool_names]
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> SimpleNamespace:
        self.called_name = name
        self.called_arguments = arguments
        return SimpleNamespace(
            isError=self.is_error,
            structuredContent=self.structured_content,
        )


class FakeRuntime:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.parameters: StdioServerParameters | None = None
        self.transport_closed = False

    @asynccontextmanager
    async def transport(
        self,
        parameters: StdioServerParameters,
        **_kwargs: object,
    ) -> AsyncIterator[tuple[object, object]]:
        self.parameters = parameters
        try:
            yield object(), object()
        finally:
            self.transport_closed = True

    def session_factory(self, *_streams: object) -> FakeSession:
        return self.session


def make_client(runtime: FakeRuntime) -> ConfirmedReservationMCPClient:
    return ConfirmedReservationMCPClient(
        transport_factory=runtime.transport,
        session_factory=runtime.session_factory,
    )


@pytest.mark.anyio
async def test_client_uses_current_python_and_initializes_session() -> None:
    runtime = FakeRuntime(FakeSession())

    await make_client(runtime).write_confirmed_reservation(confirmed_reservation())

    assert runtime.parameters is not None
    assert runtime.parameters.command == sys.executable
    assert runtime.parameters.args == [
        "-m",
        "parking_chatbot.mcp_server.server",
    ]
    assert runtime.session.initialized


@pytest.mark.anyio
async def test_client_calls_tool_with_all_reservation_fields() -> None:
    runtime = FakeRuntime(FakeSession())

    result = await make_client(runtime).write_confirmed_reservation(
        confirmed_reservation()
    )

    assert runtime.session.called_name == "write_confirmed_reservation"
    assert runtime.session.called_arguments == {
        "approval_request_id": str(REQUEST_ID),
        "approval_status": "approved",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "car_number": "ABC-123",
        "start_datetime": "2026-08-05T09:00",
        "end_datetime": "2026-08-05T17:00",
        "approval_time": "2026-08-04T10:30:00+00:00",
    }
    assert result.approval_request_id == REQUEST_ID
    assert result.stored is True


@pytest.mark.anyio
async def test_client_parses_idempotent_result() -> None:
    session = FakeSession(
        structured_content={
            "approval_request_id": str(REQUEST_ID),
            "stored": False,
            "message": "confirmed reservation already stored",
        }
    )

    result = await make_client(FakeRuntime(session)).write_confirmed_reservation(
        confirmed_reservation()
    )

    assert result.stored is False
    assert result.message == "confirmed reservation already stored"


@pytest.mark.anyio
async def test_client_rejects_missing_tool_and_closes_resources() -> None:
    runtime = FakeRuntime(FakeSession(tool_names=()))

    with pytest.raises(ConfirmedReservationMCPError, match="missing its write tool"):
        await make_client(runtime).write_confirmed_reservation(confirmed_reservation())

    assert runtime.session.closed
    assert runtime.transport_closed


@pytest.mark.anyio
async def test_client_maps_tool_error_safely() -> None:
    private_detail = "/private/secret/server-error"
    runtime = FakeRuntime(FakeSession(is_error=True))

    with pytest.raises(
        ConfirmedReservationMCPError,
        match="server rejected the request",
    ) as caught:
        await make_client(runtime).write_confirmed_reservation(confirmed_reservation())

    assert private_detail not in str(caught.value)


@pytest.mark.anyio
async def test_client_rejects_malformed_structured_result() -> None:
    runtime = FakeRuntime(FakeSession(structured_content={"stored": "not-a-bool"}))

    with pytest.raises(ConfirmedReservationMCPError, match="invalid result"):
        await make_client(runtime).write_confirmed_reservation(confirmed_reservation())


@pytest.mark.anyio
async def test_client_maps_transport_error_without_private_details() -> None:
    private_path = "/private/secret/server-binary"

    @asynccontextmanager
    async def failing_transport(
        _parameters: StdioServerParameters,
        **_kwargs: object,
    ) -> AsyncIterator[tuple[Any, Any]]:
        raise OSError(f"could not start {private_path}")
        yield object(), object()

    client = ConfirmedReservationMCPClient(transport_factory=failing_transport)

    with pytest.raises(
        ConfirmedReservationMCPError,
        match="^could not communicate with confirmed reservation server$",
    ) as caught:
        await client.write_confirmed_reservation(confirmed_reservation())

    assert private_path not in str(caught.value)
    assert isinstance(caught.value.__cause__, OSError)


@pytest.mark.anyio
async def test_real_stdio_server_writes_to_configured_temporary_file(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "confirmed.txt"
    client = ConfirmedReservationMCPClient(
        environment={"CONFIRMED_RESERVATIONS_PATH": str(output_path)}
    )

    result = await client.write_confirmed_reservation(confirmed_reservation())

    assert result.stored is True
    assert output_path.read_text(encoding="utf-8") == (
        "Ada Lovelace | ABC-123 | 2026-08-05T09:00–2026-08-05T17:00 | "
        "2026-08-04T10:30:00+00:00\n"
    )
