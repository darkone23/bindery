#!/usr/bin/env python3
"""fill_uttara_gaps — close the field gaps in the Uttara e-text dataset.

Three gap classes (HOL-259 plan rev 4, M4a):
- text_devanagari missing  -> reconstructed from text_devanagari_alt
  (the site's own alternate rendering; spacing normalized).
- transliteration missing  -> generated from the Devanagari text with the
  deterministic Devanagari->IAST charmap (fill_transliteration), marked
  "generated" in the QC report.
- translation missing      -> extracted from the Gita Press archive scans
  (the printed translation the fascicle continues): tesseract eng over the
  sarga's pages, verse located by its "( n )" / "( n - m )" marker.

Writes the filled dataset plus a QC report (dataset/uttara-eText-QC.md)
recording every fill and its source.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Devanagari -> IAST consonants (inherent 'a' added unless virama follows;
# matra vowels replace it) — GRETIL-compatible editorial style.
DEVA_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "ś",
    "ष": "ṣ", "स": "s", "ह": "h",
}
DEVA_MATRA = {
    "ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū",
    "ृ": "ṛ", "ॄ": "ṝ", "ॢ": "ḷ", "े": "e", "ै": "ai",
    "ो": "o", "ौ": "au",
}
DEVA_INDEP = {
    "अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū",
    "ऋ": "ṛ", "ॠ": "ṝ", "ऌ": "ḷ", "ए": "e", "ऐ": "ai",
    "ओ": "o", "औ": "au",
}
DEVA_SIGNS = {"ं": "ṃ", "ः": "ḥ", "ँ": "m̐", "ऽ": "'"}
DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
VIRAMA = "्"


def transliterate(deva: str) -> str:
    out = []
    i = 0
    while i < len(deva):
        ch = deva[i]
        if ch in DEVA_CONS:
            base = DEVA_CONS[ch]
            nxt = deva[i + 1] if i + 1 < len(deva) else ""
            if nxt == VIRAMA:
                out.append(base)
                i += 2
                continue
            if nxt in DEVA_MATRA:
                out.append(base + DEVA_MATRA[nxt])
                i += 2
                continue
            out.append(base + "a")
            i += 1
            continue
        if ch in DEVA_MATRA:
            out.append(DEVA_MATRA[ch])
            i += 1
            continue
        if ch in DEVA_INDEP:
            out.append(DEVA_INDEP[ch])
            i += 1
            continue
        if ch in DEVA_SIGNS:
            out.append(DEVA_SIGNS[ch])
            i += 1
            continue
        if ch == "।":
            out.append("|")
            i += 1
            continue
        if ch in ("॥", "\u0965"):
            out.append("||")
            i += 1
            continue
        if "\u0966" <= ch <= "\u096F":
            out.append(ch.translate(DEVA_DIGITS))
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def normalize_alt(alt: str) -> str:
    """The alt rendering joins words to dandas; restore standard spacing
    while keeping ।। pairs glued."""
    s = re.sub(r"\s+", " ", alt).strip()
    s = re.sub(r"([।॥])(?=[^\s।॥])", r"\1 ", s)
    s = re.sub(r"([^\s।॥])([।॥])", r"\1 \2", s)
    return re.sub(r" {2,}", " ", s).strip()


def ocr_pages(archive: Path, pages: list[int], dpi_hack: bool = False) -> str:
    """tesseract eng on the given archive pages; concatenated text."""
    chunks = []
    with tempfile.TemporaryDirectory() as td:
        for p in pages:
            src = archive / f"page-{p:04d}.png"
            if not src.is_file():
                continue
            txt = Path(td) / f"p{p}"
            subprocess.run(["tesseract", str(src), str(txt), "-l", "eng"],
                           check=True, capture_output=True)
            chunks.append((Path(str(txt) + ".txt")).read_text(errors="ignore"))
    return "\n".join(chunks)


MARKER = re.compile(r"\(\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*\)")
SARGA_END = re.compile(r"Thus ends Canto", re.I)
RUNNING_HEAD = re.compile(
    r"^\+?\s*(VALMIKI[\s.-]*RAMAYANA|UTTARAKANDA|[Vv]ālmīki.Rāmāyaṇa)\s*$", re.I)
PAGE_NO = re.compile(r"^\d{3,4}$")
# words frequent in the Gita Press translation register; used only to tell
# real English lines from Devanagari-mangled OCR gibberish
COMMON = {
    "the", "and", "of", "to", "in", "a", "is", "was", "his", "her", "he",
    "she", "they", "with", "who", "that", "then", "when", "what", "this",
    "on", "for", "at", "by", "from", "not", "all", "but", "be", "so", "no",
    "son", "king", "said", "ask", "sage", "rama", "sita", "valmiki",
    "thus", "having", "having", "there", "their", "them", "you", "your",
    "shall", "will", "have", "had", "were", "are", "as", "it", "its",
}


def _junk(line: str) -> bool:
    if RUNNING_HEAD.match(line) or PAGE_NO.match(line):
        return True
    words = [w for w in re.findall(r"[A-Za-z']+", line.lower()) if len(w) >= 3]
    return not any(w in COMMON for w in words)


def to_roman(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, sym in vals:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def english_lines(text: str) -> list[str]:
    """OCR lines that look like printed English (drop Devanagari junk);
    bare verse-marker lines are always kept. Running heads/page numbers
    are dropped outright."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or RUNNING_HEAD.match(line) or PAGE_NO.match(line):
            continue
        if MARKER.search(line):
            out.append(line)
            continue
        ascii_chars = sum(1 for c in line if c.isascii() and c.isalpha())
        if len(line) >= 3 and ascii_chars / max(1, len(line)) > 0.6:
            out.append(line)
    return out


