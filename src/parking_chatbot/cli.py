import argparse
import sys
from collections.abc import Sequence
from uuid import uuid4

from parking_chatbot.application import (
    Stage2Application,
    Stage3Application,
    Stage4Application,
    create_stage1_chatbot,
    create_stage2_application,
    create_stage3_application,
    create_stage4_application,
)
from parking_chatbot.orchestration import ApprovalMonitor


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the parking reservation chatbot.")
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument(
        "--with-admin-approval",
        action="store_true",
        help="Enable the Stage 2 LangChain administrator approval workflow.",
    )
    stage.add_argument(
        "--with-langgraph",
        action="store_true",
        help="Enable the unified Stage 4 LangGraph workflow.",
    )
    stage.add_argument(
        "--with-confirmed-processing",
        action="store_true",
        help="Enable Stage 3 administrator approval and MCP confirmed processing.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = ()) -> None:
    """Run the parking chatbot in an interactive terminal session."""
    args = _parse_args(argv)
    print("Parking Reservation Chatbot")
    print("Type 'exit' or 'quit' to stop.")

    application: Stage2Application | Stage3Application | Stage4Application | None = None
    monitor: ApprovalMonitor | None = None
    thread_id: str | None = None
    stage4_application: Stage4Application | None = None
    if args.with_langgraph:
        stage4_application = create_stage4_application()
        application = stage4_application
        thread_id = str(uuid4())
        try:
            monitor = ApprovalMonitor(
                stage4_application.orchestration,
                lambda response: print(f"\nBot: {response}"),
                interval_seconds=stage4_application.approval_poll_interval_seconds,
            )
        except BaseException:
            application.close()
            raise
        chatbot = None
    elif args.with_confirmed_processing:
        application = create_stage3_application()
        chatbot = application.chatbot
    elif args.with_admin_approval:
        application = create_stage2_application()
        chatbot = application.chatbot
    else:
        chatbot = create_stage1_chatbot()

    try:
        while True:
            try:
                message = input("You: ")
            except (KeyboardInterrupt, EOFError):
                print("Goodbye!")
                return

            if message.strip().lower() in {"exit", "quit"}:
                print("Goodbye!")
                return

            try:
                if stage4_application is not None:
                    assert thread_id is not None
                    state = stage4_application.orchestration.start_or_continue(
                        thread_id,
                        message,
                    )
                    response = state.get(
                        "response",
                        "The workflow could not produce a response.",
                    )
                    if state.get("approval_status") == "pending":
                        assert monitor is not None
                        monitor.start(thread_id)
                else:
                    assert chatbot is not None
                    response = chatbot.chat(message)
            except ValueError as error:
                response = str(error)

            print(f"Bot: {response}")
    finally:
        if monitor is not None:
            monitor.close()
        if application is not None:
            application.close()


if __name__ == "__main__":
    main(sys.argv[1:])
