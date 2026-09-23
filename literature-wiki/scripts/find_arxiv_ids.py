#!/usr/bin/env python3
"""Match each paper in papers.csv to an arXiv ID and write arxiv_sources.csv.

Match methods, in order:
  papers.csv-url        the curated direct_pdf_url is already an arXiv link;
  arxiv-title-exact     the arXiv API returns a paper whose normalized title is identical;
  arxiv-title-variant   a close but not identical title (similarity >= 0.9). Check these by
                        hand: preprints are sometimes retitled, and sometimes a different paper;
  no-confirmed-match    nothing close enough. The paper is then read from its PDF only.

Rows already present in arxiv_sources.csv are kept unless --force is given, so hand
corrections survive a re-run.

Usage: python3 .tools/find_arxiv_ids.py [--force] [--delay 3]
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS_CSV = ROOT / "papers.csv"
OUT = ROOT / "arxiv_sources.csv"
USER_AGENT = "Mozilla/5.0 (LiteratureWiki/1.0; academic-use)"
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/[0-9]{7})")
ATOM = "{http://www.w3.org/2005/Atom}"


def norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def search(title: str) -> list[tuple[str, str]]:
    words = " ".join(norm(title).split()[:12])
    # arXiv answers 406 when the colon after the field name is percent-encoded.
    query = urllib.parse.quote(f'ti:"{words}"', safe=":")
    url = f"https://export.arxiv.org/api/query?search_query={query}&max_results=5"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        feed = ET.fromstring(resp.read())
    hits = []
    for entry in feed.findall(f"{ATOM}entry"):
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/abs/", 1)[-1]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        hits.append((arxiv_id, " ".join(entry.findtext(f"{ATOM}title", "").split())))
    return hits


def match(row: dict) -> dict:
    result = {"index": row["index"], "arxiv_id": "", "match_method": "no-confirmed-match", "notes": ""}
    m = ARXIV_URL_RE.search(row.get("direct_pdf_url", ""))
    if m:
        result.update(arxiv_id=re.sub(r"v\d+$", "", m.group(1)), match_method="papers.csv-url")
        return result
    try:
        hits = search(row["title"])
    except Exception as exc:  # network trouble: leave the row for a later run
        result["notes"] = f"search failed: {exc}"
        return result
    best = max(hits, key=lambda h: difflib.SequenceMatcher(None, norm(row["title"]), norm(h[1])).ratio(),
               default=None)
    if best:
        ratio = difflib.SequenceMatcher(None, norm(row["title"]), norm(best[1])).ratio()
        if ratio == 1.0:
            result.update(arxiv_id=best[0], match_method="arxiv-title-exact")
        elif ratio >= 0.9:
            result.update(arxiv_id=best[0], match_method="arxiv-title-variant", notes=f"arXiv title: {best[1]}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-match rows already in arxiv_sources.csv")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between arXiv API calls")
    args = parser.parse_args()
    with PAPERS_CSV.open(encoding="utf-8", newline="") as fh:
        papers = list(csv.DictReader(fh))
    existing = {}
    if OUT.exists() and not args.force:
        with OUT.open(encoding="utf-8", newline="") as fh:
            existing = {r["index"]: r for r in csv.DictReader(fh)}
    rows = []
    for row in papers:
        old = existing.get(row["index"])
        if old and not old.get("notes", "").startswith("search failed"):
            rows.append(old)
            continue
        new = match(row)
        rows.append(new)
        print(f"{int(row['index']):02d} {new['match_method']:<20} {new['arxiv_id']:<12} {row['title']}", flush=True)
        if new["match_method"] != "papers.csv-url":
            time.sleep(args.delay)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["index", "arxiv_id", "match_method", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["match_method"]] = counts.get(r["match_method"], 0) + 1
    print("Done:", ", ".join(f"{v} {k}" for k, v in sorted(counts.items())), f"-> {OUT.name}")


if __name__ == "__main__":
    main()
