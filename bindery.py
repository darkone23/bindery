#!/usr/bin/env python3
"""bindery — book-reprint toolkit.

M0 stage: `ingest` renders a PDF into a per-page archival raster
(600 dpi PNG) under `archive/` plus a `manifest.json` sidecar.
Originals are never mutated.

M1 stages: `assemble` builds a validated page-order file (`order.json`);
`trim` crops pages to the book trim profile with gutter-margin math;
`impose` lays signatures onto duplex US-Letter sheets (2-up per side,
long-edge flip) with creep compensation, crop/fold marks and a black
registration check block, plus a screen proof PDF.

Design: Paperclip HOL-250 plan rev 1 (docs link in README).
Imposition geometry: fold the sheet's top half down, spin the packet
90 deg CCW (crease -> book-left), page 1 on the packet's front face,
long-edge duplex. Front slots carry pages rotated 90 deg CW, back slots
90 deg CCW; every page's spine edge sits at the fold.
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

# US Letter portrait, pt; fold line is horizontal at mid-height
LETTER_W, LETTER_H = 612.0, 792.0
CREASE = LETTER_H / 2.0

IMPOSE_DEFAULTS = {
    "paper": "letter",
    "signature_pages": 8,
    "slot_margin_pt": 14.0,
    "caliper_mm": 0.10,
    "marks": True,
    "proof_dpi": 150,
}


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


# ---------------------------------------------------------------------------
# M1: assemble / trim / impose
# ---------------------------------------------------------------------------

def parse_page_size(text: str) -> tuple[float, float]:
    """pdfinfo 'Page size' like '444 x 667.44 pts' -> (444.0, 667.44)."""
    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)", text)
    if not m:
        raise RuntimeError(f"unparsable page size: {text!r}")
    return float(m.group(1)), float(m.group(2))


def load_book(path: Path) -> dict:
    """Parse book.toml, applying impose defaults."""
    import tomllib

    cfg = tomllib.loads(Path(path).read_text())
    cfg.setdefault("book", {})
    cfg.setdefault("order", {})
    cfg["trim"] = dict(cfg.get("trim", {}))
    imp = dict(IMPOSE_DEFAULTS)
    imp.update(cfg.get("impose", {}))
    cfg["impose"] = imp
    return cfg


def signature_plan(n_pages: int, sig_pages: int) -> list[dict]:
    """Group ordered pages into fold signatures.

    A signature of S pages (multiple of 4) = S/4 nested sheets; sheet j
    (0 = outermost) carries the reading-order pages 2j+1, 2j+2 (leaf A)
    and S-2j-1, S-2j (leaf B) as global positions. Short trailing
    signatures are padded with blank slots to the next multiple of 4.

    Returns a list of signatures, each {"pages", "real_pages", "sheets"};
    every sheet is {"sheet_in_sig", "depth", "front": {"top","bottom"},
    "back": {"top","bottom"}} with global book positions or None (blank).
    """
    if sig_pages < 4:
        raise ValueError("signature_pages must be >= 4")
    sig_pages = (sig_pages // 4) * 4
    plan = []
    pos = 1
    while pos <= n_pages:
        real = min(sig_pages, n_pages - pos + 1)
        padded = (real + 3) // 4 * 4
        sheets = []
        for j in range(padded // 4):
            slots = {
                "back": {"top": 2 * j + 1, "bottom": padded - 2 * j},
                "front": {"top": 2 * j + 2, "bottom": padded - 2 * j - 1},
            }
            kept = {
                face: {name: (pos + p - 1 if 1 <= p <= real else None)
                       for name, p in names.items()}
                for face, names in slots.items()
            }
            sheets.append({"sheet_in_sig": j + 1, "depth": j, **kept})
        plan.append({"pages": padded, "real_pages": real, "sheets": sheets})
        pos += real
    return plan


def creep_pt(depth: int, caliper_mm: float) -> float:
    """Creep compensation (pt) for a sheet `depth` sheets inside its
    signature: each enclosing fold displaces the crease by twice the
    paper caliper, so inner content shifts toward the crease equally."""
    return depth * 2.0 * caliper_mm * 72.0 / 25.4


def crop_rect(page_w: float, page_h: float, verso: bool, depth: int,
              cfg: dict) -> tuple[float, float, float, float]:
    """Trim crop rect (x0, y0, x1, y1) in source-page pt, y from the TOP.

    Margins crop inward from each edge; the inside (spine-side) margin
    additionally grows with the sheet's depth in its signature. Recto
    pages (odd position) have their spine on the left edge, verso on the
    right edge. Defaults (empty cfg) keep the whole source page, so the
    trim ratio matches the source.
    """
    inside = float(cfg.get("inside_pt", 0.0))
    inside += float(cfg.get("inside_growth_per_sheet_pt", 0.0)) * depth
    outside = float(cfg.get("outside_pt", 0.0))
    top = float(cfg.get("top_pt", 0.0))
    bottom = float(cfg.get("bottom_pt", 0.0))
    if verso:
        x0, x1 = outside, page_w - inside
    else:
        x0, x1 = inside, page_w - outside
    y0, y1 = top, page_h - bottom
    for a, b, name in ((x0, x1, "width"), (y0, y1, "height")):
        if b - a <= 1.0:
            raise ValueError(
                f"degenerate trim crop ({name}): margins "
                f"inside={inside} outside={outside} top={top} bottom={bottom}")
    return (max(0.0, x0), max(0.0, y0), min(page_w, x1), min(page_h, y1))


def build_order(book: dict, archive: Path, order_path: Path | None = None) -> dict:
    """Validate archive pages against the manifest and write order.json."""
    archive = Path(archive)
    manifest = json.loads((archive / "manifest.json").read_text())
    by_page = {e["page"]: e for e in manifest["pages"]}
    spec = book.get("order", {})
    if "pages" in spec:
        seq = [int(p) for p in spec["pages"]]
    elif "slice" in spec:
        sl = spec["slice"]
        seq = list(range(int(sl["first"]), int(sl["last"]) + 1))
    else:
        raise SystemExit("book.toml [order]: need 'pages' or 'slice'")

    pages = []
    for position, n in enumerate(seq, start=1):
        entry = by_page.get(n)
        if entry is None:
            raise SystemExit(
                f"archive has no page {n} (manifest lists {len(by_page)})")
        f = archive / entry["file"]
        if not f.is_file():
            raise SystemExit(f"missing archive file: {f}")
        if sha256_file(f) != entry["sha256"]:
            raise SystemExit(f"sha256 mismatch: {f}")
        pages.append({"position": position, "archive_page": n,
                      "file": entry["file"], "sha256": entry["sha256"]})

    order = {
        "schema_version": SCHEMA_VERSION,
        "stage": "assemble",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "book": book.get("book", {}).get("title", ""),
        "archive": str(archive),
        "pages": pages,
    }
    order_path = order_path or Path("build") / "order.json"
    order_path.parent.mkdir(parents=True, exist_ok=True)
    order_path.write_text(json.dumps(order, indent=2) + "\n")
    return order


def trim(book: dict, archive: Path, out_dir: Path) -> dict:
    """Crop ordered pages to the trim profile; emit trim/page-*.png + trim.json."""
    from PIL import Image

    archive = Path(archive)
    order = json.loads((out_dir / "order.json").read_text())
    manifest = json.loads((archive / "manifest.json").read_text())
    page_w, page_h = parse_page_size(manifest["source"]["pdfinfo"]["Page size"])
    dpi = int(manifest["render"]["dpi"])
    f = dpi / 72.0
    tcfg = book.get("trim", {})
    imp = dict(IMPOSE_DEFAULTS)
    imp.update(book.get("impose", {}))
    plan = signature_plan(len(order["pages"]), int(imp["signature_pages"]))

    slot_of = {}
    for si, sig in enumerate(plan, start=1):
        for sheet in sig["sheets"]:
            for face in ("front", "back"):
                for _name, gpos in sheet[face].items():
                    if gpos is not None:
                        slot_of[gpos] = (si, sheet["sheet_in_sig"], sheet["depth"])

    trim_dir = out_dir / "trim"
    trim_dir.mkdir(parents=True, exist_ok=True)
    pages_meta = []
    for entry in order["pages"]:
        pos = entry["position"]
        sig_no, sheet_no, depth = slot_of[pos]
        rect = crop_rect(page_w, page_h, pos % 2 == 0, depth, tcfg)
        img = Image.open(archive / entry["file"])
        x0, y0, x1, y1 = rect
        box = (max(0, round(x0 * f)), max(0, round(y0 * f)),
               min(img.size[0], round(x1 * f)), min(img.size[1], round(y1 * f)))
        out_name = f"trimmed-{pos:04d}.png"
        dest = trim_dir / out_name
        if box == (0, 0, *img.size):
            shutil.copyfile(archive / entry["file"], dest)
        else:
            img.crop(box).save(dest)
        pages_meta.append({
            "position": pos, "archive_page": entry["archive_page"],
            "file": entry["file"], "out_file": out_name,
            "crop_pt": list(rect),
            "out_px": [box[2] - box[0], box[3] - box[1]],
            "verso": pos % 2 == 0,
            "signature": sig_no, "sheet_in_sig": sheet_no, "depth": depth,
        })

    meta = {
        "schema_version": SCHEMA_VERSION,
        "stage": "trim",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "book": book.get("book", {}).get("title", ""),
        "archive": str(archive),
        "source_page_pt": [page_w, page_h],
        "archive_dpi": dpi,
        "trim_cfg": tcfg,
        "pages": pages_meta,
    }
    (out_dir / "trim.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def slot_placement(side: str, pos_name: str, gap: float, h: float, w: float,
                   creep: float) -> tuple[tuple[float, float], int, list[float]]:
    """Placement for one slot: (translate anchor, rotation deg, placed rect).

    Geometry (HOL-253): fold the sheet's top half down, spin the packet
    90 deg CCW, page 1 on the packet's front face, long-edge duplex.
    Back slots place pages rotated 90 CCW, front slots 90 CW; every
    page's spine edge sits at the fold (creep shifts it toward the
    crease). `h` = scaled page height, `w` = scaled page width.
    """
    if pos_name == "top":  # region A: crease at slot bottom
        if side == "back":  # T_back, recto: spine edge at rect bottom
            tx, ty = gap + h, CREASE + gap - creep
            return (tx, ty), 90, [tx - h, ty, tx, ty + w]
        tx, ty = LETTER_W - gap - h, CREASE + gap + w - creep
        return (tx, ty), 270, [tx, ty - w, tx + h, ty]
    if side == "back":  # B_back, verso: spine edge at rect top
        tx, ty = gap + h, CREASE - gap - w + creep
        return (tx, ty), 90, [tx - h, ty, tx, ty + w]
    tx, ty = LETTER_W - gap - h, CREASE - gap + creep
    return (tx, ty), 270, [tx, ty - w, tx + h, ty]


def _draw_marks(c, rect, margin):
    """Crop marks at a placed page rect's four corners."""
    from reportlab.lib.colors import black

    x0, y0, x1, y1 = rect
    g, ln = 2.0, 4.0
    c.setStrokeColor(black)
    c.setLineWidth(1.5)
    for cx, cy, dx, dy in (
            (x0, y0, -1, -1), (x1, y0, 1, -1),
            (x0, y1, -1, 1), (x1, y1, 1, 1)):
        c.line(cx + dx * g, cy, cx + dx * (g + ln), cy)
        c.line(cx, cy + dy * g, cx, cy + dy * (g + ln))


