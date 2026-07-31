import pytest

from parking_chatbot.chatbot import Intent, detect_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("hello", Intent.GREETING),
        ("Good afternoon", Intent.GREETING),
        ("I want to reserve a parking space", Intent.RESERVATION),
        ("Can I book a covered spot?", Intent.RESERVATION),
        ("I need a reservation", Intent.RESERVATION),
        ("Book parking for tomorrow", Intent.RESERVATION),
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
        ("Hi, what are your opening hours?", Intent.GREETING),
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
