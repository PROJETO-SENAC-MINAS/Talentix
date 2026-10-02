"""Logging estruturado em JSON para API, workers e auditoria operacional."""
from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone

from app.core.config import settings


_STANDARD = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.APP_ENV,
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configurar_logging() -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": "app.core.logging_config.JsonFormatter"}},
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "level": settings.LOG_LEVEL,
            }
        },
        "root": {"handlers": ["default"], "level": settings.LOG_LEVEL},
        "loggers": {
            "uvicorn.access": {"handlers": [], "propagate": False},
        },
    })
