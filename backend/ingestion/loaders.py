"""Turn files on disk into (Source, [Section]) pairs.

Every Section carries a `position` — the chapter number it belongs to. That
integer is what makes the spoiler-safe filter possible later (NFR1): retrieval
is constrained with `position <= reader_position` at the store level, not by
asking the model nicely.

Three file shapes are supported, one per data/ subdirectory:

  data/books/*.md     notes & highlights, grouped under `## Chapter N` headings
  data/texts/*.txt    full narrative text, chapters detected from the prose
  data/articles/*.md  a saved article (no chapters — position 0, always visible)

All three take an optional `---` frontmatter block for title/author/url.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# --- Types ---------------------------------------------------------------


@dataclass
class Source:
    """One book or article in the library."""

    source_id: str
    title: str
    author: str
    source_type: str  # book_notes | book_text | article
    url: str = ""
    unit: str = "chapter"  # chapter | page — what `position` counts

    def as_metadata(self) -> dict:
        # Chroma rejects None in metadata — empty strings only.
        return {
            "source_id": self.source_id,
            "source_title": self.title,
            "author": self.author,
            "source_type": self.source_type,
            "url": self.url,
            "position_unit": self.unit,
        }


@dataclass
class Section:
    """A chapter- or page-sized span of one source, before chunking."""

    position: int  # chapter/page number; 0 = no position (articles, front matter)
    label: str  # human-readable, e.g. "Chapter 3"
    text: str


# --- Frontmatter ---------------------------------------------------------

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Pull a simple `key: value` frontmatter block off the top of a file."""
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    return meta, raw[match.end() :]


# --- Chapter detection ---------------------------------------------------

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}

# Ordered by how much we trust them: explicit markdown headings first, then
# "CHAPTER N" lines (optionally followed by a title, as Gutenberg texts do:
# "CHAPTER III: Marilla Cuthbert is Surprised"), lone roman numerals last.
_CHAPTER_PATTERNS = [
    re.compile(r"^#{1,3}\s*chapter\s+(?P<num>\d+|[ivxlcdm]+)\b", re.IGNORECASE),
    re.compile(r"^\s*chapter\s+(?P<num>\d+|[ivxlcdm]+)\s*(?:[:.—–-]\s*\S.*)?$", re.IGNORECASE),
    re.compile(r"^\s*(?P<num>[ivxlcdm]+)\.?\s*$", re.IGNORECASE),
]

# Page positions, written by the PDF importer for books with no chapter markers.
_PAGE_PATTERN = re.compile(r"^#{1,3}\s*page\s+(?P<num>\d+)\b", re.IGNORECASE)


def _roman_to_int(value: str) -> int:
    total = 0
    prev = 0
    for char in reversed(value.lower()):
        current = _ROMAN_VALUES[char]
        total += -current if current < prev else current
        prev = max(prev, current)
    return total


def _parse_chapter_number(raw: str) -> int:
    return int(raw) if raw.isdigit() else _roman_to_int(raw)


def _match_position_heading(line: str) -> tuple[int, str] | None:
    """Return (number, unit) if this line marks a new position, else None."""
    if len(line) > 80:  # a heading is short; prose is not
        return None

    page = _PAGE_PATTERN.match(line)
    if page:
        return int(page.group("num")), "page"

    for pattern in _CHAPTER_PATTERNS:
        match = pattern.match(line)
        if match:
            try:
                number = _parse_chapter_number(match.group("num"))
            except (KeyError, ValueError):
                return None
            # Guard against a stray "I." mid-prose claiming to be chapter 1.
            return (number, "chapter") if 0 < number < 500 else None
    return None


def split_into_sections(body: str) -> list[Section]:
    """Split text on position headings (chapters or pages). Anything before the
    first heading becomes a position-0 'front matter' section, always visible."""
    sections: list[Section] = []
    current_position = 0
    current_label = "Front matter"
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section(current_position, current_label, text))
        buffer.clear()

    for line in body.splitlines():
        match = _match_position_heading(line)
        if match is not None:
            flush()
            number, unit = match
            current_position = number
            current_label = f"{unit.title()} {number}"
            continue
        buffer.append(line)

    flush()
    return sections


# --- Loaders -------------------------------------------------------------


def _source_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    return slug or "untitled"


def _build_source(path: Path, meta: dict, source_type: str) -> Source:
    return Source(
        source_id=meta.get("id") or _source_id(path),
        title=meta.get("title") or path.stem.replace("-", " ").title(),
        author=meta.get("author", ""),
        source_type=source_type,
        url=meta.get("url", ""),
        unit=meta.get("unit", "chapter"),
    )


def load_notes(path: Path) -> tuple[Source, list[Section]]:
    """data/books/*.md — highlights and notes under `## Chapter N` headings."""
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return _build_source(path, meta, "book_notes"), split_into_sections(body)


def load_full_text(path: Path) -> tuple[Source, list[Section]]:
    """data/texts/* — full narrative text, chapters detected from the prose."""
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    sections = split_into_sections(body)
    if not any(s.position > 0 for s in sections):
        # No positions found — everything lands at 0, so the spoiler filter can't
        # do its job. Worth shouting about rather than silently degrading.
        raise ValueError(
            f"{path.name}: no chapter or page headings detected. The character graph "
            f"needs position boundaries to be spoiler-safe. Add `## Chapter 1`-style "
            f"headings, or re-import the PDF with "
            f"`python -m backend.scripts.import_pdf <file> --mode pages`."
        )
    return _build_source(path, meta, "book_text"), sections


def load_article(path: Path) -> tuple[Source, list[Section]]:
    """data/articles/*.md — a saved article. No chapters, so position 0."""
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    source = _build_source(path, meta, "article")
    return source, [Section(0, source.title, body.strip())]
