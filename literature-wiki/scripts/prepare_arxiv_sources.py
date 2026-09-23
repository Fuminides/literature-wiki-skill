#!/usr/bin/env python3
"""Download arXiv source and prepare compact text for the paper collection.

For each confirmed ID in arxiv_sources.csv, this script:

1. downloads the latest source package from arXiv;
2. safely extracts only text-based source files;
3. selects the most likely root TeX document;
4. expands local ``\\input`` and ``\\include`` directives into one TeX file;
5. optionally runs ``detex`` to make an even smaller prose-oriented text file.

The source package is not retained: figures and other binary assets add cost but
are not needed for text retrieval. Re-running without --force skips completed
papers.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent.parent
PAPERS_CSV = HERE / "papers.csv"
ARXIV_CSV = HERE / "arxiv_sources.csv"
OUT = HERE / "sources" / "arxiv"
MANIFEST = OUT / "manifest.csv"
USER_AGENT = "Mozilla/5.0 (LiteratureWiki/1.0; academic-use)"

TEXT_SUFFIXES = {
    ".tex",
    ".ltx",
    ".bib",
    ".bbl",
    ".bst",
    ".sty",
    ".cls",
    ".clo",
    ".cfg",
    ".def",
    ".dtx",
    ".ins",
    ".md",
    ".txt",
}
MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024
INPUT_RE = re.compile(
    r"\\(?P<command>input|include)\s*(?:\[[^\]]*\]\s*)?"
    r"(?:\{(?P<braced>[^{}]+)\}|(?P<bare>[^\s%{}]+))"
)


def slug(value: str, limit: int = 90) -> str:
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"[^A-Za-z0-9._+ -]+", "", value)
    value = re.sub(r"\s+", "_", value.strip())
    return value[:limit].rstrip("_")


def selected_indexes(values: list[str]) -> set[int] | None:
    if not values:
        return None
    result: set[int] = set()
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            if "-" in item:
                start, end = (int(part) for part in item.split("-", 1))
                result.update(range(start, end + 1))
            else:
                result.add(int(item))
    return result


def load_rows() -> list[dict[str, str]]:
    with PAPERS_CSV.open(encoding="utf-8", newline="") as handle:
        papers = {int(row["index"]): row for row in csv.DictReader(handle)}
    with ARXIV_CSV.open(encoding="utf-8", newline="") as handle:
        arxiv = {int(row["index"]): row for row in csv.DictReader(handle)}

    if set(papers) != set(arxiv):
        missing = sorted(set(papers) - set(arxiv))
        extra = sorted(set(arxiv) - set(papers))
        raise ValueError(f"arxiv_sources.csv index mismatch: missing={missing}, extra={extra}")

    rows = []
    for index in sorted(papers):
        rows.append({**papers[index], **arxiv[index]})
    return rows


def download_source(arxiv_id: str, attempts: int = 3) -> bytes:
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urlopen(request, timeout=120) as response:
                data = response.read()
            if len(data) < 100:
                raise ValueError(f"source response is unexpectedly short ({len(data)} bytes)")
            if data.lstrip().startswith(b"%PDF"):
                raise ValueError("arXiv returned a PDF rather than a source package")
            return data
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(3 * attempt)
    raise RuntimeError(f"could not download {url}: {last_error}")


def safe_member_path(name: str) -> Path | None:
    path = PurePosixPath(name)
    clean_parts = tuple(part for part in path.parts if part not in ("", "."))
    if path.is_absolute() or not clean_parts or ".." in clean_parts:
        return None
    return Path(*clean_parts)


def write_text_file(destination: Path, data: bytes) -> None:
    if b"\x00" in data[:4096]:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def unpack_text_sources(data: bytes, destination: Path) -> int:
    """Extract allowed text files and return the number written."""
    written = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            for member in archive.getmembers():
                relative = safe_member_path(member.name)
                if (
                    relative is None
                    or not member.isfile()
                    or relative.suffix.lower() not in TEXT_SUFFIXES
                    or member.size > MAX_TEXT_FILE_BYTES
                ):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                write_text_file(destination / relative, extracted.read())
                if (destination / relative).exists():
                    written += 1
    except tarfile.ReadError:
        # Some old arXiv submissions are a single gzip-compressed TeX file.
        try:
            source = gzip.decompress(data)
        except (gzip.BadGzipFile, EOFError):
            source = data
        write_text_file(destination / "main.tex", source)
        if (destination / "main.tex").exists():
            written = 1
    return written


def tex_score(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lower_name = path.name.lower()
    score = 0
    score += 10_000 if "\\documentclass" in text else 0
    score += 5_000 if "\\begin{document}" in text else 0
    score += 1_000 if "\\title" in text else 0
    score += 500 if lower_name in {"main.tex", "paper.tex", "manuscript.tex", "article.tex"} else 0
    score -= 1_000 if any(word in lower_name for word in ("supp", "appendix", "response")) else 0
    return score, len(text)


def choose_main_tex(source_dir: Path) -> Path:
    candidates = list(source_dir.rglob("*.tex")) + list(source_dir.rglob("*.ltx"))
    if not candidates:
        raise ValueError("source package contains no TeX files")
    return max(candidates, key=tex_score)


def strip_comments(text: str) -> str:
    output = []
    for line in text.splitlines():
        cut = None
        for match in re.finditer(r"%", line):
            backslashes = 0
            position = match.start() - 1
            while position >= 0 and line[position] == "\\":
                backslashes += 1
                position -= 1
            if backslashes % 2 == 0:
                cut = match.start()
                break
        if cut is not None:
            line = line[:cut]
        output.append(line.rstrip())
    # Comment removal often leaves large stretches of blank lines.
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(output)).strip() + "\n"


def resolve_input(current_file: Path, source_root: Path, name: str) -> Path | None:
    value = name.strip()
    candidate = current_file.parent / value
    if not candidate.suffix:
        candidate = candidate.with_suffix(".tex")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(source_root.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def expand_tex(path: Path, source_root: Path, active: tuple[Path, ...] = ()) -> str:
    resolved = path.resolve()
    if resolved in active:
        return f"\n% [cyclic input skipped: {path.relative_to(source_root)}]\n"
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))

    def replace(match: re.Match[str]) -> str:
        name = match.group("braced") or match.group("bare")
        included = resolve_input(path, source_root, name)
        if included is None:
            return match.group(0)
        relative = included.relative_to(source_root)
        body = expand_tex(included, source_root, active + (resolved,))
        return f"\n% BEGIN INCLUDED FILE: {relative}\n{body}% END INCLUDED FILE: {relative}\n"

    return INPUT_RE.sub(replace, text)


def make_plain_text(expanded_tex: Path, destination: Path) -> str:
    detex = shutil.which("detex")
    if detex is None:
        return "detex-not-installed"
    tex = expanded_tex.read_text(encoding="utf-8", errors="replace")
    # opendetex treats the ``\\include`` prefix in ``\\includegraphics`` as a
    # file include on some inputs, which can truncate output at the first
    # figure. The captions remain useful, but image-loading commands do not.
    tex = re.sub(
        r"\\(?:includegraphics|includepdf)\s*(?:\[[^\]]*\]\s*)?\{[^{}]*\}",
        "",
        tex,
    )
    process = subprocess.run(
        # ``-c`` is intentionally omitted: opendetex 2.8.91 can suppress all
        # content after the first cross-reference when citation echoing is on.
        [detex, "-l", "-n"],
        input=tex.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"detex failed: {message}")
    text = process.stdout.decode("utf-8", errors="replace")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    destination.write_text(text, encoding="utf-8")
    return "ok"


def relative_or_blank(path: Path | None) -> str:
    return str(path.relative_to(HERE)) if path is not None else ""


def prepare(row: dict[str, str], force: bool) -> dict[str, str]:
    index = int(row["index"])
    arxiv_id = row["arxiv_id"].strip()
    title = row["title"]
    result = {
        "index": str(index),
        "title": title,
        "arxiv_id": arxiv_id,
        "match_method": row["match_method"],
        "status": "no-confirmed-arxiv-id" if not arxiv_id else "pending",
        "source_dir": "",
        "main_tex": "",
        "expanded_tex": "",
        "plain_text": "",
        "text_source_files": "0",
        "error": "",
    }
    if not arxiv_id:
        return result

    paper_dir = OUT / f"{index:02d}_{slug(title)}"
    source_dir = paper_dir / "source"
    expanded = paper_dir / "paper.expanded.tex"
    plain = paper_dir / "paper.txt"
    metadata = paper_dir / "source.json"
    result.update(
        source_dir=relative_or_blank(source_dir),
        expanded_tex=relative_or_blank(expanded),
        plain_text=relative_or_blank(plain),
    )

    if metadata.exists() and expanded.exists() and not force:
        saved = json.loads(metadata.read_text(encoding="utf-8"))
        main_value = saved.get("main_tex", "")
        result.update(
            status="ok-existing",
            main_tex=main_value,
            text_source_files=str(saved.get("text_source_files", 0)),
            plain_text=relative_or_blank(plain) if plain.exists() else "",
        )
        return result

    OUT.mkdir(parents=True, exist_ok=True)
    try:
        data = download_source(arxiv_id)
        with tempfile.TemporaryDirectory(prefix=f".{index:02d}_", dir=OUT) as temp_name:
            staging = Path(temp_name)
            staged_source = staging / "source"
            staged_source.mkdir()
            count = unpack_text_sources(data, staged_source)
            if count == 0:
                raise ValueError("source package contained no recognized text files")
            main = choose_main_tex(staged_source)
            main_relative = main.relative_to(staged_source)
            expanded_text = expand_tex(main, staged_source)
            (staging / "paper.expanded.tex").write_text(expanded_text, encoding="utf-8")
            plain_status = make_plain_text(
                staging / "paper.expanded.tex", staging / "paper.txt"
            )
            saved = {
                "index": index,
                "title": title,
                "arxiv_id": arxiv_id,
                "source_url": f"https://arxiv.org/e-print/{arxiv_id}",
                "main_tex": str(main_relative),
                "text_source_files": count,
                "plain_text_status": plain_status,
            }
            (staging / "source.json").write_text(
                json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            if paper_dir.exists():
                shutil.rmtree(paper_dir)
            staging.rename(paper_dir)

        result.update(
            status="ok",
            main_tex=str(main_relative),
            text_source_files=str(count),
            plain_text=relative_or_blank(plain) if plain.exists() else "",
        )
    except Exception as error:  # Keep processing the rest of the collection.
        result.update(status="error", error=str(error))
    return result


def write_manifest(results: list[dict[str, str]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "index",
        "title",
        "arxiv_id",
        "match_method",
        "status",
        "source_dir",
        "main_tex",
        "expanded_tex",
        "plain_text",
        "text_source_files",
        "error",
    ]
    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        action="append",
        default=[],
        help="paper index, comma list, or inclusive range; may be repeated",
    )
    parser.add_argument("--force", action="store_true", help="replace completed outputs")
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="seconds between arXiv downloads (default: 3.0)",
    )
    args = parser.parse_args()
    indexes = selected_indexes(args.index)
    rows = load_rows()
    results = []
    downloads = 0

    for position, row in enumerate(rows, 1):
        index = int(row["index"])
        if indexes is not None and index not in indexes:
            # Preserve a full manifest, including unselected rows.
            paper_dir = OUT / f"{index:02d}_{slug(row['title'])}"
            already_prepared = (
                (paper_dir / "source.json").exists()
                and (paper_dir / "paper.expanded.tex").exists()
            )
            result = prepare(row, force=False) if already_prepared or not row["arxiv_id"].strip() else {
                "index": str(index),
                "title": row["title"],
                "arxiv_id": row["arxiv_id"],
                "match_method": row["match_method"],
                "status": "not-selected",
                "source_dir": "",
                "main_tex": "",
                "expanded_tex": "",
                "plain_text": "",
                "text_source_files": "0",
                "error": "",
            }
            results.append(result)
            continue

        print(f"[{position:02d}/{len(rows)}] {index:02d} {row['title']}", flush=True)
        result = prepare(row, force=args.force)
        results.append(result)
        print(f"  {result['status']}{': ' + result['error'] if result['error'] else ''}", flush=True)
        if result["status"] == "ok":
            downloads += 1
            if args.delay > 0:
                time.sleep(args.delay)
        write_manifest(results)

    write_manifest(results)
    ok = sum(result["status"].startswith("ok") for result in results)
    no_id = sum(result["status"] == "no-confirmed-arxiv-id" for result in results)
    errors = sum(result["status"] == "error" for result in results)
    print(
        f"Done: {ok} prepared, {no_id} without confirmed arXiv IDs, "
        f"{errors} errors. Manifest: {MANIFEST.relative_to(HERE)}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
