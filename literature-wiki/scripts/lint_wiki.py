#!/usr/bin/env python3
"""Validate wiki structure, provenance, claims, numbers, and PDF anchors."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
BIB = ROOT / "references.bib"

REQUIRED_FRONTMATTER = {"type", "status", "created", "updated", "sources"}
TYPE_BY_DIR = {
    "papers": "paper",
    "concepts": "concept",
    "methods": "method",
    "datasets": "dataset",
    "metrics": "metric",
    "comparisons": "comparison",
    "open-questions": "open-question",
    "textbook": "chapter",
}
FIXED_HEADINGS = {
    "paper": [
        "Problem", "Method", "Assumptions", "Datasets", "Metrics", "Results",
        "Limitations", "Relations", "Concepts introduced",
    ],
    "concept": [
        "Definition in use", "Competing definitions", "Why it matters",
        "How it is measured", "Open disagreements", "Appears in",
    ],
    "method": ["Core idea", "What it fixes", "What it costs", "Lineage", "Empirical standing"],
    "dataset": ["What it is", "Task and schema", "Standard splits", "Known issues", "Papers using it"],
    "metric": ["Definition", "What it actually captures", "Known failure modes", "Variants across papers"],
}
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
ANCHOR_LINK_RE = re.compile(r"\[\[([^\]|#]+)#([^\]|]+)(?:\|[^\]]+)?\]\]")
PAPER_LINK_RE = re.compile(r"\[\[papers/([a-z0-9-]+)(?:\|[^\]]+)?\]\]")
LOCATOR_RE = re.compile(
    r"(?:§+\s*\d|Tables?\s+\d|Figures?\s+\d|Equations?\s+\d|"
    r"Algorithms?\s+\d|PDF\s+p+\.\s*\d)", re.IGNORECASE,
)
INDEX_ACTIVE_RE = re.compile(
    r"^- \[\[([^\]|]+)(?:\|[^\]]+)?\]\].*?·\s*(\d+)\s+sources?\s*·\s*active\s*$",
    re.MULTILINE,
)
REVERSE_INDEX = {"dataset": "Papers using it", "concept": "Appears in"}
PAGE_LEVEL_REVERSE = {"method", "metric"}
BACKLINK_MARKER = "<!-- lint: paper-backlinks -->"
BACKLINK_PREFIX = "Linked from:"
VERBATIM_MARKER = "<!-- lint: verbatim-number -->"
# Locators and identifiers whose digits are not measurements.
NON_MEASUREMENT_RE = re.compile(
    r"(?:§+\s*[\d.]+(?:\s*[–-]\s*§?\s*[\d.]+)?"
    r"|\b(?:Tables?|Figures?|Fig\.|Equations?|Eq\.|Algorithms?|Appendix|Sections?|Theorems?|"
    r"Lemmas?|Propositions?|Definitions?|Examples?|Chapters?)\s*[A-Z]?[\d.]+(?:\s*[–,-]\s*[A-Z]?[\d.]+)*"
    r"|PDF\s*pp?\.\s*\d+(?:\s*[–-]\s*\d+)?"
    r"|\b(?:19|20)\d\d\b"
    r"|\b[A-Za-z]+\d+[A-Za-z]*(?:-\d+)*\b"
    r"|@\d+)"
)
# TeX spans: their digits are indices and constants, so measurements must stay outside them.
MATH_RE = re.compile(r"\$\$.*?\$\$|(?<!\\)\$(?:[^$\n]|\n(?!\n))+?(?<!\\)\$", re.S)
MEASUREMENT_RE = re.compile(r"(?<![\w.])[−-]?\d+(?:[.,]\d+)*%?")


@dataclass
class Page:
    path: Path
    rel: str
    meta: dict
    body: str


class Lint:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, page: str, message: str) -> None:
        self.errors.append(f"ERROR {page}: {message}")

    def warn(self, page: str, message: str) -> None:
        self.warnings.append(f"WARN  {page}: {message}")


def parse_page(path: Path, lint: Lint) -> Page | None:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    rel = path.relative_to(WIKI).with_suffix("").as_posix()
    if not match:
        lint.error(rel, "missing YAML frontmatter")
        return None
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        lint.error(rel, f"invalid YAML: {exc}")
        return None
    if not isinstance(meta, dict):
        lint.error(rel, "frontmatter must be a mapping")
        return None
    return Page(path, rel, meta, match.group(2))


def headings(body: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE)]


def heading_slugs(body: str) -> set[str]:
    """Ids that build_site.py gives to ## and ### headings."""
    return {re.sub(r"[^a-z0-9]+", "-", match.group(1).lower()).strip("-")
            for match in re.finditer(r"^#{2,3}\s+(.+?)\s*$", body, re.MULTILINE)}