def _draw_chrome(c, label, margin):
    """Fold ticks, registration block and the collation label.

    The registration block sits centered on the fold at the same PDF
    coords on front and back (mirror-symmetric position), so a duplex
    registration check is: hold the sheet to the light and see the two
    blocks coincide.
    """
    from reportlab.lib.colors import black, white

    c.setLineWidth(1.5)
    c.setStrokeColor(black)
    c.line(0, CREASE, 12, CREASE)
    c.line(LETTER_W - 12, CREASE, LETTER_W, CREASE)
    r = 8.0
    cx, cy = LETTER_W / 2.0, CREASE
    c.setFillColor(black)
    c.rect(cx - r, cy - r, 2 * r, 2 * r, fill=1, stroke=0)
    c.setStrokeColor(white)
    c.setLineWidth(1.5)
    c.line(cx - r + 2, cy, cx + r - 2, cy)
    c.line(cx, cy - r + 2, cx, cy + r - 2)
    c.setFillColor(black)
    c.setFont("Helvetica", 5)
    c.drawString(24, CREASE + 4, label)
    c.drawString(LETTER_W - 24 - c.stringWidth(label, "Helvetica", 5),
                 CREASE - 8, label)


def impose(book: dict, out_dir: Path) -> dict:
    """Impose trimmed pages onto duplex Letter sheets; emit press.pdf,
    proof-screen.pdf and impose.json."""
    from reportlab.pdfgen import canvas
    from PIL import Image

    trim_meta = json.loads((out_dir / "trim.json").read_text())
    imp = dict(IMPOSE_DEFAULTS)
    imp.update(book.get("impose", {}))
    if imp["paper"] != "letter":
        raise SystemExit(f"unsupported paper {imp['paper']!r} (M1: letter)")
    margin = float(imp["slot_margin_pt"])
    caliper = float(imp["caliper_mm"])
    proof_dpi = int(imp["proof_dpi"])
    pages = trim_meta["pages"]
    n = len(pages)
    by_pos = {p["position"]: p for p in pages}

    crop_sizes = {(round(p["crop_pt"][2] - p["crop_pt"][0], 3),
                   round(p["crop_pt"][3] - p["crop_pt"][1], 3))
                  for p in pages}
    if len(crop_sizes) != 1:
        raise SystemExit(f"non-uniform trimmed page sizes: {crop_sizes}")
    pw, ph = next(iter(crop_sizes))
    # rotated page footprint: x-extent = ph*s, y-extent = pw*s
    scale = min((LETTER_W - 2 * margin) / ph, (CREASE - 2 * margin) / pw)
    w, h = pw * scale, ph * scale
    creep_per_sheet = 2.0 * caliper * 72.0 / 25.4

    plan = signature_plan(n, int(imp["signature_pages"]))
    title = book.get("book", {}).get("title", "bindery")

    c = canvas.Canvas(str(out_dir / "press.pdf"), pagesize=(LETTER_W, LETTER_H))
    c.setTitle(f"{title} — press sheets (duplex, long-edge)")
    sheets_meta = []
    gi = 0
    for si, sig in enumerate(plan, start=1):
        for sheet in sig["sheets"]:
            gi += 1
            creep = sheet["depth"] * creep_per_sheet
            sheet_meta = {
                "global_index": gi, "signature": si,
                "sheet_in_sig": sheet["sheet_in_sig"],
                "sheets_in_sig": len(sig["sheets"]),
                "depth": sheet["depth"], "creep_pt": round(creep, 4),
                "front": {}, "back": {},
            }
            for side in ("front", "back"):
                for pos_name in ("top", "bottom"):
                    gpos = sheet[side][pos_name]
                    anchor, rot, rect = slot_placement(
                        side, pos_name, margin, h, w, creep)
                    entry = {"page": gpos}
                    if gpos is not None:
                        png = out_dir / "trim" / by_pos[gpos]["out_file"]
                        x0, y0 = anchor
                        c.saveState()
                        c.translate(x0, y0)
                        c.rotate(rot)
                        c.drawImage(str(png), 0, 0, width=pw * scale,
                                    height=ph * scale)
                        c.restoreState()
                        entry["rect"] = [round(v, 2) for v in rect]
                    else:
                        entry["rect"] = None
                    sheet_meta[side][pos_name] = entry
                if imp["marks"]:
                    for _pn, entry in sheet_meta[side].items():
                        if entry["rect"]:
                            _draw_marks(c, entry["rect"], margin)
                top = sheet[side]["top"]
                bottom = sheet[side]["bottom"]

                def fmt(p):
                    return str(p) if p is not None else "blank"

                label = (f"SIG{si} SHEET{sheet['sheet_in_sig']}/{len(sig['sheets'])} "
                         f"{side.upper()} pages {fmt(top)}|{fmt(bottom)}")
                if imp["marks"]:
                    _draw_chrome(c, label, margin)
                c.showPage()
            sheets_meta.append(sheet_meta)
    c.save()

    # screen proof: single-page sequence at trim size, downscaled rasters
    pc = canvas.Canvas(str(out_dir / "proof-screen.pdf"), pagesize=(pw, ph))
    pc.setTitle(f"{title} — screen proof (reading order)")
    pf = proof_dpi / 72.0
    for p in pages:  # reading order
        img = Image.open(out_dir / "trim" / p["out_file"])
        tw, th = round(pw * pf), round(ph * pf)
        small = out_dir / "trim" / (p["out_file"].replace(".png", f".proof{proof_dpi}.png"))
        if not small.is_file() or Image.open(small).size != (tw, th):
            img.resize((tw, th), Image.LANCZOS).save(small)
        pc.drawImage(str(small), 0, 0, width=pw, height=ph)
        pc.showPage()
    pc.save()

    meta = {
        "schema_version": SCHEMA_VERSION,
        "stage": "impose",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "book": title,
        "flip": "long-edge",
        "paper": {"w_pt": LETTER_W, "h_pt": LETTER_H},
        "scale": round(scale, 6),
        "page_pt": [pw, ph],
        "creep_per_sheet_pt": round(creep_per_sheet, 4),
        "slot_margin_pt": margin,
        "signature_pages": int(imp["signature_pages"]),
        "sheets": sheets_meta,
    }
    (out_dir / "impose.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


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

    def _book_and_archive(args):
        book = load_book(args.book)
        archive = args.archive or book.get("source", {}).get("archive")
        if not archive:
            raise SystemExit("no archive: pass --archive or set [source] archive in book.toml")
        return book, Path(archive).expanduser()

    p_asm = sub.add_parser("assemble", help="validate archive pages and build order.json")
    p_asm.add_argument("--book", type=Path, default=Path("book.toml"))
    p_asm.add_argument("--archive", type=Path, default=None)
    p_asm.add_argument("--out", type=Path, default=Path("build"))

    p_trm = sub.add_parser("trim", help="crop pages to the book trim profile")
    p_trm.add_argument("--book", type=Path, default=Path("book.toml"))
    p_trm.add_argument("--archive", type=Path, default=None)
    p_trm.add_argument("--out", type=Path, default=Path("build"))

    p_imp = sub.add_parser("impose", help="impose trimmed pages onto duplex Letter sheets")
    p_imp.add_argument("--book", type=Path, default=Path("book.toml"))
    p_imp.add_argument("--out", type=Path, default=Path("build"))

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
    if args.cmd == "assemble":
        book, archive = _book_and_archive(args)
        order = build_order(book, archive, args.out / "order.json")
        print(f"assembled {len(order['pages'])} pages -> {args.out / 'order.json'}")
        return 0
    if args.cmd == "trim":
        book, archive = _book_and_archive(args)
        meta = trim(book, archive, args.out)
        print(f"trimmed {len(meta['pages'])} pages -> {args.out / 'trim'} "
              f"(crop {meta['source_page_pt'][0]:.1f}x{meta['source_page_pt'][1]:.1f}pt profile)")
        return 0
    if args.cmd == "impose":
        meta = impose(load_book(args.book), args.out)
        print(f"imposed {len(meta['sheets'])} sheets "
              f"(scale {meta['scale']:.3f}, creep/sheet {meta['creep_per_sheet_pt']:.3f}pt, "
              f"duplex {meta['flip']}) -> {args.out / 'press.pdf'}, "
              f"{args.out / 'proof-screen.pdf'}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
