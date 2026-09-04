"""PDF -> clean, position-marked text.

PDF text extraction is where position tagging usually breaks, so this module does
three jobs before the normal ingestion pipeline ever sees the text:

1. Strip the furniture — running headers, footers, and bare page numbers repeat on
   every page and would otherwise become the highest-frequency "content" in the book.
2. Rebuild paragraphs — PDFs carry a hard line break at every *visual* line, plus
   hyphens across line ends. Left alone, chunks split mid-sentence.
3. Find positions — chapter headings if the book has detectable ones, page numbers
   if it doesn't. Real books use both, so the plan's "chapter/page position" (NFR1)
   is taken literally here.

Chapter numbering is normalised to a monotonic sequence. A book with PART TWO /
CHAPTER ONE restarts its chapter count per part; positions must never go backwards
or the spoiler bound is meaningless, so parts are flattened into one running count.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)

# "CHAPTER III: Marilla Cuthbert is Surprised", "CHAPTER ONE", "Chapter 12", "12."
# The spelled-out alternative must be greedy: a lazy `+?` matches just the "O" of
# "ONE", which then fails to parse as a number and the heading is missed entirely.
# It can't swallow a following title because `:` / `.` aren't in its class.
_CHAPTER_RE = re.compile(
    r"^\s*chapter\s+(?P<num>[0-9]+|[ivxlcdm]+|[a-z][a-z\- ]{0,20})\s*[:.—–-]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
_PART_RE = re.compile(r"^\s*part\s+(?P<num>[0-9]+|[ivxlcdm]+|[a-z\- ]+?)\s*[:.]?\s*$", re.IGNORECASE)
_BARE_ROMAN_RE = re.compile(r"^\s*(?P<num>[ivxlcdm]{1,7})\s*[.:]?\s*$")
_BARE_NUMBER_RE = re.compile(r"^\s*(?P<num>\d{1,3})\s*$")
_NAMED_RE = re.compile(r"^\s*(prologue|epilogue|foreword|afterword|preface)\s*$", re.IGNORECASE)


def _roman_to_int(value: str) -> int:
    total, prev = 0, 0
    for char in reversed(value.lower()):
        current = _ROMAN_VALUES[char]
        total += -current if current < prev else current
        prev = max(prev, current)
    return total


def _words_to_int(text: str) -> int | None:
    """'twenty-one' -> 21. Returns None if any word isn't a number word."""
    total = 0
    for word in re.split(r"[\s-]+", text.strip().lower()):
        if not word:
            continue
        if word not in _WORD_NUMBERS:
            return None
        total += _WORD_NUMBERS[word]
    return total or None


