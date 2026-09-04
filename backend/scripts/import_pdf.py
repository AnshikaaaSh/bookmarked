"""Convert book PDFs into position-marked text under data/texts/.

    # See what it detects, without writing anything:
    python -m backend.scripts.import_pdf ~/Downloads/*.pdf --dry-run

    # Convert one book:
    python -m backend.scripts.import_pdf ~/Downloads/book.pdf

    # Override detection:
    python -m backend.scripts.import_pdf ~/Downloads/book.pdf --mode pages \
        --title "The Society" --author "Jodie Andrefski"

Always dry-run first. Chapter detection is the thing that makes the spoiler bound
meaningful, and it's worth eyeballing the detected headings before ingesting a
600-page book.

After converting, run: python -m backend.scripts.ingest
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ..config import TEXTS_DIR, ensure_dirs
from ..ingestion.pdf import convert


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "untitled"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert book PDFs to position-marked text.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--mode", choices=["auto", "chapters", "pages"], default="auto",
                        help="How to assign positions (default: auto-detect).")
    parser.add_argument("--title", help="Override the title (single file only).")
    parser.add_argument("--author", help="Override the author (single file only).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be detected without writing.")
    parser.add_argument("--out", type=Path, default=None, help="Output directory.")
    args = parser.parse_args(argv)

    if (args.title or args.author) and len(args.pdfs) > 1:
        parser.error("--title/--author apply to a single file.")

    ensure_dirs()
    out_dir = args.out or TEXTS_DIR
    failures = 0

    for pdf in args.pdfs:
        if not pdf.exists():
            print(f"  MISSING  {pdf}")
            failures += 1
            continue

        try:
            contents, plan = convert(pdf, title=args.title, author=args.author, mode=args.mode)
        except Exception as exc:
            print(f"  FAIL     {pdf.name}\n           {exc}")
            failures += 1
            continue

        target = out_dir / f"{_slug(plan.title)}.txt"
        verb = "would write" if args.dry_run else "wrote"

        print(f"\n  {plan.title}" + (f" — {plan.author}" if plan.author else ""))
        print(f"    {plan.pages} pages -> {plan.positions} {plan.unit} positions")
        if plan.headings:
            preview = " | ".join(h[:38] for h in plan.headings[:4])
            print(f"    detected: {preview}{' | …' if plan.positions > 4 else ''}")
        if plan.note:
            print(f"    note: {plan.note}")
        print(f"    {verb}: {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}")

        if not args.dry_run:
            target.write_text(contents, encoding="utf-8")

    if args.dry_run:
        print("\nDry run — nothing written. Drop --dry-run to convert.")
    elif not failures:
        print("\nNow run: python -m backend.scripts.ingest")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