def paragraphs_with_sections(body: str) -> list[tuple[str, str]]:
    section = ""
    current: list[str] = []
    result: list[tuple[str, str]] = []
    for line in body.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            if current:
                result.append((section, "\n".join(current)))
                current = []
            section = heading.group(1)
        elif not line.strip():
            if current:
                result.append((section, "\n".join(current)))
                current = []
        elif not line.startswith("# "):
            current.append(line)
    if current:
        result.append((section, "\n".join(current)))
    return result


def bib_keys() -> set[str]:
    if not BIB.exists():
        return set()
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", BIB.read_text(encoding="utf-8")))


def structural_checks(pages: dict[str, Page], lint: Lint) -> None:
    keys = bib_keys()
    for rel, page in pages.items():
        missing = REQUIRED_FRONTMATTER - set(page.meta)
        if missing:
            lint.error(rel, f"missing frontmatter keys: {', '.join(sorted(missing))}")
        if page.meta.get("status") not in {"active", "planned"}:
            lint.error(rel, "status must be active or planned")
        sources = page.meta.get("sources")
        if not isinstance(sources, list) or any(not isinstance(item, str) for item in sources):
            lint.error(rel, "sources must be a list of citekeys")
            sources = []
        unknown = set(sources) - keys
        if unknown:
            lint.error(rel, f"sources absent from references.bib: {', '.join(sorted(unknown))}")

        first = rel.split("/", 1)[0]
        expected_type = TYPE_BY_DIR.get(first)
        if expected_type and page.meta.get("type") != expected_type:
            lint.error(rel, f"directory requires type: {expected_type}")
        if page.meta.get("type") == "chapter" and headings(page.body)[-1:] != ["Where to read next"]:
            lint.error(rel, "a chapter must end with the heading: Where to read next")
        required = FIXED_HEADINGS.get(str(page.meta.get("type")))
        if required:
            actual = headings(page.body)
            if actual != required:
                lint.error(rel, f"headings must be exactly: {'; '.join(required)}")

        for target in LINK_RE.findall(page.body):
            if target not in pages:
                lint.error(rel, f"broken wiki link [[{target}]]")
        for target, anchor in ANCHOR_LINK_RE.findall(page.body):
            if target in pages and anchor not in heading_slugs(pages[target].body):
                lint.error(rel, f"no heading #{anchor} in [[{target}]]")

        if page.meta.get("type") not in {"index", "vocabulary", "log", "pins"}:
            scope = page.body
            if page.meta.get("type") == "paper":
                # Relations may link other paper pages as navigation, not as sources.
                scope = scope.replace(section_body(page.body, "Relations"), "")
            linked_sources = set(PAPER_LINK_RE.findall(scope))
            drift = linked_sources - set(sources)
            if drift:
                lint.error(rel, f"paper links absent from sources: {', '.join(sorted(drift))}")

        if page.meta.get("type") == "paper" and page.meta.get("status") == "active":
            citekey = page.meta.get("citekey")
            if citekey not in keys:
                lint.error(rel, f"active paper citekey {citekey!r} absent from references.bib")
            if sources != [citekey]:
                lint.error(rel, "active paper sources must contain its own citekey only")
            for field in ("local_pdf", "source_text"):
                value = page.meta.get(field)
                if not value or not (ROOT / value).is_file():
                    lint.error(rel, f"missing or invalid {field}: {value!r}")

    index = pages.get("index")
    if index:
        for target, expected_count in INDEX_ACTIVE_RE.findall(index.body):
            if target not in pages:
                lint.error("index", f"active entry has no page: {target}")
                continue
            actual_count = len(pages[target].meta.get("sources", []))
            if int(expected_count) != actual_count:
                lint.error("index", f"source-count drift for {target}: index={expected_count}, page={actual_count}")
        for rel in pages:
            if rel == "index":
                continue
            if f"[[{rel}]]" not in index.body:
                lint.error(rel, "active page is not linked from index")


