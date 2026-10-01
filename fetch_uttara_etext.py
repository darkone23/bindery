#!/usr/bin/env python3
"""fetch_uttara_etext — harvest the Uttara-kanda e-text (sargas 42-111).

Source: ramayana.info/story/uttara/{sarga}/ (board-directed, HOL-259 plan
rev 4). The site's Next.js payload embeds one escaped-JSON object per verse
("shloka" objects) carrying text_devanagari (samhita), text_devanagari_alt,
transliteration (IAST) and translation (English); colophon objects
(ityārṣe...sargaḥ) and kanda-end markers are stripped.

Output: dataset/uttara-eText-ramayana-info.json —
  { "<sarga>": { "<verse>": {text_devanagari, text_devanagari_alt,
      transliteration, translation, explanation}, ... }, ... }
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://ramayana.info/story/uttara/{sarga}/"
FIRST_SARGA, LAST_SARGA = 42, 111
FIELDS = ("text_devanagari", "text_devanagari_alt",
          "transliteration", "translation", "explanation")

# sarga payload objects that are markers, not verses (stripped on parse)
COLOPHON_DEVA = "इत्यार्षे"
KANDA_END_DEVA = "इत्युत्तरकाण्डः"
DEDICATION_DEVA = "श्रीसीतारामचन्द्रार्पणमस्तु"


def fetch_sarga(sarga: int) -> str:
    req = urllib.request.Request(BASE.format(sarga=sarga),
                                 headers={"User-Agent": "bindery-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "ignore")


# Next.js streams the RSC payload in fragments; the seams sit INSIDE the
# escaped JSON and must be removed before field extraction, else field
# values swallow seam junk (caught by visual QC on the first render).
RSC_SEAM = re.compile(r'"\]\)</script><script>self\.__next_f\.push\(\[1,"')


def strip_rsc_seams(raw: str) -> str:
    return RSC_SEAM.sub("", raw)


def _field(blob: str, name: str, next_names: list[str]):
    start = blob.find(f'\\"{name}\\":')
    if start < 0:
        return None
    start += len(f'\\"{name}\\":')
    if blob[start:start + 4] == "null":
        return None
    start += 2  # opening \"
    end = len(blob)
    for nxt in next_names:
        p = blob.find(f'\\",\\"{nxt}\\":', start)
        if p >= 0:
            end = min(end, p)
    val = blob[start:end]
    if val.endswith('\\"'):
        val = val[:-2]
    # RSC double-escapes quotes inside values (\\\" -> \"): collapse any
    # backslash runs preceding a quote down to the bare quote. The site
    # also carries markdown artifacts — LaTeX-style inline-math verse
    # markers "\\( 3\\)" and stray doubled backslashes; none of these are
    # legitimate text, so backslashes go entirely.
    val = re.sub(r"\\+(?=\")", "", val).replace('\\"', '"')
    val = re.sub(r"\\+\(", "(", val)
    val = re.sub(r"\\+\)", ")", val)
    val = re.sub(r"\\+", "", val)
    return val


def parse_sarga(raw: str, sarga: int) -> dict[int, dict]:
    """Extract per-verse field dicts from one sarga page's RSC payload."""
    raw = strip_rsc_seams(raw)
    verses: dict[int, dict] = {}
    for m in re.finditer(r'\{\\"shloka\\":\{(.*?)\}\}\]', raw, re.S):
        blob = m.group(1)
        cut = blob.find('\\"text_telugu\\"')
        if cut > 0:
            blob = blob[:cut]
        num = re.search(r'\\"number\\":(\d+)', blob)
        if not num:
            continue
        names = list(FIELDS)
        entry = {}
        for i, name in enumerate(names):
            entry[name] = _field(blob, name, names[i + 1:])
        deva = entry.get("text_devanagari") or ""
        marker = re.sub(r"^[।॥\s]+", "", deva)
        if marker.startswith((COLOPHON_DEVA, KANDA_END_DEVA, DEDICATION_DEVA)):
            continue  # sarga/kanda markers, not verses
        for fname, val in entry.items():
            if val and ("__next_f" in val or "</script" in val):
                raise SystemExit(
                    f"sarga {sarga} verse {num.group(1)}: field {fname} "
                    f"swallowed RSC seam junk (strip_rsc_seams gap?)")
        verses[int(num.group(1))] = entry
    return verses


def harvest(first: int, last: int) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for sarga in range(first, last + 1):
        raw = fetch_sarga(sarga)
        out[str(sarga)] = {str(n): f for n, f in parse_sarga(raw, sarga).items()}
        print(f"sarga {sarga}: {len(out[str(sarga)])} verses", flush=True)
    return out


def gap_profile(data: dict) -> list[tuple[str, str, list[str]]]:
    gaps = []
    for sarga, verses in data.items():
        for num, entry in verses.items():
            missing = [k for k in ("text_devanagari", "transliteration", "translation")
                       if not entry.get(k)]
            if missing:
                gaps.append((sarga, num, missing))
    return gaps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("dataset/uttara-eText-ramayana-info.json"))
    ap.add_argument("--first", type=int, default=FIRST_SARGA)
    ap.add_argument("--last", type=int, default=LAST_SARGA)
    args = ap.parse_args(argv)

    data = harvest(args.first, args.last)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    total = sum(len(v) for v in data.values())
    gaps = gap_profile(data)
    print(f"harvested {total} verses -> {args.out}; "
          f"{len(gaps)} verse-field gaps "
          f"({'complete' if not gaps else 'run gap-fill'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
