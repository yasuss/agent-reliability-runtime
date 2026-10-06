"""Transient source aliases; durable evidence and canonical validation stay intact."""

import json
import re
from collections.abc import Sequence
from typing import Any

from agent_reliability_runtime.retrieval.contracts import Evidence

RETRIEVAL_PREFIX = "Untrusted retrieval evidence: "
PROJECTION_FIELDS = {"ref", "citation_token", "title", "source_path", "content"}


class UnknownCitationAlias(ValueError):
    pass


def reference_map(evidence: Sequence[dict[str, Any]]) -> dict[str, str]:
    return {f"E{i}": item["evidence_id"] for i, item in enumerate(evidence, 1)}


def normalize_citation_aliases(text: str, evidence: Sequence[dict[str, Any]]) -> str:
    refs = reference_map(evidence)

    def expand(match: re.Match[str]) -> str:
        ref = match.group(1)
        if ref not in refs:
            raise UnknownCitationAlias("unknown citation alias")
        return f"[evidence:{refs[ref]}]"

    return re.sub(r"\[([eE][0-9][^\]]*)\]", expand, text)


def render_retrieval_context(evidence: Sequence[dict[str, Any]]) -> str:
    projected = []
    for i, item in enumerate(evidence, 1):
        raw = Evidence.model_validate(item)
        projected.append(
            {
                "ref": f"E{i}",
                "citation_token": f"[E{i}]",
                "title": raw.title,
                "source_path": raw.source_path,
                "content": raw.content,
            }
        )
    return RETRIEVAL_PREFIX + json.dumps(projected, ensure_ascii=False, allow_nan=False)


def parse_retrieval_context(content: str) -> list[dict[str, Any]] | None:
    """Shared semantic parser, including historical checkpoint compatibility."""
    if not content.startswith(RETRIEVAL_PREFIX):
        return None
    try:
        payload = json.loads(content[len(RETRIEVAL_PREFIX) :])
        if not isinstance(payload, list):
            raise ValueError
        parsed: list[dict[str, Any]] = []
        for i, item in enumerate(payload, 1):
            if not isinstance(item, dict):
                raise ValueError
            if "ref" in item:
                if (
                    set(item) != PROJECTION_FIELDS
                    or item["ref"] != f"E{i}"
                    or item["citation_token"] != f"[E{i}]"
                    or any(not isinstance(item[k], str) for k in PROJECTION_FIELDS)
                ):
                    raise ValueError
            else:
                raw = {k: v for k, v in item.items() if k != "citation_token"}
                evidence = Evidence.model_validate(raw)
                if (
                    "citation_token" in item
                    and item["citation_token"] != f"[evidence:{evidence.evidence_id}]"
                ):
                    raise ValueError
            parsed.append(item)
        return parsed
    except (ValueError, TypeError, RecursionError):
        raise ValueError("malformed retrieval context") from None
