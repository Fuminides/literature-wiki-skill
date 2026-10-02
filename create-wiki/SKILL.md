---
name: create-wiki
description: >-
  Creates a literature wiki from whatever the user has: a topic, paper titles, a CSV,
  BibTeX or reading-list file, a folder of PDFs, or arXiv IDs and DOIs. Infers the name,
  topic and project directory, builds the corpus, then runs every phase of the
  literature-wiki skill.
argument-hint: "[topic, papers or a file/folder of them, target directory]"
disable-model-invocation: true
---

# /create-wiki

Create a literature wiki from: $ARGUMENTS

The main skill is the `literature-wiki` directory installed next to this one
(`${CLAUDE_SKILL_DIR}/../literature-wiki`), called `<skill>` below. Read `<skill>/SKILL.md`
now: its phases, checks and rules govern everything this command does. This command
replaces its "Before starting" and the first two phases' manual steps with whatever the
user gave.

## 1. Read the input

It may hold any mix of:

- a topic, or a description of the field;
- papers: titles inline, a file (`.txt`, `.md`, `.csv`, `.bib`, `.ris`, a reading list), a
  folder of PDFs, arXiv IDs or URLs, DOIs;
- a wiki name, a project directory, categories, priorities.

Read every file and folder it names. With no input at all, ask what the wiki is about and
which papers it covers.

## 2. Infer what is missing

- **Name**: a short title for the field. **Topic**: one sentence on what the corpus
  covers. **Directory**: the name as a lowercase hyphenated slug under the current
  directory, unless the input names one.
- **Per paper**: title and year (the scripts need both), venue, and a legal open-access
  `direct_pdf_url` when one is known (an arXiv ID gives `https://arxiv.org/pdf/<id>`).
  Take them from the input: BibTeX fields, arXiv IDs, a PDF's first page
  (`pdftotext -l 1`). Leave a cell empty rather than guess; ask for a missing year.
- **Categories**: the input's own headings or groups. Otherwise propose three to eight
  groups from the titles.
- **Only a topic, no papers**: propose a corpus, typically 20 to 60 papers covering the
  foundational work, the main method families, benchmarks and surveys, with a one-line
  reason per paper. Check that each one exists (search the web when available). The user
  curates the corpus, so download nothing until they approve the list.

## 3. Confirm once

In one message, show the name, topic, directory, categories and the paper table (its size
and a sample when long). Ask only what you could not infer, and do not re-ask what the user
stated.

## 4. Scaffold and fill the corpus

```bash
python3 <skill>/scripts/init_wiki.py <directory> --name "…" --topic "…"
```

It never overwrites, so an existing repository is fine. If it kept an existing `CLAUDE.md`
or `AGENTS.md`, append the contract from `<skill>/templates/CLAUDE.md` (name and topic
filled in) to it rather than replacing it, and tell the user.

Write `papers.csv` (`index,title,year,venue,category,priority,direct_pdf_url`) with
indexes 1 to N, grouped by category. For a
folder of PDFs, copy each file (never move the user's originals) into `pdfs/` under the name
`download_papers.py` would give it, `f"{index:02d}_{year}_{slug(title)}.pdf"` with `slug`
from `.tools/download_papers.py`, so the downloader keeps it instead of fetching another
copy.

## 5. Build

Run phases 2 to 8 of `<skill>/SKILL.md` in order, with each phase's check and the pilots it
asks for. A full build is long, since phase 4 writes one page per paper: after each phase,
say what is done and what comes next. If the user asked for only part of the build, such as
"just set up the corpus", stop there.

At hand-over, point the user to the project's `README.md` and to `/serve-wiki` for the site
with the Ask Claude panel and exams.
