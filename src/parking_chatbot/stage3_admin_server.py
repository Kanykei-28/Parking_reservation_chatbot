import uvicorn

from parking_chatbot.admin.api import create_admin_app
from parking_chatbot.admin.processing import ApprovedReservationProcessor
from parking_chatbot.admin.repository import InMemoryApprovalRequestRepository
from parking_chatbot.mcp_client import ConfirmedReservationMCPClient


def main() -> None:
    client = ConfirmedReservationMCPClient()
    try:
        processor = ApprovedReservationProcessor(client)
        app = create_admin_app(
            InMemoryApprovalRequestRepository(),
            approved_reservation_processor=processor,
        )
        uvicorn.run(app, host="127.0.0.1", port=8000)
    finally:
        client.close()


if __name__ == "__main__":
    main()
