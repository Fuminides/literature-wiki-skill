#!/usr/bin/env python3
"""Recover paper figures from arXiv source packages for the static site.

For each paper in sources/arxiv/manifest.csv this downloads the source package,
walks the figure environments of paper.expanded.tex in order (so the n-th
captioned environment is "Figure n"), and writes the graphics each one includes
to sources/arxiv/<paper>/figures/ as PNG, plus figures.json with captions.
Figures drawn in TikZ have no graphics file; they are listed with no files.

Usage: python3 .tools/fetch_figures.py [--only 01,14] [--force]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "sources" / "arxiv" / "manifest.csv"
USER_AGENT = "Mozilla/5.0 (LiteratureWiki/1.0; academic-use)"
GRAPHIC_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps"]
MAX_WIDTH = 1600

FIG_ENV_RE = re.compile(r"\\begin\{(figure\*?|wrapfigure)\}(.*?)\\end\{\1\}", re.S)
INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def braced(text: str, start: int) -> str:
    """Return the contents of the brace group opening at text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{" and text[i - 1] != "\\":
            depth += 1
        elif text[i] == "}" and text[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    return text[start + 1 :]


def captions(body: str) -> list[str]:
    result = []
    for m in re.finditer(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", body):
        result.append(braced(body, m.end() - 1))
    return result


MACRO_DEF_RE = re.compile(
    r"\\(?:(?:re)?newcommand\*?|providecommand\*?)\s*\{?\\([a-zA-Z]+)\}?\s*\{"
    r"|\\def\s*\\([a-zA-Z]+)\s*\{"
)


def macros(tex: str) -> dict[str, str]:
    """Zero-argument macro definitions, e.g. \\newcommand{\\ours}{RRL\\xspace}."""
    defs = {}
    tex = strip_comments(tex)
    for m in MACRO_DEF_RE.finditer(tex):
        body = braced(tex, m.end() - 1)
        if "#" not in body:
            defs[m.group(1) or m.group(2)] = body.replace("\\xspace", "").strip()
    return defs


def expand(text: str, defs: dict[str, str]) -> str:
    for _ in range(3):  # macros may be defined in terms of other macros
        text = re.sub(r"\\([a-zA-Z]+)(?![a-zA-Z])\s?",
                      lambda m: defs[m.group(1)] + " " if m.group(1) in defs else m.group(0), text)
    return text


GREEK = {name: chr(0x3B1 + i) for i, name in enumerate(
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho "
    "varsigma sigma tau upsilon phi chi psi omega".split())}
GREEK.update({"Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ",
              "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω", "varepsilon": "ε", "vartheta": "θ", "varphi": "φ",
              "times": "×", "leq": "≤", "geq": "≥", "le": "≤", "ge": "≥", "neg": "¬", "lnot": "¬",
              "wedge": "∧", "land": "∧", "vee": "∨", "lor": "∨", "rightarrow": "→", "to": "→",
              "leftarrow": "←", "forall": "∀", "exists": "∃", "in": "∈", "infty": "∞", "partial": "∂"})


def tex_to_text(tex: str) -> str:
    text = re.sub(r"\\label\{[^}]*\}", "", tex)
    text = re.sub(r"\\([a-zA-Z]+)(?![a-zA-Z])", lambda m: GREEK.get(m.group(1), m.group(0)), text)
    text = re.sub(r"\\(?:cite[tp]?|citep|citet|ref|eqref|autoref|cref|Cref)\*?(?:\[[^\]]*\])?\{[^}]*\}", "[…]", text)
    for _ in range(3):
        text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)
    text = text.replace("~", " ").replace("$", "").replace("{", "").replace("}", "").replace("\\", "")
    text = text.replace("``", "“").replace("''", "”").replace("---", "—").replace("--", "–")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)


def figure_environments(tex: str) -> list[dict]:
    defs = macros(tex)
    figures = []
    for m in FIG_ENV_RE.finditer(strip_comments(tex)):
        body = m.group(2)
        caps = captions(body)
        if not caps:
            continue
        labels = LABEL_RE.findall(body)
        figures.append(
            {
                "number": len(figures) + 1,
                "label": labels[-1] if labels else "",
                # With subfigures, the main caption comes last.
                "caption": tex_to_text(expand(caps[-1], defs)),
                "graphics": [g.strip() for g in INCLUDE_RE.findall(body)],
            }
        )
    return figures


def graphics_paths(tex: str) -> list[str]:
    m = re.search(r"\\graphicspath\s*\{(.*?)\}\s*$", strip_comments(tex), re.M)
    return re.findall(r"\{([^}]*)\}", m.group(1)) if m else []


def download(arxiv_id: str) -> bytes:
    req = Request(f"https://arxiv.org/src/{arxiv_id}", headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def members(data: bytes) -> dict[str, bytes]:
    try:
        tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except tarfile.ReadError:
        return {}  # single-file (gzipped TeX) submission: no graphics
    files = {}
    for info in tar.getmembers():
        if info.isfile() and Path(info.name).suffix.lower() in GRAPHIC_EXTS:
            files[str(PurePosixPath(info.name)).lstrip("./")] = tar.extractfile(info).read()
    return files


def resolve(ref: str, files: dict[str, bytes], prefixes: list[str], main_dir: str) -> str | None:
    ref = ref.strip().lstrip("./")
    candidates = []
    for prefix in ["", *prefixes]:
        for base in ["", main_dir]:
            stem = str(PurePosixPath(base, prefix.lstrip("./"), ref)).lstrip("./")
            candidates.append(stem)
            candidates.extend(stem + ext for ext in GRAPHIC_EXTS)
    for cand in candidates:
        if cand in files:
            return cand
    lower = {k.lower(): k for k in files}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def to_png(name: str, data: bytes, out: Path) -> None:
    suffix = Path(name).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ("in" + suffix)
        src.write_bytes(data)
        if suffix == ".pdf":
            subprocess.run(["pdftoppm", "-r", "200", "-f", "1", "-l", "1", "-singlefile", "-png",
                            str(src), str(out.with_suffix(""))], check=True, capture_output=True)
        elif suffix in {".eps", ".ps"}:
            subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop", "-r200",
                            "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", "-sDEVICE=png16m",
                            f"-sOutputFile={out}", str(src)], check=True, capture_output=True)
        else:
            from PIL import Image
            img = Image.open(src).convert("RGBA")  # flatten transparency onto white
            flat = Image.new("RGB", img.size, "white")
            flat.paste(img, mask=img.getchannel("A"))
            flat.save(out)
    from PIL import Image
    img = Image.open(out)
    if img.width > MAX_WIDTH:
        img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width))).save(out, optimize=True)


