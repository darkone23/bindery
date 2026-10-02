#!/usr/bin/env python3
"""extract_english — M5 (HOL-264): Gita Press English extraction + ToC mapping.

Source: the 2303-page Gita Press Valmiki-Ramayana PDF (two-part scan;
Part I = archive 1-1168, Part II = archive 1169-2303). The PDF has a real
text layer; `pdftotext -layout` reproduces body English, the two-column
Sanskrit/English layout, and the dotted-leader ToC pages faithfully.

Pipeline (deterministic, flag-no-repair):
  1. pdftotext -layout over the whole PDF -> pages split on form feeds.
  2. strip_page_chrome: running heads (`NNN * TITLE *` / `* TITLE * NNN` /
     `(NNN)` ToC pages), bare folio numbers, Om marks, lone `U` folio marks.
  3. normalize: single-char legacy-diacritics -> IAST/Unicode table built
     empirically from the low-frequency glyph inventory (English-zone glyphs
     only; the custom-encoded Devanagari body is a separate glyph population
     that is flagged, never transliterated).
  4. ToC parse: archive pages 21-58 (Part I, kandas 1-4) and 1170-1190
     (Part II, kandas 5-7) -> {part, kanda, canto_no, title, printed_page,
     archive_page}. printed->archive offsets: Part I +0 (derived: printed
     folios equal archive index), Part II +1167 (derived: body folios
     992/333/1033/1136 on archive 2159/1500/2200/2303 and ToC folio (23) on
     archive 1190).
  5. sarga assembly: page ranges from ToC starts; line-level refinement at
     detected `Canto <Roman>` headings; `Thus ends Canto <words>` closers
     cross-checked. English prose = lines whose words are not
     Devanagari-encoding (deterministic glyph classifier).

Quirks are flagged, never silently repaired (M2 lesson): numeral omissions,
shared heading pages, unclosed ToC entries, closer mismatches.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

MAPPING_VERSION = "1"

# ---------------------------------------------------------------------------
# 1. Diacritics: legacy glyph -> IAST / correct Unicode.
# Empirically derived: every glyph below was seen inside English words in the
# -layout text of the full document (see tests/test_english_units.py).
# Single-char table; compounds like `≈h` -> `ṃh` fall out of `≈` -> `ṃ`.
# ---------------------------------------------------------------------------
DIACRITICS = {
    # vowels / vocalic r
    "å": "ā", "∂": "ī", "æ": "ṛ", "Æ": "ṛ",
    # consonants (under-dots and palatals)
    "ƒ": "ṇ", "∆": "ṅ", "¢": "ṭ", "¶": "ṣ", "‹": "ś", "›": "Ś",
    "Œ": "ḍ", "œ": "Ḍ", "¤": "ñ", "®": "Ṣ",
    # anusvara / visarga marks
    "≈": "ṃ", "¨": "ḥ",
    # punctuation the print encodes as legacy glyphs
    "í": "’", "ë": "‘", "ì": "“", "î": "”", "ó": "—", "ñ": "–",
    # all-caps running-head glyph set (kanda names, colophons, headers)
    "Å": "Ā",
}
# correct Unicode already present in the print: pass through untouched
PASSTHROUGH = frozenset("—–‘’“”…†×")
# glyph population of the custom-encoded Devanagari body: never occurs
# inside English words (verified over the whole document); these drive the
# Devanagari-zone classifier and are flagged, never transliterated.
# `§` and `°` belong here too: their English roles exist only inside the
# ligature pairs handled by _PREPASS (§R -> Ṛ, °N -> Ṇ).
ENCODING_ONLY = frozenset(
    # corpus-derived: every non-ASCII glyph in the 2303-page -layout text
    # minus DIACRITICS minus PASSTHROUGH (see qc note MAPPING_VERSION 1).
    # `∫` (case-aware) and `µ` (ligature/drop) are handled by _normalize_word;
    # \uf8ff (Apple private-use "vocalic-r" mark) was invisible in terminal
    # output when the set was first pasted — added explicitly.
    "¡¥§©ª«¬°´·¸º»¿ÀÁÂÃÄÇÈÉÊËÌÍÎÏÑÒÔÕÖÙÛÜßàáâãäçèéêòô÷øûüÿıŸˆˇ˘˙˛˜˝̧̃̋π‚„‡•‰⁄™∑√∞◊✺\uf8ffﬂ"
)
_TRANSLATE = str.maketrans(DIACRITICS)

# ligature pairs: two legacy glyphs render ONE transliteration unit.
# - `§R` -> `Ṛ` (e.g. `§R¶i` -> `Ṛṣi`); a lone `§` is Devanagari-encoding.
# - `°N` -> `Ṇ` (the under-dot precedes the letter: `RÅMÅYA°NA` -> `RĀMĀYAṆA`).
# - `µu` -> `ū` (macron precedes the u: `Citrakµu¢a` -> `Citrakūṭa`).
# - `°{2,}` are dotted-leader dots inside all-caps ToC kanda headers
#   (`ARA°NYAKÅ°°°°°°°°°NœA`) — dropped.
_PREPASS = [
    (re.compile(r"°{2,}"), ""),
    (re.compile(r"§R"), "Ṛ"),
    (re.compile(r"°N"), "Ṇ"),
    (re.compile(r"µu"), "ū"),
    # a bare `µ` (macron carrier misplaced by the typesetter; 2 corpus
    # instances: `lifµe` -> life, `Sumitrµå` -> Sumitrā) — dropped, see QC
    (re.compile(r"µ"), ""),
]
# case-aware single glyph: `∫` = `ī` in lowercase words, `Ī` in all-caps
# running heads / colophons (`SARASWAT∫` -> `SARASWATĪ`)
_LOWER_INTEGRAL = str.maketrans({"∫": "ī"})
_UPPER_INTEGRAL = str.maketrans({"∫": "Ī"})


def normalize(text: str) -> str:
    """Normalize legacy diacritics -> IAST/Unicode, word-wise.

    Words containing any encoding-only glyph (the custom Devanagari body)
    are left untouched — flagged, never transliterated.
    """
    out: list[str] = []
    last = 0
    for m in _WORD_RE.finditer(text):
        w = m.group(0)
        if word_is_devanagari(w):
            continue
        out.append(text[last:m.start()])
        out.append(_normalize_word(w))
        last = m.end()
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# 2. English-zone classifier: the custom encoding borrows ASCII letters
# (h, K, d, C, N, U, p, ...), so "has latin letters" is not a test. A word is
# Devanagari-encoding iff it contains >=1 encoding-only glyph.
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"\S+")


def _prepass(word: str) -> str:
    for rx, repl in _PREPASS:
        word = rx.sub(repl, word)
    return word


def _normalize_word(word: str) -> str:
    w = _prepass(word)
    caps = not any(c.islower() for c in w)
    w = w.translate(_UPPER_INTEGRAL if caps else _LOWER_INTEGRAL)
    return w.translate(_TRANSLATE)


def word_is_devanagari(word: str) -> bool:
    return any(ch in ENCODING_ONLY for ch in _normalize_word(word))


def word_is_english(word: str) -> bool:
    return not word_is_devanagari(word) and (
        len(re.findall(r"[A-Za-z]", word)) >= 2 or any(ch in DIACRITICS for ch in word)
    )


def line_is_english(line: str) -> bool:
    return any(word_is_english(w) for w in _WORD_RE.findall(line))


# every non-ASCII character a rule can EMIT (mapped values, ligature
# outputs, case-aware ∫) — anything else surviving normalization in an
# English-zone word is unmapped
OUTPUT_OK = frozenset(DIACRITICS.values()) | PASSTHROUGH | {"Ṛ", "Ṇ", "ū", "ī", "Ī"}


def unmapped_english_glyphs(text: str) -> dict[str, int]:
    """Non-ASCII glyphs surviving all rules inside English-zone words.

    Expected zero over the real corpus; a non-zero count is a QC failure.
    """
    counts: Counter = Counter()
    for w in _WORD_RE.findall(text):
        if not re.search(r"[A-Za-z]{2,}", w) or word_is_devanagari(w):
            continue
        for ch in _normalize_word(w):
            if ord(ch) > 126 and ch not in OUTPUT_OK:
                counts[ch] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# 3. Chrome stripper: running heads, folio numbers, Om marks, lone-U marks.
# ---------------------------------------------------------------------------
_HEADER_NUM = r"\d{1,4}"
HEADER_PATTERNS = [
    re.compile(rf"^\s*{_HEADER_NUM}\s+\*[^*]+\*\s*$"),      # 992  * TITLE *
    re.compile(rf"^\s*\*[^*]+\*\s+{_HEADER_NUM}\s*$"),      # * TITLE *  993
    re.compile(r"^\s*\*[^*]+\*\s*$"),                       # * TITLE *      (no folio)
    re.compile(rf"^\s*\({_HEADER_NUM}\)\s*$"),              # (23)  ToC folios
    re.compile(rf"^\s*{_HEADER_NUM}\s*$"),                  # bare folio (453 on 1169)
]
OM_RE = re.compile(r"^\s*O[°]?À\s*$")
FOLIO_U_RE = re.compile(r"^\s*U\s*$")


def strip_page_chrome(text: str) -> tuple[str, list[str]]:
    """Strip running heads (top zone), folio numbers, Om and lone-U marks.

    Returns (clean_text, flags). Content lines are never dropped; everything
    stripped is enumerated in flags.
    """
    lines = text.splitlines()
    flags: list[str] = []
    # top zone: skip blanks, strip Om/header lines until the first content
    i = 0
    while i < len(lines) and i <= 8:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if OM_RE.match(line):
            flags.append("chrome:om")
            lines[i] = None
            i += 1
            continue
        if any(p.match(line) for p in HEADER_PATTERNS):
            flags.append("chrome:header")
            lines[i] = None
            i += 1
            continue
        break
    for j, line in enumerate(lines):
        if line is not None and FOLIO_U_RE.match(line):
            flags.append("chrome:folio")
            lines[j] = None
    clean = "\n".join(ln for ln in lines if ln is not None)
    if text and not clean.endswith("\n") and text.endswith("\n"):
        clean += "\n"
    return clean, sorted(set(flags))


# ---------------------------------------------------------------------------
# 4. Numerals
# ---------------------------------------------------------------------------
_ROMAN = {
    "I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000,
}
_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

# the print mixes cardinal and ordinal closer styles ("Thus ends Canto
# Nineteenth", "Twenty-two"); ordinals map onto their cardinals
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fifth": 5, "ninth": 9,
    "twelfth": 12,
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
    "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90,
    "hundredth": 100,
}


def roman_to_int(s: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(s.upper()):
        val = _ROMAN[ch]
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total


def word_number(s: str) -> int | None:
    """'One' / 'Forty-one' / 'one hundred and eleven' / 'Nineteenth' -> int."""
    tokens = re.split(r"[\s-]+", s.strip().lower())
    total, current = 0, 0
    for tok in tokens:
        if tok in ("and", "the", "of", "in", ""):
            continue
        if tok in _UNITS:
            current += _UNITS[tok]
        elif tok in _TENS:
            current += _TENS[tok]
        elif tok in _ORDINALS:
            current += _ORDINALS[tok]
        elif tok.endswith("th") and tok[:-2] in _UNITS:
            current += _UNITS[tok[:-2]]
        elif tok == "hundred":
            current = (current or 1) * 100
        else:
            return None
        if current >= 100:
            total += current
            current = 0
    return total + current


# ---------------------------------------------------------------------------
# 5. ToC parsing (archive 21-58 and 1170-1190)
# ---------------------------------------------------------------------------
ENTRY_START_RE = re.compile(r"^\s{0,8}(\d{1,3})\.\s+(\S.*)$")
LEADER_RE = re.compile(r"^(.*?)\s*\.{3,}\s*(\d{1,4})\s*$")
KANDA_BY_BOOK = {
    "One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7,
}
KANDA_NAMES = {
    1: "Bālakāṇḍa", 2: "Ayodhyākāṇḍa", 3: "Araṇyakāṇḍa", 4: "Kiṣkindhākāṇḍa",
    5: "Sundarakāṇḍa", 6: "Yuddhakāṇḍa", 7: "Uttarakāṇḍa",
}
KANDA_RAW = {
    "BålakåƒŒa": 1, "AyodhyåkåƒŒa": 2, "AraƒyakåƒŒa": 3, "Ki¶kindhåkåƒŒa": 4,
    "SundarakåƒŒa": 5, "YuddhakåƒŒa": 6, "UttarakåƒŒa": 7,
}
# normalized kanda names (post-diacritics), for `Thus ends ... in the X`
KANDA_BY_NAME = {v: k for k, v in KANDA_NAMES.items()}
# all-caps ToC kanda-header forms (normalized): `ARA°NYAKÅ°NœA` ->
# `ARAṆYAKĀṆḌA`
KANDA_CAPS = {
    1: "BĀLAKĀṆḌA", 2: "AYODHYĀKĀṆḌA", 3: "ARAṆYAKĀṆḌA", 4: "KIṢKINDHĀKĀṆḌA",
    5: "SUNDARAKĀṆḌA", 6: "YUDDHAKĀṆḌA", 7: "UTTARAKĀṆḌA",
}
KANDA_BY_CAPS = {v: k for k, v in KANDA_CAPS.items()}


def toc_kanda_headers(text: str) -> list[dict]:
    """All kanda header blocks on one ToC page, with line positions.

    Two printed shapes (normalized): the full block (title line, kanda name,
    `Book <Word>`) used at part openings, and the short block (kanda name,
    `Book <Word>`) used when a kanda's ToC continues on from the previous
    kanda's entries on the same page. The name line's index matters: entries
    ABOVE it belong to the previous kanda.
    """
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[dict] = []
    for i, ln in enumerate(lines):
        kanda = KANDA_BY_NAME.get(ln) or KANDA_BY_CAPS.get(ln)
        if kanda is None:
            continue
        prev_line = lines[i - 1] if i else ""
        book = next((x.split()[-1] for x in lines[i + 1:i + 3]
                     if x.startswith("Book ") and x.split()[-1] in KANDA_BY_BOOK),
                    None)
        if book is None:
            continue
        out.append({"name_raw": ln, "book": book, "kanda": kanda, "line": i,
                    "with_title": prev_line == "The Vālmīki-Rāmāyaṇa"})
    return out


def toc_kanda_header(text: str) -> dict | None:
    heads = toc_kanda_headers(text)
    return heads[0] if heads else None


def parse_toc_page(text: str) -> tuple[list[dict], list[str]]:
    """Parse one ToC page -> (entries, leading_fragments).

    Titles may wrap across lines (hanging indent); an entry closes at the
    dotted leader + printed page number. Each entry carries `start_line`
    (index in this page) for kanda attribution. `leading_fragments` are the
    indented lines BEFORE the first entry start — the tail of an entry whose
    number sat on the previous page (the caller stitches them onto the
    pending entry). Kanda-header and centered decorative lines are excluded
    by the continuation indent window.
    """
    entries: list[dict] = []
    leading: list[str] = []
    open_entry: dict | None = None
    structural = {"The Vālmīki-Rāmāyaṇa"} | frozenset(KANDA_BY_NAME) \
        | frozenset(KANDA_BY_CAPS)
    for line_no, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped in structural or stripped.startswith("Number of Cantos") \
                or stripped == "Page":
            continue          # structural ToC lines: never title content
        m = ENTRY_START_RE.match(line)
        if m:
            open_entry = {"canto_no": int(m.group(1)), "title_raw": m.group(2),
                          "printed_page": None, "page_end": False,
                          "start_line": line_no}
            entries.append(open_entry)
            lm = LEADER_RE.match(open_entry["title_raw"])
            if lm:
                open_entry["title_raw"] = re.sub(r"\s+", " ", lm.group(1)).strip()
                open_entry["printed_page"] = int(lm.group(2))
                open_entry["page_end"] = True
                open_entry = None
            continue
        indent = len(line) - len(line.lstrip())
        if open_entry is None:
            if 2 <= indent <= 12:
                leading.append(stripped)
            continue
        open_entry["title_raw"] += (" " if not open_entry["title_raw"].endswith("-")
                                    else "") + stripped
        lm = LEADER_RE.match(open_entry["title_raw"])
        if lm:
            open_entry["title_raw"] = re.sub(r"\s+", " ", lm.group(1)).strip()
            open_entry["printed_page"] = int(lm.group(2))
            open_entry["page_end"] = True
            open_entry = None
    return entries, leading


def resolve_duplicate_bands(toc: dict) -> tuple[dict, list[str]]:
    """Resolve duplicate canto numbers within a kanda (print anomalies).

    The only known case (kanda 6, p1177): a band of entries printed with the
    numbers 12-19 between sargas 1 and 10, whose page refs (295-320) slot
    monotonically where sargas 2-9 belong — a typesetting error where the
    2nd-9th sargas carry wrong numbers. Resolution is applied ONLY when it
    is provable from the page sequence itself:

    - for each duplicated number, the copy that fits between the resolved
      pages of its neighbours is kept; the others are anomaly copies;
    - when the anomaly copies' count equals the count of MISSING numbers
      and the re-paired sequence is strictly monotone in page order, the
      anomaly copies are renumbered to the missing numbers (`printed_as`
      preserves what the print showed);
    - otherwise nothing is invented: duplicates stay, flagged.

    Returns (toc, quirks).
    """
    quirks = list(toc["quirks"])
    added: list[str] = []
    for k in toc["kandas"]:
        sargas = k["sargas"]
        nos = [s["canto_no"] for s in sargas]
        dups = sorted({n for n in nos if nos.count(n) > 1})
        if not dups:
            continue
        by_no: dict[int, list[dict]] = {}
        for s in sargas:
            by_no.setdefault(s["canto_no"], []).append(s)
        missing = [n for n in range(1, max(nos) + 1) if n not in by_no]
        anomalies: list[dict] = []
        unresolved = False
        resolved_pages: dict[int, int] = {
            n: by_no[n][0]["printed_page"] for n in by_no if len(by_no[n]) == 1
            and by_no[n][0]["printed_page"] is not None}
        for n in dups:
            copies = sorted(by_no[n], key=lambda s: s["printed_page"] or 0)
            prev_p = max((p for m, p in resolved_pages.items() if m < n),
                         default=0)
            next_p = min((p for m, p in resolved_pages.items() if m > n),
                         default=10 ** 9)
            fit = [c for c in copies if c["printed_page"] is not None
                   and prev_p <= c["printed_page"] <= next_p]
            if fit:
                kept = fit[-1]
                resolved_pages[n] = kept["printed_page"]
                anomalies.extend(c for c in copies if c is not kept)
            else:
                unresolved = True
                kept = copies[0]
                anomalies.extend(copies[1:])
        if unresolved or len(anomalies) != len(missing) or not missing:
            added.append(f"kanda{k['kanda']}:unresolved_duplicates:"
                          f"{sorted(set(a['canto_no'] for a in anomalies))}")
            continue
        pairs = sorted(zip(missing, anomalies),
                       key=lambda t: t[1]["printed_page"] or 0)
        anomaly_ids = {id(s) for s in anomalies}
        trial = [(s["printed_page"], s["canto_no"]) for s in sargas
                 if id(s) not in anomaly_ids and s["printed_page"] is not None]
        trial += [(s["printed_page"], n) for n, s in pairs]
        order = sorted(trial, key=lambda t: t[0])
        seq_nos = [n for _p, n in order]
        monotone = (all(order[i][0] < order[i + 1][0] for i in range(len(order) - 1))
                    and all(seq_nos[i] < seq_nos[i + 1]
                            for i in range(len(seq_nos) - 1))
                    and seq_nos == list(range(1, max(seq_nos) + 1)))
        if monotone:
            for n, s in pairs:
                s["printed_as"] = s["canto_no"]
                s["canto_no"] = n
            k["anomalies"] = [{
                "kind": "renumbered_band",
                "printed_as": s["printed_as"], "renumbered_to": s["canto_no"],
                "printed_page": s["printed_page"], "title": s["title"],
            } for _n, s in pairs]
            k["sargas"] = sorted(k["sargas"], key=lambda s: s["canto_no"])
            added.append(
                f"kanda{k['kanda']}:renumbered_band:"
                f"printed {[s['printed_as'] for _n, s in pairs]} "
                f"@pages {[s['printed_page'] for _n, s in pairs]} "
                f"-> sargas {missing} (page-monotone pairing)")
        else:
            added.append(f"kanda{k['kanda']}:unresolved_duplicates:"
                          f"{sorted(set(a['canto_no'] for a in anomalies))}")
    return toc, added


# ---------------------------------------------------------------------------
# 6. Part geometry: printed -> archive offsets
# ---------------------------------------------------------------------------
PART_SPLIT = 1168   # Part I = archive 1..1168, Part II = 1169..2303
PART_OFFSETS = {1: 0, 2: 1167}


def part_for_archive(archive_page: int) -> int:
    return 1 if archive_page <= PART_SPLIT else 2


def archive_page_for(printed: int, part: int) -> int:
    return printed + PART_OFFSETS[part]


def printed_page_for(archive_page: int) -> int | None:
    return archive_page - PART_OFFSETS[part_for_archive(archive_page)]


def derive_offsets(header_records: list[tuple[int, int]]) -> dict[int, int]:
    """Empirical printed->archive offset per part from (archive, printed) folios."""
    diffs: dict[int, list[int]] = {1: [], 2: []}
    for archive, printed in header_records:
        diffs[part_for_archive(archive)].append(archive - printed)
    return {p: Counter(ds).most_common(1)[0][0] if ds else PART_OFFSETS[p]
            for p, ds in diffs.items()}


# ---------------------------------------------------------------------------
# 7. Canto markers in body text
# ---------------------------------------------------------------------------
CANTO_HEADING_RE = re.compile(r"^\s*Canto\s+([IVXLCDM]+)\s*$")
# closer shapes the print uses (probed corpus-wide): "Thus ends Canto N in
# the <K>kāṇḍa", "…of the <K>kāṇḍa", stray "of"/"the" after "ends", "end"
# for "ends", lowercase "canto", dropped "in"/"the". A corrupted closer
# (print typo) fails to parse and is flagged instead.
CLOSER_RE = re.compile(
    r"^\s*Thus end[s]?\s+(?:of |the )?[Cc]anto\s+([A-Za-z -]+?)\s+"
    r"(?:(?:in|of)\s+(?:the\s+)?)?(\S*kāṇḍa)\b")

TOC_PAGE_RANGES = {1: (21, 58), 2: (1170, 1190)}


def toc_entries(pages_text: dict[int, str]) -> dict:
    """Full ToC extraction over both parts -> structured dataset.

    Kanda attribution is line-position aware: a header block mid-page (a
    kanda's ToC continuing under the previous kanda's last entries) switches
    the current kanda exactly at its name line. Entries that never get a
    kanda are kept under kanda=None and flagged — never silently dropped.
    """
    kandas_out: list[dict] = []
    quirks: list[str] = []
    unattributed: list[dict] = []
    for part, (first, last) in TOC_PAGE_RANGES.items():
        current: int | None = None
        pending: dict | None = None
        attributed: dict[int | None, list[dict]] = {}

        def close(e: dict) -> bool:
            """Resolve the leader; True when the entry is complete."""
            m = LEADER_RE.match(e["title_raw"])
            if m:
                e["title_raw"] = re.sub(r"\s+", " ", m.group(1)).strip()
                e["printed_page"] = int(m.group(2))
            if e["printed_page"] is None:
                return False
            attributed.setdefault(e["kanda"], []).append(e)
            return True

        for ap in range(first, last + 1):
            text = pages_text.get(ap, "")
            heads = toc_kanda_headers(text)
            entries, leading = parse_toc_page(text)
            if pending is not None:
                for frag in leading:
                    pending["title_raw"] += (" " if not
                                             pending["title_raw"].endswith("-")
                                             else "") + frag
                if close(pending):
                    pending = None
            for e in entries:
                above = [h for h in heads if h["line"] <= e.get("start_line", 0)]
                if above:
                    current = above[-1]["kanda"]
                e["kanda"] = current
                if not close(e):
                    pending = e
        if pending is not None:
            quirks.append(f"part{part}:toc:open_entry_at_end")
            pending["kanda"] = current
            attributed.setdefault(pending["kanda"], []).append(pending)
            pending = None
        for kanda in sorted(k for k in attributed if k):
            ents = sorted(attributed[kanda], key=lambda e: e["canto_no"])
            kandas_out.append({
                "part": part, "kanda": kanda, "name": KANDA_NAMES[kanda],
                "sargas": [
                    {"canto_no": e["canto_no"], "title": e["title_raw"],
                     "printed_page": e["printed_page"],
                     "archive_page": archive_page_for(e["printed_page"], part)
                     if e["printed_page"] is not None else None}
                    for e in ents
                ],
            })
        for e in attributed.get(None, []):
            e2 = dict(e)
            e2["part"] = part
            unattributed.append(e2)
    if unattributed:
        quirks.append(f"toc:kanda_unattributed:{len(unattributed)} entries")
    toc = {"kandas": kandas_out, "quirks": quirks, "unattributed": unattributed}
    toc, extra_quirks = resolve_duplicate_bands(toc)
    toc["quirks"] = list(toc["quirks"]) + extra_quirks
    return toc


# ---------------------------------------------------------------------------
# 8. Sarga assembly
# ---------------------------------------------------------------------------
def _sarga_for_page(ap: int, starts: list[dict]) -> dict | None:
    """Record covering archive page ap (ranges assumed non-overlapping)."""
    best: dict | None = None
    for s in starts:
        if s["archive_start"] > ap:
            break
        best = s
    if best and ap <= best["archive_end"]:
        return best
    return None


def assemble_sargas(pages_text: dict[int, str], toc: dict) -> list[dict]:
    """Per-sarga records via a canonical sequence walk with dual markers.

    `pages_text` must already be chrome-stripped + normalized. Cantos are
    strictly sequential in the print, so ownership is sequence-driven and
    BOTH printed markers can advance it, each in line order:

    - `Canto <Roman>` heading matching the next expected sarga (and within
      HEADING_WINDOW pages of its ToC start) opens the new sarga's segment;
    - `Thus ends Canto <words> in the <Kanda>-kāṇḍa` closer naming the next
      expected sarga closes the current segment — the print's closers name
      their own kanda, so they carry kanda context that bare headings lack;
    - pre-heading lines on a heading page go to the previous sarga when they
      contain its closer, to the new sarga when the heading page is its ToC
      start (kanda-opener title blocks), else to the previous owner;
    - non-matching markers are flagged, never used;
    - a sarga reached by neither marker gets its ToC page range appended
      whole, flagged `range_fallback`.
    """
    seq: list[dict] = []
    for k in sorted(toc["kandas"], key=lambda k: k["kanda"]):
        for e in sorted(k["sargas"], key=lambda e: e["archive_page"] or 10 ** 9):
            if e["archive_page"] is None:
                continue
            seq.append({
                "part": k["part"], "kanda": k["kanda"], "sarga": e["canto_no"],
                "title": e["title"], "printed_page": e["printed_page"],
                "archive_start": e["archive_page"],
            })
    # contiguous ranges for the sidecar page index + fallback
    for i, s in enumerate(seq):
        if i + 1 < len(seq) and seq[i + 1]["kanda"] == s["kanda"]:
            s["archive_end"] = seq[i + 1]["archive_start"] - 1
        elif i + 1 < len(seq):
            s["archive_end"] = min(seq[i + 1]["archive_start"] - 1,
                                   PART_SPLIT if s["part"] == 1 else 2303)
        else:
            s["archive_end"] = 2303
    for s in seq:
        s["text"] = ""
        s["flags"] = []
        s["closers"] = []
        s["heading_pages"] = []
        s["pages"] = []
    page_of = {(s["kanda"], s["sarga"]): s for s in seq}

    def emit(rec: dict | None, lines: list[str], ap: int) -> None:
        if rec is None or not lines:
            return
        rec["text"] += "\n".join(lines).rstrip() + "\n"
        rec["pages"].append(ap)

    HEADING_WINDOW = 40   # pages a heading may stray from its ToC start
    current: dict | None = None
    ptr = 0
    for ap in sorted(pages_text):
        lines = pages_text[ap].splitlines()
        if not pages_text[ap].strip():
            continue
        # stall recovery: past the expected start + window with no marker
        # -> catch up to the sarga covering this page (flagged)
        if ptr < len(seq):
            expected = seq[ptr]
            if ap - expected["archive_start"] > HEADING_WINDOW:
                cov = _sarga_for_page(ap, seq)
                if cov is not None and cov is not current:
                    for skipped in seq[ptr:seq.index(cov)]:
                        skipped["flags"].append("sequence_stall_skipped")
                    ptr = seq.index(cov)
                    current = cov
        # marker split points: (line_idx, kind)
        splits: list[tuple[int, str]] = []
        ptr_local = ptr
        for i, ln in enumerate(lines):
            expected = seq[ptr_local] if ptr_local < len(seq) else None
            cur_s = seq[ptr_local - 1] if ptr_local > 0 else None
            hm = CANTO_HEADING_RE.match(ln)
            cm = CLOSER_RE.match(normalize(ln))
            if hm and expected is not None:
                rn = roman_to_int(hm.group(1))
                if rn == expected["sarga"] and \
                        abs(ap - expected["archive_start"]) <= HEADING_WINDOW:
                    expected["heading_pages"].append(ap)
                    splits.append((i, "heading"))
                    ptr_local += 1
                elif cur_s is not None and rn == cur_s["sarga"]:
                    # the current sarga's own opener (ownership already set)
                    cur_s["heading_pages"].append(ap)
                else:
                    expected["flags"].append(
                        f"heading_mismatch:Canto {hm.group(1)} vs sarga "
                        f"{expected['sarga']}")
            elif cm:
                n = word_number(cm.group(1))
                kanda = KANDA_BY_NAME.get(cm.group(2))
                if n is None or not kanda:
                    continue
                if cur_s is not None and kanda == cur_s["kanda"] \
                        and n == cur_s["sarga"] and expected is not None:
                    # the closer line itself stays with the closing sarga
                    splits.append((i + 1, "closer"))
                    ptr_local += 1
                else:
                    s = page_of.get((kanda, n))
                    if s is not None:
                        s["closers"].append(ap)   # out-of-turn closer: record
        if not splits:
            emit(current, lines, ap)
            ptr = ptr_local
            continue
        # pre-segment owner: previous sarga's closer present -> previous;
        # heading page is the new sarga's ToC start -> new sarga; else current
        first_i, _kind = splits[0]
        first_s = seq[ptr]           # ptr (not ptr_local): still the expected
        prev_s = seq[ptr - 1] if ptr > 0 else None
        pre = lines[:first_i]
        pre_closer_n = None
        for ln in pre:
            cm = CLOSER_RE.match(normalize(ln))
            if cm:
                pre_closer_n = word_number(cm.group(1))
                break
        if pre_closer_n is not None and prev_s is not None \
                and pre_closer_n == prev_s["sarga"]:
            pre_owner = prev_s
            prev_s["closers"].append(ap)
        elif first_s["archive_start"] == ap:
            pre_owner = first_s
        else:
            pre_owner = current
        emit(pre_owner, pre, ap)
        bounds = [i for i, _k in splits] + [len(lines)]
        for s_idx, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
            emit(seq[ptr + s_idx], lines[a:b], ap)
        ptr = ptr_local

    for s in seq:
        s["text"] = s["text"].strip("\n")
        s["pages"] = sorted(set(s["pages"]))
        s["closers"] = sorted(set(s["closers"]))
        s["english_prose"] = "\n".join(
            ln for ln in s["text"].splitlines() if line_is_english(ln))
        for hp in s["heading_pages"]:
            if hp < s["archive_start"]:
                s["flags"].append("heading_before_start_page")
            elif hp > s["archive_start"]:
                s["flags"].append("heading_after_start_page")
        if not s["closers"]:
            s["flags"].append("closer_not_found")
        if not s["text"]:
            s["flags"].append("range_fallback")
            s["text"] = "\n".join(pages_text.get(ap, "").strip("\n")
                                  for ap in range(s["archive_start"],
                                                  s["archive_end"] + 1)
                                  if ap in pages_text).strip("\n")
            s["english_prose"] = "\n".join(
                ln for ln in s["text"].splitlines() if line_is_english(ln))
            s["pages"] = [ap for ap in range(s["archive_start"],
                                             s["archive_end"] + 1)
                          if ap in pages_text]
        s["flags"] = sorted(set(s["flags"]))
    return seq


EXPECTED_SARGA_COUNTS = {1: 77, 2: 119, 3: 75, 4: 67, 5: 68, 6: 128, 7: 111}


def kanda_coverage(sargas: list[dict]) -> list[dict]:
    out = []
    for kanda in sorted({s["kanda"] for s in sargas}):
        ks = [s for s in sargas if s["kanda"] == kanda]
        flag_counts: Counter = Counter()
        for s in ks:
            for f in s["flags"]:
                flag_counts[f.split(":")[0] if ":" in f else f] += 1
        out.append({
            "kanda": kanda,
            "name": KANDA_NAMES[kanda],
            "sargas": len(ks),
            "expected": EXPECTED_SARGA_COUNTS.get(kanda),
            "textless": sum(1 for s in ks if not s.get("text")),
            "flag_counts": dict(flag_counts),
            "archive_span": (min(s["archive_start"] for s in ks),
                             max(s["archive_end"] for s in ks)),
        })
    return out


def page_gaps(pages: dict[int, str], first: int = 1, last: int = 2303,
              min_english: int = 25) -> list[int]:
    """Archive pages with little or no English-zone content (plates, blanks)."""
    gaps = []
    for ap in range(first, last + 1):
        text = pages.get(ap, "")
        letters = sum(1 for _ in re.findall(r"[A-Za-z]{3,}", text))
        if letters < min_english:
            gaps.append(ap)
    return gaps


def spot_check_report(pages: dict[int, str], toc: dict | None,
                      sargas: list[dict] | None) -> list[dict]:
    """Word-for-word containment checks of known passages (normalized text)."""
    checks: list[dict] = []

    def add(name: str, page: int, needle: str) -> None:
        ok = needle in pages.get(page, "")
        checks.append({"name": name, "page": page, "needle": needle, "ok": ok})

    add("toc_p21_entry1", 21,
        "The celestial sage Nārada narrates to Vālmīki the Story of")
    add("toc_p21_leader_page", 21,
        "Śrī Rāma in a nutshell.")
    add("sarga1_opener_59", 59, "Who has subdued his self?")
    add("sarga1_closer_68", 68, "Thus ends Canto One in the Bālakāṇḍa")
    add("part2_title_1169", 1169, "Part-II")
    add("splice_2159_closer", 2159,
        "Thus ends Canto Forty-one in the Uttarakāṇḍa")
    add("splice_2159_heading", 2159, "Canto XLII")
    add("splice_2160_body", 2160, "fragrant flowers, blossoms")
    add("colophon_2303", 2303, "THE END OF THE RĀMĀYAṆA OF VĀLMĪKI")
    add("colophon_canto111", 2303,
        "Thus ends Canto one hundred and eleven in the Uttarakāṇḍa")
    if toc:
        k1 = next((k for k in toc["kandas"] if k["kanda"] == 1), None)
        if k1:
            e = k1["sargas"][0]
            checks.append({"name": "toc_json_entry1_matches_p21", "page": 21,
                           "needle": e["title"][:40], "ok":
                               e["title"][:40] in pages.get(21, "")})
    if sargas:
        for s in sargas:
            if s["kanda"] == 7 and s["sarga"] == 42:
                checks.append({
                    "name": "sarga42_asoke_grove", "page": s["archive_start"],
                    "needle": "Aśoka-grove" if s["english_prose"] else "",
                    "ok": "Aśoka-grove" in s["english_prose"]})
    return checks


def build_qc(pages_norm: dict[int, str], toc: dict, sargas: list[dict],
             sidecars: dict[int, dict], committed_map: dict | None) -> dict:
    unmapped_total: Counter = Counter()
    for side in sidecars.values():
        for ch, n in side["unmapped_glyphs"].items():
            unmapped_total[ch] += n
    header_pages = sum(1 for s in sidecars.values() if "chrome:header" in s["flags"])
    qc = {
        "schema_version": 1,
        "mapping_version": MAPPING_VERSION,
        "pages": len(pages_norm),
        "offsets": PART_OFFSETS,
        "kanda_coverage": kanda_coverage(sargas),
        "toc_quirks": toc["quirks"],
        "page_gaps": page_gaps(pages_norm),
        "unmapped_english_glyphs": dict(unmapped_total),
        "header_pages_stripped": header_pages,
        "spot_checks": spot_check_report(pages_norm, toc, sargas),
    }
    if committed_map:
        qc["uttara_reconciliation"] = reconcile_uttara(toc, committed_map)
    return qc


def qc_markdown(qc: dict) -> str:
    lines = ["# M5 QC report (HOL-264)", "",
             f"- pages extracted: {qc['pages']} (of 2303)",
             f"- printed->archive offsets: Part I {qc['offsets'][1]}, "
             f"Part II {qc['offsets'][2]}",
             f"- unmapped glyphs in English zones: "
             f"{sum(qc['unmapped_english_glyphs'].values())} "
             f"{qc['unmapped_english_glyphs'] or '(zero)'}",
             f"- running-head pages stripped: {qc['header_pages_stripped']}",
             f"- page gaps (thin/blank archive pages): {len(qc['page_gaps'])}",
             "", "| kanda | sargas | expected | textless | flags | span |",
             "|---|---|---|---|---|---|"]
    for k in qc["kanda_coverage"]:
        lines.append(f"| {k['kanda']} {k['name']} | {k['sargas']} | "
                     f"{k['expected']} | {k['textless']} | "
                     f"{json.dumps(k['flag_counts'])} | {k['archive_span'][0]}–"
                     f"{k['archive_span'][1]} |")
    lines += ["", "## Spot checks (word-for-word vs -layout)", "",
              "| check | archive page | ok |", "|---|---|---|"]
    for c in qc["spot_checks"]:
        lines.append(f"| {c['name']} | {c['page']} | "
                     f"{'✓' if c['ok'] else '✗ FAIL'} |")
    if "uttara_reconciliation" in qc:
        r = qc["uttara_reconciliation"]
        lines += ["", f"## Uttara (kanda 7) reconciliation vs committed M2 map",
                  f"- matched: {r['matched']}, mismatches: {len(r['mismatches'])}, "
                  f"m2-only: {r['m2_only_sargas']}"]
        for m in r["mismatches"]:
            lines.append(f"- sarga {m['sarga']}: toc {m['toc_archive_page']} "
                         f"vs m2 {m['m2_archive_page']}")
    if qc["toc_quirks"]:
        lines += ["", "## ToC quirks (flagged, not repaired)"]
        lines += [f"- {q}" for q in qc["toc_quirks"]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 11. CLI
# ---------------------------------------------------------------------------
def extract_pages(pdf: Path, first: int = 1, last: int | None = None) -> dict[int, str]:
    last = last or 2303
    proc = subprocess.run(
        ["pdftotext", "-f", str(first), "-l", str(last), "-layout", str(pdf), "-"],
        check=True, capture_output=True, text=True)
    pages: dict[int, str] = {}
    for i, chunk in enumerate(proc.stdout.split("\f")):
        ap = first + i
        if ap <= last:
            pages[ap] = chunk
    return pages


SOURCE_URL = ("https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/"
              "Valmiki_Ramayana_Gita_Press.pdf")


def toc_dataset_envelope(toc: dict, pdf: Path) -> dict:
    """Wrap the extracted ToC with provenance (source, checksum, mapping)."""
    import hashlib
    h = hashlib.sha256()
    with open(pdf, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {
        "schema_version": 1,
        "mapping_version": MAPPING_VERSION,
        "source": {
            "url": SOURCE_URL,
            "file": pdf.name,
            "sha256": h.hexdigest(),
            "pages": 2303,
        },
        "part_offsets": {str(p): o for p, o in PART_OFFSETS.items()},
        "kandas": toc["kandas"],
        "quirks": toc["quirks"],
        "unattributed": toc.get("unattributed", []),
    }


def reconcile_uttara(toc: dict, committed_map: dict) -> dict:
    """Cross-check ToC-derived kanda-7 start pages against the committed M2
    sarga map (dataset/uttara-sarga-pages.json). Disagreements are listed,
    never repaired."""
    committed = {int(n): v["start_page"]
                 for n, v in committed_map.get("sargas", {}).items()}
    k7 = next((k for k in toc["kandas"] if k["kanda"] == 7), None)
    mismatches: list[dict] = []
    matched = 0
    if k7:
        for e in k7["sargas"]:
            want = committed.get(e["canto_no"])
            if want is None:
                continue
            if e["archive_page"] == want:
                matched += 1
            else:
                mismatches.append({"sarga": e["canto_no"],
                                   "toc_archive_page": e["archive_page"],
                                   "m2_archive_page": want})
    return {"matched": matched, "mismatches": mismatches,
            "m2_only_sargas": sorted(set(committed) - {e["canto_no"] for e in
                                                      (k7["sargas"] if k7 else [])})}


def write_pages(out: Path, pages: dict[int, str], sarga_index,
                chrome_flags: dict[int, list[str]],
                unmapped_by_page: dict[int, dict] | None = None) -> dict[int, dict]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "pages").mkdir(exist_ok=True)
    sidecars: dict[int, dict] = {}
    for ap in sorted(pages):
        clean = pages[ap]
        sref = sarga_index.get(ap)
        if unmapped_by_page is not None and ap in unmapped_by_page:
            unmapped = unmapped_by_page[ap]
        else:
            unmapped = unmapped_english_glyphs(clean)
        side = {
            "archive_page": ap,
            "printed_page": printed_page_for(ap),
            "sarga": sref["sarga"] if sref else None,
            "kanda": sref["kanda"] if sref else None,
            "flags": chrome_flags.get(ap, []),
            "unmapped_glyphs": unmapped,
        }
        sidecars[ap] = side
        (out / "pages" / f"page-{ap:04d}.txt").write_text(clean, encoding="utf-8")
        (out / "pages" / f"page-{ap:04d}.json").write_text(
            json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
    return sidecars


def sarga_index_for_pages(sargas: list[dict]) -> dict[int, dict]:
    idx: dict[int, dict] = {}
    for s in sargas:
        for ap in range(s["archive_start"], s["archive_end"] + 1):
            idx[ap] = {"kanda": s["kanda"], "sarga": s["sarga"]}
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("build/english"))
    ap.add_argument("--pages", default=None, help="A-B slice (default all 2303)")
    args = ap.parse_args(argv)
    first, last = 1, 2303
    if args.pages:
        a, _, b = args.pages.partition("-")
        first, last = int(a), int(b or a)
    pages_text = extract_pages(args.pdf, first, last)
    pages_clean: dict[int, str] = {}
    pages_norm: dict[int, str] = {}
    chrome_flags: dict[int, list[str]] = {}
    unmapped_by_page: dict[int, dict] = {}
    for ap, raw in pages_text.items():
        clean, flags = strip_page_chrome(raw)
        chrome_flags[ap] = flags
        unmapped_by_page[ap] = unmapped_english_glyphs(clean)
        pages_clean[ap] = clean
        pages_norm[ap] = normalize(clean)
    toc = toc_entries(pages_norm)
    sargas = assemble_sargas(pages_norm, toc)
    sidx = sarga_index_for_pages(sargas)
    sidecars = write_pages(args.out, pages_norm, sidx, chrome_flags,
                           unmapped_by_page)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "toc.json").write_text(
        json.dumps(toc_dataset_envelope(toc, args.pdf),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    slim = [{k: v for k, v in s.items() if k not in ("text", "english_prose")}
            for s in sargas]
    (args.out / "sargas-index.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
    for s in sargas:
        d = args.out / "sargas"
        d.mkdir(exist_ok=True)
        (d / f"k{s['kanda']}-s{s['sarga']:03d}.txt").write_text(
            s["english_prose"], encoding="utf-8")
    committed_path = Path("dataset/uttara-sarga-pages.json")
    committed_map = None
    if committed_path.exists():
        committed_map = json.loads(committed_path.read_text(encoding="utf-8"))
    qc = build_qc(pages_norm, toc, sargas, sidecars, committed_map)
    (args.out / "qc.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "qc.md").write_text(qc_markdown(qc), encoding="utf-8")
    print(f"pages={len(pages_norm)} toc_kandas={len(toc['kandas'])} "
          f"sargas={len(sargas)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
