#!/usr/bin/env python3
"""bindery-structure — M2 structure stage.

Layout-parses the archival page rasters (docling 2.118.0 layout pass +
tesseract eng full-page OCR pass) and derives, boundaries-only, a
per-page structure record: Devanagari block vs English column,
verse-number runs, canto/sarga headings, kanda tokens, OCR confidence
and image-quality stats. From the per-page records it builds:

  build/structure/records/page-NNNN.json   per-page structure record
  build/structure/sarga-map.json           kanda/sarga -> archive page ranges
  build/structure/toc-draft.md             book/canto table with archive refs
  build/structure/fidelity-report.md       OCR-confidence + blur/skew flags

Design: Paperclip HOL-250 plan rev 1, milestone M2 (issue HOL-255).
Boundaries only — no verbatim retype. The heavy deps (docling, torch,
tesseract) are confined to this stage; import them lazily so the pure
flake (`nix build`, plain pytest) never needs them. The structure shell
is the only nix environment allowed to be impure/unfree.

Passes are resumable: `pages` skips per-page outputs that already
exist, `map` rebuilds artifacts from the raw pass outputs on disk.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCHEMA_VERSION = 1

# Canonical kanda list (Valmiki Ramayana); sarga counts are expectation
# only — the edition itself is authoritative and deviations get flagged.
KANDAS = [
    (1, "Bala", "Book One"),
    (2, "Ayodhya", "Book Two"),
    (3, "Aranya", "Book Three"),
    (4, "Kishkindha", "Book Four"),
    (5, "Sundara", "Book Five"),
    (6, "Yuddha", "Book Six"),
    (7, "Uttara", "Book Seven"),
]
EXPECTED_SARGA_COUNTS = {1: 77, 2: 119, 3: 75, 4: 67, 5: 68, 6: 128, 7: 111}

ROMAN_VALUES = [("C", 100), ("L", 50), ("X", 10), ("V", 5), ("I", 1)]
ROMAN_MAP = dict(ROMAN_VALUES)
CANTO_HEADING_RE = re.compile(r"^cant[o0]\s*\.?\s*([ivxlc|l10]+)[.,]?\s*$", re.IGNORECASE)
CANTO_END_RE = re.compile(r"thus\s+ends\s+canto\s+", re.IGNORECASE)
KANDA_END_RE = re.compile(r"end\s+of\s+[a-z]*kand", re.IGNORECASE)
KANDA_NAME_RE = re.compile(r"\((bala|ayodhya|aranya|kishkindha|sundara|yuddha|uttara)kand", re.IGNORECASE)
BOOK_TOKEN_RE = re.compile(r"\[?book\s+(one|two|three|four|five|six|seven)\]?", re.IGNORECASE)
VERSE_NUM_RE = re.compile(r"^\((\d{1,3})\)$")
HEADER_KANDA_RE = re.compile(
    r"\b(BALA|AYODHYA|ARANYA|KISHKINDH|SUNDARA|YUDDHA|UTTARA)")
HEADER_VALMIKI_RE = re.compile(r"VALMIKI", re.IGNORECASE)
TOC_ENTRY_NUM_RE = re.compile(r"^\s{0,8}(\d{1,3})\.\s")
TOC_PAGE_REF_RE = re.compile(r"[.\s·…]{3,}\s*(\d{1,4})\s*$")

ENGLISH_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                    " ,.;:!?'\"()[]-–—&/")

BLUR_FLAG_THRESHOLD = 35.0   # Laplacian variance on 1200px gray; vector pages sit far above
SKEW_FLAG_DEG = 0.75
OCR_CONF_FLAG = 0.55


def roman_to_int(s: str) -> int:
    total = prev = 0
    for ch in reversed(s.upper()):
        val = ROMAN_MAP[ch]
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total


def int_to_roman(n: int) -> str:
    out = []
    for sym, val in ROMAN_VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def roman_multiset(s: str) -> str:
    return "".join(sorted(s.upper()))


def normalize_canto_numeral(tok: str) -> str:
    """Fix common tesseract misreads of large-font roman numerals
    (thin strokes read as 1/|/l, e.g. 'Canto II' -> 'Canto 11')."""
    return (tok.replace("|", "I").replace("l", "I").replace("!", "I")
            .replace("1", "I").upper())


def is_english_word(text: str) -> bool:
    """True if a tesseract word looks like clean Latin text (not Devanagari
    mojibake, which surfaces as symbol soup or IAST-laden caps)."""
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) <= 1 and stripped not in "aAI":
        return False
    clean = sum(c in ENGLISH_CHARS for c in stripped)
    return clean / len(stripped) >= 0.95


# ---------------------------------------------------------------------------
# Derivation: raw pass outputs -> per-page structure record
# ---------------------------------------------------------------------------

def items_topdown(items: list[dict], w: float, h: float) -> list[dict]:
    """docling stores pixel bboxes y-up (bottom-left origin); normalize to
    top-down fractions in both axes."""
    out = []
    for i, it in enumerate(items):
        l, t, r, b = it["bbox"]
        y_top = 1.0 - t / h
        y_bot = 1.0 - b / h
        if y_bot < y_top:
            y_top, y_bot = y_bot, y_top
        out.append({"_i": i, "label": it["label"],
                    "bbox": [l / w, y_top, r / w, y_bot]})
    return out


def assign_words_to_items(words: list[dict], items: list[dict]) -> None:
    """Tag each word with the docling item that contains it (smallest wins)."""
    for w in words:
        w["_item"] = None
        cx, cy = (w["l"] + w["r"]) / 2.0, (w["t"] + w["b"]) / 2.0
        best, best_area = None, None
        for it in items:
            il, it_, ir, ib = it["bbox"]
            if il - 0.005 <= cx <= ir + 0.005 and it_ - 0.005 <= cy <= ib + 0.005:
                area = max(0.0, ir - il) * max(0.0, ib - it_)
                if best is None or area < best_area:
                    best, best_area = it, area
        if best is not None:
            w["_item"] = best["_i"]


def _label_hist(items: list[dict]) -> dict:
    hist: dict = {}
    for it in items:
        hist[it["label"]] = hist.get(it["label"], 0) + 1
    return hist


def _union(ws: list[dict]) -> list[float] | None:
    if not ws:
        return None
    return [round(min(w["l"] for w in ws), 4), round(min(w["t"] for w in ws), 4),
            round(max(w["r"] for w in ws), 4), round(max(w["b"] for w in ws), 4)]


def derive_record(page: int, layout: dict, ocr: dict) -> dict:
    """Combine one layout pass output and one OCR pass output into the
    per-page structure record (deliverable 1 of M2)."""
    w_px, h_px = ocr["size_px"]
    items = items_topdown(layout["items"], w_px, h_px)
    words = [
        {
            "text": w["text"],
            "conf": w["conf"],
            "l": w["l"] / w_px,
            "r": w["r"] / w_px,
            "t": w["t"] / h_px,
            "b": w["b"] / h_px,
        }
        for w in ocr["words"]
    ]
    assign_words_to_items(words, items)

    header_zone = 0.065
    footer_zone = 0.955

    def in_body(w):
        return w["t"] > header_zone and w["b"] < footer_zone

    body_words = [w for w in words if in_body(w)]

    # Per-item script classification. Tesseract(eng) renders the custom-
    # encoded Devanagari verse lines as low-confidence ASCII garbage, so
    # item mean word confidence separates the Devanagari blocks (~0-40)
    # from the English column (~85-95) far more reliably than charset.
    item_words: dict = {}
    for w in body_words:
        if w["_item"] is not None:
            item_words.setdefault(w["_item"], []).append(w)
    english_items = set()
    for i, ws in item_words.items():
        confs = [w["conf"] for w in ws if w["conf"] >= 0]
        mean_conf = sum(confs) / len(confs) if confs else 0.0
        if mean_conf >= 60.0 and any(is_english_word(w["text"]) for w in ws):
            english_items.add(i)
    english_words = [
        w for w in body_words
        if (w["_item"] is None or w["_item"] in english_items)
        and w["conf"] >= 50 and is_english_word(w["text"])
    ]
    deva_words = [
        w for w in body_words
        if w["_item"] is not None and w["_item"] not in english_items
    ]

    # header token + printed page number (top strip)
    head = [w for w in words if w["b"] <= header_zone]
    head_text = " ".join(w["text"] for w in head)
    head_text = unicodedata.normalize("NFD", head_text)
    head_text = "".join(c for c in head_text if not unicodedata.combining(c))
    head_norm = re.sub(r"[^A-Za-z ]", "", head_text).upper()
    m = HEADER_KANDA_RE.search(head_norm)
    header_kanda = m.group(1).lower() if m else None
    if header_kanda is None and HEADER_VALMIKI_RE.search(head_norm):
        header_kanda = "ramayana"
    printed_page = None
    digit_words = [w for w in head
                   if w["text"].isdigit() and len(w["text"]) <= 4 and w["conf"] >= 60]
    if digit_words:
        printed_page = int(max(digit_words, key=lambda w: w["l"])["text"])

    # canto heading: standalone line "Canto <roman>" (large-font line)
    canto_heading = None
    for line in ocr["lines"]:
        norm = line["text"].strip()
        m = CANTO_HEADING_RE.match(norm)
        if m:
            canto_heading = {
                "numeral": normalize_canto_numeral(m.group(1)),
                "text": norm,
                "t": round(line["t"] / h_px, 4),
            }
            break

    canto_end = None
    kanda_end_marker = None
    for line in ocr["lines"]:
        txt = line["text"].strip()
        if canto_end is None and CANTO_END_RE.search(txt):
            canto_end = txt[:120]
        if kanda_end_marker is None and KANDA_END_RE.search(txt):
            kanda_end_marker = txt[:120]

    title_book_token = None
    kanda_title = None
    for line in ocr["lines"]:
        m = BOOK_TOKEN_RE.search(line["text"])
        if m and title_book_token is None:
            title_book_token = m.group(1).lower()
        m2 = KANDA_NAME_RE.search(line["text"])
        if m2 and kanda_title is None:
            kanda_title = m2.group(1).lower()

    # verse-number runs: "(N)" words, normal body height, decent confidence
    heights = sorted(w["b"] - w["t"] for w in body_words if w["text"].strip())
    med_h = heights[len(heights) // 2] if heights else 0.0
    verse_numbers = []
    for w in body_words:
        m = VERSE_NUM_RE.match(w["text"].strip())
        if m and w["conf"] >= 25 and (w["b"] - w["t"]) <= max(0.02, med_h * 2.2):
            verse_numbers.append(int(m.group(1)))
    verse_numbers = sorted(set(verse_numbers))

    conf_vals = [w["conf"] for w in words if w["conf"] >= 0]
    mean_conf = round(sum(conf_vals) / len(conf_vals) / 100.0, 4) if conf_vals else None

    return {
        "page": page,
        "file": ocr["file"],
        "size_px": [w_px, h_px],
        "docling": {
            "layout_score": layout.get("layout_score"),
            "n_items": len(items),
            "labels": _label_hist(items),
        },
        "ocr": {
            "engine": ocr["engine"],
            "lang": ocr["lang"],
            "mean_word_conf": mean_conf,
            "n_words": len(words),
        },
        "image_stats": ocr.get("image_stats"),
        "derived": {
            "header_kanda": header_kanda,
            "printed_page": printed_page,
            "canto_heading": canto_heading,
            "canto_end": canto_end,
            "kanda_end_marker": kanda_end_marker,
            "title_book_token": title_book_token,
            "kanda_title": kanda_title,
            "verse_numbers": verse_numbers,
            "english_bbox": _union(english_words),
            "devanagari_bbox": _union(deva_words),
            "english_word_count": len(english_words),
            "devanagari_word_count": len(deva_words),
        },
    }


# ---------------------------------------------------------------------------
# Map / ToC / fidelity builders (pure)
# ---------------------------------------------------------------------------

def build_sarga_map(records: list[dict], first_page: int, last_page: int) -> dict:
    """Per-page records -> kanda/sarga page ranges (deliverable 2).

    Kanda starts are the "Canto I" heading pages (each kanda opens with
    Canto I; cross-checked against "(<name>kanda)" + "[Book <n>]" title
    tokens). Sarga boundaries are the "Canto <roman>" heading pages,
    aligned to the expected 1..N sequence with tolerance for misprints:
    transposed roman numerals are recorded and flagged, not silently
    corrected. Kanda ends use the "END OF <name>KANDA" marker when the
    edition prints one, else the page before the next kanda's start.
    """
    headings = []  # (page, numeral_str, value)
    for r in records:
        ch = r["derived"]["canto_heading"]
        if ch:
            headings.append((r["page"], ch["numeral"], roman_to_int(ch["numeral"])))
    headings.sort()

    kanda_starts = [pg for pg, num, val in headings if val == 1]
    notes = []
    if not kanda_starts:
        notes.append("no Canto I heading found — partial slice?")

    kandas = []
    all_flags = []
    used_knos = set()
    for idx, start in enumerate(kanda_starts):
        next_start = kanda_starts[idx + 1] if idx + 1 < len(kanda_starts) else None
        end = (next_start - 1) if next_start else last_page
        span_records = [r for r in records if start <= r["page"] <= end]
        for r in reversed(span_records):
            if r["derived"]["kanda_end_marker"]:
                end = r["page"]
                break
        # Identify the kanda from title tokens on its pages ("[Book N]" /
        # "(<name>kanda)" title-page lines); fall back to the run order.
        kno = None
        for r in span_records:
            d = r["derived"]
            if d["title_book_token"]:
                for n, _, book in KANDAS:
                    if book.split()[-1].lower() == d["title_book_token"]:
                        kno = n
                        break
            if kno is None and d["kanda_title"]:
                for n, name, _ in KANDAS:
                    if name.lower() == d["kanda_title"]:
                        kno = n
                        break
            if kno is not None:
                break
        if kno is None or kno in used_knos:
            kno = idx + 1
        used_knos.add(kno)
        kname, kbook = next((name, book) for n, name, book in KANDAS if n == kno)

        kheadings = [(pg, num, val) for pg, num, val in headings if start <= pg <= end]
        sargas = []
        flags_k = []
        expected = 1
        title_ok = any(
            r["derived"]["title_book_token"] == kbook.split()[-1].lower()
            or r["derived"]["kanda_title"] == kname.lower()
            for r in span_records)
        if not title_ok:
            flags_k.append({"page": start, "kind": "title_token_missing",
                            "detail": f"no '{kbook}'/'({kname.lower()}kanda' token in span"})
        for pg, num, val in kheadings:
            if val == expected:
                pass
            elif roman_multiset(num) == roman_multiset(int_to_roman(expected)):
                flags_k.append({"page": pg, "kind": "numeral_transposition",
                                "detail": f"printed '{num}' where sequence expects "
                                          f"{int_to_roman(expected)}"})
            elif val == expected + 1:
                flags_k.append({"page": pg, "kind": "missing_heading",
                                "detail": f"no heading for {int_to_roman(expected)}; "
                                          f"range shares the start of {int_to_roman(expected + 1)}"})
                sargas.append({"sarga": expected, "start_page": pg, "end_page": pg,
                               "heading_page": None, "printed_numeral": None,
                               "flags": ["missing_heading"]})
                expected += 1
            elif val < expected:
                continue  # stray repeat of an earlier heading
            else:
                flags_k.append({"page": pg, "kind": "sequence_gap",
                                "detail": f"heading {num} found while expecting "
                                          f"{int_to_roman(expected)}"})
                expected = val
            sargas.append({"sarga": expected, "start_page": pg, "end_page": None,
                           "heading_page": pg, "printed_numeral": num, "flags": []})
            expected += 1
        for i, s in enumerate(sargas):
            if s["end_page"] is None:
                s["end_page"] = (sargas[i + 1]["start_page"] - 1) if i + 1 < len(sargas) else end
        kandas.append({
            "kanda": kno, "name": kname, "book_token": kbook,
            "title_tokens_found": title_ok,
            "start_page": start, "end_page": end,
            "sarga_count": len(sargas),
            "expected_sarga_count": EXPECTED_SARGA_COUNTS.get(kno),
            "sargas": sargas,
            "flags": flags_k,
        })
        all_flags.extend(flags_k)

    # interstitial (non-body) blocks: front matter, part divisions, ToC runs
    body_pages = set()
    for k in kandas:
        body_pages.update(range(k["start_page"], k["end_page"] + 1))
    blocks = []
    run = None
    for pg in range(first_page, last_page + 1):
        if pg in body_pages:
            if run:
                blocks.append(run)
                run = None
        elif run is None:
            run = {"start_page": pg, "end_page": pg}
        else:
            run["end_page"] = pg
    if run:
        blocks.append(run)

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "structure",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "span": {"first": first_page, "last": last_page},
        "kandas": kandas,
        "interstitial_blocks": blocks,
        "notes": notes,
        "flags": all_flags,
    }


def build_toc_draft(smap: dict) -> str:
    """Book/canto table with archive page refs (deliverable 3)."""
    lines = [
        "# ToC draft — Valmiki-Ramayana (Gita Press, source B)",
        "",
        "Archive page refs are the 600 dpi rendered pages (`archive/page-NNNN.png`).",
        f"Coverage: archive pages {smap['span']['first']}–{smap['span']['last']}.",
        "",
    ]
    for b in smap.get("interstitial_blocks", []):
        lines.append(f"- front matter / part division: pages {b['start_page']}–{b['end_page']}")
    if smap.get("interstitial_blocks"):
        lines.append("")
    for k in smap["kandas"]:
        lines.append(
            f"## {k['book_token']} — {k['name']} Kanda "
            f"(archive pages {k['start_page']}–{k['end_page']}, {k['sarga_count']} sargas)")
        lines.append("")
        lines.append("| Sarga | Archive pages | Heading page | Notes |")
        lines.append("|---|---|---|---|")
        for s in k["sargas"]:
            notes = "; ".join(s["flags"]) if s["flags"] else ""
            hp = s["heading_page"] if s["heading_page"] is not None else "—"
            lines.append(f"| {s['sarga']} | {s['start_page']}–{s['end_page']} | {hp} | {notes} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def build_fidelity_report(records: list[dict], smap: dict,
                          spot_checks: list[dict] | None = None) -> str:
    """OCR-confidence + image-stat flags (deliverable 4)."""
    flagged = []
    for r in records:
        d = r["derived"]
        tags = []
        st = r.get("image_stats") or {}
        if st.get("blur_lapvar") is not None and st["blur_lapvar"] < BLUR_FLAG_THRESHOLD:
            tags.append(f"blur (lapvar {st['blur_lapvar']:.1f})")
        if st.get("skew_deg") is not None and abs(st["skew_deg"]) > SKEW_FLAG_DEG:
            tags.append(f"askew ({st['skew_deg']:+.2f} deg)")
        mc = r["ocr"]["mean_word_conf"]
        if mc is not None and mc < OCR_CONF_FLAG:
            tags.append(f"low OCR conf ({mc:.2f})")
        if d["english_word_count"] < 5:
            tags.append("no English text (plate/blank/title?)")
        if tags:
            flagged.append((r["page"], tags))

    lines = [
        "# Fidelity report — bindery M2 structure pass (source B)",
        "",
        f"Pages analyzed: {len(records)} (archive {smap['span']['first']}–{smap['span']['last']}).",
        "",
        "## Boundary confidence",
        "",
    ]
    for k in smap["kandas"]:
        exp, got = k["expected_sarga_count"], k["sarga_count"]
        status = "OK" if exp is None or exp == got else f"MISMATCH (expected {exp})"
        lines.append(f"- kanda {k['kanda']} {k['name']}: {got} sargas "
                     f"[pages {k['start_page']}–{k['end_page']}] — {status}")
        for f in k["flags"]:
            lines.append(f"  - flag: {f['kind']} on page {f['page']}: {f['detail']}")
    lines += ["", "## Flagged pages", ""]
    if flagged:
        for pg, tags in flagged:
            lines.append(f"- page {pg}: {', '.join(tags)}")
    else:
        lines.append("- none")

    confs = [r["ocr"]["mean_word_conf"] for r in records if r["ocr"]["mean_word_conf"] is not None]
    blurs = [r["image_stats"]["blur_lapvar"] for r in records
             if r.get("image_stats") and r["image_stats"].get("blur_lapvar") is not None]
    skews = [abs(r["image_stats"]["skew_deg"]) for r in records
             if r.get("image_stats") and r["image_stats"].get("skew_deg") is not None]
    lines += ["", "## Distributions", ""]
    if confs:
        lines.append(f"- OCR mean word confidence: min {min(confs):.2f}, "
                     f"median {sorted(confs)[len(confs) // 2]:.2f}, max {max(confs):.2f}")
    if blurs:
        lines.append(f"- blur (Laplacian variance, 1200px gray): min {min(blurs):.1f}, "
                     f"median {sorted(blurs)[len(blurs) // 2]:.1f}, max {max(blurs):.1f} "
                     f"(flag threshold {BLUR_FLAG_THRESHOLD})")
    if skews:
        lines.append(f"- |skew| (deg): max {max(skews):.2f} (flag threshold {SKEW_FLAG_DEG})")
    lines += ["", "## Vector-vs-scan sanity", "",
              "Source B is a vector-body PDF rendered at 600 dpi, so every body page",
              f"should sit well above the blur flag ({BLUR_FLAG_THRESHOLD}) and near 0 deg skew.",
              "Scanned pages (source A, M4) are the ones expected to trip these flags."]
    if spot_checks:
        lines += ["", "## ToC spot-check (draft vs printed ToC, OCR'd from the archive)", "",
                  "| Boundary | Printed ToC ref | Detected archive page | Verdict |",
                  "|---|---|---|---|"]
        for sc in spot_checks:
            lines.append(f"| {sc['label']} | {sc['toc_ref']} | {sc['detected_page']} | {sc['verdict']} |")
        mismatched = [sc for sc in spot_checks if not sc["ok"]]
        lines += ["", f"Mismatches: {len(mismatched)}" + ("" if mismatched else " (none)")]
    return "\n".join(lines) + "\n"


def parse_toc_entries(records: list[dict], raw_lines_by_page: dict[int, list[dict]]) -> list[dict]:
    """Extract printed-ToC entries "N. summary ... page" from OCR'd ToC pages.

    An entry's canto number leads its first line; the page ref trails the
    final line after a dot leader. Pages are kept only when they yield at
    least three entries (i.e. they really are ToC pages).
    """
    per_page = []
    for r in sorted(records, key=lambda r: r["page"]):
        p = r["page"]
        d = r["derived"]
        is_body = bool(d["canto_heading"] or d["title_book_token"] or d["kanda_title"])
        entries = []
        open_num = None
        for ln in raw_lines_by_page.get(p, []):
            txt = ln["text"].strip()
            if not txt:
                continue
            mnum = TOC_ENTRY_NUM_RE.match(txt)
            if mnum:
                open_num = int(mnum.group(1))
            mref = TOC_PAGE_REF_RE.search(txt)
            if mref and open_num is not None:
                entries.append({"canto": open_num, "printed_page": int(mref.group(1))})
                open_num = None
        per_page.append((p, entries, is_body))
    final = []
    last_book = None
    for p, entries, is_body in per_page:
        for ln in raw_lines_by_page.get(p, []):
            m = BOOK_TOKEN_RE.search(ln["text"])
            if m:
                last_book = m.group(1).lower()
        # A page counts as a ToC page when it yields several dotted
        # entries, or sparse entries and none of the body-page markers.
        if entries and not is_body and (len(entries) >= 3 or last_book):
            for e in entries:
                e["book"] = last_book
            final.extend(entries)
    return final


def write_spot_checks(out_dir: Path, smap: dict, records: list[dict],
                      raw_lines_by_page: dict[int, list[dict]]) -> list[dict]:
    """Spot-check the draft against the printed ToC OCR'd from the archive.

    Part I printed page numbers equal archive pages; Part II restarts its
    numbering, so for kandas 5-7 the archive-minus-printed OFFSET is
    compared for constancy instead of equality.
    """
    toc_entries = parse_toc_entries(records, raw_lines_by_page)
    checks = []
    wanted = [(1, 1), (1, 2), (1, 3), (2, 1), (4, 1), (5, 1), (7, 1), (7, 42)]
    for kno, sno in wanted:
        if kno > len(smap["kandas"]):
            continue
        k = smap["kandas"][kno - 1]
        s = next((s for s in k["sargas"] if s["sarga"] == sno), None)
        if s is None:
            continue
        book_word = k["book_token"].split()[-1].lower()
        toc = next((e for e in toc_entries
                    if e["book"] == book_word and e["canto"] == sno), None)
        if toc is None:
            checks.append({"label": f"bk{kno} c{sno}", "toc_ref": "not parsed",
                           "detected_page": s["start_page"], "ok": False,
                           "verdict": "no printed ToC entry parsed for this boundary"})
            continue
        offset = s["start_page"] - toc["printed_page"]
        if kno <= 4:
            ok = offset == 0
            verdict = "match" if ok else f"offset {offset} (Part I printed pages should equal archive pages)"
        else:
            ok = True  # Part II: offset constancy is validated below
            verdict = f"offset {offset} (Part II restarts printed numbering)"
        checks.append({"label": f"bk{kno} c{sno}", "toc_ref": toc["printed_page"],
                       "detected_page": s["start_page"], "ok": ok,
                       "verdict": verdict, "offset": offset})
    part2 = [c for c in checks if c.get("offset") is not None
             and c["label"].startswith(("bk5", "bk6", "bk7"))]
    if len(part2) >= 2:
        offs = {c["offset"] for c in part2}
        if len(offs) > 1:
            for c in part2:
                c["ok"] = False
                c["verdict"] = f"inconsistent Part II offsets: {sorted(offs)}"
    return checks


# ---------------------------------------------------------------------------
# Pass A: docling layout
# ---------------------------------------------------------------------------

def docling_layout_pass(archive: Path, out_dir: Path, pages: list[int],
                        chunk: int = 32) -> None:
    """docling layout-only pass over rendered pages (lazy heavy imports).

    OCR stays off: with `layout_options.keep_empty_clusters` the docling
    layout model still emits the block tree (TEXT/SECTION_HEADER/FOOTNOTE
    items with bboxes), which is what the Devanagari-vs-English
    classification fuses against. TORCHDYNAMO_DISABLE avoids a ~10x
    slowdown from dynamo compile checks inside transformers.
    """
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    import torch
    torch._dynamo.config.disable = True
    from docling.document_converter import DocumentConverter, ImageFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat

    rec_dir = out_dir / "pages"
    rec_dir.mkdir(parents=True, exist_ok=True)
    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.do_table_structure = False
    opts.generate_page_images = False
    opts.generate_picture_images = False
    opts.layout_options.keep_empty_clusters = True
    opts.accelerator_options = AcceleratorOptions(num_threads=4, device="cpu")
    conv = DocumentConverter(
        allowed_formats=[InputFormat.IMAGE],
        format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=opts)},
    )

    todo = [p for p in pages if not (rec_dir / f"page-{p:04d}.layout.json").is_file()]
    print(f"[layout] {len(todo)}/{len(pages)} pages to parse", flush=True)
    n_chunks = (len(todo) + chunk - 1) // chunk
    for i in range(0, len(todo), chunk):
        batch = todo[i:i + chunk]
        t0 = dt.datetime.now()
        results = conv.convert_all([archive / f"page-{p:04d}.png" for p in batch])
        for p, res in zip(batch, results):
            if res.status.name != "SUCCESS":
                raise RuntimeError(f"docling failed on page {p}: {res.errors}")
            doc = res.document
            page = doc.pages[1]
            items = []
            for item, _ in doc.iterate_items():
                prov = item.prov[0] if item.prov else None
                if prov is None:
                    continue
                bb = prov.bbox
                items.append({"label": item.label.name,
                              "bbox": [round(bb.l, 2), round(bb.t, 2),
                                       round(bb.r, 2), round(bb.b, 2)]})
            layout_score = None
            if res.confidence is not None:
                ls = res.confidence.layout_score
                if ls == ls:  # not NaN
                    layout_score = round(float(ls), 4)
            (rec_dir / f"page-{p:04d}.layout.json").write_text(json.dumps({
                "page": p,
                "file": f"page-{p:04d}.png",
                "size_px": [round(page.size.width), round(page.size.height)],
                "layout_score": layout_score,
                "items": items,
            }, separators=(",", ":")) + "\n")
        dt_s = (dt.datetime.now() - t0).total_seconds()
        print(f"[layout] chunk {i // chunk + 1}/{n_chunks}: {len(batch)} pages "
              f"in {dt_s:.0f}s ({dt_s / len(batch):.1f}s/page)", flush=True)


# ---------------------------------------------------------------------------
# Pass B: tesseract full-page OCR + image stats
# ---------------------------------------------------------------------------

def _ocr_one(args):
    archive_s, page, rec_dir_s, lang = args
    import numpy as np
    from PIL import Image

    rec_dir = Path(rec_dir_s)
    out_json = rec_dir / f"page-{page:04d}.ocr.json"
    if out_json.is_file():
        return page, "cached"
    png = Path(archive_s) / f"page-{page:04d}.png"
    tmp_dir = rec_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    base = tmp_dir / f"p{page:04d}"
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    proc = subprocess.run(
        ["tesseract", str(png), str(base), "-l", lang, "--psm", "3", "tsv"],
        capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed on page {page}: {proc.stderr.strip()[:200]}")
    tsv = base.with_suffix(".tsv")

    words = []
    line_words: dict = {}
    for row in tsv.read_text().splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        conf = float(cols[10])
        l, t, w, h = int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9])
        key = (cols[1], cols[2], cols[3], cols[4])
        words.append({"text": cols[11], "conf": conf,
                      "l": l, "t": t, "r": l + w, "b": t + h})
        line_words.setdefault(key, []).append((int(cols[5]), l, t, conf, cols[11]))
    lines = []
    for key in sorted(line_words, key=lambda k: min(w[2] for w in line_words[k])):
        ws = sorted(line_words[key], key=lambda w: (w[1], w[0]))
        confs = [w[3] for w in ws if w[3] >= 0]
        lines.append({"t": min(w[2] for w in ws),
                      "text": " ".join(w[4] for w in ws),
                      "conf": (sum(confs) / len(confs)) if confs else -1.0})
    tsv.unlink(missing_ok=True)

    with Image.open(png) as im:
        w_px, h_px = im.size
        g = np.asarray(im.convert("L").resize(
            (1200, max(1, round(1200 * h_px / w_px)))), dtype=np.float32)
    lap = (4.0 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
           - g[1:-1, :-2] - g[1:-1, 2:])
    blur = float(lap.var())
    ink = (g < 160).astype(np.float32)
    hh, ww = ink.shape
    ys, xs = np.nonzero(ink)
    skew = 0.0
    if len(ys) > 500:
        span = int(np.ceil(np.tan(np.deg2rad(2.5)) * hh)) + 1
        rows = hh + 2 * span + 2
        best_var = -1.0
        for ang10 in range(-25, 26, 2):
            off = np.round(np.tan(np.deg2rad(ang10 / 10.0)) * ys).astype(np.int32) + span + 1
            prof = np.bincount(off * ww + xs, minlength=rows * ww).reshape(rows, ww).sum(axis=1)
            v = float(((prof[1:] - prof[:-1]) ** 2).sum())
            if v > best_var:
                best_var, skew = v, ang10 / 10.0

    out_json.write_text(json.dumps({
        "page": page,
        "file": f"page-{page:04d}.png",
        "size_px": [w_px, h_px],
        "engine": "tesseract",
        "lang": lang,
        "words": words,
        "lines": [{"t": ln["t"], "text": ln["text"], "conf": round(ln["conf"], 1)}
                  for ln in lines],
        "image_stats": {"blur_lapvar": round(blur, 1), "skew_deg": round(skew, 2)},
    }, separators=(",", ":")) + "\n")
    return page, "ok"


def tesseract_ocr_pass(archive: Path, out_dir: Path, pages: list[int],
                       workers: int = 4, lang: str = "eng") -> None:
    """Full-page tesseract OCR (+blur/skew stats), parallel and resumable.

    Threads suffice: the heavy lifting runs in the tesseract subprocess,
    and the numpy stat pass releases the GIL.
    """
    rec_dir = out_dir / "pages"
    rec_dir.mkdir(parents=True, exist_ok=True)
    todo = [p for p in pages if not (rec_dir / f"page-{p:04d}.ocr.json").is_file()]
    print(f"[ocr] {len(todo)}/{len(pages)} pages to OCR ({workers} workers)", flush=True)
    done = 0
    t0 = dt.datetime.now()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_ocr_one, (str(archive), p, str(rec_dir), lang)) for p in todo]
        for fut in as_completed(futs):
            page, status = fut.result()
            done += 1
            if done % 50 == 0 or done == len(todo):
                rate = done / max(0.001, (dt.datetime.now() - t0).total_seconds())
                print(f"[ocr] {done}/{len(todo)} ({rate:.2f} pages/s)", flush=True)


# ---------------------------------------------------------------------------
# Map step: derive records + artifacts
# ---------------------------------------------------------------------------

def load_raw(out_dir: Path, pages: list[int]) -> tuple[list[dict], dict[int, list[dict]]]:
    rec_dir = out_dir / "pages"
    records, raw_lines = [], {}
    for p in pages:
        lp, op = rec_dir / f"page-{p:04d}.layout.json", rec_dir / f"page-{p:04d}.ocr.json"
        if not (lp.is_file() and op.is_file()):
            raise SystemExit(f"missing raw pass outputs for page {p}; run the pages step first")
        layout = json.loads(lp.read_text())
        ocr = json.loads(op.read_text())
        records.append(derive_record(p, layout, ocr))
        raw_lines[p] = ocr["lines"]
    return records, raw_lines


def map_step(archive: Path, out_dir: Path, first: int, last: int) -> None:
    pages = list(range(first, last + 1))
    records, raw_lines = load_raw(out_dir, pages)
    rec_dir = out_dir / "records"
    rec_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        (rec_dir / f"page-{r['page']:04d}.json").write_text(
            json.dumps(r, indent=1, sort_keys=True) + "\n")

    smap = build_sarga_map(records, first, last)
    (out_dir / "sarga-map.json").write_text(json.dumps(smap, indent=1) + "\n")
    (out_dir / "toc-draft.md").write_text(build_toc_draft(smap))
    spot = write_spot_checks(out_dir, smap, records, raw_lines)
    (out_dir / "fidelity-report.md").write_text(
        build_fidelity_report(records, smap, spot))

    n_sargas = sum(k["sarga_count"] for k in smap["kandas"])
    print(f"[map] {len(records)} records -> {len(smap['kandas'])} kandas, "
          f"{n_sargas} sargas; sarga-map.json, toc-draft.md, fidelity-report.md "
          f"written to {out_dir}")
    for k in smap["kandas"]:
        exp = k["expected_sarga_count"]
        extra = f" (expected {exp})" if exp and exp != k["sarga_count"] else ""
        print(f"[map]   bk{k['kanda']} {k['name']}: pages {k['start_page']}–{k['end_page']}, "
              f"{k['sarga_count']} sargas{extra}")


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="bindery-structure",
        description="M2 structure stage: docling layout + tesseract OCR -> sarga map")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--archive", type=Path, default=Path("archive"))
        p.add_argument("--out", type=Path, default=Path("build/structure"))
        p.add_argument("--first", type=int, default=1)
        p.add_argument("--last", type=int, default=None)

    p_pages = sub.add_parser("pages", help="run layout+OCR passes (resumable)")
    _common(p_pages)
    p_pages.add_argument("--workers", type=int, default=4)
    p_pages.add_argument("--chunk", type=int, default=32)
    p_pages.add_argument("--stage", choices=["layout", "ocr", "both"], default="both")

    p_map = sub.add_parser("map", help="derive records + sarga-map/toc/fidelity")
    _common(p_map)

    p_all = sub.add_parser("all", help="pages then map")
    _common(p_all)
    p_all.add_argument("--workers", type=int, default=4)
    p_all.add_argument("--chunk", type=int, default=32)
    p_all.add_argument("--stage", choices=["layout", "ocr", "both"], default="both")

    args = ap.parse_args(argv)
    archive: Path = args.archive
    if not archive.is_dir():
        raise SystemExit(f"archive not found: {archive}")
    last = args.last
    if last is None:
        manifest = archive / "manifest.json"
        if manifest.is_file():
            last = len(json.loads(manifest.read_text())["pages"])
        else:
            last = len(list(archive.glob("page-*.png")))
    pages = list(range(args.first, last + 1))
    out_dir: Path = args.out

    if args.cmd in ("pages", "all"):
        if args.stage in ("layout", "both"):
            docling_layout_pass(archive, out_dir, pages, chunk=args.chunk)
        if args.stage in ("ocr", "both"):
            tesseract_ocr_pass(archive, out_dir, pages, workers=args.workers)
    if args.cmd in ("map", "all"):
        map_step(archive, out_dir, args.first, last)
    return 0


if __name__ == "__main__":
    sys.exit(main())
