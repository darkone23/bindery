#!/usr/bin/env python3
"""uttara_typeset — typeset the Uttara-kanda fascicle (HOL-259 M4b).

Turns the harvested e-text (dataset/uttara-eText-ramayana-info.json,
plan rev 4) into press-ready pages in a typesetting that mirrors the
1970s Gita Press edition (board pivot): full-width Devanagari verse
blocks alternating with two-column English translation, centered canto
headings, running head + folio.

Pipeline output (build/):
  typeset/page-NNNN.png + manifest.json   ingest-schema raster archive
  order.json                              assemble-schema page sequence
  typeset-sarga-NN.pdf                    render (debug)
The pages then flow through the existing trim -> impose chain
(book-fascicle.toml profile).

Fonts: Lohit Devanagari (shaping via Pango — verified spike) + DejaVu
Serif for English; FONTCONFIG_FILE must point at a fontconfig that sees
them (the flake typeset devShell sets it declaratively).
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1

# --- 70s-mirror layout profile (pt; canvas = volume trim 444 x 667.44) ---
PAGE_W, PAGE_H = 444.0, 667.44
MARGIN_SIDE = 46.6          # 70s: 2cm on 19cm page (10.5%)
MARGIN_TOP = 53.4           # 70s: 2cm on 25cm (8%)
MARGIN_BOTTOM = 26.7        # 70s: 1cm on 25cm (4%)
CONTENT_W = PAGE_W - 2 * MARGIN_SIDE
VERSE_SIZE, VERSE_LEAD = 11.5, 18.0
TRANS_SIZE, TRANS_LEAD = 9.5, 12.8
HEAD_SIZE = 13.0
VERSE_CHUNK = 12            # verses per verse-block / translation alternation
DEVA_FONT = "Lohit Devanagari"
SERIF_FONT = "DejaVu Serif"

DEVA_DIGITS = "०१२३४५६७८९"


def to_devanagari_digits(n: int) -> str:
    return "".join(DEVA_DIGITS[int(d)] for d in str(n))


def verse_ref_devanagari(sarga: int, verse: int) -> str:
    """Printed verse-ref tail: ॥७.४२.१॥ (the site's ASCII refs dropped)."""
    return f"॥{to_devanagari_digits(sarga)}.{to_devanagari_digits(verse)}॥"


def clean_deva(text: str, sarga: int, verse: int) -> str:
    """Strip the site's ASCII verse-ref tail; append the printed-form ref."""
    t = re.sub(r"\s*[।॥\s]*7\.\d+\.\d+\s*[।॥\s]*$", "", text.strip())
    return f"{t} {verse_ref_devanagari(sarga, verse)}"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CSS = f"""
@page {{
    size: {PAGE_W}pt {PAGE_H}pt;
    margin: 0;
}}
@page content {{
    margin: {MARGIN_TOP}pt {MARGIN_SIDE}pt {MARGIN_BOTTOM}pt {MARGIN_SIDE}pt;
    @top-center {{
        content: "VĀLMĪKI-RĀMĀYAṆA  ·  " counter(page);
        font-family: "{SERIF_FONT}";
        font-size: 7.5pt;
        letter-spacing: 0.08em;
        color: #222;
    }}
}}
body {{ margin: 0; font-family: "{SERIF_FONT}"; }}
.fixed-page {{ page-break-after: always; }}
.flow-page {{ page: content; page-break-after: always; }}
.verse {{
    font-family: "{DEVA_FONT}";
    font-size: {VERSE_SIZE}pt;
    line-height: {VERSE_LEAD}pt;
    margin: 0 0 {VERSE_LEAD * 0.45}pt 0;
}}
.trans {{
    columns: 2;
    column-gap: {CONTENT_W * 0.055:.1f}pt;
    font-size: {TRANS_SIZE}pt;
    line-height: {TRANS_LEAD}pt;
    text-align: justify;
}}
.trans p {{
    margin: 0 0 {TRANS_LEAD * 0.42}pt 0;
    orphans: 2;
    widows: 2;
}}
.canto-head {{ text-align: center; margin: 0 0 16pt 0; }}
.canto-head .deva {{ font-family: "{DEVA_FONT}"; font-size: {HEAD_SIZE}pt; }}
.canto-head .lat {{
    font-size: {TRANS_SIZE}pt;
    letter-spacing: 0.14em;
    margin-top: 5pt;
}}
.title-page {{ text-align: center; }}
.title-page .deva-big {{ font-family: "{DEVA_FONT}"; font-size: 24pt; margin-top: 150pt; }}
.title-page .sub {{ font-size: 13pt; letter-spacing: 0.12em; margin-top: 26pt; }}
.title-page .note {{
    font-size: 8.5pt; line-height: 12.5pt; text-align: left;
    margin: 44pt 12pt 0 12pt; color: #222;
}}
.toc-row {{ font-size: 9pt; line-height: 14pt; }}
"""


def canto_heading(sarga: int) -> str:
    return (f'<div class="canto-head">'
            f'<div class="deva">॥ उत्तरकाण्डे सर्गः {to_devanagari_digits(sarga)} ॥</div>'
            f'<div class="lat">UTTARA-KĀṆḊA · SARGA {sarga}</div>'
            f'</div>')


def title_page_html(data: dict) -> str:
    n_verses = sum(len(v) for v in data.values())
    sargas = sorted(int(s) for s in data)
    editorial = (
        "Editorial note — on the sarga count. This fascicle completes the "
        "Uttara-kanda as printed in the Gita Press edition (sargas 42–111), "
        "following the traditional vulgate — the living, continuous text of "
        "the devotional tradition. Readers consulting modern critical editions "
        "(e.g. the Baroda critical edition of the Valmiki-Ramayana, vol. VII, "
        "U. P. Shah, 1975, which reconstructs a 100-sarga Uttara-kanda) will "
        "find sarga boundaries shifted and several passages — pronounced "
        "interpolations by those editors — renumbered, consolidated, or "
        "relegated to the apparatus. No text has been omitted here by design: "
        "what follows is the vulgate, continued without editorial pruning.")
    return f"""<div class="fixed-page"><div class="title-page">
  <div class="deva-big">श्रीमद्वाल्मीकिरामायण</div>
  <div class="sub">UTTARA-KĀṆḊA · SARGAS {sargas[0]}–{sargas[-1]}</div>
  <div class="sub" style="font-size:9.5pt; letter-spacing:0.05em;">
    {n_verses} verses · a fascicle completing the Gītā Press edition</div>
  <div class="note">{esc(editorial)}</div>
  <div class="note" style="margin-top:20pt; font-size:7.5pt; color:#444;">
    Text source: ramayana.info (Sanskrit with samhita and pada paths, IAST,
    English translation), cross-checked against the GRETIL Tokunaga/Smith
    e-text (sargas 42–100) and the Gītā Press scans. Typeset in Lohit
    Devanagari and DejaVu Serif.</div>
</div></div>"""


def toc_page_html(data: dict) -> str:
    rows = [f'<div class="toc-row">Sarga {s} — {len(data[str(s)])} verses</div>'
            for s in sorted(int(s) for s in data)]
    return (f'<div class="fixed-page" style="padding: {MARGIN_TOP}pt '
            f'{MARGIN_SIDE}pt {MARGIN_BOTTOM}pt {MARGIN_SIDE}pt;">'
            f'<div class="canto-head"><div class="lat">CONTENTS</div></div>'
            f'<div style="columns:2; column-gap:24pt;">{"".join(rows)}</div>'
            f'</div>')


def sarga_html(data: dict, sarga: int) -> str:
    verses = data[str(sarga)]
    nums = sorted(int(n) for n in verses)
    parts = [canto_heading(sarga)]
    for i in range(0, len(nums), VERSE_CHUNK):
        chunk = nums[i:i + VERSE_CHUNK]
        deva_lines = "".join(
            f'<div class="verse">'
            f'{esc(clean_deva(verses[str(n)]["text_devanagari"], sarga, n))}</div>'
            for n in chunk)
        parts.append(f'<div>{deva_lines}</div>')
        trans = "".join(
            f'<p>{esc(verses[str(n)]["translation"])} ({n})</p>' for n in chunk)
        parts.append(f'<div class="trans">{trans}</div>')
    return f'<div class="flow-page">{"".join(parts)}</div>'


def build_html(data: dict, sargas: list[int],
               with_front_matter: bool = True) -> str:
    pages = []
    if with_front_matter:
        pages.append(title_page_html(data))
        pages.append(toc_page_html(data))
    pages += [sarga_html(data, s) for s in sargas]
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{CSS}</style></head><body>{"".join(pages)}</body></html>')


def render_pdf(html: str, out_pdf: Path) -> None:
    from weasyprint import HTML  # lazy: heavy import
    HTML(string=html, base_url=".").write_pdf(str(out_pdf))


def rasterize(pdf: Path, out_dir: Path, dpi: int = 600) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi),
                    str(pdf), str(out_dir / "pg")],
                   check=True, capture_output=True)
    return sorted(out_dir.glob("pg-*.png"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_archive(pages_png: list[Path], out_dir: Path, dpi: int,
                  meta: dict) -> dict:
    """Move rendered pages into the ingest-schema archive + order.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, src in enumerate(sorted(pages_png), start=1):
        dst = out_dir / f"page-{i:04d}.png"
        src.replace(dst)
        entries.append({"page": i, "file": dst.name,
                        "sha256": sha256_file(dst),
                        "size_bytes": dst.stat().st_size})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": "ingest",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": dict(meta, typeset=True),
        "render": {"dpi": dpi, "format": "png", "color": False,
                   "tool": "weasyprint+pdftoppm"},
        "pages": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    order = {
        "schema_version": SCHEMA_VERSION,
        "stage": "assemble",
        "created_utc": manifest["created_utc"],
        "book": meta.get("book", ""),
        "archive": str(out_dir),
        "pages": [{"position": e["page"], "archive_page": e["page"],
                   "file": e["file"], "sha256": e["sha256"]}
                  for e in entries],
    }
    (out_dir.parent / "order.json").write_text(
        json.dumps(order, indent=2) + "\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path,
                    default=Path("dataset/uttara-eText-ramayana-info.json"))
    ap.add_argument("--out", type=Path, default=Path("build"))
    ap.add_argument("--sargas", default="42-111",
                    help="sarga range, e.g. 42-111 or a single 42 (fixture)")
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--no-front-matter", action="store_true",
                    help="skip title/ToC pages (fixture runs)")
    args = ap.parse_args(argv)

    m = re.match(r"^(\d+)(?:-(\d+))?$", args.sargas)
    if not m:
        raise SystemExit("--sargas: expect N or N-M")
    s_first, s_last = int(m.group(1)), int(m.group(2) or m.group(1))
    data = json.loads(args.data.read_text())
    sargas = [s for s in range(s_first, s_last + 1) if str(s) in data]
    if not sargas:
        raise SystemExit(f"no sargas {s_first}-{s_last} in {args.data}")

    html = build_html(data, sargas, with_front_matter=not args.no_front_matter)
    html_path = args.out / f"typeset-sarga-{s_first}.html"
    html_path.write_text(html)
    pdf_path = args.out / f"typeset-sarga-{s_first}.pdf"
    render_pdf(html, pdf_path)

    with tempfile.TemporaryDirectory() as tmp:
        pngs = rasterize(pdf_path, Path(tmp), dpi=args.dpi)
        meta = {"book": "Valmiki-Ramayana — Uttara-kanda fascicle (typeset)",
                "sargas": f"{s_first}-{s_last}",
                "text_source": "ramayana.info (dataset/uttara-eText-PROVENANCE.md)"}
        manifest = write_archive(pngs, args.out / "typeset", args.dpi, meta)
    print(f"typeset sargas {s_first}-{s_last}: {len(manifest['pages'])} pages "
          f"-> {args.out / 'typeset'} (manifest + order.json written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
