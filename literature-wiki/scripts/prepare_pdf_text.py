#!/usr/bin/env python3
"""Convert local corpus PDFs into compact, page-marked text files.

The output is a derived search layer. PDFs remain the authority for visual tables,
equations, figures, metadata, and any extraction ambiguity.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "pdfs"
OUT_DIR = ROOT / "sources" / "pdf_text"
PAPERS_CSV = ROOT / "papers.csv"
MANIFEST = OUT_DIR / "manifest.csv"


def slug(value: str, limit: int = 100) -> str:
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"[^A-Za-z0-9._+ -]+", "", value)
    value = re.sub(r"\s+", "_", value.strip())
    return value[:limit].rstrip("_")


def find_pdf(index: int) -> Path | None:
    matches = sorted(PDF_DIR.glob(f"{index:02d}_*.pdf"))
    if len(matches) > 1:
        raise RuntimeError(f"multiple PDFs for paper {index}: {matches}")
    return matches[0] if matches else None


def page_count(pdf: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf)], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    if not match:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(match.group(1))


def extract_page(pdf: Path, page: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.replace("\f", "").rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="replace existing text")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PAPERS_CSV.open(encoding="utf-8", newline="") as handle:
        papers = list(csv.DictReader(handle))

    results = []
    errors = 0
    for row in papers:
        index = int(row["index"])
        pdf = find_pdf(index)
        output = OUT_DIR / f"{index:02d}_{slug(row['title'])}.txt"
        result = {
            "index": str(index),
            "title": row["title"],
            "pdf": str(pdf.relative_to(ROOT)) if pdf else "",
            "text": str(output.relative_to(ROOT)) if pdf else "",
            "pages": "",
            "status": "missing-pdf" if pdf is None else "pending",
            "error": "",
        }
        if pdf is None:
            results.append(result)
            continue
        try:
            pages = page_count(pdf)
            result["pages"] = str(pages)
            if output.exists() and not args.force:
                result["status"] = "ok-existing"
            else:
                chunks = []
                for page in range(1, pages + 1):
                    chunks.append(f"=== PDF PAGE {page} ===\n{extract_page(pdf, page)}")
                output.write_text("\n\n".join(chunks).rstrip() + "\n", encoding="utf-8")
                result["status"] = "ok"
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            errors += 1
        results.append(result)
        print(f"[{index:02d}/{len(papers)}] {result['status']}: {row['title']}", flush=True)

    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["index", "title", "pdf", "text", "pages", "status", "error"]
        )
        writer.writeheader()
        writer.writerows(results)

    ready = sum(item["status"].startswith("ok") for item in results)
    missing = sum(item["status"] == "missing-pdf" for item in results)
    print(f"Done: {ready} ready, {missing} missing PDFs, {errors} errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
