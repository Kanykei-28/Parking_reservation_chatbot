import pytest

from parking_chatbot.chatbot import Intent, detect_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("hello", Intent.GREETING),
        ("hi", Intent.GREETING),
        ("hey there", Intent.GREETING),
        ("Good afternoon", Intent.GREETING),
        ("I want to reserve a parking space", Intent.RESERVATION),
        ("Can I book a covered spot?", Intent.RESERVATION),
        ("I need a reservation", Intent.RESERVATION),
        ("Book parking for tomorrow", Intent.RESERVATION),
        ("What is the status of my reservation?", Intent.APPROVAL_STATUS),
        ("Check my reservation status", Intent.APPROVAL_STATUS),
        ("Has my reservation been approved?", Intent.APPROVAL_STATUS),
        ("Is my reservation approved?", Intent.APPROVAL_STATUS),
        ("Was my reservation rejected?", Intent.APPROVAL_STATUS),
        ("Was my booking rejected?", Intent.APPROVAL_STATUS),
        ("Was my reservation recorded?", Intent.APPROVAL_STATUS),
        ("Is my booking still pending?", Intent.APPROVAL_STATUS),
        ("What are the parking hours?", Intent.INFORMATION),
        ("How much does covered parking cost?", Intent.INFORMATION),
        ("Where is the parking located?", Intent.INFORMATION),
        ("Can I pay by cash?", Intent.INFORMATION),
        ("What happens if I arrive late?", Intent.INFORMATION),
        ("Write a poem", Intent.UNKNOWN),
        ("Explain Python decorators", Intent.UNKNOWN),
    ],
)
def test_detects_intent(message: str, expected: Intent) -> None:
    assert detect_intent(message) is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("  HELLO  ", Intent.GREETING),
        ("\tBOOK PARKING FOR TOMORROW\n", Intent.RESERVATION),
        ("  WHAT IS THE PARKING COST? ", Intent.INFORMATION),
    ],
)
def test_matching_is_case_insensitive_and_ignores_outer_whitespace(
    message: str,
    expected: Intent,
) -> None:
    assert detect_intent(message) is expected


@pytest.mark.parametrize(
    "message",
    [
        "How many parking spaces are available?",
        "What parking spaces do you have?",
    ],
)
def test_parking_space_questions_are_information(message: str) -> None:
    assert detect_intent(message) is Intent.INFORMATION


@pytest.mark.parametrize("message", ["", "   ", "\t\n"])
def test_rejects_empty_messages(message: str) -> None:
    with pytest.raises(ValueError, match="^message must not be empty$"):
        detect_intent(message)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("this is unrelated", Intent.UNKNOWN),
        ("higher performance", Intent.UNKNOWN),
    ],
)
def test_greeting_substrings_do_not_match(
    message: str,
    expected: Intent,
) -> None:
    assert detect_intent(message) is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Hello, I want to book parking", Intent.RESERVATION),
        ("Hi, what are your opening hours?", Intent.INFORMATION),
        ("Can I reserve a covered parking space?", Intent.RESERVATION),
    ],
)
def test_applies_intent_priority(message: str, expected: Intent) -> None:
    assert detect_intent(message) is expected


@pytest.mark.parametrize(
    "message",
    [
        "Who won the football match?",
        "Explain Python decorators",
    ],
)
def test_unrelated_messages_are_unknown(message: str) -> None:
    assert detect_intent(message) is Intent.UNKNOWN


@pytest.mark.parametrize(
    "message",
    [
        "What is the system status?",
        "What is your employment status?",
    ],
)
def test_unrelated_status_phrases_do_not_match_approval_status(message: str) -> None:
    assert detect_intent(message) is Intent.UNKNOWN


@pytest.mark.parametrize(
    "message",
    [
        "hello, what parking types do you have?",
        "hi, how much does covered parking cost?",
        "hey, where is the parking?",
    ],
)
def test_greeting_with_parking_question_is_information(message: str) -> None:
    assert detect_intent(message) is Intent.INFORMATION


def test_greeting_with_status_question_keeps_status_priority() -> None:
    assert detect_intent("hello, is my reservation approved?") is Intent.APPROVAL_STATUS


@pytest.mark.parametrize(
    "message",
    ["thanks", "thank you", "thanks a lot", "got it", "okay, thanks"],
)
def test_acknowledgement_only_messages(message: str) -> None:
    assert detect_intent(message) is Intent.ACKNOWLEDGEMENT


@pytest.mark.parametrize(
    "message",
    [
        "Thanks, what are the working hours?",
        "Great, how can I pay?",
        "Okay, where is the parking?",
    ],
)
def test_acknowledgement_does_not_hide_parking_question(message: str) -> None:
    assert detect_intent(message) is Intent.INFORMATION
