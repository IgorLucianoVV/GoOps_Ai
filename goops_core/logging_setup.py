"""Logs estruturados em JSON com redação de segredos."""
from __future__ import annotations

import json
import logging
import re
import sys

_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"(?i)((?:api[_-]?key|password|secret|token)\"?\s*[:=]\s*\"?)[^\s\",]+"), r"\1***"),
]


def redact(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        for key in ("run_id", "incident_id", "agent", "request_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_goops", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._goops = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
