#!/usr/bin/env python3
"""Render wiki/ as a static HTML site in site/ that works straight from disk.

All links are relative, the search index is a script file (browsers block
fetch() on file:// pages), and nothing is loaded from the network. $...$ and
$$...$$ in the wiki are TeX, rendered in the browser by a vendored KaTeX; write
a literal dollar sign as \\$. Figures are
chosen in .tools/site_figures.yaml; see the comment at the top of that file.

Usage: python3 .tools/build_site.py [--check-figures]
"""

from __future__ import annotations

import csv
import html
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from PIL import Image
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

ROOT = Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
SITE = ROOT / "site"
ASSETS = Path(__file__).resolve().parent / "site_assets"
FIGURES_CFG = Path(__file__).resolve().parent / "site_figures.yaml"
# wiki.yaml at the project root names the wiki: {name: ..., mark: one character for the logo}.
CONFIG = yaml.safe_load((ROOT / "wiki.yaml").read_text(encoding="utf-8")) if (ROOT / "wiki.yaml").exists() else {}
WIKI_NAME = CONFIG.get("name", "Literature Wiki")
WIKI_MARK = CONFIG.get("mark", "§")

LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")
LINT_COMMENT_RE = re.compile(r"\s*<!-- lint:[^>]*-->")
INDEX_ENTRY_RE = re.compile(r"^- (?:\[\[([^\]|]+)\]\]|`([^`]+)`) — (.*?)(?: · (\d+) sources?)? · (active|planned)(.*)$")

# Sidebar and home-page order: (type, directory, plural label).
SECTIONS = [
    ("chapter", "textbook", "Textbook"),
    ("paper", "papers", "Papers"),
    ("concept", "concepts", "Concepts"),
    ("method", "methods", "Methods"),
    ("comparison", "comparisons", "Comparisons"),
    ("open-question", "open-questions", "Open questions"),
    ("dataset", "datasets", "Datasets"),
    ("metric", "metrics", "Metrics"),
]

md = MarkdownIt("commonmark", {"html": True, "typographer": False}).enable("table").use(dollarmath_plugin, allow_digits=False)


@dataclass
class Page:
    rel: str  # e.g. "papers/yang2017a"
    meta: dict
    body: str
    title: str
    out_links: set[str] = field(default_factory=set)

    @property
    def type(self) -> str:
        return self.meta.get("type", "")

    @property
    def href(self) -> str:
        # site/index.html is the home page, so the wiki's own index moves aside.
        return "wiki-index.html" if self.rel == "index" else self.rel + ".html"


# ---------------------------------------------------------------- loading


def load_pages() -> dict[str, Page]:
    pages = {}
    for path in sorted(WIKI.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.S)
        meta, body = (yaml.safe_load(m.group(1)) or {}, m.group(2)) if m else ({}, text)
        rel = path.relative_to(WIKI).with_suffix("").as_posix()
        h1 = re.search(r"^# (.+)$", body, re.M)
        title = str(meta.get("title") or (h1.group(1).strip() if h1 else rel))
        page = Page(rel, meta, body, title)
        page.out_links = {t.strip() for t, _, _ in LINK_RE.findall(body)}
        pages[rel] = page
    return pages


