import logging
import sys
from typing import Any

import structlog


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

    # Decision: Using ConsoleRenderer for the demo (colors!),
    # but in a real k8s pod, we would use JSONRenderer. # TODO
    processors.append(structlog.dev.ConsoleRenderer)
    processors.append(structlog.processors.JSONRenderer)

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        cache_logger_on_first_use=True,
    )
