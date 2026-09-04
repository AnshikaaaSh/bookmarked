"""Split sections into embedding-sized chunks, preserving chapter position.

Chunks never straddle a chapter boundary — a chunk belongs to exactly one
position, which is what lets the store filter on it cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS
from .loaders import Section

_SENTENCE_ENDINGS = (". ", "? ", "! ", ".\n", "?\n", "!\n")


@dataclass
class Chunk:
    text: str
    position: int
    position_label: str
    chunk_index: int


def _split_long_paragraph(paragraph: str, target: int) -> list[str]:
    """Break a paragraph that's longer than a whole chunk on sentence endings."""
    pieces: list[str] = []
    remaining = paragraph
    while len(remaining) > target:
        window = remaining[:target]
        cut = max(window.rfind(end) for end in _SENTENCE_ENDINGS)
        if cut <= target // 2:  # no sensible sentence break — hard split
            cut = target
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_section(
    section: Section,
    target: int = CHUNK_TARGET_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """Greedily pack paragraphs into ~`target`-char chunks with a small overlap."""
    paragraphs: list[str] = []
    for block in section.text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if len(block) > target * 1.5:
            paragraphs.extend(_split_long_paragraph(block, target))
        else:
            paragraphs.append(block)

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > target:
            chunks.append(current.strip())
            # Carry the tail of the last chunk so an idea split across a
            # boundary is still retrievable from either side.
            current = (current[-overlap:] + "\n\n" + paragraph) if overlap else paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_sections(sections: list[Section]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        for text in chunk_section(section):
            chunks.append(
                Chunk(
                    text=text,
                    position=section.position,
                    position_label=section.label,
                    chunk_index=len(chunks),
                )
            )
    return chunks