def process(row: dict, force: bool) -> str:
    paper_dir = ROOT / Path(row["expanded_tex"]).parent
    out_dir = paper_dir / "figures"
    if (out_dir / "figures.json").exists() and not force:
        return "skip"
    tex = (ROOT / row["expanded_tex"]).read_text(errors="replace")
    figures = figure_environments(tex)
    files = members(download(row["arxiv_id"]))
    main_dir = str(PurePosixPath(row["main_tex"]).parent)
    prefixes = graphics_paths(tex)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()
    missing = 0
    for fig in figures:
        fig["files"] = []
        for i, ref in enumerate(fig.pop("graphics")):
            name = resolve(ref, files, prefixes, main_dir)
            if name is None:
                missing += 1
                continue
            out = out_dir / f"fig{fig['number']:02d}_{i + 1}.png"
            try:
                to_png(name, files[name], out)
                fig["files"].append(out.name)
            except Exception:  # corrupt or unsupported graphic: leave it out
                missing += 1
    (out_dir / "figures.json").write_text(json.dumps(figures, indent=2, ensure_ascii=False))
    with_files = sum(1 for f in figures if f["files"])
    return f"{len(figures)} figures, {with_files} with graphics, {missing} unresolved includes"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    only = {int(x) for x in args.only.split(",") if x}
    with MANIFEST.open() as fh:
        rows = [r for r in csv.DictReader(fh) if r["expanded_tex"]]
    for row in rows:
        if only and int(row["index"]) not in only:
            continue
        try:
            status = process(row, args.force)
        except Exception as exc:
            status = f"ERROR {exc}"
        print(f"{int(row['index']):02d} {row['arxiv_id']}: {status}", flush=True)
        if status != "skip":
            time.sleep(3)  # arXiv asks for polite pacing


if __name__ == "__main__":
    main()
