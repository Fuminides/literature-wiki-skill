# Writing a paper page

A paper page describes one paper, in its own terms, with a locator on every claim. It
is the unit everything else cites, so it must be right before it is complete.

## Reading the paper

1. `python3 .tools/src.py NN meta` for the title page, then read the section outline:
   `grep -n '\\section\|\\subsection' sources/arxiv/NN_*/paper.expanded.tex`, or the PDF
   text when there is no TeX source.
2. Read the method sections in full, from the TeX if there is one (equations are exact
   there) and the PDF for anything you will cite by number: `src.py NN pdf 4 6`.
3. The PDF is the authority. arXiv and published versions differ in section, equation
   and figure numbering; cite what the local PDF says. When they differ, trust the PDF
   and leave the TeX aside.
4. Find the numbers you will report in the PDF tables, not in the TeX.

## Frontmatter

```yaml
---
type: paper
status: active
created: 2026-01-15
updated: 2026-01-15
citekey: smith2020
title: "Exact Title as Printed"
authors: [First Author, Second Author]
year: 2020
venue: NeurIPS
local_pdf: pdfs/07_2020_Exact_Title_as_Printed.pdf
source_text: sources/arxiv/07_Exact_Title_as_Printed/paper.expanded.tex
sources: [smith2020]
---
```

`source_text` is the expanded TeX when there is one, else `sources/pdf_text/NN_*.txt`.
`sources` holds the page's own citekey and nothing else.

## The nine sections

After `# Title`, exactly these `##` headings, in this order:

- **Problem**: what the paper tries to solve and why the authors think existing work
  falls short, in their terms.
- **Method**: see below. The longest section.
- **Assumptions**: what must hold for the method to apply (input format, supervision,
  given knowledge, language restrictions). Stated and unstated; say which.
- **Datasets**: link each dataset page, `[[datasets/x]]`, with a locator.
- **Metrics**: link each metric page, with a locator.
- **Results**: the headline results, numbers verified and marked, with the comparison
  conditions that matter (what baselines, what protocol). Include what did not work.
- **Limitations**: the authors' own, then any that follow from the method's design
  (say which is which).
- **Relations**: how the paper relates to other corpus papers. The only section
  where other paper pages may be linked; the claim itself cites this paper. Ends with
  the generated `Linked from:` line; never write that line by hand.
- **Concepts introduced**: links to concept and method pages, one line each.

## The Method section

Open with one summary paragraph: what the method is, in two or three sentences, with a
locator. Then walk through it in `###` subsections, in the order a reader needs them:

1. **Setting and notation**: inputs, outputs, the objects the method manipulates.
2. **One subsection per component**, each with its key equation(s) in TeX and a sentence
   on what every symbol means and why the component is there.
3. **Training**: the loss, the optimization, the schedule, the hyperparameters that
   matter (numbers in prose, verified and marked).
4. **Reading out the result**: how the trained model becomes the output the paper
   reports (rules, a tree, a program, a ranking).
5. **Worked example (ours)**: a small concrete case computed by hand, in a blockquote
   starting `> **Toy example (ours, not from the paper).**`. It carries no paper link.
   Compute its arithmetic with a script before writing it down; check that it uses the
   paper's conventions (index order, which argument is the head, sign conventions).
   If the paper has its own running example, restating it is better: say so in the
   heading, e.g. `### Worked example (the paper's XOR, restated)`.

Subsection headings are short noun phrases ("Rank-$L$ confidences", "The pricing
problem"). They become link targets (`#rank-l-confidences`) from the textbook, so avoid
renaming them later, and never give two headings on one page the same slug.

Aim for a reader who knows the field but not this paper being able to reimplement the
core idea from the page. Explain *why* each step exists, not only what it computes.

## Locators and the lint

- Forms: `§3`, `§3.2–§3.4`, `Table 2`, `Figure 3`, `Equation 7`, `Equations 5–11`,
  `Algorithm 1`, `PDF p. 8`, `PDF pp. 4–6`. Every paragraph that links the paper needs one.
- `--anchors` checks section numbers against the PDF text: a number must start a line,
  followed by whitespace. It fails on right-column headings of two-column PDFs and on
  headings numbered `3.1.`, and it reads `§3.3.1` as `§3.3`. Use the parent section, or
  `PDF p. N` plus the verbatim marker, instead.
- Figures captioned `Fig. 3` fail a `Figure 3` check; use the page locator.
- Equations are found as `Equation N` or `(N)` in the PDF text.
- Every digit outside math, code and locators counts as a number: add the marker
  `<!-- lint: verbatim-number -->` on its own line after the paragraph, or reword
  ("exactly zero", "at most two"), or move a symbolic constant into math (`$0/1$`).
- Keep measured values in prose, not math: the number check skips math.
- `--verify-numbers` warns when a marked number is not found in the paper's text. Table
  cells are often dropped from the text layer; check the PDF and move on.

## Pitfalls seen in practice

- Directional mistakes in relational notation (`child(W, X)` vs `child(X, W)`): recheck
  against the paper's definitions.
- Temperatures, probabilities and gate values in toy examples that do not match the
  paper's formula: compute them.
- Citing a section that exists in the arXiv version but not the local PDF.
- Linking another paper outside Relations: the lint rejects it; mention it in plain text.
- Stating a limitation as the authors' when it is our inference.