def parse_number(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if _ROMAN_RE.match(raw):
        try:
            return _roman_to_int(raw)
        except KeyError:
            return None
    return _words_to_int(raw)


# --- Cleaning ------------------------------------------------------------


def strip_furniture(pages: list[str], threshold: float = 0.25) -> list[str]:
    """Remove running headers/footers: short lines that repeat across many pages."""
    if len(pages) < 8:
        return pages

    counts: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        # Furniture lives in the top/bottom two lines of a page.
        for line in set(lines[:2] + lines[-2:]):
            if len(line) <= 60:
                counts[line] += 1

    cutoff = max(3, int(len(pages) * threshold))
    furniture = {line for line, count in counts.items() if count >= cutoff}

    cleaned = []
    for page in pages:
        kept = [
            line
            for line in page.splitlines()
            if line.strip() not in furniture and not _BARE_NUMBER_RE.match(line)
        ]
        cleaned.append("\n".join(kept))
    return cleaned


# Sentinel standing in for a real paragraph break while single newlines
# (PDF line wraps) are collapsed. Any character that cannot occur in the
# extracted text works; \x1f is the ASCII unit separator.
_PARA = "\x1f"


def looks_like_heading(line: str) -> bool:
    """Cheap structural test used to protect headings from paragraph rebuilding."""
    line = line.strip()
    if not line or len(line) > 70:
        return False
    if _PART_RE.match(line) or _NAMED_RE.match(line):
        return True
    if _BARE_ROMAN_RE.match(line):
        return True
    match = _CHAPTER_RE.match(line)
    return bool(match and parse_number(match.group("num")) is not None)


def rebuild_paragraphs(text: str) -> str:
    """Undo PDF line wrapping so chunks don't split mid-sentence."""
    text = re.sub(r"(\w)[-‐‑]\n(\w)", r"\1\2", text)  # de-hyphenate

    # Headings must survive as standalone lines — joining them into the following
    # paragraph is exactly what hides them from find_headings().
    text = "\n".join(
        f"{_PARA}{line.strip()}{_PARA}" if looks_like_heading(line) else line
        for line in text.splitlines()
    )

    text = re.sub(r"\n{2,}", _PARA, text)  # protect real paragraph breaks

    # A single newline is a wrap unless the line clearly ended a sentence or the
    # next line starts something new (heading, dialogue, capitalised opener).
    def join(match: re.Match) -> str:
        before, after = match.group(1), match.group(2)
        if before[-1] in ".!?\"'”’:" and (after[0].isupper() or after[0] in "“\"'"):
            return f"{before}{_PARA}{after}"
        return f"{before} {after}"

    text = re.sub(r"(\S)\n(\S)", join, text)
    text = text.replace(_PARA, "\n\n")
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# --- Position detection --------------------------------------------------


@dataclass
class Heading:
    line_index: int
    label: str
    kind: str  # chapter | part | named
    number: int | None = None  # the chapter number as printed, if any


@dataclass
class ImportPlan:
    title: str
    author: str
    unit: str  # chapter | page
    positions: int
    headings: list[str] = field(default_factory=list)
    pages: int = 0
    note: str = ""


def find_headings(lines: list[str]) -> list[Heading]:
    """Locate chapter-like headings. Only short, standalone lines qualify."""
    headings: list[Heading] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or len(line) > 70:
            continue

        if _PART_RE.match(line):
            headings.append(Heading(index, line.title(), "part"))
            continue
        if _NAMED_RE.match(line):
            headings.append(Heading(index, line.title(), "named"))
            continue

        match = _CHAPTER_RE.match(line)
        if match and parse_number(match.group("num")) is not None:
            number = parse_number(match.group("num"))
            title = match.group("title").strip(" :.-—")
            label = f"Chapter {number}" + (f": {title}" if title else "")
            headings.append(Heading(index, label, "chapter", number))
            continue

        # A lone roman numeral or number on its own line, surrounded by blanks —
        # a common chapter marker once the page furniture is gone.
        bare = _BARE_ROMAN_RE.match(line)
        if bare and index + 1 < len(lines):
            neighbours_blank = (index == 0 or not lines[index - 1].strip())
            if neighbours_blank and parse_number(bare.group("num")):
                bare_number = parse_number(bare.group("num"))
                headings.append(Heading(index, f"Chapter {bare_number}", "chapter", bare_number))
    return drop_contents_listing(headings)


def drop_contents_listing(
    headings: list[Heading], body_gap: int = 15, run_length: int = 4
) -> list[Heading]:
    """Discard table-of-contents entries.

    A contents page lists headings a few lines apart with no prose between them;
    real chapters are separated by hundreds of lines of body text. So group the
    headings into runs of tightly-spaced neighbours and drop any run long enough
    to be a listing rather than a couple of genuinely short chapters.

    Without this, a book's TOC silently consumes the first N positions and every
    real chapter is numbered N too high — the spoiler bound still holds, but every
    label is wrong, which is worse because it looks like it works.
    """
    if len(headings) < run_length:
        return headings

    runs: list[list[Heading]] = [[headings[0]]]
    for previous, heading in zip(headings, headings[1:]):
        if heading.line_index - previous.line_index < body_gap:
            runs[-1].append(heading)
        else:
            runs.append([heading])

    return [h for run in runs if len(run) < run_length for h in run]


def build_chapter_text(lines: list[str], headings: list[Heading]) -> tuple[str, list[str]]:
    """Emit text with normalised, monotonically-numbered `## Chapter N` markers.

    Part boundaries are absorbed: a book that restarts numbering inside PART TWO
    still gets one increasing sequence, because a position that goes backwards
    breaks the `position <= reader_position` guarantee.
    """
    positions = _assign_positions([h for h in headings if h.kind != "part"])

    out: list[str] = []
    labels: list[str] = []
    by_index = {h.line_index: h for h in headings}

    for index, line in enumerate(lines):
        heading = by_index.get(index)
        if heading is None:
            out.append(line)
            continue
        if heading.kind == "part":
            out.append(f"\n{heading.label}\n")  # keep as prose, not a position
            continue
        labels.append(heading.label)
        out.append(f"\n## Chapter {positions[heading.line_index]}\n")
        if heading.kind == "named" or ":" in heading.label:
            out.append(f"*{heading.label}*\n")  # keep the original title as content
    return "\n".join(out), labels


def _assign_positions(headings: list[Heading]) -> dict[int, int]:
    """Map each heading to its position number.

    Prefer the book's own chapter numbers — then "chapter 10" in the UI is chapter
    10 in the reader's hands. That only works if they run strictly upward; a book
    that restarts numbering inside each PART (Crime and Punishment does) would
    produce positions that go backwards and break the `<=` spoiler bound, so those
    fall back to a sequential count.
    """
    numbers = [h.number for h in headings]
    printed_usable = (
        all(n is not None for n in numbers)
        and all(a < b for a, b in zip(numbers, numbers[1:]))
    )
    if printed_usable:
        return {h.line_index: h.number for h in headings}
    return {h.line_index: i for i, h in enumerate(headings, start=1)}


def build_page_text(pages: list[str]) -> str:
    """Fallback: one position per page, for books with no detectable chapters."""
    blocks = []
    for number, page in enumerate(pages, start=1):
        body = page.strip()
        if body:
            blocks.append(f"\n## Page {number}\n\n{body}")
    return "\n".join(blocks)


# --- Entry point ---------------------------------------------------------


def convert(
    pdf_path: Path,
    title: str | None = None,
    author: str | None = None,
    mode: str = "auto",
    min_chapters: int = 3,
) -> tuple[str, ImportPlan]:
    """Convert a PDF to position-marked text. Returns (file_contents, plan)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pypdf is required: pip install pypdf") from exc

    reader = PdfReader(str(pdf_path))
    raw_pages = [(page.extract_text() or "") for page in reader.pages]

    extracted = sum(len(p) for p in raw_pages)
    if extracted < 200 * len(raw_pages):
        raise ValueError(
            f"{pdf_path.name}: only {extracted // max(len(raw_pages), 1)} chars/page "
            f"extracted — this looks like a scanned PDF and needs OCR, not this importer."
        )

    pages = strip_furniture(raw_pages)
    pages = [rebuild_paragraphs(page) for page in pages]

    guessed_title, _, guessed_author = pdf_path.stem.partition(" - ")
    title = title or re.sub(r"[_\s]*\(?[Ww]orldfreebooks\.com\)?[_\s]*", "", guessed_title).strip()
    author = author or re.sub(r"[_\s]*\(?[Ww]orldfreebooks\.com\)?[_\s]*", "", guessed_author).strip()

    lines = "\n".join(pages).splitlines()
    headings = [h for h in find_headings(lines) if h.kind != "part"]

    use_chapters = mode == "chapters" or (mode == "auto" and len(headings) >= min_chapters)
    if use_chapters and not headings:
        raise ValueError(f"{pdf_path.name}: no chapter headings found — use --mode pages.")

    if use_chapters:
        body, labels = build_chapter_text(lines, find_headings(lines))
        plan = ImportPlan(title, author, "chapter", len(labels), labels[:6], len(pages))
    else:
        body = build_page_text(pages)
        plan = ImportPlan(
            title, author, "page", len([p for p in pages if p.strip()]), [], len(pages),
            note="No reliable chapter headings — using page positions instead.",
        )

    front = f"---\ntitle: {title}\nauthor: {author}\nunit: {plan.unit}\n---\n"
    return front + body, plan
