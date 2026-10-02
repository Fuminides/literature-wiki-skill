# Exams

Three question banks let a reader test what they understood: `wiki/exams/easy.yaml`,
`medium.yaml` and `hard.yaml`. `build_site.py` renders one page per bank under
`site/exams/`. Each attempt draws `per_attempt` questions at random and shuffles the
options. Multiple choice is graded in the browser. With the site served by
`.tools/serve_site.py`, Claude grades written answers and explains any mistake in the
chat panel.

## What the questions test

Knowledge of the field, not of the corpus. A reader who understood the textbook, but never
memorised which paper did what, should be able to answer every question.

- Ask about ideas: what a mechanism does, why it works, what it costs, when it fails, how
  two approaches differ, what would happen if a design choice changed.
- Never ask who proposed something, in which paper, year or venue, on which dataset, or
  what number a paper reported. Questions and options must not link papers (a lint error)
  and should not name authors (a warning). Explanations may cite papers as evidence.
- Prefer situations the reader has not seen: a new setting where the idea has to be
  applied. A question that can be answered by matching a phrase from the wiki tests
  reading, not understanding.
- The evidence contract still holds. Every correct answer must be established by the wiki:
  list the pages that establish it under `sources`. Do not present a claim the wiki marks
  as contested or open as settled, unless the question is about that disagreement.

## Levels

| Level | Tests | Typical question |
|---|---|---|
| easy | Core ideas: what the main concepts mean, what each family of methods is for, which problem each addresses | "What does X produce?" · "Which situation calls for X?" · "Which of these is an instance of X?" |
| medium | Mechanisms and trade-offs: why a method works, what it costs, how approaches compare, the effect of a design choice | "Why does X become expensive as Y grows?" · "What does X give up, compared with Z, to gain W?" · "What changes if…?" |
| hard | Reasoning in new situations: choosing and justifying an approach, diagnosing a failure, judging a claim or an experiment, connecting topics | "A team sees symptom S when doing T. What is the likeliest cause?" · "Which evidence would settle…?" · written explanations |

Written questions belong in the hard bank only.

## Multiple-choice questions

- Three to five options (four is the norm), exactly one correct. No "all of the above" or
  "none of the above".
- Every distractor is a real misconception, or a near miss that someone who half
  understood would pick. Never use a joke option. Its `why` names the misconception and
  corrects it in one to three sentences.
- The correct option's `why` gives the reasoning, not just "this is right", and links the
  page to read.
- Avoid cues. The correct option must not be the longest, the most hedged, or the only one
  that repeats the question's wording. Keep options parallel in length and form. Correct
  answers tend to come out longer, because they carry the qualification; trim them and make
  distractors specific. The lint warns when the correct option is the longest in more than a
  third of a bank's questions.

## Written questions (hard only)

- Ask for an explanation, a justified choice, a diagnosis or a short design, answerable in
  three to six sentences.
- `answer` is a model answer: what a strong reader would write.
- `rubric` lists two to four points a full answer makes. The grader marks the answer
  correct (every point, or an equivalent), partial (some points) or incorrect (none, or a
  substantive error), and credits valid reasoning that takes another route.

## Format

```yaml
level: medium
per_attempt: 8
questions:
  - id: m01                       # unique within the bank; e/m/h prefix by level
    kind: choice
    sources: [concepts/foo, methods/bar]   # wiki pages that establish the answer
    question: |
      A generator must produce the weights of a layer with $n$ inputs and $n$ outputs. …
    options:
      - text: "…"
        correct: true
        why: "… [[methods/bar]] explains the mechanism ([[papers/smith2020]] §3.2)."
      - text: "…"
        why: "This confuses … with …; see [[concepts/foo]]."
  - id: h07
    kind: written
    sources: [comparisons/x-vs-y]
    question: "…"
    answer: |
      …
    rubric:
      - "…"
      - "…"
```

Text fields are Markdown with `[[links]]` and `$TeX$`, rendered like the site's pages. A
paper link in `why`, `answer` or `rubric` needs a locator, as anywhere in the wiki.

## Size and balance

- `per_attempt` is 8 for easy and medium and 6 for hard. Make each bank at least twice
  `per_attempt` so retakes differ. In the hard bank, about a third of the questions are
  written; every attempt keeps that share.
- Spread the questions across the textbook's chapters and the main topics in the index.
  No two questions should test the same point.

## Practice counts and new questions

With the site served by `.tools/serve_site.py`, every submitted attempt is counted in
`.exam-stats.json` at the project root, which is git-ignored: how often each question was
answered, and how often answered right. Written answers count as right when Claude grades them
correct. Attempts draw the least-answered questions first, random among equals, so practice
spreads evenly and new questions come up at once. The exam page shows these counts.

Once every question of a level has been answered `--new-questions-after` times (default 3; 0
turns this off), the server runs Claude in the background to add up to `per_attempt` new
questions to that bank. Claude follows the rules above, which the server's prompt restates. It
may edit only that bank and `wiki/log.md`. The server keeps the result only if the bank still
parses, no existing question changed, and the lint reports no error for it. Otherwise it
restores both files. It then re-renders the exam pages (`build_site.py --exams`), and the page
offers a reload.

When the wiki supports no further significant question at a level, Claude adds none and marks
the bank instead:

```yaml
exhausted: "Every mechanism and trade-off in the textbook at this level is already tested."
```

The exam page then shows the reason, the index marks the level complete, and no more
questions are generated for it. Delete the line, for example after the wiki has grown, to
allow new questions again.

## Workflow

1. Write the exams after the textbook, since they draw on the whole wiki. Read the textbook
   and the comparison and open-question pages first. They hold the field's mechanisms and
   trade-offs.
2. Pilot: write about five questions per level, build the site, and show the user. Adjust
   difficulty and style from their feedback before filling the banks.
3. `python3 .tools/lint_wiki.py` checks the banks: structure, one correct option, sources,
   links, no paper links in questions, locators on paper claims, and option-length cues.
4. `python3 .tools/build_site.py`, then take each exam once in the browser. Read every
   explanation as a reader who chose that option would.
5. Append the operation to `wiki/log.md`.
