"""Eval harness for the Ask agent (NFR3).

    python -m backend.scripts.eval                    # run every case
    python -m backend.scripts.eval --id gatsby-narrator  # run just one

Deliberately not RAGAS or any other framework — a JSON file of cases plus this
scoring script measures the two things NFR3 actually asks for (retrieval hit
rate, answer faithfulness) and is easy to explain to someone reading the code.
It doubles as a spoiler-safety regression suite: several cases assert that a
citation never exceeds a given position, or that a fact from later in the book
never appears in the answer — exactly the guarantee the whole project is built
around, now checked automatically instead of by hand each time something changes.

Each case in data/eval/cases.json may assert any combination of:
  expect_keywords              every string must appear in the answer (case-insensitive)
  expect_no_keywords           none of these may appear (spoiler-leak check)
  expect_web                   used_web must match this bool exactly
  expect_max_citation_position no citation's `position` may exceed this

Every real LLM call costs quota — this makes one per case. Free-tier models can
also legitimately word an answer around a keyword rather than using it verbatim,
so a failure here is a signal to go read the trace, not an automatic bug.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..agent import ask
from ..config import DATA_DIR
from ..llm.providers import LLMConfigError, LLMUnavailableError

CASES_FILE = DATA_DIR / "eval" / "cases.json"


def _check(case: dict, result) -> list[str]:
    """Return a list of failure reasons; empty means the case passed."""
    failures = []
    answer_lower = result.answer.lower()

    for keyword in case.get("expect_keywords", []):
        if keyword.lower() not in answer_lower:
            failures.append(f"missing expected keyword {keyword!r}")

    for keyword in case.get("expect_no_keywords", []):
        if keyword.lower() in answer_lower:
            failures.append(f"leaked forbidden keyword {keyword!r} (SPOILER LEAK)")

    if "expect_web" in case and result.used_web != case["expect_web"]:
        failures.append(f"used_web={result.used_web}, expected {case['expect_web']}")

    max_position = case.get("expect_max_citation_position")
    if max_position is not None:
        for citation in result.citations:
            if citation.source_type != "web" and citation.position > max_position:
                failures.append(
                    f"citation at position {citation.position} exceeds bound "
                    f"{max_position} (SPOILER LEAK): {citation.label}"
                )

    return failures


def run(cases: list[dict]) -> tuple[int, int]:
    passed = 0
    for case in cases:
        cid = case["id"]
        try:
            result = ask(
                case["question"],
                source_id=case.get("source_id"),
                position=case.get("position"),
            )
        except (LLMConfigError, LLMUnavailableError) as exc:
            print(f"  ERROR  {cid}: {exc}")
            continue

        failures = _check(case, result)
        if failures:
            print(f"  FAIL   {cid}")
            for f in failures:
                print(f"           {f}")
            if case.get("note"):
                print(f"           note: {case['note']}")
        else:
            passed += 1
            print(f"  pass   {cid}  (retrieved={result.retrieved}, used_web={result.used_web})")

    return passed, len(cases)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Ask agent eval harness.")
    parser.add_argument("--id", help="Run only the case with this id.")
    args = parser.parse_args(argv)

    if not CASES_FILE.exists():
        print(f"No eval cases found at {CASES_FILE}")
        return 1

    cases = json.loads(CASES_FILE.read_text())
    if args.id:
        cases = [c for c in cases if c["id"] == args.id]
        if not cases:
            print(f"No case with id '{args.id}'")
            return 1

    print(f"Running {len(cases)} case(s) — each makes a real LLM call.\n")
    passed, total = run(cases)

    print(f"\n{passed}/{total} passed ({round(100 * passed / total)}%)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
