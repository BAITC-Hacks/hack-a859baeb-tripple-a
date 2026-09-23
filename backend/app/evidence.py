"""Source integrity checks. Quotes are exact substrings of normalized source chunks."""

from collections.abc import Iterable

from .models import Chunk, Document, Evidence


def chunk_index(documents: list[Document]) -> dict[str, tuple[Document, Chunk]]:
    return {c.id: (d, c) for d in documents for c in d.chunks}


def validate_evidence(
    evidence: Iterable[Evidence],
    documents: list[Document],
    required_sides: set[str] | None = None,
) -> bool:
    index = chunk_index(documents)
    refs = list(evidence)
    if not refs:
        return False
    sides = set()
    for ref in refs:
        source = index.get(ref.chunk_id)
        if source is None:
            return False
        document, chunk = source
        if (
            chunk.document_id != document.id
            or not ref.quote.strip()
            or ref.quote not in chunk.text
        ):
            return False
        sides.add(document.side)
    return not required_sides or required_sides.issubset(sides)


def unique_evidence(refs: Iterable[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    output = []
    for ref in refs:
        key = (ref.chunk_id, ref.quote)
        if key not in seen:
            seen.add(key)
            output.append(ref)
    return output


def location(chunk: Chunk) -> str:
    parts = []
    if chunk.page is not None:
        parts.append(f"page {chunk.page}")
    if chunk.section:
        parts.append(f"section {chunk.section}")
    if chunk.paragraph is not None:
        parts.append(f"paragraph {chunk.paragraph}")
    if chunk.sheet:
        parts.append(f"sheet {chunk.sheet}")
    if chunk.row is not None:
        parts.append(f"row {chunk.row}")
    return ", ".join(parts) or "source excerpt"
