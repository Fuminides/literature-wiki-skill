# {name}

A source-grounded literature wiki. Topic: {topic}

Every claim about a paper links that paper's page and carries a locator into the paper
itself (§, Table, Figure, Equation or PDF page), and our own synthesis is kept visibly
separate from what the authors claim. `CLAUDE.md` (and the identical `AGENTS.md`) is the
editing contract; it governs everything under `wiki/`.

## Layout

| Path | What it is |
|---|---|
| `papers.csv` | The corpus: one row per paper, curated by hand. |
| `pdfs/`, `sources/` | The papers and the text extracted from them. Evidence: the wiki reads them, never edits them. |
| `wiki/` | The wiki: paper pages, concepts, methods, datasets, metrics, comparisons, open questions, a textbook in `wiki/textbook/` and exam question banks in `wiki/exams/`. |
| `site/` | The static site generated from `wiki/`. Never edit it by hand. |
| `.tools/` | Lint, site builder, the local server for chat and exams, and the download scripts. |
| `references.bib` | BibTeX for every paper, under the wiki's citekeys. |

## Reading the wiki

```bash
pip install pyyaml markdown-it-py mdit-py-plugins pillow
python3 .tools/build_site.py        # renders wiki/ into site/
```

Open `site/index.html` in a browser. The site works offline from disk, with full-text
search, figures from the papers and typeset maths. Rebuild it after every wiki edit.

## Asking Claude on the site

Served by `.tools/serve_site.py`, every page gets an **Ask Claude** button. It opens a chat
panel where Claude answers questions about the page, the wiki and the papers, citing them
with clickable links.

### One-time setup

1. Install [Claude Code](https://claude.com/claude-code) and check that `claude --version`
   works in a terminal.
2. Run `claude` once and log in. The chat uses that login, so questions count against that
   account's usage.
3. Optional check: `claude -p "say hi"` should print a reply without asking anything. If it
   does, the site's chat will work.

### Each time

```bash
python3 .tools/build_site.py     # only after editing the wiki
python3 .tools/serve_site.py     # prints the URL, e.g. http://127.0.0.1:8765
```

Open the printed URL, not `site/index.html` from disk: the button only exists on pages the
server delivers. Stop the server with Ctrl+C.

- **Ask about the page you are on.** The panel tells Claude which page you are reading.
- **Ask about a passage.** Highlight text in the article before asking; it is quoted above
  the input box and sent with the question. Click × on the quote to drop it.
- **Follow up.** The conversation continues across pages in the same browser tab. **New**
  starts a fresh one.
- Enter sends, Shift+Enter adds a line break, and Esc closes the panel.

Answers take a few seconds to a minute, because Claude opens the wiki pages and papers it
needs; the panel shows what it is reading meanwhile. Claude is read-only here: it cannot
change the wiki. It follows the evidence rules in `CLAUDE.md` and marks anything it adds
that does not come from the wiki.

Options: `--port 8800` picks another port (the server also moves to the next free port by
itself), and `--model sonnet`, or any model name, overrides your Claude Code default. The
server listens on 127.0.0.1 only, so nobody else on the network can reach it.

### When it does not work

| Symptom | Cause and fix |
|---|---|
| No Ask Claude button | The page was opened from disk. Use the URL `serve_site.py` printed. |
| `site/index.html not found` when starting the server | Run `python3 .tools/build_site.py` first. |
| `ModuleNotFoundError` when starting the server | Run the `pip install` line under Reading the wiki. |
| An error in the panel mentioning `claude` | The terminal running the server cannot find or run Claude Code. Check `claude --version` there, and log in again with `claude`. |
| A page does not show a recent wiki edit | Rebuild with `build_site.py`. Pages show the last build; Claude reads the current wiki files. |

### Exams

Once the wiki has question banks, the **Exams** link in the sidebar tests the field at
three levels: easy, medium and hard. The questions test understanding, not memory of which
paper did what. Multiple choice is graded in the browser, and every option explains why it
is right or wrong. In the hard exam, Claude grades the written answers, which needs the
same setup as the chat.

Practice counts go to `.exam-stats.json`, which is git-ignored and per machine. Once every
question of a level has been answered three times (`--new-questions-after`), Claude writes
new questions into that bank in the background. Those edits change `wiki/exams/*.yaml` and
`wiki/log.md`, so review and commit them like any other wiki edit.

## Working on the wiki

Open Claude Code (or Codex) in this directory; `CLAUDE.md` is the contract it works under.
To download the papers and extract their text and figures, Poppler (`pdftotext`, `pdfinfo`,
`pdftoppm`) is also needed: `sudo apt install poppler-utils`, or `brew install poppler`.

```bash
python3 .tools/lint_wiki.py                        # the gate: must report 0 errors
python3 .tools/build_site.py                       # render wiki/ into site/
python3 .tools/build_site.py --check-figures       # confirm each figure against its PDF
```

`wiki/index.md` lists every page and its status, and `wiki/log.md` records every material
operation.
