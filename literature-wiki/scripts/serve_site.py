#!/usr/bin/env python3
"""Serve site/ locally with an "Ask Claude" chat panel on every page.

    python3 .tools/serve_site.py               # then open the printed URL (port 8765 or the next free one)
    python3 .tools/serve_site.py --port 8800 --model sonnet

Each question runs Claude Code (`claude -p`) in the project directory with read-only tools
(Read, Grep, Glob), so it follows CLAUDE.md and can open the wiki pages, PDFs and sources.
The panel tells Claude which page the reader is on and any passage they highlighted;
follow-up questions resume the same Claude session. Needs the `claude` CLI, logged in.

On exam pages (wiki/exams/*.yaml) it grades written answers and counts, in .exam-stats.json,
how often each question was answered and answered right. Once every question of a level has
been answered --new-questions-after times (default 3; 0 turns this off), Claude writes new
questions for it in the background, allowed to edit only that bank and wiki/log.md; the result
is linted and kept only if no existing question changed. When the wiki supports no further
significant questions, Claude marks the bank `exhausted` instead, and the exam page says so.
The server listens on 127.0.0.1 only; site/ itself stays a plain offline site.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import threading
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

import build_site as site

ROOT, SITE = site.ROOT, site.SITE
TOOLS = Path(__file__).resolve().parent
ASSETS = TOOLS / "site_assets"
INJECT = b'<link rel="stylesheet" href="/__chat/chat.css">\n<script src="/__chat/chat.js"></script>\n'
SESSION_RE = re.compile(r"\A[0-9a-f-]{36}\Z")
# Model output is untrusted, so raw HTML stays escaped.
md = MarkdownIt("commonmark", {"html": False}).enable("table").use(dollarmath_plugin, allow_digits=False)

SYSTEM = """You are answering a reader's question in a chat panel on this literature wiki's website.
You are read-only: answer questions, never propose edits to the wiki.
Ground claims in the wiki pages under wiki/ and in the papers' own sources, following the
evidence rules in CLAUDE.md. When neither answers the question, say so plainly, and mark any
general knowledge you add as not coming from the wiki.
Cite with wiki links and locators, e.g. [[papers/smith2020]] §3.2 or [[concepts/foo]]; the
reader sees them as clickable links. Do not cite file paths or line numbers.
Be concise: a few short paragraphs or a short list. Markdown and $TeX$ math are rendered."""

GRADER = """You grade a reader's written answer to an exam question on this literature wiki.
Judge it against the full answer and the points it makes; both come from the wiki. Credit sound
reasoning in other words or by another valid route; do not credit an answer that only names the
right terms without the reasoning.
verdict: "correct" if the answer makes every point or an equivalent, "partial" if it makes some,
"incorrect" if it makes none or states something wrong about the topic.
feedback: two to five sentences to the reader ("you"): what is right, what is missing or wrong,
and why. Point to pages worth reviewing as wiki links, chosen from the pages listed."""
GRADE_SCHEMA = json.dumps({"type": "object", "required": ["verdict", "feedback"], "properties": {
    "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]}, "feedback": {"type": "string"}}})

# A compact form of the skill's references/exams.md, which is not copied into the wiki; keep
# the two in step.
GENERATOR = """Readers have now answered every question in the {level} exam, wiki/exams/{level}.yaml,
at least {times} times, so it needs new questions. Add up to {k} of them.

1. Read CLAUDE.md, then the whole bank, to learn its format and which points it already tests.
2. Read the wiki for significant points of the field that the bank does not test yet: the
   textbook chapters, the comparison and open-question pages, and the concept and method pages
   they link. The {level} level tests: {about}
3. Append the new questions to the bank in the existing format, with ids numbered on from the
   last one. Never change or remove an existing question.

Rules for every question:
- Test understanding of the field, not memory of the corpus. Never ask who proposed something,
  in which paper, year or venue, or what number a paper reported; questions and options never
  link papers or name authors. Prefer situations the reader has not seen.
- Each question tests a significant point that no other question in the bank tests. List under
  `sources` the wiki pages that establish its answer; the answer must follow from them.
- Multiple choice has four options, exactly one correct. Each wrong option is a real
  misconception or a near miss, and its `why` names and corrects it; the correct option's `why`
  gives the reasoning and links the page to read. Keep options parallel in length and form: the
  correct one must not stand out as the longest.
- {written}
- Text is Markdown with [[links]] and $TeX$. A paper link in `why`, `answer` or `rubric` needs a
  locator. Quote any YAML string that contains ": ".

If the wiki supports no further significant question at this level that the bank does not already
test, add none and do not write filler. Instead add a top-level line to the bank:
exhausted: "<one sentence on why>"

