#!/usr/bin/env python3
"""Scaffold a source-grounded literature wiki in a project directory.

Creates (never overwrites):
  .tools/            source reader, lint, site builder, downloaders, KaTeX assets
  wiki/              index, vocabulary, pins, log, overview, and the page directories
  AGENTS.md          the editing contract for Codex
  CLAUDE.md          the same editing contract for Claude
  wiki.yaml          name and logo mark used by the static site
  papers.csv         corpus template (index,title,year,venue,category,priority,direct_pdf_url)
  references.bib     empty BibTeX file
  .gitignore

Usage: python3 init_wiki.py <project_dir> --name "Causal Discovery" --topic "..." [--mark "C"]
"""

from __future__ import annotations

import argparse
import datetime
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TOOLS = ["src.py", "lint_wiki.py", "build_site.py", "fetch_figures.py", "download_papers.py",
         "find_arxiv_ids.py", "prepare_arxiv_sources.py", "prepare_pdf_text.py", "check_math.js"]
DIRS = ["papers", "concepts", "methods", "datasets", "metrics", "comparisons", "open-questions", "textbook"]

FIGURES_YAML = """\
# Figures shown on the static site (built by .tools/build_site.py).
#
# Keys are wiki page paths. Each entry is one figure, placed at the end of `section`
# (default: Method; the first section when the page has no such heading). `section` may
# name a ### subsection too.
#   fig: N          Figure N as printed in the local PDF.
#   tex: N          position among the TeX figure environments, when it differs from fig
#                   (the arXiv version is not always the version in pdfs/).
#   paper: key      citekey the figure comes from (default: the paper page itself).
#   parts: [1, 2]   subset of a figure's image files (arXiv figures only).
#   crop: {page, box}  cut the figure from the local PDF instead of the arXiv source;
#                   box is [x0, y0, x1, y1] as fractions of the page. Needs `caption`.
#   caption: text   overrides the caption recovered from the TeX source.
#   note: text      our remark, shown in italics under the authors' caption.
#
# arXiv figures come from sources/arxiv/*/figures/ (python3 .tools/fetch_figures.py).
# python3 .tools/build_site.py --check-figures confirms each fig number against the PDF.
#
# papers/smith2020:
#   - {fig: 1, section: Problem}
#   - fig: 3
#     crop: {page: 5, box: [0.1, 0.07, 0.9, 0.3]}
#     caption: "The architecture."
"""


def front(type_: str, today: str) -> str:
    return f"---\ntype: {type_}\nstatus: active\ncreated: {today}\nupdated: {today}\nsources: []\n---\n\n"


def meta_pages(name: str, topic: str, today: str) -> dict[str, str]:
    return {
        "index.md": front("index", today) + f"""# Index

Every approved wiki page is listed here. Read this page first. `active` means the page
has an evidence-backed body; `planned` reserves a controlled name but makes no claim.

## Meta

- [[index]] — this file · active
- [[overview]] — synthesis over the active evidence boundary · 0 sources · active
- [[vocabulary]] — citekeys, canonical names, and aliases · active
- [[pins]] — durable human corrections and constraints · active
- [[log]] — append-only operation log · active

## Textbook (0)

## Papers (0)

## Concepts (0)

## Methods (0)

## Datasets (0)

## Metrics (0)

## Comparisons (0)

## Open questions (0)
""",
        "vocabulary.md": front("vocabulary", today) + """# Controlled vocabulary

This file reserves stable citekeys and canonical page names for the corpus.
Add a name here and to [[index]] in the same operation that creates or plans a page.
Prefer an existing page over a near-synonym.

## 1. Citekeys

The year is part of the identifier; metadata still has to be checked in the source.

| # | citekey | year | short name | first author |
|---:|---|---:|---|---|

## 2. Concepts

| canonical page | aliases absorbed |
|---|---|

## 3. Methods

| canonical page | aliases absorbed |
|---|---|

## 4. Datasets and metrics

| canonical page | aliases absorbed |
|---|---|

## 5. Reserved synthesis pages

| canonical page | scope |
|---|---|

## 6. Textbook chapters

| canonical page | scope |
|---|---|
""",
        "pins.md": front("pins", today) + """# Pins

Human corrections and durable constraints live here. They override regenerated prose.

- A citekey year is an identifier, not proof of a document date. Check the source.
- An arXiv title variant is not an exact-title match. Preserve the match method recorded
  in `arxiv_sources.csv`.
- Do not cite numbers extracted from TeX alone; verify them in the PDF.
""",
        "log.md": front("log", today) + f"""# Operation log

Append-only. Never rewrite an earlier entry.

## {today} — Scaffold

- Created the wiki skeleton for {name}.
""",
        "overview.md": front("overview", today) + f"""# Overview

{topic}

This page will synthesize the corpus once paper pages are active.
""",
    }


def write_new(path: Path, text: str, created: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    created.append(str(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project")
    parser.add_argument("--name", required=True, help="wiki name, e.g. 'Causal Discovery'")
    parser.add_argument("--topic", required=True, help="one sentence on what the corpus covers")
    parser.add_argument("--mark", default="", help="one character for the site logo (default: first letter)")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    today = datetime.date.today().isoformat()
    created: list[str] = []

    tools = root / ".tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in TOOLS:
        if not (tools / name).exists():
            shutil.copy2(HERE / name, tools / name)
            created.append(str(tools / name))
    if not (tools / "site_assets").exists():
        shutil.copytree(HERE / "site_assets", tools / "site_assets")
        created.append(str(tools / "site_assets"))
    write_new(tools / "site_figures.yaml", FIGURES_YAML, created)

    for d in DIRS:
        (root / "wiki" / d).mkdir(parents=True, exist_ok=True)
    for name, text in meta_pages(args.name, args.topic, today).items():
        write_new(root / "wiki" / name, text, created)

    contract = (SKILL / "templates" / "CLAUDE.md").read_text(encoding="utf-8")
    contract = contract.replace("{name}", args.name).replace("{topic}", args.topic)
    write_new(root / "AGENTS.md", contract, created)
    write_new(root / "CLAUDE.md", contract, created)
    mark = args.mark or args.name[:1].upper()
    write_new(root / "wiki.yaml", f'name: "{args.name}"\nmark: "{mark}"\n', created)
    write_new(root / "papers.csv", "index,title,year,venue,category,priority,direct_pdf_url\n", created)
    write_new(root / "references.bib", "", created)
    write_new(root / ".gitignore", "__pycache__/\n*.py[cod]\n.venv/\n*:Zone.Identifier\n.DS_Store\n", created)

    print(f"Scaffolded {root} ({len(created)} new files or directories).")
    for item in created:
        print("  +", Path(item).relative_to(root))


if __name__ == "__main__":
    main()
