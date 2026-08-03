from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from parking_chatbot.admin.client import AdministratorApprovalClient
from parking_chatbot.admin.gateway import ApprovalGateway, LangChainApprovalGateway
from parking_chatbot.admin.integration import ReservationApprovalIntegration
from parking_chatbot.chatbot import ParkingChatbot
from parking_chatbot.config import Settings, get_settings
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
    resolved_settings = settings or get_settings()
    client = client_factory(resolved_settings.admin_approval_base_url)
    try:
        model = model_factory()
        gateway = gateway_factory(model, client)
        integration = ReservationApprovalIntegration(gateway)
        chatbot = ParkingChatbot(approval_integration=integration)
    except Exception:
        client.close()
        raise

    return Stage2Application(
        chatbot=chatbot,
        client=client,
        gateway=gateway,
        integration=integration,
    )
