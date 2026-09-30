#!/usr/bin/env python3
"""bindery — book-reprint toolkit.

M0 stage: `ingest` renders a PDF into a per-page archival raster
(600 dpi PNG) under `archive/` plus a `manifest.json` sidecar.
Originals are never mutated.

Design: Paperclip HOL-250 plan rev 1 (docs link in README).
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def pdfinfo(pdf: Path) -> dict:
    """Minimal pdfinfo parse: page count plus a few informative fields."""
    proc = run(["pdfinfo", str(pdf)])
    out: dict = {}
    for line in proc.stdout.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            if key in ("Pages", "Encrypted", "PDF version", "Page size", "Producer", "Creator"):
                out[key] = val.strip()
    if "Pages" not in out:
        raise RuntimeError(f"pdfinfo gave no page count for {pdf}")
    return out


def page_count(pdf: Path) -> int:
    return int(pdfinfo(pdf)["Pages"])


def render_all(pdf: Path, staging: Path, dpi: int, gray: bool, total: int,
               workers: int = 4) -> None:
    """Render every page into staging, split across concurrent pdftoppm runs.

    Chunks share one output prefix, so files land as pg-<page>.png with no
    collisions (each chunk owns a disjoint page range).
    """
    workers = max(1, min(workers, total))
    bounds = [round(i * total / workers) + 1 for i in range(workers)] + [total + 1]
    procs = []
    for i in range(workers):
        first, last = bounds[i], bounds[i + 1] - 1
        cmd = ["pdftoppm", "-r", str(dpi), "-png"]
        if gray:
            cmd.append("-gray")
        cmd += ["-f", str(first), "-l", str(last), str(pdf), str(staging / "pg")]
        procs.append(subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
    errors: list[str] = []
    for p in procs:
        _, err = p.communicate()
        if p.returncode != 0:
            errors.append(err.strip() or f"pdftoppm exited {p.returncode}")
    if errors:
        raise RuntimeError("; ".join(errors))


def render_page(pdf: Path, n: int, staging: Path, dpi: int, gray: bool) -> None:
    cmd = ["pdftoppm", "-r", str(dpi), "-png"]
    if gray:
        cmd.append("-gray")
    cmd += ["-f", str(n), "-l", str(n), str(pdf), str(staging / "pg")]
    run(cmd)


def pdftoppm_version() -> str:
    proc = run(["pdftoppm", "-v"])
    return proc.stderr.strip() or proc.stdout.strip()


def canonical_pages(staging: Path) -> list[Path]:
    """All rendered page images, sorted by their numeric index."""
    pages: dict[int, Path] = {}
    for p in sorted(staging.glob("pg-*")):
        m = re.search(r"pg-(\d+)\.png$", p.name)
        if m:
            pages[int(m.group(1))] = p
    return [pages[k] for k in sorted(pages)]


def ingest(pdf: Path, out_dir: Path, dpi: int, source_url: str, gray: bool,
           resume: bool = False) -> dict:
    """Render every page of `pdf` into `out_dir` and write manifest.json.

    The source PDF is only ever read; nothing in it is touched.
    Returns the manifest dict.
    """
    if not pdf.is_file():
        raise SystemExit(f"no such PDF: {pdf}")
    out_dir.mkdir(parents=True, exist_ok=True)
    info = pdfinfo(pdf)
    total = int(info["Pages"])
    name = pdf.name

    staging = out_dir / ".staging"
    if staging.exists() and not resume:
        shutil.rmtree(staging)
    staging.mkdir(exist_ok=True)

    archive: list[tuple[int, Path]] = []
    if resume:
        existing = {p.name for p in out_dir.glob("page-*.png")}
        archive = sorted((int(name[5:9]), out_dir / name) for name in existing)
    else:
        existing = set()
        for p in out_dir.glob("page-*.png"):
            p.unlink()
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        render_all(pdf, staging, dpi, gray, total)
        rendered = canonical_pages(staging)
        if len(rendered) != total:
            raise RuntimeError(f"rendered {len(rendered)} pages but expected {total}")
        for p in rendered:
            m = re.search(r"pg-(\d+)\.png$", p.name)
            n = int(m.group(1))
            dest = out_dir / f"page-{n:04d}.png"
            shutil.move(str(p), dest)
            archive.append((n, dest))

    if resume and len(existing) < total:
        # render only the missing pages, one at a time
        for n in range(1, total + 1):
            if f"page-{n:04d}.png" in existing:
                continue
            render_page(pdf, n, staging, dpi, gray)
        rendered = canonical_pages(staging)
        if len(rendered) != total - len(existing):
            raise RuntimeError(
                f"rendered {len(rendered)} pages but expected {total - len(existing)}")
        for p in rendered:
            m = re.search(r"pg-(\d+)\.png$", p.name)
            n = int(m.group(1))
            dest = out_dir / f"page-{n:04d}.png"
            shutil.move(str(p), dest)
            archive.append((n, dest))

    pages_meta = []
    for n, path in sorted(archive):
        pages_meta.append({
            "page": n,
            "file": f"page-{n:04d}.png",
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": "ingest",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "url": source_url or "",
            "file": name,
            "sha256": sha256_file(pdf),
            "size_bytes": pdf.stat().st_size,
            "pages": total,
            "pdfinfo": info,
        },
        "render": {
            "dpi": dpi,
            "format": "png",
            "color": not gray,
            "tool": pdftoppm_version(),
        },
        "pages": pages_meta,
    }
    tmp = out_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=2) + "\n")
    tmp.replace(out_dir / "manifest.json")
    shutil.rmtree(staging, ignore_errors=True)
    return manifest


def verify(out_dir: Path) -> int:
    """Check an archive against its manifest; exit 0 if consistent."""
    mpath = out_dir / "manifest.json"
    manifest = json.loads(mpath.read_text())
    total = manifest["source"]["pages"]
    pages = manifest["pages"]
    bad = 0
    if len(pages) != total:
        print(f"MISMATCH: manifest lists {len(pages)} pages, source has {total}")
        bad += 1
    for entry in pages:
        p = out_dir / entry["file"]
        if not p.is_file():
            print(f"MISSING: {p}")
            bad += 1
            continue
        if sha256_file(p) != entry["sha256"]:
            print(f"HASH MISMATCH: {p}")
            bad += 1
    status = "OK" if bad == 0 else f"FAILED ({bad} problems)"
    print(f"verify {out_dir}: {status} — {len(pages)}/{total} pages, "
          f"dpi={manifest['render']['dpi']}")
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bindery", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="render a PDF into an archival page raster + manifest")
    p_ing.add_argument("pdf", type=Path)
    p_ing.add_argument("--out", type=Path, default=Path("archive"))
    p_ing.add_argument("--dpi", type=int, default=600)
    p_ing.add_argument("--source-url", default="")
    p_ing.add_argument("--gray", action="store_true", help="render grayscale instead of color")
    p_ing.add_argument("--resume", action="store_true",
                       help="keep existing page files; render only what is missing")

    p_ver = sub.add_parser("verify", help="recheck an archive against its manifest")
    p_ver.add_argument("out_dir", type=Path)

    args = ap.parse_args(argv)
    if args.cmd == "ingest":
        manifest = ingest(args.pdf, args.out, args.dpi, args.source_url, args.gray,
                          resume=args.resume)
        n = len(manifest["pages"])
        size = sum(e["size_bytes"] for e in manifest["pages"])
        print(f"ingested {n} pages -> {args.out} ({size / 1e6:.1f} MB total); "
              f"manifest.json written")
        return 0
    if args.cmd == "verify":
        return verify(args.out_dir)
    return 2


if __name__ == "__main__":
    sys.exit(main())
