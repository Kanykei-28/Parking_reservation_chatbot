import re

BLOCKED_MESSAGE = "I can't provide confidential or internal system information."

_RETRIEVAL_TERMS = (
    "show",
    "tell",
    "give",
    "reveal",
    "display",
    "print",
    "output",
    "expose",
    "leak",
    "send",
    "provide",
    "list",
    "dump",
    "export",
)
_APPLICATION_OWNERSHIP_TERMS = (
    "your",
    "chatbot",
    "application",
    "app",
    "internal",
    "current",
)


class GuardrailViolation(ValueError):
    pass


def check_message(message: str) -> None:
    if requests_internal_prompts(message):
        raise GuardrailViolation(BLOCKED_MESSAGE)
    if requests_credentials(message):
        raise GuardrailViolation(BLOCKED_MESSAGE)
    if requests_database(message):
        raise GuardrailViolation(BLOCKED_MESSAGE)
    if requests_other_users_data(message):
        raise GuardrailViolation(BLOCKED_MESSAGE)


def requests_internal_prompts(message: str) -> bool:
    normalized_message = _normalize(message)
    prompt_terms = (
        "system prompt",
        "developer prompt",
        "internal instruction",
        "hidden instruction",
    )
    return (
        _contains_any(normalized_message, prompt_terms)
        and _requests_retrieval(normalized_message)
        and _contains_any(normalized_message, _APPLICATION_OWNERSHIP_TERMS)
    )


def requests_credentials(message: str) -> bool:
    normalized_message = _normalize(message)
    administrator_terms = (
        "administrator credential",
        "administrator password",
        "admin credential",
        "admin password",
    )
    credential_terms = (
        *administrator_terms,
        "api key",
        "secret key",
        "access token",
        "environment variable",
        ".env",
    )
    owns_credentials = _contains_any(
        normalized_message,
        _APPLICATION_OWNERSHIP_TERMS,
    ) or _contains_any(normalized_message, administrator_terms)
    return (
        _contains_any(normalized_message, credential_terms)
        and _requests_retrieval(normalized_message)
        and owns_credentials
    )


def requests_database(message: str) -> bool:
    normalized_message = _normalize(message)
    database_terms = (
        "database dump",
        "database contents",
        "database records",
        "entire database",
        "whole database",
    )
    asks_for_database = _contains_any(normalized_message, database_terms) or (
        "database" in normalized_message
        and _contains_any(normalized_message, ("dump", "export"))
    )
    return asks_for_database and _requests_retrieval(normalized_message)


def requests_other_users_data(message: str) -> bool:
    normalized_message = _normalize(message)
    other_user_terms = (
        "other user",
        "other customer",
        "someone else",
        "all users",
        "all customers",
        "every user",
        "every customer",
    )
    reservation_terms = (
        "reservation",
        "booking",
        "personal data",
        "user data",
        "customer data",
    )
    return (
        _contains_any(normalized_message, other_user_terms)
        and _contains_any(normalized_message, reservation_terms)
        and _requests_retrieval(normalized_message)
    )


def _normalize(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip().lower().replace("’", "'"))


def _requests_retrieval(message: str) -> bool:
    return _contains_any(message, _RETRIEVAL_TERMS)


def _contains_any(message: str, terms: tuple[str, ...]) -> bool:
    return any(term in message for term in terms)
