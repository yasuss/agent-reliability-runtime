"""Deterministic UTF-8 source plans; no database or provider operations."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agent_reliability_runtime.contracts.domain import (
    KnowledgeChunk,
    KnowledgeDocument,
    chunk_id,
    document_id,
)

TARGET = 1200
OVERLAP = 150
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def normalize(data: bytes) -> str:
    return (
        data.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sections(text: str, markdown: bool) -> list[tuple[str, str]]:
    headings = list(HEADING.finditer(text)) if markdown else []
    starts = [0] + [h.start() for h in headings if h.start() != 0]
    pieces: list[tuple[str, str]] = []
    for start, end in zip(starts, starts[1:] + [len(text)], strict=True):
        section = text[start:end].strip()
        if section:
            heading = HEADING.match(section) if markdown else None
            pieces.append((section, heading.group(0) if heading else ""))
    return pieces


def split_section(section: str, heading: str) -> list[str]:
    if len(section) <= TARGET:
        return [section]
    # Repeat its heading on split pieces, without crossing a section boundary.
    prefix = heading + "\n" if heading else ""
    body = section[len(heading) :].lstrip("\n") if heading else section
    capacity = TARGET - len(prefix)
    if capacity <= OVERLAP:
        raise ValueError("heading too long for deterministic chunk context")
    parts: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + capacity, len(body))
        # Prefer the last newline, then space, in the last quarter; hard-cut else.
        if end < len(body):
            lower = start + capacity * 3 // 4
            boundary = body.rfind("\n", lower, end)
            if boundary < lower:
                boundary = body.rfind(" ", lower, end)
            if boundary >= lower:
                end = boundary + 1
        parts.append(prefix + body[start:end])
        if end == len(body):
            break
        start = end - OVERLAP
    return parts


@dataclass(frozen=True)
class SourcePlan:
    document: KnowledgeDocument
    chunks: tuple[KnowledgeChunk, ...]


def plan_source(source_path: str, data: bytes) -> SourcePlan:
    doc_id = document_id(source_path)  # Also validates normalized repo-relative paths.
    path = PurePosixPath(source_path)
    if path.suffix not in {".md", ".txt"}:
        raise ValueError("only .md and .txt sources are supported")
    text = normalize(data)
    if not text.strip():
        raise ValueError("source must contain nonempty text")
    headings = list(HEADING.finditer(text)) if path.suffix == ".md" else []
    title = next(
        (h.group(2) for h in headings if h.group(1) == "#"),
        path.stem.replace("-", " ").replace("_", " "),
    )
    content_digest = digest(text)
    contents = [
        part
        for section, heading in sections(text, path.suffix == ".md")
        for part in split_section(section, heading)
    ]
    document = KnowledgeDocument(
        document_id=doc_id,
        source_path=source_path,
        content_digest=content_digest,
        title=title,
    )
    chunks = tuple(
        KnowledgeChunk(
            chunk_id=chunk_id(doc_id, content_digest, ordinal),
            document_id=doc_id,
            document_digest=content_digest,
            ordinal=ordinal,
            content=content,
        )
        for ordinal, content in enumerate(contents)
    )
    return SourcePlan(document, chunks)


def read_source(root: Path, source_path: str) -> SourcePlan:
    document_id(source_path)
    path = (root / source_path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("source must remain within repository root")
    return plan_source(source_path, path.read_bytes())
