import argparse
import sys
from collections.abc import Sequence

from parking_chatbot.application import (
    Stage2Application,
    create_stage1_chatbot,
    create_stage2_application,
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the parking reservation chatbot.")
    parser.add_argument(
        "--with-admin-approval",
        action="store_true",
        help="Enable the Stage 2 LangChain administrator approval workflow.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = ()) -> None:
    """Run the parking chatbot in an interactive terminal session."""
    args = _parse_args(argv)
    print("Parking Reservation Chatbot")
    print("Type 'exit' or 'quit' to stop.")

    application: Stage2Application | None = None
    if args.with_admin_approval:
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
                response = chatbot.chat(message)
            except ValueError as error:
                response = str(error)

            print(f"Bot: {response}")
    finally:
        if application is not None:
            application.close()


if __name__ == "__main__":
    main(sys.argv[1:])
