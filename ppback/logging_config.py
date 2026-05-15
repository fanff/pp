import json
import logging
import os
from logging import config


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "level": record.levelname,
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include request_id if available (set by RequestIDMiddleware via contextvars)
        request_id = getattr(record, "request_id", "")
        if request_id:
            log_entry["request_id"] = request_id
        # Include exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(levelname)s %(asctime)s %(name)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "ppback": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console"],
    },
}


def setup_logging():
    """Set up logging configuration. Set LOG_FORMAT=json for structured JSON output."""
    log_format = os.getenv("LOG_FORMAT", "text")
    if log_format == "json":
        logging_config["formatters"]["default"] = {
            "()": "ppback.logging_config.JSONFormatter",
        }
    config.dictConfig(logging_config)
    logger = logging.getLogger("ppback")
    logger.info("Logging is set up with the provided configuration.")
    return logger
