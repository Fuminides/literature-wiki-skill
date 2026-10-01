#!/usr/bin/env python3
"""Serve site/ locally with an "Ask Claude" chat panel on every page.

    python3 .tools/serve_site.py               # then open the printed URL (port 8765 or the next free one)
    python3 .tools/serve_site.py --port 8800 --model sonnet

Each question runs Claude Code (`claude -p`) in the project directory with read-only tools
(Read, Grep, Glob), so it follows CLAUDE.md and can open the wiki pages, PDFs and sources.
The panel tells Claude which page the reader is on and any passage they highlighted;
follow-up questions resume the same Claude session. Needs the `claude` CLI, logged in.
The server listens on 127.0.0.1 only; site/ itself stays a plain offline site.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

import build_site as site

ROOT, SITE = site.ROOT, site.SITE
ASSETS = Path(__file__).resolve().parent / "site_assets"
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
    else:
        where = "The reader is on the site's home page, which lists every paper and synthesis page."
    parts = [where]
    if selection := str(req.get("selection", "")).strip()[:4000]:
        parts.append("They highlighted this passage:\n" + "\n".join("> " + line for line in selection.splitlines()))
    parts.append("Question: " + str(req["question"]).strip())
    return "\n\n".join(parts)


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


def make_handler(port: int, model: str | None):
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

        def send_event(self, event: dict):
            self.wfile.write((json.dumps(event) + "\n").encode())
            self.wfile.flush()

        def do_POST(self):
            # Only this site may start a Claude run: other web pages open in the browser can
            # also reach localhost, but they send their own Origin.
            origin = self.headers.get("Origin")
            if self.path != "/__chat/ask" or self.headers.get("Host") not in hosts or (
                origin is not None and origin.removeprefix("http://") not in hosts
            ):
                return self.send_error(403)
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
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

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", help="Claude model alias or id; defaults to your Claude Code setting")
    args = ap.parse_args()
    if not (SITE / "index.html").is_file():
        ap.error(f"{SITE / 'index.html'} not found; run python3 .tools/build_site.py first")
    # Several wikis can be served at once: when the port is taken, use the next free one.
    for port in range(args.port, args.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(port, args.model))
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
