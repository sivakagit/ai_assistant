import logging
import os
from logging.handlers import RotatingFileHandler


class ErrorCounterHandler(logging.Handler):

    def emit(self, record):

        if record.levelno >= logging.ERROR:

            try:

                from services.health_monitor import increment_error_count

                increment_error_count()

            except Exception:

                pass


def get_logger():

    logger = logging.getLogger("assistant")

    if logger.handlers:

        return logger

    log_dir = "logs"

    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "assistant.log"),
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.addHandler(ErrorCounterHandler())

    logger.setLevel(logging.INFO)

    return logger