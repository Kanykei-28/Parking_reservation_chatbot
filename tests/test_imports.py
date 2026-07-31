"""Package import smoke tests."""

import logging

import parking_chatbot
from parking_chatbot.config import Settings
from parking_chatbot.logging_config import configure_logging


def test_package_imports_successfully() -> None:
    assert parking_chatbot.__version__ == "0.1.0"
    assert parking_chatbot.Settings is not None


def test_logging_uses_configured_level() -> None:
    root_logger = logging.getLogger()
    original_level = root_logger.level

    try:
        configure_logging(Settings(log_level="DEBUG"))
        assert root_logger.level == logging.DEBUG
    finally:
        root_logger.setLevel(original_level)


def test_logging_does_not_add_duplicate_handlers() -> None:
    root_logger = logging.getLogger()

    configure_logging(Settings())
    configure_logging(Settings())

    matching_handlers = [
        handler
        for handler in root_logger.handlers
        if handler.get_name() == "parking_chatbot_console"
    ]
    assert len(matching_handlers) == 1
