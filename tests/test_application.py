from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.application import (
    create_stage1_chatbot,
    create_stage2_application,
    create_stage3_application,
    create_stage4_application,
)
from parking_chatbot.chatbot import ParkingChatbot
from parking_chatbot.config import Settings
from parking_chatbot.mcp_client import ConfirmedReservationMCPClient


def test_stage2_factory_builds_chatbot_with_approval_integration() -> None:
    settings = Settings(admin_approval_base_url="http://admin.test:8765")
    client = MagicMock(spec=AdministratorApprovalClient)
    client_factory = MagicMock(return_value=client)
    model = cast(BaseChatModel, MagicMock())
    model_factory = MagicMock(return_value=model)
    approval_gateway = MagicMock(spec=ApprovalGateway)
    gateway_factory = MagicMock(return_value=approval_gateway)
    application = create_stage2_application(
        settings,
        client_factory=client_factory,
        model_factory=model_factory,
        gateway_factory=gateway_factory,
    )

    assert isinstance(application.chatbot, ParkingChatbot)
    assert application.client is client
    assert application.gateway is approval_gateway
    assert application.integration is not None
    assert not hasattr(application, "confirmed_reservation_client")
    client_factory.assert_called_once_with("http://admin.test:8765")
    model_factory.assert_called_once_with()
    gateway_factory.assert_called_once_with(model, client)


def test_stage3_factory_builds_and_injects_mcp_client() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    approval_gateway = MagicMock(spec=ApprovalGateway)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)
    mcp_client_factory = MagicMock(return_value=mcp_client)

    application = create_stage3_application(
        Settings(),
        client_factory=MagicMock(return_value=admin_client),
        model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
        gateway_factory=MagicMock(return_value=approval_gateway),
        confirmed_reservation_client_factory=mcp_client_factory,
    )

    assert application.confirmed_reservation_client is mcp_client
    assert application.integration is not None
    mcp_client_factory.assert_called_once_with()


def test_stage2_application_closes_administrator_client() -> None:
    client = MagicMock(spec=AdministratorApprovalClient)
    application = create_stage2_application(
        Settings(),
        client_factory=MagicMock(return_value=client),
        model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
        gateway_factory=MagicMock(return_value=MagicMock(spec=ApprovalGateway)),
    )

    application.close()

    client.close.assert_called_once_with()


def test_stage3_application_closes_both_clients() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)
    application = create_stage3_application(
        Settings(),
        client_factory=MagicMock(return_value=admin_client),
        model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
        gateway_factory=MagicMock(return_value=MagicMock(spec=ApprovalGateway)),
        confirmed_reservation_client_factory=MagicMock(return_value=mcp_client),
    )

    application.close()

    mcp_client.close.assert_called_once_with()
    admin_client.close.assert_called_once_with()


def test_stage3_construction_failure_closes_both_clients() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)

    with pytest.raises(RuntimeError, match="model failed"):
        create_stage3_application(
            Settings(),
            client_factory=MagicMock(return_value=admin_client),
            model_factory=MagicMock(side_effect=RuntimeError("model failed")),
            confirmed_reservation_client_factory=MagicMock(return_value=mcp_client),
        )

    mcp_client.close.assert_called_once_with()
    admin_client.close.assert_called_once_with()


def test_stage2_construction_failure_closes_administrator_client() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)

    with pytest.raises(RuntimeError, match="model failed"):
        create_stage2_application(
            Settings(),
            client_factory=MagicMock(return_value=admin_client),
            model_factory=MagicMock(side_effect=RuntimeError("model failed")),
        )

    admin_client.close.assert_called_once_with()


def test_stage1_factory_builds_chatbot_without_stage2_dependencies() -> None:
    chatbot = create_stage1_chatbot()

    assert isinstance(chatbot, ParkingChatbot)
    assert chatbot.chat("Check my reservation status") == (
        "There is no submitted reservation to check."
    )


def test_stage4_factory_composes_checkpointed_orchestration() -> None:
    settings = Settings(
        admin_approval_base_url="http://admin.test:8765",
        approval_poll_interval_seconds=0.5,
    )
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)
    gateway = MagicMock(spec=ApprovalGateway)
    checkpointer = InMemorySaver()

    application = create_stage4_application(
        settings,
        client_factory=MagicMock(return_value=admin_client),
        model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
        gateway_factory=MagicMock(return_value=gateway),
        confirmed_reservation_client_factory=MagicMock(return_value=mcp_client),
        checkpointer_factory=MagicMock(return_value=checkpointer),
    )

    assert application.client is admin_client
    assert application.gateway is gateway
    assert application.confirmed_reservation_client is mcp_client
    assert application.checkpointer is checkpointer
    assert application.approval_poll_interval_seconds == 0.5
    assert application.orchestration is not None


def test_stage4_application_closes_both_clients() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)
    application = create_stage4_application(
        Settings(),
        client_factory=MagicMock(return_value=admin_client),
        model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
        gateway_factory=MagicMock(return_value=MagicMock(spec=ApprovalGateway)),
        confirmed_reservation_client_factory=MagicMock(return_value=mcp_client),
    )

    application.close()

    mcp_client.close.assert_called_once_with()
    admin_client.close.assert_called_once_with()


def test_stage4_construction_failure_closes_created_clients() -> None:
    admin_client = MagicMock(spec=AdministratorApprovalClient)
    mcp_client = MagicMock(spec=ConfirmedReservationMCPClient)

    with pytest.raises(RuntimeError, match="checkpoint failed"):
        create_stage4_application(
            Settings(),
            client_factory=MagicMock(return_value=admin_client),
            model_factory=MagicMock(return_value=cast(BaseChatModel, MagicMock())),
            gateway_factory=MagicMock(return_value=MagicMock(spec=ApprovalGateway)),
            confirmed_reservation_client_factory=MagicMock(return_value=mcp_client),
            checkpointer_factory=MagicMock(
                side_effect=RuntimeError("checkpoint failed")
            ),
        )

    mcp_client.close.assert_called_once_with()
    admin_client.close.assert_called_once_with()
