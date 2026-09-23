# Meta pages: index, vocabulary, pins, log

The scaffold creates all four. Their line formats are parsed by the lint and the site
builder, so keep them exact.

## `wiki/index.md`

Every page file must be linked here, and every entry line has this shape:

```
- [[papers/smith2020]] — Exact Paper Title · 1 source · active
- [[concepts/sparsity]] — what the corpus means by a small model · 23 sources · active
- `papers/jones2019` — Title of a paper without a local PDF · planned
```

- The em dash and the middle dots (`·`) are part of the format.
- `N sources` must equal the length of the page's `sources` list (the lint checks it).
- Planned entries have no page file, so they are written in backticks, not as links.
- Papers go under `## Papers (N)`, grouped by `### <category>` headings. The categories
  become the sidebar groups, card chips and filters on the site, in index order.
- Section counts in `## Concepts (N)` etc. are for readers; keep them current.
- The description after the dash is shown on the site's home page for synthesis pages:
  write it as a short phrase that says what the page answers.

## `wiki/vocabulary.md`

The controlled vocabulary. A page name is registered here before the page is created.

- **Citekeys** table: `| # | citekey | year | short name | first author |`. The `short
  name` (e.g. the method's acronym) is shown in the site's sidebar and paper chips.
  Citekeys are `surnameYEAR` in lowercase ASCII, with `a`, `b` for collisions.
- **Concepts / Methods / Datasets and metrics** tables:
  `| canonical page | aliases absorbed |`. Before creating a page, check whether an
  existing one already covers the name under an alias; prefer extending it.
- **Reserved synthesis pages** and **Textbook chapters**: lists of slugs.

## `wiki/pins.md`

Durable human corrections. When the user corrects a fact, a name or a convention, record
it here in one line; pins override regenerated prose. Also record corpus facts every
later operation needs (papers without a PDF, known version mismatches between arXiv and
the local PDF).

## `wiki/log.md`

Append-only. One `## YYYY-MM-DD — What was done` entry per material operation, with a few
bullets: what changed, what was checked, what was left open. Never edit an earlier entry,
even to fix it; append a correction instead. Avoid writing `[[...]]` examples in the log:
they are real links and the lint checks them.