Then run `python3 .tools/lint_wiki.py` and fix every error or warning it reports for this bank.
Finally append an entry to wiki/log.md headed "## {today} — {level} exam extended", with one or two
bullets. You may edit only wiki/exams/{level}.yaml and wiki/log.md."""
WRITTEN_RULE = {
    "hard": "About a third of the new questions are written (kind: written), each with a model `answer` "
            "and a `rubric` of two to four points a full answer makes.",
}

# ---------------------------------------------------------------- exam counts and new questions

STATS = ROOT / ".exam-stats.json"
LEVELS = ("easy", "medium", "hard")
lock = threading.Lock()
jobs: dict[str, dict] = {}  # level -> {"state": "running" | "done" | "failed", "message": ...}


def load_bank(level: str) -> dict | None:
    path = site.WIKI / "exams" / f"{level}.yaml"
    if level not in LEVELS or not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_stats() -> dict:
    try:
        return json.loads(STATS.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def count(level: str, answered: list[str], correct: list[str]) -> None:
    with lock:
        stats = read_stats()
        counts = stats.setdefault(level, {})
        for field, ids in (("answered", answered), ("correct", correct)):
            for qid in ids:
                counts.setdefault(qid, {"answered": 0, "correct": 0})[field] += 1
        STATS.write_text(json.dumps(stats, indent=1, sort_keys=True), encoding="utf-8")


def exam_status(level: str, threshold: int) -> dict:
    bank = load_bank(level) or {}
    ids = [q["id"] for q in bank.get("questions", [])]
    counts = read_stats().get(level, {})
    counts = {i: counts.get(i, {"answered": 0, "correct": 0}) for i in ids}
    return {"threshold": threshold, "counts": counts, "exhausted": bank.get("exhausted"), "job": jobs.get(level),
            "least": min((c["answered"] for c in counts.values()), default=0)}


def maybe_generate(level: str, threshold: int, model: str | None) -> None:
    status = exam_status(level, threshold)
    with lock:
        # One job at a time; a failed level waits for a restart rather than retrying on every attempt.
        if (threshold <= 0 or status["exhausted"] or status["least"] < threshold
                or any(j["state"] == "running" for j in jobs.values())
                or jobs.get(level, {}).get("state") == "failed"):
            return
        jobs[level] = {"state": "running", "message": "Claude is writing new questions for this exam."}
    threading.Thread(target=generate, args=(level, threshold, model), daemon=True).start()


def generate(level: str, threshold: int, model: str | None) -> None:
    bank_path, log_path = site.WIKI / "exams" / f"{level}.yaml", site.WIKI / "log.md"
    saved = {p: p.read_text(encoding="utf-8") for p in (bank_path, log_path) if p.is_file()}
    before = load_bank(level)
    old = before["questions"]

    def fail(reason: str) -> None:
        for path, text in saved.items():
            path.write_text(text, encoding="utf-8")
        jobs[level] = {"state": "failed", "message": f"Writing new questions failed: {reason}"}

    prompt = GENERATOR.format(level=level, times=threshold, k=before.get("per_attempt", 8),
                              about=site.LEVELS[level][1], today=date.today().isoformat(),
                              written=WRITTEN_RULE.get(level, "Every question is multiple choice (kind: choice)."))
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "Read,Grep,Glob,Edit,Write,Bash",
           "--allowedTools", f"Edit(wiki/exams/{level}.yaml)", f"Write(wiki/exams/{level}.yaml)",
           "Edit(wiki/log.md)", "Bash(python3 .tools/lint_wiki.py)", "--permission-prompts", "none",
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    try:
        run = subprocess.run(cmd, cwd=ROOT, input=prompt, capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        return fail("Claude took more than an hour.")
    try:
        bank = yaml.safe_load(bank_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return fail("the new bank is not valid YAML.")
    questions = bank.get("questions") or []
    if questions[:len(old)] != old:
        return fail("an existing question was changed.")
    lint = subprocess.run([sys.executable, str(TOOLS / "lint_wiki.py")], cwd=ROOT, capture_output=True, text=True)
    errors = [line for line in lint.stdout.splitlines() if line.startswith("ERROR") and f"exams/{level}.yaml" in line]
    if errors:
        return fail(errors[0])
    added = len(questions) - len(old)
    if not added and not bank.get("exhausted"):
        try:
            said = json.loads(run.stdout).get("result", "")
        except ValueError:
            said = run.stderr
        return fail("no questions were added. " + said.strip()[-300:])
    subprocess.run([sys.executable, str(TOOLS / "build_site.py"), "--exams"], cwd=ROOT, capture_output=True)
    message = (f"Claude added {added} new question{'s' if added != 1 else ''}; they come first in your next attempts." if added
               else f"No new questions: {bank['exhausted']}")
    jobs[level] = {"state": "done", "added": added, "message": message}


def render_answer(text: str) -> str:
    pages = site.load_pages()  # re-read each time, so wiki edits show up without a restart
    anchors = []

    def link(m: re.Match) -> str:
        target, anchor, label = m.group(1).strip(), m.group(2), m.group(3)
        page = pages.get(target)
        if page is None:
            anchors.append(f'<span class="wl missing">{html.escape(label or target)}</span>')
        else:
            href = "/" + page.href + (f"#{anchor}" if anchor else "")
            text = label or (site.cite_label(page) if page.type == "paper" else page.title)
            anchors.append(f'<a class="wl wl-{page.type}" href="{html.escape(href)}" '
                           f'title="{html.escape(page.title)}">{html.escape(text)}</a>')
        return f"WIKILINK{len(anchors) - 1}X"

    # Placeholders keep the links out of markdown's way (a "|" inside a table would split the cell).
    out = md.render(site.LINK_RE.sub(link, text))
    return re.sub(r"WIKILINK(\d+)X", lambda m: anchors[int(m.group(1))], out)


def build_prompt(req: dict) -> str:
    path = str(req.get("page", "")).lstrip("/")
    rel = "" if path in ("", "index.html") else "index" if path == "wiki-index.html" else path.removesuffix(".html")
    source = site.WIKI / f"{rel}.md"
    if rel and source.resolve().is_relative_to(site.WIKI) and source.is_file():
        where = f'The reader is on the page "{req.get("title", rel)}" (source: wiki/{rel}.md).'
    elif rel.startswith("exams/"):
        where = f'The reader is on the exam page "{req.get("title", rel)}"; the question banks are wiki/exams/*.yaml.'
    else:
        where = "The reader is on the site's home page, which lists every paper and synthesis page."
    parts = [where]
    if selection := str(req.get("selection", "")).strip()[:4000]:
        parts.append("They highlighted this passage:\n" + "\n".join("> " + line for line in selection.splitlines()))
    parts.append("Question: " + str(req["question"]).strip())
    return "\n\n".join(parts)


def grade_prompt(req: dict) -> str | None:
    """The grading prompt for a written exam answer, built from the bank on disk."""
    level = str(req.get("level", ""))
    if level not in ("easy", "medium", "hard") or not (site.WIKI / "exams" / f"{level}.yaml").is_file():
        return None
    bank = yaml.safe_load((site.WIKI / "exams" / f"{level}.yaml").read_text(encoding="utf-8")) or {}
    q = next((q for q in bank.get("questions", []) if q.get("id") == req.get("id") and q.get("kind") == "written"), None)
    if q is None:
        return None
    points = "\n".join(f"- {p}" for p in q["rubric"])
    sources = "\n".join(f"- [[{s}]]" for s in q.get("sources", []))
    return (f"Question:\n{q['question']}\n\nFull answer:\n{q['answer']}\n\nPoints it makes:\n{points}\n\n"
            f"Wiki pages behind it:\n{sources}\n\nThe reader's answer:\n{str(req.get('response', ''))[:6000]}")


def tool_status(block: dict) -> str:
    args = block.get("input", {})
    if block["name"] == "Read":
        return "Reading " + os.path.relpath(args.get("file_path", ""), ROOT)
    if block["name"] == "Grep":
        return f"Searching for “{args.get('pattern', '')}”"
    return f"Looking for {args.get('pattern', 'files')}"


def translate_event(e: dict) -> dict | None:
    """One line of `claude -p --output-format stream-json` -> one event for the page, or None."""
    kind = e.get("type")
    if kind == "system" and e.get("subtype") == "init":
        return {"session": e["session_id"]}
    if kind == "stream_event":
        delta = e["event"].get("delta", {})
        return {"text": delta["text"]} if delta.get("type") == "text_delta" else None
    if kind == "assistant":
        tools = [b for b in e["message"]["content"] if b.get("type") == "tool_use"]
        return {"tool": tool_status(tools[-1])} if tools else None
    if kind == "result":
        if e.get("is_error") or e.get("subtype") != "success":
            return {"error": e.get("result") or ""}
        return {"done": True, "html": render_answer(e["result"])}
    return None


def make_handler(port: int, model: str | None, threshold: int):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SITE), **kwargs)

        def log_message(self, fmt, *args):
            if self.command == "POST":
                super().log_message(fmt, *args)

        def do_GET(self):
            name = self.path.split("?")[0].removeprefix("/__chat/")
            if name in ("chat.js", "chat.css"):
                return self.send_bytes((ASSETS / name).read_bytes(), "text/javascript" if name.endswith("js") else "text/css")
            if name == "exam-status":
                level = self.path.partition("level=")[2]
                if load_bank(level) is None:
                    return self.send_error(404)
                return self.send_json(exam_status(level, threshold))
            path = self.translate_path(self.path)
            if os.path.isdir(path) and self.path.split("?")[0].endswith("/"):
                path = os.path.join(path, "index.html")
            if path.endswith(".html") and os.path.isfile(path):
                page = Path(path).read_bytes()
                i = page.rfind(b"</body>")
                return self.send_bytes(page[:i] + INJECT + page[i:], "text/html; charset=utf-8")
            super().do_GET()

        def send_bytes(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, body: dict):
            self.send_bytes(json.dumps(body).encode(), "application/json")

        def send_event(self, event: dict):
            self.wfile.write((json.dumps(event) + "\n").encode())
            self.wfile.flush()

        def do_POST(self):
            # Only this site may start a Claude run: other web pages open in the browser can
            # also reach localhost, but they send their own Origin.
            origin = self.headers.get("Origin")
            if self.path not in ("/__chat/ask", "/__chat/grade", "/__chat/attempt") or self.headers.get("Host") not in hosts or (
                origin is not None and origin.removeprefix("http://") not in hosts
            ):
                return self.send_error(403)
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/__chat/grade":
                return self.grade(req)
            if self.path == "/__chat/attempt":
                return self.attempt(req)
            if not str(req.get("question", "")).strip():
                return self.send_error(400)

            cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                   "--tools", "Read,Grep,Glob", "--permission-prompts", "none",
                   "--strict-mcp-config", "--disable-slash-commands", "--append-system-prompt", SYSTEM]
            if model:
                cmd += ["--model", model]
            if SESSION_RE.match(str(req.get("session", ""))):
                cmd += ["--resume", req["session"]]
            proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            proc.stdin.write(build_prompt(req))
            proc.stdin.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                started = done = False
                error = None
                for line in proc.stdout:
                    out = translate_event(json.loads(line) if line.startswith("{") else {})
                    if out and "error" in out:
                        error = out["error"]
                    elif out:
                        self.send_event(out)
                        started = started or "session" in out
                        done = done or "done" in out
                if not done:
                    # A failed --resume (e.g. a deleted session) reports only on stderr and never
                    # starts; "reset" tells the page to drop its session id and start afresh.
                    error = error or proc.stderr.read().strip() or f"claude exited with code {proc.wait()}"
                    self.send_event({"error": error[-2000:], "reset": not started})
            except (BrokenPipeError, ConnectionResetError):
                pass  # the reader left the page
            finally:
                proc.kill()
                proc.wait()

        def grade(self, req: dict):
            prompt = grade_prompt(req)
            if prompt is None:
                return self.send_error(404)
            cmd = ["claude", "-p", "--output-format", "json", "--json-schema", GRADE_SCHEMA, "--tools", "",
                   "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands",
                   "--append-system-prompt", GRADER]
            if model:
                cmd += ["--model", model]
            try:
                run = subprocess.run(cmd, cwd=ROOT, input=prompt, capture_output=True, text=True, timeout=300)
                out = json.loads(run.stdout)["structured_output"]
                body = {"verdict": out["verdict"], "html": render_answer(out["feedback"])}
            except subprocess.TimeoutExpired:
                body = {"error": "Grading took more than five minutes."}
            except (ValueError, KeyError, TypeError):
                body = {"error": (run.stderr.strip() or run.stdout.strip())[-1000:] or "Grading failed."}
            if body.get("verdict") == "correct":
                count(req["level"], [], [req["id"]])
            self.send_json(body)

        def attempt(self, req: dict):
            """A submitted attempt: count its answered and correct questions, then maybe extend the bank."""
            level = str(req.get("level", ""))
            bank = load_bank(level)
            if bank is None:
                return self.send_error(404)
            ids = {q["id"] for q in bank.get("questions", [])}
            count(level, [i for i in req.get("answered", []) if i in ids], [i for i in req.get("correct", []) if i in ids])
            maybe_generate(level, threshold, model)
            self.send_json(exam_status(level, threshold))

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", help="Claude model alias or id; defaults to your Claude Code setting")
    ap.add_argument("--new-questions-after", type=int, default=3, metavar="N",
                    help="write new exam questions once every question of a level was answered N times (0: never)")
    args = ap.parse_args()
    if not (SITE / "index.html").is_file():
        ap.error(f"{SITE / 'index.html'} not found; run python3 .tools/build_site.py first")
    # Several wikis can be served at once: when the port is taken, use the next free one.
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(port, args.model, args.new_questions_after))
            break
        except OSError:
            continue
    else:
        ap.error(f"ports {args.port}-{args.port + 19} are all in use; pass another --port")
    print(f"Serving {ROOT.name} at http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
