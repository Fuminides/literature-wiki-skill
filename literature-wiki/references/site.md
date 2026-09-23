# The static site

`python3 .tools/build_site.py` renders `wiki/` into `site/`: one HTML page per wiki page,
a home page with paper cards and the textbook, a sidebar, offline full-text search, dark
mode, figures from the papers, and KaTeX math. Everything is relative, so `site/index.html`
opens straight from disk with no server or network. Rebuild after every wiki edit;
`site/` is generated, never edit it by hand.

## Configuration

- `wiki.yaml`: `name` (top bar, page titles, home heading) and `mark` (one character
  for the logo).
- `wiki/index.md`: paper categories become sidebar groups and home-page filters; entry
  descriptions appear in the home-page listings.
- `wiki/vocabulary.md`: citekey short names label papers in the sidebar and on cards.
- `wiki/overview.md`: its first paragraph is the home-page introduction.

## Rendering rules

- `[[target]]`, `[[target|label]]`, `[[target#anchor|label]]` become links; a paper link
  without a label shows "Surname et al. YEAR".
- `##` and `###` headings get ids (the slug rule above); `##` headings form the
  "On this page" list.
- `$...$` and `$$...$$` are TeX, rendered by the vendored KaTeX in
  `.tools/site_assets/katex/`, loaded only on pages with math. A literal dollar sign is
  `\$`.
- `<!-- lint: ... -->` comments are stripped.

## Figures

1. `python3 .tools/fetch_figures.py` extracts each arXiv paper's figures to
   `sources/arxiv/*/figures/` (PNG plus `figures.json` with captions). TikZ figures have
   no image file.
2. Pick figures in `.tools/site_figures.yaml` (the header comment documents every field).
   One to three per paper is plenty: the architecture or overview figure, placed in the
   Method section or the `###` subsection it illustrates (`section: The controller`).
3. When the arXiv figure numbering differs from the local PDF, set `fig` to the PDF's
   number and `tex` to the arXiv position. When there is no arXiv source or no image
   file, cut the figure from the PDF with `crop: {page, box}` and give a `caption`.
4. `python3 .tools/build_site.py --check-figures` confirms each `fig` number against the
   PDF caption; fix anything it reports.

## Checks before handing the site over

- `build_site.py` finishes and `--check-figures` reports 0 problems.
- Open a paper page, a chapter and the home page, or ask the user to; check math,
  figures and search.
- `node .tools/check_math.js` (needs Node.js) renders every TeX expression in `site/`
  with KaTeX and reports any that fail to parse; the browser would show them as red text.