def sarga_translation_flow(ocr_text: str, sarga: int) -> str:
    """English lines of one sarga's translation flow: slice between the
    sarga's own "Canto <roman>" heading and its "Thus ends" close, drop
    Devanagari junk lines."""
    roman = to_roman(sarga)
    head = re.search(rf"Canto\s+{roman}\b", ocr_text)
    start = head.end() if head else 0
    end_m = SARGA_END.search(ocr_text, start)
    end = end_m.start() if end_m else len(ocr_text)
    return "\n".join(english_lines(ocr_text[start:end]))


def extract_translation(ocr_text: str, verse: int, sarga: int | None = None):
    """Find the translation block for `verse` in Gita Press OCR output.

    Printed markers CLOSE their block: "...in sequence. (16)". The verse's
    English paragraph is the English text between the previous marker and
    this one. Handles single "( n )" and range "( n - m )" / "( n — m )"
    markers (ASCII hyphen, en/em dash). Returns (text, marker) or (None, None).
    """
    flow = (sarga_translation_flow(ocr_text, sarga) if sarga
            else "\n".join(english_lines(ocr_text)))
    marks = [(m, int(m.group(1)), int(m.group(2) or m.group(1)))
             for m in MARKER.finditer(flow)]
    for i, (m, lo, hi) in enumerate(marks):
        if not (lo <= verse <= hi):
            continue
        start = marks[i - 1][0].end() if i > 0 else 0
        lines = [l for l in flow[start:m.start()].splitlines() if l.strip()]
        while lines and _junk(lines[0].strip()):
            lines = lines[1:]  # leading Devanagari-mangled gibberish
        block = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if len(block) > 20:
            return block, f"({lo}-{hi})" if hi != lo else f"({lo})"
    return None, None


def fill_gaps(data: dict, sarga_pages: dict, archive: Path, report: list):
    gaps = []
    for sarga, verses in sorted(data.items(), key=lambda kv: int(kv[0])):
        todo = [n for n, f in verses.items()
                if not f.get("text_devanagari") or not f.get("transliteration")
                or not f.get("translation")]
        if not todo:
            continue
        pages = sarga_pages.get("sargas", {}).get(sarga)
        ocr = None
        need_ocr = any(not verses[n].get("translation") for n in todo)
        if need_ocr and pages:
            span = list(range(int(pages["start_page"]) - 1,
                              int(pages["end_page"]) + 2))
            ocr = ocr_pages(archive, span)
        for n in todo:
            f = verses[n]
            # 1. devanagari from the alt rendering
            if not f.get("text_devanagari") and f.get("text_devanagari_alt"):
                f["text_devanagari"] = normalize_alt(f["text_devanagari_alt"])
                report.append((sarga, n, "text_devanagari", "alt-reconstruction"))
            # 2. transliteration from the Devanagari
            if not f.get("transliteration") and f.get("text_devanagari"):
                f["transliteration"] = transliterate(f["text_devanagari"])
                report.append((sarga, n, "transliteration", "generated-from-deva"))
            # 3. translation from the printed Gita Press scan
            if not f.get("translation") and ocr is not None:
                text, marker = extract_translation(ocr, int(n), int(sarga))
                if text:
                    f["translation"] = text
                    report.append((sarga, n, "translation", f"scan-ocr {marker}"))
                else:
                    report.append((sarga, n, "translation", "MISSING-after-fill"))
            gaps.append((sarga, n))
    return gaps


QC_HEADER = """# Uttara e-text QC report

Generated by fill_uttara_gaps.py. Every field fill is recorded with its
source; "generated-from-deva" transliterations and "scan-ocr" translations
need a read-through at typesetting time (they are few — see counts).
"""


def write_report(path: Path, report: list, data: dict):
    lines = [QC_HEADER, ""]
    kinds = {}
    for _, _, field, src in report:
        kinds.setdefault((field, src.split()[0]), 0)
        kinds[(field, src.split()[0])] += 1
    lines.append("## Fill summary")
    lines.append("")
    for (field, src), count in sorted(kinds.items()):
        lines.append(f"- **{field}** via {src}: {count}")
    remaining = [(s, n) for s, vv in data.items() for n, f in vv.items()
                 if not (f.get("text_devanagari") and f.get("transliteration")
                         and f.get("translation"))]
    lines.append(f"- verses still incomplete after fill: {len(remaining)}"
                 + (f" — {remaining[:10]}" if remaining else ""))
    lines.append("")
    lines.append("## Fills")
    lines.append("")
    lines += [f"- sarga {s} verse {n}: {field} <- {src}" for s, n, field, src in report]
    path.write_text("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path,
                    default=Path("dataset/uttara-eText-ramayana-info.json"))
    ap.add_argument("--sarga-pages", type=Path,
                    default=Path("dataset/uttara-sarga-pages.json"))
    ap.add_argument("--archive", type=Path, default=Path("archive"))
    ap.add_argument("--report", type=Path, default=Path("dataset/uttara-eText-QC.md"))
    args = ap.parse_args(argv)

    data = json.loads(args.data.read_text())
    pages = json.loads(args.sarga_pages.read_text()) if args.sarga_pages.is_file() else {}
    report: list = []
    fill_gaps(data, pages, args.archive, report)
    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    write_report(args.report, report, data)
    incomplete = sum(1 for vv in data.values() for f in vv.values()
                     if not (f.get("text_devanagari") and f.get("transliteration")
                             and f.get("translation")))
    print(f"{len(report)} fills applied; {incomplete} verses still incomplete; "
          f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
