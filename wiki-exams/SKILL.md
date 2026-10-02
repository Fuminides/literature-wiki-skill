---
name: wiki-exams
description: >-
  Writes or extends the easy, medium and hard exam banks of an existing literature wiki,
  questions that test understanding of the field rather than memory of which paper did
  what, piloting a few per level with the user first.
argument-hint: "[easy|medium|hard|all] [number of questions] [wiki directory]"
disable-model-invocation: true
---

# /wiki-exams

Exams for: $ARGUMENTS

The main skill is the `literature-wiki` directory installed next to this one
(`${CLAUDE_SKILL_DIR}/../literature-wiki`), called `<skill>` below.

## 1. Find the wiki and check its tools

The wiki is the directory given, or the current one; it has `.tools/` and `wiki/`. If
`.tools/site_assets/exam.js` is missing, the wiki's tools predate exams: run `/update-wiki`
first, and tell the user why.

## 2. Read

Read `<skill>/references/exams.md`; it holds every rule for the questions, the bank format,
and the workflow. Then read the wiki's textbook, comparisons and open questions, and the
banks already in `wiki/exams/`.

## 3. Decide what to write

From the input: one level or all three, and a number of questions. By default, fill each
bank to at least twice its `per_attempt`.

- **No banks yet**: pilot first. Write about five questions per level, build the site, show
  the user, and adjust difficulty and style from their feedback before filling the banks.
- **Existing banks**: give new questions new ids, continuing the numbering. Never change an
  existing question unless the user asks: practice counts in `.exam-stats.json` are keyed by
  id.
- **A bank marked `exhausted`**: add nothing to it unless the user asks, for example
  because the wiki has grown. Then remove the mark.

## 4. Check

```bash
python3 .tools/lint_wiki.py
python3 .tools/build_site.py
```

Lint must report 0 errors for the banks. Take each exam once in the browser, or ask the
user to, reading every explanation as a reader who chose that option would. Append the
operation to `wiki/log.md`.

Tell the user that multiple choice works from `site/` on disk, while written answers are
graded only when the site is served (`/serve-wiki`).
