import re
from enum import Enum


class Intent(str, Enum):  # noqa: UP042
    GREETING = "greeting"
    RESERVATION = "reservation"
    APPROVAL_STATUS = "approval_status"
    INFORMATION = "information"
    UNKNOWN = "unknown"


RESERVATION_PATTERN = re.compile(r"\b(?:reserve|reservation|book|booking)\b")

APPROVAL_STATUS_PATTERN = re.compile(
    r"\b(?:status\s+of\s+my\s+(?:reservation|booking)"
    r"|check\s+my\s+(?:reservation|booking)\s+status"
    r"|has\s+my\s+(?:reservation|booking)\s+been\s+approved"
    r"|was\s+my\s+(?:reservation|booking)\s+rejected"
    r"|is\s+my\s+(?:reservation|booking)\s+still\s+pending)\b"
)

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

    if APPROVAL_STATUS_PATTERN.search(normalized_message):
        return Intent.APPROVAL_STATUS
    if RESERVATION_PATTERN.search(normalized_message):
        return Intent.RESERVATION
    if GREETING_PATTERN.search(normalized_message):
        return Intent.GREETING
    if INFORMATION_PATTERN.search(normalized_message):
        return Intent.INFORMATION
    return Intent.UNKNOWN
