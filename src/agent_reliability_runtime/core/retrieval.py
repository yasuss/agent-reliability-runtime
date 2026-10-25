"""Only explicit canonical evidence markers are citations; no fuzzy matching."""

import re

_CITATION = re.compile(r"\[evidence:([0-9a-f]{64})\]")


def citation_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_CITATION.findall(text)))


def validate_citations(text: str, retrieved_ids: set[str]) -> list[str]:
    citations = citation_ids(text)
    if not set(citations) <= retrieved_ids:
        raise ValueError("citation outside retrieved evidence")
    return citations
