# {name}

This repository is a source-grounded literature wiki over the paper collection in
`papers.csv`. Topic: {topic}. The human curates the corpus; agents maintain `wiki/`,
`references.bib`, and the supporting tools in `.tools/`.

## Source boundary

- Treat `pdfs/` and `sources/arxiv/*/source/` as immutable evidence.
- Prefer `sources/arxiv/*/paper.expanded.tex` or `sources/pdf_text/*.txt` for inexpensive search.
- Verify all numeric claims, tables, figures, equations, author lists, dates, and venues
  against the PDF when a PDF exists.
- Never fill gaps with memory or a related paper. Mark missing evidence explicitly.
- `papers.csv` is the corpus inventory. A paper without a local PDF stays `planned`
  until a full source is available.

## Wiki contract

Read `wiki/index.md`, `wiki/vocabulary.md`, and `wiki/pins.md` before editing.

- Every page starts with YAML frontmatter containing `type`, `status`, `created`,
  `updated`, and `sources`.
- `status` is `active` or `planned`. Planned entries are reservations in the index;
  they normally do not have page files.
- Each citekey, page slug, and alias must be registered in `wiki/vocabulary.md`.
- Add or activate a page in `wiki/index.md` in the same operation that creates it.
- `sources` contains only corpus citekeys. Synthesis must not outrun those sources.
- A paper page's Relations section may link other paper pages as navigation. The claim
  itself still carries a locator into the page's own paper; the other paper is never a
  source. Elsewhere on a paper page, only its own citekey may be linked.
- Each paper page ends its Relations section with a generated `Linked from:` line
  listing the paper pages whose Relations link it. Regenerate it with
  `--write-paper-backlinks`; `--backlinks` fails when it is stale.
- Use Obsidian-style internal links: `[[papers/smith2020]]`.
- Use stable evidence locators: `[[papers/smith2020]] §3.3`, `Table 4`, `Figure 3`,
  `Equation 7`, or `PDF p. 8`. A paper link without a locator is not a claim citation.
- For a numeric result, verify the PDF and append `<!-- lint: verbatim-number -->`.
  `--verify-numbers` then looks each marked number up in the cited paper's text and warns
  when it cannot find one; the text layer drops some table cells, so a warning means
  "check the PDF", not "wrong".
- Separate an author's claims from our synthesis. Use wording such as "the authors
  report" unless the evidence directly establishes the stronger statement.
- Every page that a paper page links must account for that paper. Dataset and concept pages
  list it under "Papers using it" or "Appears in"; method and metric pages cite it somewhere
  on the page. A dataset's list is the exact inverse of its inbound links; the others may also
  cite a paper whose own page does not link back. `--backlinks` enforces this.
- Append material operations to `wiki/log.md`; never rewrite earlier log entries.

## Fixed page shapes

Paper pages use these headings, in order:

1. Problem
2. Method
3. Assumptions
4. Datasets
5. Metrics
6. Results
7. Limitations
8. Relations
9. Concepts introduced

The Method section opens with a short summary paragraph, then walks through the method
in `###` subsections (setting and notation, each component with its key equations,
training, how the output is read). Every subsection cites its paper section, equation,
or algorithm. Worked examples are welcome but must be labelled "(ours, not from the
paper)" and carry no paper link.

The anchor lint matches a section number only at the start of a PDF text line, followed
by whitespace. Headings in the right column of two-column PDFs, or numbered like `3.1.`,
therefore fail. Use `PDF p. N` (with the verbatim marker) for those. The lint also reads
`§3.3.1` as `§3.3`.

Textbook chapters may link a paper's Method subsection as `[[papers/key#slug|label]]`, where
the slug is the heading lowercased with runs of other characters turned into `-`. The lint
checks that the heading exists. Such links are navigation; they do not replace the locator
citation.

Math is TeX in `$...$` or `$$...$$`, rendered by the vendored KaTeX in
`.tools/site_assets/katex/`. Write a literal dollar sign as `\$`. The lint ignores digits
inside math, so keep measured values (results, hyperparameters) in prose, where the
verbatim-number check sees them.

Concept pages use: Definition in use; Competing definitions; Why it matters; How it
is measured; Open disagreements; Appears in.

Method pages use: Core idea; What it fixes; What it costs; Lineage; Empirical standing.

Dataset pages use: What it is; Task and schema; Standard splits; Known issues; Papers
using it.

Metric pages use: Definition; What it actually captures; Known failure modes; Variants
across papers.

Comparison pages must state "Comparability conditions". Open-question pages must state
the question, why it is open, current evidence, and what would resolve it.

Textbook chapters (`wiki/textbook/NN-slug.md`, frontmatter `type: chapter` and `order: N`)
explain the field rather than one paper. They follow the same evidence contract, end with
"Key points" and then "Where to read next", and label every illustration of our own as ours.

## Workflow

1. Select the next planned paper from `wiki/index.md`.
2. Inspect source metadata and the full section structure. Recover relevant PDF pages.
3. Add the paper's BibTeX entry to `references.bib`.
4. Write its paper page with the fixed headings and precise locators.
5. Update existing synthesis pages before creating new ones. New names go through the
   controlled vocabulary.
6. Update source lists and counts, then append the operation log.
7. Run `python3 .tools/lint_wiki.py --write-paper-backlinks`, then
   `python3 .tools/lint_wiki.py --claims --numbers --anchors --backlinks --verify-numbers`.

## Commands

```bash
python3 .tools/src.py 01 meta
python3 .tools/src.py 01 pdf 6 8
python3 .tools/src.py 01 grep 'accuracy|F1'
python3 .tools/lint_wiki.py --write-paper-backlinks
python3 .tools/lint_wiki.py --claims --numbers --anchors --backlinks --verify-numbers
python3 .tools/build_site.py                  # regenerate site/ after wiki edits
python3 .tools/build_site.py --check-figures  # figure numbers vs. local PDFs
node .tools/check_math.js                     # every TeX expression in site/ parses
```
