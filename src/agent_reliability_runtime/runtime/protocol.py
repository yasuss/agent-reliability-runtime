"""Non-authorizing classification of two bounded model protocol mistakes."""

import json
import re
from collections.abc import Sequence

from agent_reliability_runtime.retrieval.citations import citation_ids

MAX_REPAIRS = 2
TEXTUAL_CORRECTION = (
    "Protocol correction: your previous response described a tool request as ordinary "
    "text, so it was not executed. If you need a tool, emit it through the structured "
    "tool-call mechanism. Do not print JSON or function-call syntax as a substitute. "
    "Otherwise provide a normal final answer."
)
CITATION_CORRECTION = (
    "Protocol correction: your evidence reference was not in the required source alias "
    "format. Restate the final answer using one or more exact allowed citation tokens "
    "below. Copy tokens verbatim; do not invent or abbreviate references."
)


def repair_reason(
    text: str, tool_names: set[str], evidence_ids: set[str]
) -> str | None:
    """Return a label only; parsed arguments never leave this detector."""
    try:
        value = json.loads(text.strip())
    except (ValueError, RecursionError):
        value = None
    if isinstance(value, dict) and (
        (
            set(value) == {"name", "arguments"}
            and isinstance(value["name"], str)
            and value["name"] in tool_names
            and isinstance(value["arguments"], dict)
        )
        or (
            set(value) == {"tool", "parameters"}
            and isinstance(value["tool"], str)
            and value["tool"] in tool_names
            and isinstance(value["parameters"], dict)
        )
    ):
        return "textual_tool_request"
    for name in tool_names:
        if re.search(r"(?m)^\s*" + re.escape(name) + r"\s*\([^\n]*\)\s*$", text):
            return "textual_tool_request"
        if re.search(
            r"<tool_call>.*?\b" + re.escape(name) + r"\b.*?</tool_call>",
            text,
            re.DOTALL,
        ):
            return "textual_tool_request"
    without_aliases = re.sub(r"\[E[1-9][0-9]*\]", "", text)
    if evidence_ids and re.search(r"\b[eE][0-9]+\b", without_aliases):
        return "citation_format"
    # Any canonical token belongs exclusively to the strict citation validator.
    if citation_ids(text) or not evidence_ids:
        return None
    if re.search(r"\bevidence(?:_id|\s+ID)\b", text, re.IGNORECASE):
        return "citation_format"
    if any(evidence_id in text for evidence_id in evidence_ids):
        return "citation_format"
    for prefix in re.findall(r"(?<![0-9a-f])([0-9a-f]{8,64})(?:\.\.\.|\u2026)", text):
        if sum(e.startswith(prefix) for e in evidence_ids) == 1:
            return "citation_format"
    return None


def correction(
    reason: str, evidence_ids: set[str], aliases: Sequence[str] | None = None
) -> str:
    if reason == "mixed_tool_batch":
        return (
            "Protocol correction: the entire structured batch was not executed. "
            "Independent READ_ONLY calls may be grouped. Emit a SIDE_EFFECT alone, "
            "only after required read observations; the trusted runtime obtains "
            "exact approval."
        )
    if reason == "textual_tool_request":
        return TEXTUAL_CORRECTION
    if reason == "citation_format":
        return (
            CITATION_CORRECTION
            + "\n"
            + (
                "\n".join(f"[{ref}]" for ref in aliases)
                if aliases is not None
                else "\n".join(f"[evidence:{e}]" for e in sorted(evidence_ids))
            )
        )
    raise ValueError("unknown protocol repair reason")
