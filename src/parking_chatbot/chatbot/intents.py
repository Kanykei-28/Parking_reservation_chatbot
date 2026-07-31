import re
from enum import Enum


class Intent(str, Enum):  # noqa: UP042
    GREETING = "greeting"
    RESERVATION = "reservation"
    INFORMATION = "information"
    UNKNOWN = "unknown"


RESERVATION_PATTERN = re.compile(r"\b(?:reserve|reservation|book|booking)\b")

GREETING_PATTERN = re.compile(
    r"\b(?:hello|hi|hey)\b"
    r"|\bgood\s+(?:morning|afternoon|evening)\b"
)
INFORMATION_PATTERN = re.compile(
    r"\b(?:parking|spot|space|price|cost|hours|open|location|address|payment|"
    r"cash|card|available|availability|standard|covered|ev|charging|cancel|"
    r"cancellation|late|administrator|approval)\b"
)


def detect_intent(message: str) -> Intent:
    normalized_message = message.strip().lower()
    if not normalized_message:
        raise ValueError("message must not be empty")

    if RESERVATION_PATTERN.search(normalized_message):
        return Intent.RESERVATION
    if GREETING_PATTERN.search(normalized_message):
        return Intent.GREETING
    if INFORMATION_PATTERN.search(normalized_message):
        return Intent.INFORMATION
    return Intent.UNKNOWN