def index_entries() -> tuple[dict[str, dict], dict[str, str]]:
    """Parse wiki/index.md into {rel: {desc, sources, status}} and {paper rel: category}."""
    entries, categories = {}, {}
    category = ""
    in_papers = False
    for line in (WIKI / "index.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_papers = line.startswith("## Papers")
        elif line.startswith("### ") and in_papers:
            category = line[4:].strip()
        m = INDEX_ENTRY_RE.match(line)
        if m:
            rel = (m.group(1) or m.group(2)).strip()
            entries[rel] = {"desc": m.group(3), "sources": m.group(4), "status": m.group(5),
                            "note": m.group(6).lstrip("; ").strip()}
            if rel.startswith("papers/"):
                categories[rel] = category
    return entries, categories


def short_names() -> dict[str, str]:
    names = {}
    for line in (WIKI / "vocabulary.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[1].startswith("`"):
            names[cells[1].strip("`")] = cells[3]
    return names


def bibtex_entries() -> dict[str, str]:
    text = (ROOT / "references.bib").read_text(encoding="utf-8")
    return {m.group(1): m.group(0).strip()
            for m in re.finditer(r"@\w+\{([^,]+),.*?\n\}", text, re.S)}


def arxiv_ids() -> dict[str, str]:
    """Map a sources/arxiv/<dir> name to its arXiv id."""
    ids = {}
    manifest = ROOT / "sources" / "arxiv" / "manifest.csv"
    if not manifest.exists():
        return ids
    with manifest.open() as fh:
        for row in csv.DictReader(fh):
            if row["source_dir"]:
                ids[Path(row["source_dir"]).parent.name] = row["arxiv_id"]
    return ids


# ---------------------------------------------------------------- helpers


def rel_prefix(rel: str) -> str:
    return "../" * rel.count("/")


def surname(author: str) -> str:
    parts = author.split()
    # Keep particles such as "van Krieken" together.
    for i, p in enumerate(parts[:-1]):
        if p[0].islower():
            return " ".join(parts[i:])
    return parts[-1]


def cite_label(page: Page) -> str:
    authors = page.meta.get("authors") or []
    year = page.meta.get("year", "")
    if not authors:
        return page.title
    first = surname(str(authors[0]))
    if len(authors) == 1:
        return f"{first} {year}"
    if len(authors) == 2:
        return f"{first} & {surname(str(authors[1]))} {year}"
    return f"{first} et al. {year}"


def esc(text) -> str:
    return html.escape(str(text), quote=True)


# ---------------------------------------------------------------- figures


def load_figure_config() -> dict[str, list[dict]]:
    if not FIGURES_CFG.exists():
        return {}
    return yaml.safe_load(FIGURES_CFG.read_text(encoding="utf-8")) or {}


def arxiv_dir(paper: Page) -> Path | None:
    src = paper.meta.get("source_text")
    return (ROOT / src).parent if src else None


def prepare_figure(spec: dict, paper: Page, n: int) -> dict | None:
    """Copy or render one figure into site/figures/<citekey>/ and return its display data."""
    key = paper.meta["citekey"]
    out_dir = SITE / "figures" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    caption = spec.get("caption")
    number = spec.get("fig")
    files: list[str] = []
    if "crop" in spec:  # region of a PDF page, box in fractions of the page
        crop = spec["crop"]
        pdf = ROOT / paper.meta["local_pdf"]
        dpi = 200
        size = subprocess.run(["pdfinfo", "-f", str(crop["page"]), "-l", str(crop["page"]), str(pdf)],
                              capture_output=True, text=True).stdout
        w_pt, h_pt = map(float, re.search(r"Page\s+\d+ size:\s+([\d.]+) x ([\d.]+)", size).groups())
        x0, y0, x1, y1 = crop["box"]
        scale = dpi / 72
        stem = out_dir / f"fig{number or n:02}_crop"
        subprocess.run(["pdftoppm", "-png", "-singlefile", "-r", str(dpi),
                        "-f", str(crop["page"]), "-l", str(crop["page"]),
                        "-x", str(round(x0 * w_pt * scale)), "-y", str(round(y0 * h_pt * scale)),
                        "-W", str(round((x1 - x0) * w_pt * scale)), "-H", str(round((y1 - y0) * h_pt * scale)),
                        str(pdf), str(stem)], check=True)
        files.append(stem.name + ".png")
        locator = f"Figure {number}, PDF p. {crop['page']}" if number else f"PDF p. {crop['page']}"
    else:
        src_dir = arxiv_dir(paper) / "figures"
        figs = {f["number"]: f for f in json.loads((src_dir / "figures.json").read_text())}
        fig = figs[spec.get("tex", number)]
        caption = caption or fig["caption"]
        wanted = spec.get("parts") or range(1, len(fig["files"]) + 1)
        for name in fig["files"]:
            part = int(name.rsplit("_", 1)[1].split(".")[0])
            if part in wanted:
                shutil.copy2(src_dir / name, out_dir / name)
                files.append(name)
        locator = f"Figure {number}"
    if not files:
        return None
    return {"files": [f"figures/{key}/{f}" for f in files], "caption": caption or "",
            "locator": locator, "section": spec.get("section", "Method"),
            "note": spec.get("note", ""), "paper": paper.rel}


def figure_html(fig: dict, pages: dict[str, Page], prefix: str) -> str:
    imgs = "".join(f'<a href="{prefix}{f}" class="fig-img"><img src="{prefix}{f}" alt="" loading="lazy"></a>'
                   for f in fig["files"])
    paper = pages[fig["paper"]]
    note = f'<p class="fig-note">{esc(fig["note"])}</p>' if fig["note"] else ""
    return (f'<figure class="paper-fig{" multi" if len(fig["files"]) > 1 else ""}">'
            f'<div class="fig-imgs">{imgs}</div>'
            f'<figcaption><span class="fig-loc"><a href="{prefix}{paper.href}">{esc(cite_label(paper))}</a>'
            f' · {esc(fig["locator"])}</span> {esc(fig["caption"])}{note}</figcaption></figure>')


# ---------------------------------------------------------------- rendering


def render_body(page: Page, pages: dict[str, Page], figures: list[dict]) -> str:
    prefix = rel_prefix(page.rel)
    body = LINT_COMMENT_RE.sub("", page.body)
    body = re.sub(r"^# .+\n", "", body, count=1, flags=re.M)

    # Place each figure at the end of its section as a placeholder paragraph.
    for i, fig in enumerate(figures):
        marker = f"\n\nFIGUREPLACEHOLDER{i}\n\n"
        m = (re.search(rf"^(#{{2,3}}) {re.escape(fig['section'])}\s*$", body, re.M)
             or re.search(r"^(##) .+$", body, re.M))
        if not m:
            body = body + marker
            continue
        # The section ends at the next heading of the same or a higher level.
        nxt = re.search(rf"^#{{2,{len(m.group(1))}}} ", body[m.end():], re.M)
        pos = m.end() + nxt.start() if nxt else len(body)
        body = body[:pos].rstrip() + marker + body[pos:]

    def link(m: re.Match) -> str:
        target, anchor, label = m.group(1).strip(), m.group(2), m.group(3)
        other = pages.get(target)
        if other is None:
            return f'<span class="wl missing">{esc(label or target)}</span>'
        cls = f"wl wl-{other.type}" + (" wl-self" if other.rel == page.rel else "")
        href = prefix + other.href + (f"#{anchor}" if anchor else "")
        if other.type == "paper":
            text = label or cite_label(other)
            return f'<a class="{cls}" href="{href}" title="{esc(other.title)}">{esc(text)}</a>'
        return f'<a class="{cls}" href="{href}">{esc(label or other.title)}</a>'

    body = LINK_RE.sub(link, body)
    out = md.render(body)
    for i, fig in enumerate(figures):
        out = out.replace(f"<p>FIGUREPLACEHOLDER{i}</p>", figure_html(fig, pages, prefix))
    # Heading anchors.
    out = re.sub(r"<(h[23])>(.*?)</\1>",
                 lambda m: f'<{m.group(1)} id="{re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", m.group(2)).lower()).strip("-")}">{m.group(2)}</{m.group(1)}>',
                 out)
    out = out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    return out


def toc(body_html: str) -> str:
    items = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body_html)
    if len(items) < 3:
        return ""
    lis = "".join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a></li>' for i, t in items)
    return f'<nav class="toc"><div class="toc-title">On this page</div><ol>{lis}</ol></nav>'


def paper_header(page: Page, ctx: dict) -> str:
    m, prefix = page.meta, rel_prefix(page.rel)
    key = m.get("citekey", "")
    authors = ", ".join(str(a) for a in m.get("authors", []))
    bits = [str(m.get("year", "")), esc(m.get("venue", ""))]
    cat = ctx["categories"].get(page.rel)
    chips = f'<span class="chip chip-cat">{esc(cat)}</span>' if cat else ""
    if ctx["short"].get(key) and ctx["short"][key].lower() != page.title.lower():
        chips += f'<span class="chip">{esc(ctx["short"][key])}</span>'
    links = []
    if m.get("local_pdf"):
        links.append(f'<a class="btn" href="{prefix}../{esc(m["local_pdf"])}">Local PDF</a>')
    d = arxiv_dir(page)
    if d and d.name in ctx["arxiv"]:
        links.append(f'<a class="btn" href="https://arxiv.org/abs/{ctx["arxiv"][d.name]}">arXiv</a>')
    bib = ctx["bib"].get(key)
    bib_html = (f'<details class="bib"><summary>BibTeX</summary><pre>{esc(bib)}</pre></details>' if bib else "")
    return (f'<div class="paper-meta"><div class="authors">{esc(authors)}</div>'
            f'<div class="venue">{" · ".join(b for b in bits if b)} <code>{esc(key)}</code></div>'
            f'<div class="chips">{chips}</div>'
            f'<div class="actions">{"".join(links)}</div>{bib_html}</div>')


def backlinks_html(page: Page, pages: dict[str, Page], inbound: dict[str, set[str]]) -> str:
    prefix = rel_prefix(page.rel)
    sources = {r for r in inbound.get(page.rel, set())
               if pages[r].type not in {"index", "vocabulary", "log", "pins"}}
    if page.type == "paper":  # paper-to-paper links are already in "Linked from:"
        sources = {r for r in sources if pages[r].type != "paper"}
    if not sources:
        return ""
    groups = []
    for typ, _, label in SECTIONS + [("overview", "", "Overview")]:
        rels = sorted((r for r in sources if pages[r].type == typ),
                      key=lambda r: pages[r].title.lower())
        if rels:
            links = "".join(
                f'<a class="wl wl-{typ}" href="{prefix}{pages[r].href}">'
                f'{esc(cite_label(pages[r]) if typ == "paper" else pages[r].title)}</a>' for r in rels)
            groups.append(f'<div class="bl-group"><span class="bl-label">{label}</span>{links}</div>')
    title = "Discussed on" if page.type == "paper" else "Referenced by"
    return f'<section class="backlinks"><h2>{title}</h2>{"".join(groups)}</section>'


def sidebar(current: Page | None, pages: dict[str, Page], ctx: dict) -> str:
    prefix = rel_prefix(current.rel) if current else ""
    cur = current.rel if current else ""

    def a(rel: str, text: str) -> str:
        on = ' class="on" aria-current="page"' if rel == cur else ""
        return f'<a{on} href="{prefix}{pages[rel].href}">{esc(text)}</a>'

    parts = [f'<a class="home{" on" if not current else ""}" href="{prefix}index.html">Home</a>',
             a("overview", "Overview")]
    for typ, directory, label in SECTIONS:
        rels = [r for r in pages if pages[r].type == typ]
        if not rels:
            continue
        open_ = " open" if current and current.type == typ else ""
        if typ == "paper":
            by_cat: dict[str, list[str]] = {c: [] for c in dict.fromkeys(ctx["categories"].values())}
            for r in rels:
                by_cat.setdefault(ctx["categories"].get(r, "Other"), []).append(r)
            inner = ""
            for cat, rs in by_cat.items():
                if not rs:
                    continue
                rs.sort(key=lambda r: (pages[r].meta.get("year", 0), r))
                inner += f'<div class="nav-sub">{esc(cat)}</div>' + "".join(
                    a(r, f"{ctx['short'].get(pages[r].meta.get('citekey'), pages[r].title)}") for r in rs)
        elif typ == "chapter":
            inner = "".join(a(r, f"{pages[r].meta['order']}. {pages[r].title}") for r in chapters(pages))
        else:
            rels.sort(key=lambda r: pages[r].title.lower())
            inner = "".join(a(r, pages[r].title) for r in rels)
        parts.append(f'<details{open_}><summary>{label} <span class="count">{len(rels)}</span></summary>'
                     f'<div class="nav-list">{inner}</div></details>')
    meta_open = " open" if current and current.rel in {"index", "vocabulary", "pins", "log"} else ""
    parts.append(f'<details{meta_open}><summary>Wiki meta</summary><div class="nav-list">'
                 + a("index", "Index") + a("vocabulary", "Vocabulary") + a("pins", "Pins") + a("log", "Operation log")
                 + "</div></details>")
    return "".join(parts)


def chapters(pages: dict[str, Page]) -> list[str]:
    return sorted((r for r in pages if pages[r].type == "chapter"), key=lambda r: pages[r].meta["order"])


def chapter_nav(page: Page, pages: dict[str, Page]) -> str:
    order = chapters(pages)
    i = order.index(page.rel)
    prefix = rel_prefix(page.rel)
    links = []
    if i > 0:
        prev = pages[order[i - 1]]
        links.append(f'<a class="chap-prev" href="{prefix}{prev.href}"><span>← Previous</span>'
                     f'{prev.meta["order"]}. {esc(prev.title)}</a>')
    if i + 1 < len(order):
        nxt = pages[order[i + 1]]
        links.append(f'<a class="chap-next" href="{prefix}{nxt.href}"><span>Next →</span>'
                     f'{nxt.meta["order"]}. {esc(nxt.title)}</a>')
    return f'<nav class="chap-nav">{"".join(links)}</nav>'


TYPE_LABEL = {"chapter": "Textbook", "paper": "Paper", "concept": "Concept", "method": "Method", "dataset": "Dataset",
              "metric": "Metric", "comparison": "Comparison", "open-question": "Open question",
              "overview": "Overview", "index": "Meta", "vocabulary": "Meta", "pins": "Meta", "log": "Meta"}


# Loaded only by pages that contain math.
KATEX_HEAD = """<link rel="stylesheet" href="{prefix}assets/katex/katex.min.css">
<script defer src="{prefix}assets/katex/katex.min.js"
  onload="document.querySelectorAll('.math').forEach(function(e){{try{{katex.render(e.textContent,e,{{displayMode:e.classList.contains('block'),throwOnError:false}})}}catch(x){{}}}})"></script>
"""


def layout(title: str, prefix: str, nav: str, content: str, wide: bool = False) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(WIKI_NAME)}</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
{KATEX_HEAD.format(prefix=prefix) if 'class="math ' in content else ""}<script>try{{var t=localStorage.getItem("theme");if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
</head>
<body data-prefix="{prefix}">
<header class="topbar">
  <button class="menu-btn" aria-label="Toggle navigation">☰</button>
  <a class="brand" href="{prefix}index.html"><span class="brand-mark">{esc(WIKI_MARK)}</span> {esc(WIKI_NAME)}</a>
  <div class="search"><input id="q" type="search" placeholder="Search papers, concepts, methods…  ( / )" autocomplete="off"><div id="search-results" hidden></div></div>
  <button class="theme-btn" aria-label="Toggle dark mode" title="Toggle dark mode">◐</button>
</header>
<div class="shell{' wide' if wide else ''}">
  <nav class="sidebar">{nav}</nav>
  <main>{content}</main>
</div>
<script src="{prefix}assets/search-index.js"></script>
<script src="{prefix}assets/site.js"></script>
</body>
</html>
"""


def render_page(page: Page, pages: dict[str, Page], ctx: dict) -> str:
    figs = ctx["figures"].get(page.rel, [])
    body = render_body(page, pages, figs)
    kicker = (f"Textbook · Chapter {page.meta['order']}" if page.type == "chapter"
              else TYPE_LABEL.get(page.type, page.type.title()))
    head = f'<div class="kicker kicker-{page.type}">{kicker}</div>'
    head += f"<h1>{esc(page.title)}</h1>"
    if page.type == "paper":
        head += paper_header(page, ctx)
    else:
        n = len(page.meta.get("sources") or [])
        upd = page.meta.get("updated", "")
        if n or upd:
            head += (f'<div class="page-meta">{f"{n} source papers" if n else ""}'
                     f'{" · " if n and upd else ""}{f"updated {upd}" if upd else ""}</div>')
    content = (f'<article class="page page-{page.type}"><header class="page-head">{head}</header>'
               f'<div class="page-body">{toc(body)}<div class="prose">{body}'
               f'{chapter_nav(page, pages) if page.type == "chapter" else ""}'
               f'{backlinks_html(page, pages, ctx["inbound"])}</div></div></article>')
    return layout(page.title, rel_prefix(page.rel), sidebar(page, pages, ctx), content)


def render_home(pages: dict[str, Page], ctx: dict) -> str:
    papers = sorted((p for p in pages.values() if p.type == "paper"),
                    key=lambda p: (-p.meta.get("year", 0), p.rel))
    overview = pages["overview"].body
    intro = re.split(r"\n\s*\n", re.sub(r"^# .+\n", "", overview).strip())[0]
    intro_html = md.render(LINK_RE.sub(lambda m: m.group(3) or pages[m.group(1)].title if m.group(1) in pages else m.group(1), intro))

    def thumb_file(figs: list[dict]) -> str:
        """The figure image whose shape best fits the card (about 1.6:1)."""
        files = [f for fig in figs for f in fig["files"]]
        with_ratio = [(abs(math.log(w / h / 1.6)), f) for f in files for w, h in [Image.open(SITE / f).size]]
        return min(with_ratio)[1]

    cards = []
    for p in papers:
        figs = ctx["figures"].get(p.rel, [])
        thumb = (f'<img src="{thumb_file(figs)}" alt="" loading="lazy">' if figs
                 else f'<div class="no-thumb">{esc(ctx["short"].get(p.meta["citekey"], ""))}</div>')
        cat = ctx["categories"].get(p.rel, "")
        cards.append(
            f'<a class="card" href="{p.href}" data-cat="{esc(cat)}" data-year="{p.meta.get("year", "")}" '
            f'data-text="{esc((p.title + " " + " ".join(map(str, p.meta.get("authors", []))) + " " + ctx["short"].get(p.meta["citekey"], "")).lower())}">'
            f'<div class="thumb">{thumb}</div><div class="card-body">'
            f'<div class="card-meta">{p.meta.get("year", "")} · {esc(p.meta.get("venue", ""))}</div>'
            f'<div class="card-title">{esc(p.title)}</div>'
            f'<div class="card-authors">{esc(cite_label(p))}</div>'
            f'<span class="chip chip-cat">{esc(cat)}</span></div></a>')
    cats = list(dict.fromkeys(ctx["categories"][p.rel] for p in papers if p.rel in ctx["categories"]))
    filters = '<button class="filter on" data-cat="">All</button>' + "".join(
        f'<button class="filter" data-cat="{esc(c)}">{esc(c)}</button>' for c in cats)
    planned = [r for r, e in ctx["entries"].items() if r.startswith("papers/") and e["status"] == "planned"]
    planned_html = ""
    if planned:
        planned_html = ('<p class="muted small">Not yet covered (no full text available): '
                        + "; ".join(esc(ctx["entries"][r]["desc"]) for r in planned) + ".</p>")

    def listing(typ: str, directory: str, label: str) -> str:
        rels = sorted((r for r in pages if pages[r].type == typ), key=lambda r: pages[r].title.lower())
        items = "".join(
            f'<li><a href="{pages[r].href}">{esc(pages[r].title)}</a>'
            f'<span class="desc">{esc(ctx["entries"].get(r, {}).get("desc", ""))}</span>'
            f'<span class="n">{ctx["entries"].get(r, {}).get("sources") or ""}</span></li>' for r in rels)
        return f'<section class="listing" id="{directory}"><h2>{label}</h2><ul>{items}</ul></section>'

    chapter_items = "".join(
        f'<li><a href="{pages[r].href}"><span class="chap-n">{pages[r].meta["order"]}</span>'
        f'<span class="chap-t">{esc(pages[r].title)}</span>'
        f'<span class="desc">{esc(ctx["entries"].get(r, {}).get("desc", ""))}</span></a></li>'
        for r in chapters(pages))
    textbook = (f'<section class="textbook" id="textbook"><div class="section-head"><h2>Textbook</h2></div>'
                f'<p class="muted">A guided tour of the field in {len(chapters(pages))} chapters: what has been '
                f'researched, why it matters and how it works. Every claim links back to the papers.</p>'
                f'<ol class="chapter-list">{chapter_items}</ol></section>') if chapters(pages) else ""

    counts = {typ: sum(1 for p in pages.values() if p.type == typ) for typ, _, _ in SECTIONS}
    stats = "".join(f'<a class="stat" href="#{d}"><b>{counts[t]}</b><span>{l.lower()}</span></a>'
                    for t, d, l in SECTIONS if counts[t])
    content = f"""
<section class="hero">
  <div class="kicker">Literature wiki</div>
  <h1>{esc(WIKI_NAME)}</h1>
  <div class="hero-intro">{intro_html}</div>
  <p class="hero-links">{f'<a class="btn primary" href="{pages[chapters(pages)[0]].href}">Start the textbook</a>' if chapters(pages) else ""}
  <a class="btn" href="overview.html">Read the overview</a>
  <a class="btn" href="#papers">Browse papers</a> <a class="btn" href="#concepts">Concepts</a></p>
  <div class="stats">{stats}</div>
</section>
{textbook}
<section id="papers">
  <div class="section-head"><h2>Papers</h2>
  <input id="paper-filter" type="search" placeholder="Filter by title, author, name…"></div>
  <div class="filters">{filters}</div>
  <div class="cards">{"".join(cards)}</div>
  {planned_html}
</section>
{listing("concept", "concepts", "Concepts")}
<div class="two-col">{listing("comparison", "comparisons", "Comparisons")}{listing("open-question", "open-questions", "Open questions")}</div>
{listing("method", "methods", "Methods")}
<div class="two-col">{listing("dataset", "datasets", "Datasets")}{listing("metric", "metrics", "Metrics")}</div>
<p class="muted small footer-note">Generated from <code>wiki/</code> by <code>.tools/build_site.py</code>.
Figures are reproduced from the papers for private reference; captions are the authors' own.</p>
"""
    return layout("Home", "", sidebar(None, pages, ctx), f'<div class="home">{content}</div>', wide=True)


def search_index(pages: dict[str, Page], ctx: dict) -> str:
    docs = []
    for p in pages.values():
        if p.type in {"index", "vocabulary", "log", "pins"}:
            continue
        text = LINK_RE.sub(lambda m: m.group(3) or (cite_label(pages[m.group(1)]) if m.group(1) in pages and pages[m.group(1)].type == "paper" else pages[m.group(1)].title if m.group(1) in pages else m.group(1)), p.body)
        text = LINT_COMMENT_RE.sub("", text)
        text = re.sub(r"[#*_`>|]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        extra = ""
        if p.type == "paper":
            extra = " ".join([cite_label(p), ctx["short"].get(p.meta.get("citekey"), ""),
                              " ".join(map(str, p.meta.get("authors", []))), p.meta.get("citekey", "")])
        docs.append({"h": p.href, "t": p.title, "y": TYPE_LABEL.get(p.type, p.type), "k": extra, "x": text})
    return "window.SEARCH_DOCS=" + json.dumps(docs, ensure_ascii=False, separators=(",", ":")) + ";\n"


def check_figures(pages: dict[str, Page]) -> int:
    """Confirm each arXiv figure's number by finding its caption after "Figure N" in the PDF."""
    by_key = {p.meta["citekey"]: p for p in pages.values() if p.type == "paper"}
    problems = 0
    for rel, specs in load_figure_config().items():
        for spec in specs:
            if "crop" in spec:
                continue
            paper = by_key[spec["paper"]] if "paper" in spec else pages[rel]
            src = arxiv_dir(paper) / "figures" / "figures.json"
            fig = {f["number"]: f for f in json.loads(src.read_text())}.get(spec.get("tex", spec["fig"]))
            text = subprocess.run(["pdftotext", str(ROOT / paper.meta["local_pdf"]), "-"],
                                  capture_output=True, text=True).stdout
            # Compare letters only: the PDF text layer splits words and drops hyphens.
            want = re.sub(r"[^a-z]", "", (fig or {}).get("caption", "").lower())[:30]
            found = any(want and want in re.sub(r"[^a-z]", "", text[m.end():m.end() + 300].lower())
                        for m in re.finditer(rf"(?:Figure|Fig\.?|F\s?IG\s?\.?)\s*{spec['fig']}\s*[.:]", text, re.I))
            if not found:
                problems += 1
                print(f"CHECK {rel}: Figure {spec['fig']} of {paper.meta['citekey']} not confirmed"
                      f" ({want or 'no caption'})")
    print(f"{problems} figure(s) need a look")
    return problems


def main() -> None:
    pages = load_pages()
    if "--check-figures" in sys.argv:
        raise SystemExit(1 if check_figures(pages) else 0)
    entries, categories = index_entries()
    inbound: dict[str, set[str]] = {}
    for p in pages.values():
        for t in p.out_links:
            if t in pages and t != p.rel:
                inbound.setdefault(t, set()).add(p.rel)

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    shutil.copytree(ASSETS, SITE / "assets", dirs_exist_ok=True)
    # Diagrams drawn for the textbook live beside its chapters.
    if (WIKI / "textbook" / "figures").is_dir():
        shutil.copytree(WIKI / "textbook" / "figures", SITE / "textbook" / "figures")

    by_key = {p.meta["citekey"]: p for p in pages.values() if p.type == "paper"}
    figures: dict[str, list[dict]] = {}
    for rel, specs in load_figure_config().items():
        for n, spec in enumerate(specs, 1):
            paper = by_key[spec["paper"]] if "paper" in spec else pages[rel]
            fig = prepare_figure(spec, paper, n)
            if fig:
                figures.setdefault(rel, []).append(fig)

    ctx = {"entries": entries, "categories": categories, "short": short_names(), "bib": bibtex_entries(),
           "arxiv": arxiv_ids(), "inbound": inbound, "figures": figures}
    for p in pages.values():
        out = SITE / p.href
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_page(p, pages, ctx), encoding="utf-8")
    (SITE / "index.html").write_text(render_home(pages, ctx), encoding="utf-8")
    (SITE / "assets" / "search-index.js").write_text(search_index(pages, ctx), encoding="utf-8")
    n_figs = sum(len(v) for v in figures.values())
    print(f"Built {len(pages) + 1} pages with {n_figs} figures into {SITE.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
