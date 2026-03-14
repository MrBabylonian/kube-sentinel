import logging
import os
from typing import Literal, cast

import structlog

"""
We are not using cached 'get_app_settings' here because we want to be able to
use the logger in testing or per file scenarios without having to worry about
setting all of the enforced environment variables that 
'get_app_settings' requires (via pydantic-settings). 
"""

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]

_log_level_from_env = cast(LogLevel, os.getenv("LOG_LEVEL", "NOTSET").upper())

_log_level = getattr(logging, _log_level_from_env)
_is_production: bool = os.getenv("ENVIRONMENT") == "PRODUCTION"

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(min_level=_log_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=_is_production,
)


log = structlog.get_logger()

log.info("Logger initialized")
