import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from parking_chatbot.mcp_server.server import create_reservation_mcp_server
from parking_chatbot.processing import (
    ConfirmedReservationFileRepository,
    ConfirmedReservationStorageError,
)

REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")
APPROVAL_TIME = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)


def tool_arguments(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "approval_request_id": REQUEST_ID,
        "approval_status": "approved",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "car_number": "ABC-123",
        "start_datetime": "2026-08-05T09:00",
        "end_datetime": "2026-08-05T17:00",
        "approval_time": APPROVAL_TIME,
    }
    arguments.update(overrides)
    return arguments


def create_server(output_path: Path) -> FastMCP[None]:
    return create_reservation_mcp_server(
        ConfirmedReservationFileRepository(output_path)
    )


def call_tool(server: FastMCP[None], **overrides: object) -> dict[str, Any]:
    result = asyncio.run(
        server.call_tool("write_confirmed_reservation", tool_arguments(**overrides))
    )
    if isinstance(result, tuple):
        structured_result = result[1]
        assert isinstance(structured_result, dict)
        return structured_result
    assert isinstance(result, dict)
    return result


def test_server_exposes_only_write_tool_without_path_argument(tmp_path: Path) -> None:
    tools = asyncio.run(create_server(tmp_path / "confirmed.txt").list_tools())

    assert [tool.name for tool in tools] == ["write_confirmed_reservation"]
    properties = tools[0].inputSchema["properties"]
    assert "path" not in properties
    assert "file_path" not in properties
    assert not {"read", "delete", "list"} & set(properties)


def test_approved_reservation_is_stored_in_exact_format(tmp_path: Path) -> None:
    output_path = tmp_path / "confirmed.txt"
    result = call_tool(create_server(output_path))

    assert result == {
        "approval_request_id": str(REQUEST_ID),
        "stored": True,
        "message": "confirmed reservation stored",
    }
    assert output_path.read_text(encoding="utf-8") == (
        "Ada Lovelace | ABC-123 | 2026-08-05T09:00–2026-08-05T17:00 | "
        "2026-08-04T10:30:00+00:00\n"
    )


def test_identical_duplicate_returns_not_stored(tmp_path: Path) -> None:
    server = create_server(tmp_path / "confirmed.txt")

    assert call_tool(server)["stored"] is True
    result = call_tool(server)

    assert result["stored"] is False
    assert result["message"] == "confirmed reservation already stored"


@pytest.mark.parametrize("status", ["pending", "rejected", "unknown"])
def test_non_approved_status_is_rejected(tmp_path: Path, status: str) -> None:
    server = create_server(tmp_path / "confirmed.txt")

    with pytest.raises(ToolError, match="status must be approved"):
        call_tool(server, approval_status=status)


def test_invalid_reservation_text_is_rejected(tmp_path: Path) -> None:
    server = create_server(tmp_path / "confirmed.txt")

    with pytest.raises(ToolError, match="confirmed reservation is invalid"):
        call_tool(server, first_name="Ada|Injected")


def test_naive_approval_time_is_rejected(tmp_path: Path) -> None:
    server = create_server(tmp_path / "confirmed.txt")

    with pytest.raises(ToolError, match="confirmed reservation is invalid"):
        call_tool(server, approval_time=datetime(2026, 8, 4, 10, 30))


def test_conflict_error_is_mapped_safely(tmp_path: Path) -> None:
    server = create_server(tmp_path / "confirmed.txt")
    call_tool(server)

    with pytest.raises(
        ToolError,
        match="approval request conflicts with a stored reservation",
    ) as caught:
        call_tool(server, car_number="DIFFERENT")

    assert str(tmp_path) not in str(caught.value)


def test_storage_error_does_not_expose_internal_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "private" / "confirmed.txt"
    repository = ConfirmedReservationFileRepository(output_path)
    server = create_reservation_mcp_server(repository)

    def fail_append(_reservation: object) -> bool:
        raise ConfirmedReservationStorageError(f"failure at {output_path}")

    monkeypatch.setattr(repository, "append", fail_append)

    with pytest.raises(
        ToolError,
        match="could not store confirmed reservation$",
    ) as caught:
        call_tool(server)

    assert str(tmp_path) not in str(caught.value)
