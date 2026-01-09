import logging
import os
import sys
from typing import Any

import structlog
from dotenv import load_dotenv

load_dotenv()


def setup_logging(level: str = "INFO") -> None:
    """
    Configures structlog to format logs for human readability (dev)
    or JSON (prod). For this CLI agent, we prioritize readability.
    """

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,  # merge context variables into the log output  # noqa: E501
        structlog.processors.add_log_level,  # add the log level to each log entry
        structlog.processors.StackInfoRenderer(),  # render stack info for debug logs
        structlog.dev.set_exc_info,  # set exception info for error logs
        structlog.processors.TimeStamper(
            fmt="%H:%M:%S", utc=False
        ),  # add timestamps to logs
    ]

    is_prod: bool = os.getenv("ENVIRONMENT", "development") == "production"

    if is_prod:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        cache_logger_on_first_use=True,
    )
