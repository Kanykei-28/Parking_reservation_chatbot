from typing import cast
from unittest.mock import MagicMock

from langchain_core.language_models import BaseChatModel

from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.admin.gateway import ApprovalGateway
from parking_chatbot.application import (
    create_stage1_chatbot,
    create_stage2_application,
)
from parking_chatbot.chatbot import ParkingChatbot
from parking_chatbot.config import Settings


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
    client_factory.assert_called_once_with("http://admin.test:8765")
    model_factory.assert_called_once_with()
    gateway_factory.assert_called_once_with(model, client)


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


def test_stage1_factory_builds_chatbot_without_stage2_dependencies() -> None:
    chatbot = create_stage1_chatbot()

    assert isinstance(chatbot, ParkingChatbot)
    assert chatbot.chat("Check my reservation status") == (
        "There is no submitted reservation to check."
    )
