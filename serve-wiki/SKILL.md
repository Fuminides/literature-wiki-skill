---
name: serve-wiki
description: >-
  Serves a literature wiki's site locally with the Ask Claude chat panel and graded exams,
  rebuilding the site first when the wiki changed, and gives the user the URL.
argument-hint: "[wiki directory or name] [--port N] [--model NAME]"
disable-model-invocation: true
---

# /serve-wiki

Serve: $ARGUMENTS

## 1. Find the wiki

A wiki is a directory with `.tools/` and `wiki/`. Take, in order: the directory given; a
name matched against the directories below the current one that hold
`.tools/serve_site.py` (a unique prefix is enough); the current directory. If the match is
ambiguous, list the candidates and ask. If the wiki has no `.tools/serve_site.py`, its tools
predate the chat: offer `/update-wiki`.

## 2. Check

- `claude --version` must work: the chat panel and the exam grading run Claude Code. If it
  fails, point the user to the one-time setup in the wiki's `README.md`.
- Rebuild with `python3 .tools/build_site.py` when `site/index.html` is missing or the wiki
  changed since the last build:
  `find wiki \( -name '*.md' -o -name '*.yaml' \) -newer site/index.html -print -quit`
  prints a file.

## 3. Start

From the wiki directory, start `python3 .tools/serve_site.py` as a background process,
passing on `--port` and `--model` from the input. Wait for its line
`Serving <wiki> at http://127.0.0.1:<port>` and give the user that URL. If the port is
taken, the server moves to the next free one by itself.

Tell the user:

- Open the URL, not `site/index.html` from disk; only served pages have the Ask Claude
  button and graded written answers.
- The server stops when this session ends. To keep it running on its own, run
  `python3 .tools/serve_site.py` in a terminal in the wiki directory.
- Questions in the panel count against their Claude usage.
