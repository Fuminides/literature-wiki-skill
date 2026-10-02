---
name: add-papers
description: >-
  Adds papers to an existing literature wiki from any list (titles, a CSV, BibTeX or
  reading-list file, a folder of PDFs, arXiv IDs or DOIs) and carries them through
  download, paper pages, synthesis, textbook, exams and the site.
argument-hint: "[papers: titles, a file, a folder of PDFs, arXiv IDs] [wiki directory]"
disable-model-invocation: true
---

# /add-papers

Add to the wiki: $ARGUMENTS

The main skill is the `literature-wiki` directory installed next to this one
(`${CLAUDE_SKILL_DIR}/../literature-wiki`), called `<skill>` below. Read `<skill>/SKILL.md`
now: its phases, checks and rules govern everything this command does.

## 1. Find the wiki and read the papers

The wiki is the directory given, or the current one; it has `.tools/` and `wiki/`. Read its
`CLAUDE.md`, `papers.csv`, `wiki/index.md` and `wiki/vocabulary.md`.

Read the papers from the input, in any of the forms `/create-wiki` accepts, and fill in
title, year, venue and a legal open-access `direct_pdf_url` the same way. Drop any paper
already in `papers.csv` (compare normalised titles and arXiv IDs) and say which. Give each
new paper the next free index; never reuse or renumber an index, since file names and
anchors depend on them. Use the existing categories where they fit, and add a category only
if the user agrees.

## 2. Confirm, then add

Show the new rows once and wait for approval. Then append them to `papers.csv`. For a folder
of PDFs, copy each file into `pdfs/` as `f"{index:02d}_{year}_{slug(title)}.pdf"`, with
`slug` from `.tools/download_papers.py`.

## 3. Sources (phase 2)

Re-run the corpus scripts as they are. Each one skips work already done, so only the new
papers are processed:

```bash
python3 .tools/find_arxiv_ids.py          # review every new title-variant row by hand
python3 .tools/download_papers.py
python3 .tools/prepare_pdf_text.py
python3 .tools/prepare_arxiv_sources.py
python3 .tools/fetch_figures.py
```

Report which new papers have no PDF; they stay `planned`.

## 4. Pages (phases 3 and 4)

Register each citekey in `wiki/vocabulary.md`, list the paper in `wiki/index.md`, and write
its paper page following `<skill>/references/paper-pages.md`, with its BibTeX, index
activation, log entry and lint after each page, as phase 4 says.

## 5. Propagate (phases 5 to 8)

New papers change what the wiki can say:

- Extend the concept, method, dataset and metric pages they touch, and revisit the
  overview, comparisons and open questions with them in view.
- Where the textbook covers their topic, add them to the relevant chapter.
- If they establish something the exams do not test yet, add questions as `/wiki-exams`
  describes. If a bank is marked `exhausted`, tell the user the wiki has grown, so the mark
  may no longer hold.
- Choose figures in `.tools/site_figures.yaml`, then rebuild the site.

## 6. Check

```bash
python3 .tools/lint_wiki.py --claims --numbers --anchors --backlinks --verify-numbers
python3 .tools/build_site.py && python3 .tools/build_site.py --check-figures
```

Lint must report 0 errors. Tell the user which pages were added and which were revised.
