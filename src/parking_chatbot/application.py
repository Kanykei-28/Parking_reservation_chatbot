from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.admin.gateway import ApprovalGateway, LangChainApprovalGateway
from parking_chatbot.admin.integration import ReservationApprovalIntegration
from parking_chatbot.chatbot import ParkingChatbot
from parking_chatbot.config import Settings, get_settings
from parking_chatbot.mcp_client import ConfirmedReservationMCPClient
from parking_chatbot.rag.generator import create_llm


@dataclass
class Stage2Application:
    chatbot: ParkingChatbot
    client: AdministratorApprovalClient
    gateway: ApprovalGateway
    integration: ReservationApprovalIntegration

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Stage2Application":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


@dataclass
class Stage3Application(Stage2Application):
    confirmed_reservation_client: ConfirmedReservationMCPClient

    def close(self) -> None:
        try:
            self.confirmed_reservation_client.close()
        finally:
            super().close()


def create_stage1_chatbot() -> ParkingChatbot:
    return ParkingChatbot()


def create_stage2_application(
    settings: Settings | None = None,
    *,
    client_factory: Callable[[str], AdministratorApprovalClient] = (
        AdministratorApprovalClient
    ),
    model_factory: Callable[[], BaseChatModel] = create_llm,
    gateway_factory: Callable[
        [BaseChatModel, AdministratorApprovalClient], ApprovalGateway
    ] = LangChainApprovalGateway.from_model_and_client,
) -> Stage2Application:
    client, gateway, integration, chatbot = _create_approval_components(
        settings,
        client_factory=client_factory,
        model_factory=model_factory,
        gateway_factory=gateway_factory,
    )
    return Stage2Application(
        chatbot=chatbot,
        client=client,
        gateway=gateway,
        integration=integration,
    )


def create_stage3_application(
    settings: Settings | None = None,
    *,
    client_factory: Callable[[str], AdministratorApprovalClient] = (
        AdministratorApprovalClient
    ),
    model_factory: Callable[[], BaseChatModel] = create_llm,
    gateway_factory: Callable[
        [BaseChatModel, AdministratorApprovalClient], ApprovalGateway
    ] = LangChainApprovalGateway.from_model_and_client,
    confirmed_reservation_client_factory: Callable[
        [], ConfirmedReservationMCPClient
    ] = ConfirmedReservationMCPClient,
) -> Stage3Application:
    confirmed_reservation_client = confirmed_reservation_client_factory()
    try:
        client, gateway, integration, chatbot = _create_approval_components(
            settings,
            client_factory=client_factory,
            model_factory=model_factory,
            gateway_factory=gateway_factory,
            confirmed_reservation_client=confirmed_reservation_client,
        )
    except BaseException:
        confirmed_reservation_client.close()
        raise
    return Stage3Application(
        chatbot=chatbot,
        client=client,
        gateway=gateway,
        integration=integration,
        confirmed_reservation_client=confirmed_reservation_client,
    )


def _create_approval_components(
    settings: Settings | None,
    *,
    client_factory: Callable[[str], AdministratorApprovalClient],
    model_factory: Callable[[], BaseChatModel],
    gateway_factory: Callable[
        [BaseChatModel, AdministratorApprovalClient], ApprovalGateway
    ],
    confirmed_reservation_client: ConfirmedReservationMCPClient | None = None,
) -> tuple[
    AdministratorApprovalClient,
    ApprovalGateway,
    ReservationApprovalIntegration,
    ParkingChatbot,
]:
    resolved_settings = settings or get_settings()
    client = client_factory(resolved_settings.admin_approval_base_url)
    try:
        model = model_factory()
        gateway = gateway_factory(model, client)
        integration = ReservationApprovalIntegration(
            gateway,
            confirmed_reservation_client,
        )
        chatbot = ParkingChatbot(approval_integration=integration)
    except BaseException:
        client.close()
        raise
    return client, gateway, integration, chatbot
