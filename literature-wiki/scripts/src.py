#!/usr/bin/env python3
"""Small source reader for the wiki corpus.

Usage:
  src.py <pattern> meta
  src.py <pattern> source
  src.py <pattern> pdf N [M]
  src.py <pattern> grep REGEX

`pattern` may be a paper number (for example ``01``) or part of a filename.
PDF extraction uses Poppler's pdftotext so no Python package is required.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
ARXIV_DIR = ROOT / "sources" / "arxiv"
PDF_TEXT_DIR = ROOT / "sources" / "pdf_text"


def die(message: str) -> "NoReturn":
    raise SystemExit(message)


def find_one(pattern: str, paths: list[Path], kind: str) -> Path:
    needle = pattern.casefold()
    if pattern.isdigit():
        prefix = f"{int(pattern):02d}_"
        hits = [path for path in sorted(paths) if path.name.startswith(prefix)]
    else:
        hits = [path for path in sorted(paths) if needle in path.name.casefold()]
    if not hits:
        die(f"no {kind} match for {pattern!r}")
    if len(hits) > 1:
        die("ambiguous:\n" + "\n".join(str(path.relative_to(ROOT)) for path in hits))
    return hits[0]


def find_pdf(pattern: str) -> Path:
    return find_one(pattern, list(PDF_DIR.glob("*.pdf")), "PDF")


def find_source(pattern: str) -> Path:
    candidates = list(ARXIV_DIR.glob("*/paper.expanded.tex"))
    needle = pattern.casefold()
    if pattern.isdigit():
        prefix = f"{int(pattern):02d}_"
        hits = [path for path in candidates if path.parent.name.startswith(prefix)]
    else:
        hits = [path for path in candidates if needle in path.parent.name.casefold()]
    if not hits:
        die(f"no prepared source match for {pattern!r}")
    if len(hits) > 1:
        die("ambiguous:\n" + "\n".join(str(path.relative_to(ROOT)) for path in hits))
    return hits[0]


def find_pdf_text(pattern: str) -> Path:
    return find_one(pattern, list(PDF_TEXT_DIR.glob("*.txt")), "PDF text")


def run(command: list[str]) -> str:
    process = subprocess.run(command, text=True, capture_output=True)
    if process.returncode:
        die(process.stderr.strip() or f"command failed: {' '.join(command)}")
    return process.stdout


def pdf_page(path: Path, page: int) -> str:
    return run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(path), "-"])


def main() -> None:
    if len(sys.argv) < 3:
        die(__doc__.strip())
    pattern, command = sys.argv[1:3]

    if command == "source":
        try:
            source = find_source(pattern)
        except SystemExit:
            source = find_pdf_text(pattern)
        print(f"### FILE {source.relative_to(ROOT)}")
        print(source.read_text(encoding="utf-8", errors="replace"))
        return

    pdf = find_pdf(pattern)
    if command == "meta":
        print(f"FILE: {pdf.relative_to(ROOT)}")
        print(run(["pdfinfo", str(pdf)]).rstrip())
        print("--- PDF PAGE 1 ---")
        print(pdf_page(pdf, 1))
    elif command == "pdf":
        if len(sys.argv) < 4:
            die("pdf requires a first page number")
        first = int(sys.argv[3])
        last = int(sys.argv[4]) if len(sys.argv) > 4 else first
        if first < 1 or last < first:
            die("invalid page range")
        for page in range(first, last + 1):
            print(f"=== PDF PAGE {page} ===")
            print(pdf_page(pdf, page))
    elif command == "grep":
        if len(sys.argv) < 4:
            die("grep requires a regular expression")
        regex = re.compile(sys.argv[3], re.IGNORECASE)
        info = run(["pdfinfo", str(pdf)])
        match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
        if not match:
            die("could not determine PDF page count")
        for page in range(1, int(match.group(1)) + 1):
            for line in pdf_page(pdf, page).splitlines():
                if regex.search(line):
                    print(f"p{page}: {line}")
    else:
        die(f"unknown command {command!r}\n\n{__doc__.strip()}")


if __name__ == "__main__":
    main()
