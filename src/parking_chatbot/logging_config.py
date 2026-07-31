import logging
from typing import Final

from parking_chatbot.config import Settings, get_settings

_HANDLER_NAME: Final = "parking_chatbot_console"
_FORMAT: Final = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    level = getattr(logging, active_settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if handler.get_name() == _HANDLER_NAME:
            handler.setLevel(level)
            return

    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root_logger.addHandler(handler)
