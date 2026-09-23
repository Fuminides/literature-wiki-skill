# The textbook

The paper pages describe one work at a time; the textbook does the opposite. It teaches
the field in order: the problem, the families of solutions, why each exists, how the
pieces work, how to evaluate them, what is open. It follows the same evidence contract as
every other page.

## Planning the chapters

Propose a chapter plan to the user before writing. A shape that worked for a 60-paper
corpus, eleven chapters:

- `00` A map of the field: the problem in one paragraph, the main families, reading paths.
- `01` The object being learned: what the models are, and how their variants differ.
- `02`–`07` One chapter per family or technique, ordered so each builds on earlier ones
  (put the shared toolbox before the chapters that use it).
- `08` The chapter the field most needs a careful reader for (in the reference wiki,
  where soft models become symbolic and whether extracted output is faithful).
- `09` Evaluation: what is measured, what each measure captures, when two numbers are
  comparable, with a checklist for reading a results table.
- `10` Open problems: each as a question, why it is open, what would settle it.

## File and frontmatter

`wiki/textbook/NN-slug.md`, registered in the vocabulary and listed in the index under
`## Textbook (N)`:

```yaml
---
type: chapter
status: active
created: 2026-01-15
updated: 2026-01-15
order: 5
sources: [smith2020, jones2021]
---
```

## Chapter shape

- An opening paragraph that says what the chapter covers and how it connects to the
  previous one.
- Topic sections (`##`), each explaining one idea: what problem it solves, how it works,
  what it costs. Cite papers with locators exactly as on synthesis pages.
- Worked examples and illustrations in blockquotes, labelled as ours:
  `> **Worked example (ours).** ...`. Compute every number in them with a script.
- Summary tables are welcome; say "The table is our summary of the sections above."
- `## Key points`: four or five bullets.
- `## Where to read next`, always last (the lint checks it): the next chapter, then the
  synthesis pages that hold the detailed evidence.

## Linking into paper walkthroughs

After a topic paragraph that cites papers, add one line pointing at the relevant Method
subsections of those papers' pages:

```
*In detail:* [[papers/smith2020#the-pricing-problem|pricing a new column]], [[papers/jones2021#training|its training loop]].
```

- The anchor is the subsection heading's slug: lowercase, every run of other characters
  replaced by `-` ("Rank-$L$ confidences" → `rank-l-confidences`). The lint fails on an
  anchor that does not exist.
- These links are navigation, not citations: keep the locator citation in the paragraph.
- Put the line after the paragraph and after its `<!-- lint: verbatim-number -->`
  marker, never directly under a heading. Avoid digits in the labels.
- One line per topic, two to six links; skip it where the paragraph is not about how a
  method works.

## Diagrams

Diagrams drawn for the textbook go in `wiki/textbook/figures/` (SVG preferred) and are
embedded with `![alt](figures/name.svg)`; the site builder copies the directory. Say in
the text that the diagram is ours.
