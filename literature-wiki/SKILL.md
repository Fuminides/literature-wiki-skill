---
name: literature-wiki
description: >-
  Builds and maintains a source-grounded literature wiki over a curated corpus of
  research papers: downloads open-access PDFs and arXiv sources, writes one page per
  paper with a detailed Method walkthrough and precise locators (§, Table, Figure,
  Equation, PDF page), synthesizes concept, method, dataset, metric, comparison and
  open-question pages, writes a didactic textbook, and renders everything as an offline
  static site with search, figures and KaTeX math. A lint enforces the evidence
  contract. Use when the user wants to create a wiki, knowledge base, survey site or
  textbook from a list of papers, or to extend or check such a wiki. Do not use for a
  single paper summary, a one-off literature review in chat, or a bibliography.
---

# Literature wiki

A wiki where every claim about a paper links the paper's page and carries a locator
into the paper itself, and where our own synthesis is kept visibly separate from what
the authors claim. The reference implementation is a 60-paper wiki on differentiable
rule learning; the tools in `scripts/` are its tools, generalized.

## Before starting

Ask the user only for what cannot be inferred:

1. **The corpus.** A list of papers (titles, or a file), ideally with a category per
   paper; categories become the paper groups in the index and the site filters.
2. **The wiki's name and a one-sentence topic.**
3. **The project directory.** A new directory, or an existing repository.

Then check dependencies: `python3 -c "import yaml, markdown_it, mdit_py_plugins, PIL"`
(install with `pip install pyyaml markdown-it-py mdit-py-plugins pillow`) and
`pdftotext`/`pdfinfo`/`pdftoppm` (package `poppler-utils`). `detex` and `gs`
(Ghostscript) are optional: without them there is no `paper.txt` and no EPS figures.

## Phases

Work through the phases in order. Each ends with a check that must pass. For phases
that write many pages (3, 4, 5, 6), pilot on one or two representative pages and use
available feedback to calibrate depth and style before scaling up. Ask for a review
when the user's preferences cannot be inferred.

### 1. Scaffold

```bash
python3 <skill-directory>/scripts/init_wiki.py <project> --name "…" --topic "…"
```

It creates `.tools/` (all scripts plus the site assets and vendored KaTeX), `wiki/` with
index, vocabulary, pins, log and overview, `AGENTS.md` and `CLAUDE.md` (the editing
contract; read it now, it governs every later phase), `wiki.yaml`, `papers.csv`,
`references.bib`. It never overwrites. `<skill-directory>` is the installed
`literature-wiki` directory, such as `~/.codex/skills/literature-wiki` or
`~/.claude/skills/literature-wiki`. Check: `python3 .tools/lint_wiki.py` reports 0 errors.

### 2. Corpus

Fill `papers.csv` (`index,title,year,venue,category,priority,direct_pdf_url`). Indexes are
stable integers; files are named `NN_year_title`. A `direct_pdf_url` must be a legal
open-access copy (arXiv, proceedings, author page); leave it empty rather than guess. Then:

```bash
python3 .tools/find_arxiv_ids.py          # -> arxiv_sources.csv; review every title-variant row by hand
python3 .tools/download_papers.py         # -> pdfs/, download_report.csv
python3 .tools/prepare_pdf_text.py        # -> sources/pdf_text/ (page-marked text)
python3 .tools/prepare_arxiv_sources.py   # -> sources/arxiv/*/paper.expanded.tex
python3 .tools/fetch_figures.py           # -> sources/arxiv/*/figures/ (for the site)
```

Report to the user which papers have no PDF; they stay `planned` until the user supplies
one. Check: `python3 .tools/src.py 01 meta` prints the first paper.

### 3. Vocabulary and index

Register every citekey (`surnameYEAR`, with `a`/`b` suffixes for collisions) in
`wiki/vocabulary.md` and list every paper in `wiki/index.md` as `planned`, grouped under
`### <category>` headings. Reserve concept, method, dataset and metric names only as they
become needed. Formats: [references/meta-pages.md](references/meta-pages.md).

### 4. Paper pages

One page per paper, with the nine fixed headings and a detailed Method walkthrough.
This is most of the work and most of the value. Read
[references/paper-pages.md](references/paper-pages.md) before writing the first one.
After each page: add its BibTeX to `references.bib`, activate it in the index, append to
the log, and run

```bash
python3 .tools/lint_wiki.py --write-paper-backlinks
python3 .tools/lint_wiki.py --claims --numbers --anchors --backlinks --verify-numbers
```

A paper page links concept, method, dataset and metric pages, so create those pages (or
extend them) in the same operation: see
[references/synthesis-pages.md](references/synthesis-pages.md).

### 5. Synthesis

Once the paper pages are in, write the overview, comparisons and open questions, and
revisit concept and method pages with the whole corpus in view.
[references/synthesis-pages.md](references/synthesis-pages.md).

### 6. Textbook

Ten or so chapters that teach the field in order, from a map of the field to open
problems, citing papers with locators and linking into their Method subsections.
[references/textbook.md](references/textbook.md).

### 7. Site

```bash
python3 .tools/build_site.py && python3 .tools/build_site.py --check-figures
```

Choose figures in `.tools/site_figures.yaml`; rebuild after every wiki edit.
[references/site.md](references/site.md).

## Rules that hold in every phase

- **Evidence only from the corpus.** Never fill a gap from memory or from a related
  paper. If the paper does not say it, the wiki does not claim it, or says it is missing.
- **Every paper claim has a locator**, every number is checked in the PDF and marked
  `<!-- lint: verbatim-number -->`, and "the authors report" separates their claims
  from established fact.
- **Our own material is labelled as ours**: worked examples, illustrations, framings,
  checklists. Recompute any toy arithmetic with a script before publishing it.
- **The lint is the gate.** Do not report a phase done with lint errors. Warnings from
  `--verify-numbers` mean "look at the PDF", not "wrong"; check each one once and say so.
- **Append to `wiki/log.md`** for every material operation; never rewrite it.
