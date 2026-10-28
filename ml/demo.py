"""Interactively try the ML analyzer before a backend or frontend exists."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from .analyzer import ErrorAnalyzer


def read_source(
    language: str,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str | None:
    """Read a multiline source snippet, ending when the user enters END."""
    output_fn(
        f"Paste {language.upper()} source below. Enter END on its own line when done."
    )
    lines: list[str] = []
    while True:
        line = input_fn("")
        if line == "END":
            break
        lines.append(line)
    source = "\n".join(lines)
    return source if source.strip() else None


def run_demo(top_k: int = 3) -> dict[str, object]:
    """Prompt for source files and print model predictions plus parser output."""
    analyzer = ErrorAnalyzer()
    sources = {
        language: read_source(language)
        for language in ("html", "css", "javascript")
    }
    result = analyzer.analyze(**sources, top_k=top_k)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if args.top_k <= 0:
        parser.error("--top-k must be a positive integer")
    run_demo(top_k=args.top_k)


if __name__ == "__main__":
    main()
