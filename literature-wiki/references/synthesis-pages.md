# Synthesis pages

Synthesis pages combine evidence across papers. Every paper claim on them still carries
a locator, and every paper they link must be in their `sources` frontmatter. What they
add is structure: which papers agree, where definitions differ, what is comparable.

## Frontmatter

```yaml
---
type: concept          # concept | method | dataset | metric | comparison | open-question | overview
status: active
created: 2026-01-15
updated: 2026-01-15
sources: [smith2020, jones2021]
---
```

## Fixed shapes

The lint enforces these `##` headings, exactly and in order:

| type | headings |
|---|---|
| concept | Definition in use; Competing definitions; Why it matters; How it is measured; Open disagreements; Appears in |
| method | Core idea; What it fixes; What it costs; Lineage; Empirical standing |
| dataset | What it is; Task and schema; Standard splits; Known issues; Papers using it |
| metric | Definition; What it actually captures; Known failure modes; Variants across papers |

Comparisons must include a `## Comparability conditions` section; open questions state
the question, why it is open, the current evidence, and what would resolve it (the
reference wiki uses `## The question`, `## Why it is open`, `## Current evidence`, `## What
would resolve it`). The overview (`wiki/overview.md`, `type: overview`) is free-form; its
first paragraph becomes the site's home-page introduction.

## Reverse links (the `--backlinks` check)

When a paper page links a synthesis page, that page must account for the paper:

- **dataset**: "Papers using it" lists exactly the papers whose pages link it, one line
  each, `- [[papers/x]] — what the paper does with it.` No more, no fewer.
- **concept**: "Appears in" lists at least every linking paper (it may list more).
- **method, metric**: cite the linking paper somewhere on the page, with a locator.

So when writing a paper page, create or update the pages it links in the same operation.

## What makes synthesis useful

- **Keep definitions apart.** When two papers use one word for two things, say so under
  "Competing definitions" rather than merging them.
- **State comparability before comparing.** Same data version, same splits, same
  preprocessing, same metric, same tuning budget, same stopping rule. If they differ,
  the numbers do not share a table; say which condition fails.
- **Separate the authors' claims from ours.** "The authors report" for their claims;
  "(our synthesis)" or "our reading" for connections the wiki draws.
- **Name the evidence gap.** An open question is only useful if it says what experiment
  or result would settle it.
- **Prefer extending a page to creating a near-duplicate.** Check the vocabulary aliases.

## Order of work

Create concept, method, dataset and metric pages as paper pages first need them. After
all papers are in, write the overview, then comparisons and open questions, then revisit
the concept and method pages with the whole corpus in view: early pages were written
from a few papers and usually need their "Competing definitions" and "Empirical standing"
rewritten.
