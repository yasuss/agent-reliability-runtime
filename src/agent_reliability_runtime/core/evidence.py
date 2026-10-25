"""Canonical JSON and unchanged public evidence redaction."""

import json
import re
from collections.abc import Mapping
from typing import Any

SENSITIVE = re.compile(
    r"authorization|api.?key|token|credential|secret|password|cookie|idempotency.?key",
    re.I,
)
RAW = {
    "messages",
    "prompt",
    "arguments",
    "result",
    "reasoning",
    "chain_of_thought",
    "content",
    "raw_payload",
}
SECRET = re.compile(
    r"Bearer\s+[^\s\"<>]+|\b(?:sk-|gh[pousr]_|AKIA)[A-Za-z0-9_-]+|"
    r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)|"
    r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@:]+:[^\s/@]+@[^\s]+|"
    r"ARR_FORBIDDEN_SECRET_[A-Za-z0-9]+",
    re.I,
)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): v
            if k in {"input_tokens", "output_tokens", "total_tokens"}
            and (v is None or type(v) is int)
            else "[REDACTED]"
            if SENSITIVE.search(str(k)) or str(k).lower() in RAW
            else sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return SECRET.sub("[REDACTED]", value)[:2048]
    if value is None or type(value) in (int, float, bool):
        return value
    raise ValueError("non-JSON observability payload")


def public_safe(data: bytes) -> None:
    if SECRET.search(data.decode("utf-8")):
        raise ValueError("unsafe public artifact")

    def inspect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                usage = key in {"input_tokens", "output_tokens", "total_tokens"} and (
                    item is None or type(item) is int
                )
                if (
                    (SENSITIVE.search(key) or key.lower() in RAW)
                    and not usage
                    and item != "[REDACTED]"
                ):
                    raise ValueError("unsafe public field")
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    inspect(json.loads(data))
