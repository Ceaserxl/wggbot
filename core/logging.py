from __future__ import annotations

import logging
import re
import sys

TOKEN_PATTERN = re.compile(r"([A-Za-z\d_-]{20,30}\.[A-Za-z\d_-]{5,10}\.[A-Za-z\d_-]{20,})")


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = TOKEN_PATTERN.sub("[REDACTED_DISCORD_TOKEN]", record.getMessage())
        if message != record.getMessage():
            record.msg = message
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
