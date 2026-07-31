from parking_chatbot.chatbot import ParkingChatbot


def main() -> None:
    """Run the parking chatbot in an interactive terminal session."""
    print("Parking Reservation Chatbot")
    print("Type 'exit' or 'quit' to stop.")

    chatbot = ParkingChatbot()
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


if __name__ == "__main__":
    main()