def section_body(body: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        body, re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def backlink_checks(pages: dict[str, Page], lint: Lint) -> None:
    """Hold the materialized reverse indexes level with the paper link graph.

    A dataset's "Papers using it" is the exact inverse of the paper pages linking it.
    A concept's "Appears in" may also cite papers whose own page never names the
    concept, so it must only cover every paper that links in. Method and metric pages
    carry no reverse-index section, so they are held to the same covering rule against
    the whole page rather than one section.
    """
    inbound: dict[str, set[str]] = {}
    for rel, page in pages.items():
        if page.meta.get("type") != "paper":
            continue
        for target in LINK_RE.findall(page.body):
            inbound.setdefault(target, set()).add(rel)

    for rel, page in pages.items():
        heading = REVERSE_INDEX.get(str(page.meta.get("type")))
        if heading is None:
            continue
        listed = {
            target for target in LINK_RE.findall(section_body(page.body, heading))
            if target.startswith("papers/")
        }
        actual = inbound.get(rel, set())
        for missing in sorted(actual - listed):
            lint.error(rel, f"{heading!r} omits linking paper: {missing}")
        if page.meta.get("type") == "dataset":
            for extra in sorted(listed - actual):
                lint.error(rel, f"{heading!r} lists {extra}, whose page does not link back")

    for rel, page in pages.items():
        if page.meta.get("type") not in PAGE_LEVEL_REVERSE:
            continue
        cited = {f"papers/{key}" for key in PAPER_LINK_RE.findall(page.body)}
        for missing in sorted(inbound.get(rel, set()) - cited):
            lint.error(rel, f"page never cites linking paper: {missing}")

    for rel, expected, listed in paper_backlink_state(pages):
        if listed != expected:
            lint.error(rel, "Relations backlink line is stale; run --write-paper-backlinks")


def paper_backlink_state(pages: dict[str, Page]) -> list[tuple[str, set[str], set[str]]]:
    """For each paper page: (rel, papers whose Relations link it, papers its backlink line lists)."""
    inbound: dict[str, set[str]] = {}
    for rel, page in pages.items():
        if page.meta.get("type") != "paper":
            continue
        relations = section_body(page.body, "Relations")
        relations = "\n".join(line for line in relations.splitlines() if BACKLINK_MARKER not in line)
        for key in PAPER_LINK_RE.findall(relations):
            if f"papers/{key}" != rel:
                inbound.setdefault(f"papers/{key}", set()).add(rel)
    result = []
    for rel, page in pages.items():
        if page.meta.get("type") != "paper":
            continue
        listed: set[str] = set()
        for _, paragraph in paragraphs_with_sections(page.body):
            if BACKLINK_MARKER in paragraph:
                listed = {f"papers/{key}" for key in PAPER_LINK_RE.findall(paragraph)}
        result.append((rel, inbound.get(rel, set()), listed))
    return result


def write_paper_backlinks(pages: dict[str, Page]) -> int:
    """Materialize each paper page's backlink line at the end of its Relations section."""
    changed = 0
    for rel, expected, listed in paper_backlink_state(pages):
        if listed == expected:
            continue
        page = pages[rel]
        text = page.path.read_text(encoding="utf-8")
        text = re.sub(rf"\n*^{BACKLINK_PREFIX}.*?{re.escape(BACKLINK_MARKER)}\n", "\n", text, flags=re.MULTILINE | re.DOTALL)
        if expected:
            links = ", ".join(f"[[{target}]]" for target in sorted(expected))
            line = f"\n{BACKLINK_PREFIX} {links} {BACKLINK_MARKER}\n"
            text = re.sub(r"(?m)^## Concepts introduced\s*$", lambda m: line + "\n" + m.group(0), text, count=1)
        page.path.write_text(text, encoding="utf-8")
        changed += 1
    return changed


def claim_checks(pages: dict[str, Page], lint: Lint) -> None:
    exempt_sections = {"Appears in", "Papers using it"}
    for rel, page in pages.items():
        if page.meta.get("type") in {"index", "vocabulary", "log", "pins"}:
            continue
        for section, paragraph in paragraphs_with_sections(page.body):
            if section in exempt_sections or not PAPER_LINK_RE.search(paragraph):
                continue
            if BACKLINK_MARKER in paragraph:
                continue
            if not LOCATOR_RE.search(paragraph):
                snippet = re.sub(r"\s+", " ", paragraph)[:100]
                lint.error(rel, f"paper claim has no section/table/figure anchor: {snippet!r}")


def number_checks(pages: dict[str, Page], lint: Lint) -> None:
    for rel, page in pages.items():
        if page.meta.get("type") in {"index", "vocabulary", "log", "pins"}:
            continue
        for _, paragraph in paragraphs_with_sections(page.body):
            if "<!-- lint: verbatim-number -->" in paragraph:
                continue
            if not PAPER_LINK_RE.search(paragraph):
                continue
            cleaned = re.sub(r"\[\[[^\]]+\]\]", "", paragraph)
            cleaned = re.sub(r"`[^`]+`", "", cleaned)
            cleaned = MATH_RE.sub("", cleaned)
            cleaned = re.sub(
                r"§+\s*\d+(?:\.\d+)*(?:\s*[–-]\s*§?\s*\d+(?:\.\d+)*)?",
                "", cleaned,
            )
            cleaned = re.sub(
                r"(?:Tables?|Figures?|Equations?|Algorithms?)\s+\d+"
                r"(?:\s*(?:,?\s*and|[,;–-])\s*\d+)*",
                "", cleaned, flags=re.IGNORECASE,
            )
            # Identifiers such as dataset names (FB15k, WN18RR) are not measurements.
            cleaned = re.sub(r"\b[A-Z]{2,}\d+[A-Za-z]*\b", "", cleaned)
            # Cross-references between textbook chapters are not measurements.
            cleaned = re.sub(r"\bChapters?\s+\d+(?:\s*(?:–|-|to|and|,)\s*\d+)*", "", cleaned)
            if re.search(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?(?![A-Za-z0-9])", cleaned):
                snippet = re.sub(r"\s+", " ", paragraph)[:100]
                lint.error(rel, f"numeric claim lacks verbatim marker: {snippet!r}")


def pdf_text(path: Path, cache: dict[Path, str]) -> str:
    if path not in cache:
        process = subprocess.run(["pdftotext", "-layout", str(path), "-"], text=True, capture_output=True)
        if process.returncode:
            raise RuntimeError(process.stderr.strip())
        cache[path] = process.stdout
    return cache[path]


def paper_pdf_map(pages: dict[str, Page]) -> dict[str, Path]:
    result = {}
    for page in pages.values():
        if page.meta.get("type") != "paper" or page.meta.get("status") != "active":
            continue
        value = page.meta.get("local_pdf")
        if value:
            result[str(page.meta.get("citekey"))] = ROOT / value
    return result


def anchor_checks(pages: dict[str, Page], lint: Lint) -> None:
    pdfs = paper_pdf_map(pages)
    cache: dict[Path, str] = {}
    seen: set[tuple[str, str, str]] = set()
    for rel, page in pages.items():
        own = page.meta.get("citekey") if page.meta.get("type") == "paper" else None
        for paragraph in (item[1] for item in paragraphs_with_sections(page.body)):
            for link in PAPER_LINK_RE.finditer(paragraph):
                key = link.group(1)
                if own and key != own:
                    continue
                path = pdfs.get(key)
                if path is None or not path.is_file():
                    lint.error(rel, f"cannot validate anchors for inactive or missing PDF: {key}")
                    continue
                tail = paragraph[link.end():]
                next_link = PAPER_LINK_RE.search(tail)
                if next_link:
                    tail = tail[:next_link.start()]
                try:
                    text = pdf_text(path, cache)
                except RuntimeError as exc:
                    lint.error(rel, f"could not extract {path.name}: {exc}")
                    continue

                for section in re.findall(r"§+\s*(\d+(?:\.\d+)?)", tail):
                    token = (rel, key, f"§{section}")
                    if token in seen:
                        continue
                    seen.add(token)
                    pattern = rf"(?m)^\s*{re.escape(section)}\s+\S"
                    if not re.search(pattern, text):
                        lint.error(rel, f"anchor not found in {key}: §{section}")

                for label in ("Table", "Figure", "Equation", "Algorithm"):
                    pattern = rf"{label}s?\s+([0-9][0-9,\s–\-and]*)"
                    for group in re.findall(pattern, tail, re.IGNORECASE):
                        for number in re.findall(r"\d+", group):
                            token = (rel, key, f"{label} {number}")
                            if token in seen:
                                continue
                            seen.add(token)
                            anchor_pattern = rf"\b{label}\s+{number}\b"
                            if label == "Equation":
                                anchor_pattern = rf"(?:\bEquation\s+{number}\b|\({number}\))"
                            if not re.search(anchor_pattern, text, re.IGNORECASE):
                                lint.error(rel, f"anchor not found in {key}: {label} {number}")


def source_text(key: str, pages: dict[str, Page], pdfs: dict[str, Path], cache: dict[Path, str]) -> str:
    page = pages.get(f"papers/{key}")
    parts = []
    if page and key in pdfs and pdfs[key].is_file():
        try:
            parts.append(pdf_text(pdfs[key], cache))
        except RuntimeError:
            pass
    tex = page.meta.get("source_text") if page else None
    if tex and (ROOT / tex).is_file():
        parts.append((ROOT / tex).read_text(encoding="utf-8", errors="ignore"))
    return re.sub(r"\s+", " ", " ".join(parts))


def verify_number_checks(pages: dict[str, Page], lint: Lint) -> None:
    """Look up every number in a verbatim-marked paragraph in the text of the papers it cites.

    The text layer drops some table cells, so a miss is a warning to check the PDF by hand,
    not proof of an error.
    """
    pdfs = paper_pdf_map(pages)
    cache: dict[Path, str] = {}
    texts: dict[str, str] = {}
    for rel, page in pages.items():
        if page.meta.get("type") in {"index", "vocabulary", "log", "pins"}:
            continue
        for _, paragraph in paragraphs_with_sections(page.body):
            if VERBATIM_MARKER not in paragraph:
                continue
            keys = set(PAPER_LINK_RE.findall(paragraph))
            if not keys and page.meta.get("type") == "paper":
                keys = {str(page.meta.get("citekey"))}
            for key in keys:
                if key not in texts:
                    texts[key] = source_text(key, pages, pdfs, cache)
            blob = " ".join(texts[key] for key in keys)
            if not blob.strip():
                continue
            cleaned = re.sub(r"\[\[[^\]]+\]\]|`[^`]+`|<!--.*?-->", "", paragraph)
            cleaned = MATH_RE.sub("", cleaned)
            cleaned = NON_MEASUREMENT_RE.sub("", cleaned)
            for token in MEASUREMENT_RE.findall(cleaned):
                raw = token.replace("−", "-").rstrip("%")
                if re.fullmatch(r"-?\d", raw):
                    continue
                candidates = {raw, raw.replace(",", ""), raw.lstrip("-")}
                if "." in raw:
                    candidates |= {raw.rstrip("0").rstrip("."), raw + "0"}
                if not any(candidate and candidate in blob for candidate in candidates):
                    snippet = re.sub(r"\s+", " ", paragraph)[:80]
                    lint.warn(rel, f"number {token!r} not found in text of {', '.join(sorted(keys))}; check PDF: {snippet!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", action="store_true", help="require locators on paper-backed claims")
    parser.add_argument("--numbers", action="store_true", help="require PDF-verification markers on numeric claims")
    parser.add_argument("--anchors", action="store_true", help="check cited locators against active PDFs")
    parser.add_argument("--backlinks", action="store_true", help="check reverse indexes against the paper link graph")
    parser.add_argument("--verify-numbers", action="store_true", help="look up marked numbers in the cited papers' text (warnings)")
    parser.add_argument("--write-paper-backlinks", action="store_true", help="rewrite the 'Linked from' line of every paper page")
    args = parser.parse_args()

    lint = Lint()
    pages: dict[str, Page] = {}
    for path in sorted(WIKI.rglob("*.md")):
        page = parse_page(path, lint)
        if page:
            pages[page.rel] = page

    if args.write_paper_backlinks:
        print(f"Rewrote backlink lines on {write_paper_backlinks(pages)} paper page(s).")
        return 0

    structural_checks(pages, lint)
    if args.claims:
        claim_checks(pages, lint)
    if args.numbers:
        number_checks(pages, lint)
    if args.backlinks:
        backlink_checks(pages, lint)
    if args.anchors:
        anchor_checks(pages, lint)
    if args.verify_numbers:
        verify_number_checks(pages, lint)

    for message in lint.warnings + lint.errors:
        print(message)
    print(f"Checked {len(pages)} pages: {len(lint.errors)} error(s), {len(lint.warnings)} warning(s).")
    return 1 if lint.errors else 0


if __name__ == "__main__":
    sys.exit(main())
