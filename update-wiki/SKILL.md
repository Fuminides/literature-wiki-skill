---
name: update-wiki
description: >-
  Brings an existing literature wiki's tools up to date with the installed literature-wiki
  skill (Ask Claude chat panel, exams, lint and site fixes, README), keeping the wiki's own
  changes to its tools and contract.
argument-hint: "[wiki directory]"
disable-model-invocation: true
---

# /update-wiki

Update the wiki at: $ARGUMENTS

The main skill is the `literature-wiki` directory installed next to this one
(`${CLAUDE_SKILL_DIR}/../literature-wiki`), called `<skill>` below.

`init_wiki.py` never overwrites, so a wiki keeps the tools it was created with. This command
brings them up to date without losing what the wiki changed locally.

## 1. Find the wiki

The directory given, or the current one; a wiki has `.tools/` and `wiki/`. If none was given
and several wikis sit below the current directory, list them and ask. If the wiki is a git
repository with uncommitted changes, ask the user to commit or stash them first, so this
update is one reviewable diff.

## 2. Update the tools

```bash
diff -rq --exclude=__pycache__ --exclude='*:Zone.Identifier' <skill>/scripts <wiki>/.tools
```

`init_wiki.py` exists only in the skill, and `site_figures.yaml` and any wiki-specific
scripts only in the wiki; leave those alone. For every other file:

- **Missing in the wiki** (for example `serve_site.py`, `site_assets/chat.js`,
  `site_assets/exam.js`): copy it.
- **Different**: read `diff -u` and, when the wiki is in git, `git log -p` for that file, to
  tell which side changed.
  - Only the skill moved on: copy the skill's version.
  - The wiki has its own changes (a fix, wiki-specific behaviour): apply the skill's changes
    to the wiki's version and keep its own. When a local change is a general fix, tell the
    user it belongs in the skill too.
  - The wiki's file is a different tool under the same name, with its own history: do not
    replace it. Port only the features the user wants, such as exam rendering, and say what
    was ported.

## 3. Update the project files

- `.gitignore`: add `.exam-stats.json` if it is missing.
- `CLAUDE.md` and `AGENTS.md`: compare with `<skill>/templates/CLAUDE.md`. Add any rule
  paragraph the wiki lacks, such as the one on exam banks; never remove or reword the
  wiki's own rules. Keep the two files identical if they were.
- `README.md`: if there is none, create it from `<skill>/templates/README.md`, with
  `{name}` from `wiki.yaml` and `{topic}` from `CLAUDE.md`. If there is one without the
  chat and exam sections, offer to add them from the template.

## 4. Check

```bash
python3 .tools/lint_wiki.py
python3 .tools/build_site.py && python3 .tools/build_site.py --check-figures
python3 .tools/serve_site.py --help
```

A newer lint can find problems the old one missed. Fix them in the wiki, or report them;
never weaken the lint to pass.

## 5. Report

Append the update to `wiki/log.md`. Tell the user which files were added, replaced, merged
or kept, and what is now available: `/serve-wiki` for the chat panel, and `/wiki-exams` if
`wiki/exams/` has no banks yet.
