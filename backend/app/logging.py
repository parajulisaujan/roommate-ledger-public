"""Structured application events without request bodies or SQL parameter values."""

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def configure() -> None:
    # Uvicorn also logs unhandled ASGI errors after the safe response is sent.
    # Its production handler must not append exception values/traceback locals.
    for name in ("app", "roommateledger", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
