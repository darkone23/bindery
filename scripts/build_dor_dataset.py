#!/usr/bin/env python3
"""build dream-of-ravan.json from the raw episode inventory.

Input:  dataset/correspondences/dor-inventory.jsonl  (one JSON record/line,
        the raw deep-read inventory of the 1895 djvu.txt OCR text)
Output: dataset/correspondences/dream-of-ravan.json  (correspondences/v1)

The conversion applies the manual verification pass: sarga anchors checked
against GP-numbered ramayana.info pages (bala/27,28 aranya/17,18,25,33,34,42,44
sundara/53,54 yuddha/90,106 kishkindha/19 uttara/8 — see HOL-263), corrected
ranges (Surpanakha's flight to Ravana is aranya 33-34, not 31-32; the astra
grant "dwell in my mind" is bala 27-28), and the source's own citations
([Aranya Kanda — Sarga V] = Adhyatma Ramayana numbering; Schlegel/Gorresio
Adi-kanda XXIX/XXX) are surfaced in source_citation_in_text.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "dataset" / "correspondences"
SRC = HERE / "dor-inventory.jsonl"
OUT = HERE / "dream-of-ravan.json"

# id -> (refs override, source_citation_in_text, notes appendix)
CORRECTIONS = {
    "dor-001": ({"refs": [{"kanda": "ayodhya", "sarga": "14-19", "confidence": "medium",
                           "notes": "Kaikeyi's boons, the banishment decree and 14-year term (editorial recap; composite)"}]},
                None, "Editorial recap of the frame story only."),
    "dor-002": ({"refs": [{"kanda": "aranya", "sarga": "16-18", "confidence": "high",
                           "verified_against": "ramayana.info aranya/18 (nose/ears)"}]},
                None, "Editorial recap; Surpanakha's self-named 'winnowing-basket nails' motif belongs to her aranya 16 introduction."),
    "dor-003": ({"refs": [{"kanda": "aranya", "sarga": "16-18", "confidence": "high",
                           "verified_against": "ramayana.info aranya/17,18 (nose/ears in 18)"}],
                 "source_citation_in_text": "[Aranya Kanda — Sarga V] — but this is the Adhyatma Ramayana's Aranya-kanda numbering, not Valmiki's (vulgate Aranya-kanda sarga 5 is a different episode)"},
                None, "Author cites the Adhyatma Ramayana's numbering while retelling Valmiki's episode — exactly the mis-sourced-paraphrase case HOL-263 targets."),
    "dor-004": ({"refs": [{"kanda": "aranya", "sarga": "24-30", "confidence": "high",
                           "verified_against": "ramayana.info aranya/25 (Khara's destroyed host)"}]},
                None, None),
    "dor-005": ({"refs": [{"kanda": "aranya", "sarga": "24-30", "confidence": "medium"}]},
                None, None),
    "dor-006": ({"refs": [{"kanda": "aranya", "sarga": "33", "confidence": "high",
                           "verified_against": "ramayana.info aranya/33 ('anguished Surpanakha met Ravana')"}]},
                None, "Inventory said aranya 30-31; corrected: the flight to Ravana's court is sarga 33 (30-31 is Akampana's report)."),
    "dor-007": ({"refs": [{"kanda": "aranya", "sarga": "33-34", "confidence": "high",
                           "verified_against": "ramayana.info aranya/33,34"}]},
                None, "Corrected from aranya 31-32."),
    "dor-008": ({"refs": [{"kanda": "aranya", "sarga": "33-34", "confidence": "medium"},
                          {"kanda": "yuddha", "sarga": "98-107", "confidence": "high",
                           "verified_against": "ramayana.info yuddha/106 (Ravana slain)"}]},
                None, None),
    "dor-009": ({"refs": [{"kanda": "aranya", "sarga": "47-51", "confidence": "medium"},
                          {"kanda": "yuddha", "sarga": "19-22", "confidence": "medium"},
                          {"kanda": "yuddha", "sarga": "87-90", "confidence": "high",
                           "verified_against": "ramayana.info yuddha/90 (Indrajit slain)"},
                          {"kanda": "yuddha", "sarga": "98-107", "confidence": "high",
                           "verified_against": "ramayana.info yuddha/106"},
                          {"kanda": "sundara", "sarga": "53-54", "confidence": "high",
                           "verified_against": "ramayana.info sundara/53,54 (tail set fire; burning mansions)"}]},
                None, "Whole-story compression; 'takes and burns Lanka' = sundara 53-54 in GP numbering."),
    "dor-010": ({"refs": [{"kanda": "yuddha", "sarga": "87-90", "confidence": "high",
                           "verified_against": "ramayana.info yuddha/90"}]},
                None, None),
    "dor-011": ({"refs": [{"kanda": "yuddha", "sarga": "87-90", "confidence": "medium"}]},
                None, "The later-birth destiny is the author's own fantasy overlay, not Valmiki."),
    "dor-012": ({"refs": [{"kanda": "aranya", "sarga": "16-18", "confidence": "high",
                           "verified_against": "ramayana.info aranya/18"},
                          {"kanda": "yuddha", "sarga": "87-90", "confidence": "medium"}]},
                None, None),
    "dor-013": ({"refs": [{"kanda": "yuddha", "sarga": "6-19", "confidence": "medium"}]},
                None, None),
    "dor-014": ({"refs": [{"kanda": "bala", "sarga": "27-28", "confidence": "high",
                           "verified_against": "ramayana.info bala/27 ('of those weapons'), bala/28 ('residing in my mind')"}],
                 "source_citation_in_text": "RAMAYANA — ADI-KANDA — SARGA XXIX ED. SCHLEGEL / XXX. ED. GORRESIO"},
                None, "Strongest explicit citation in the book — but in 19th-century edition numbering, not GP numbering. GP/vulgate home of the astra grant + 'dwell within my mind' verse is bala 27-28 (content-verified)."),
    "dor-015": ({"refs": [{"kanda": "aranya", "sarga": "37", "confidence": "medium"},
                          {"kanda": "aranya", "sarga": "42-45", "confidence": "high",
                           "verified_against": "ramayana.info aranya/42,44 (deer)"}]},
                None, None),
    "dor-016": ({"refs": [{"kanda": "kishkindha", "sarga": "3-6", "confidence": "medium"}]},
                None, None),
    "dor-017": ({"refs": [{"kanda": "uttara", "sarga": "2-16", "confidence": "medium",
                           "verified_against": "ramayana.info uttara/8 (Kubera conquered)"}]},
                None, None),
    "dor-018": ({"refs": [{"kanda": "bala", "sarga": "66-67", "confidence": "high",
                           "verified_against": "ramayana.info bala/66,67 (Shiva's bow)"}]},
                None, None),
    "dor-019": ({"refs": [{"kanda": "yuddha", "sarga": "19-22", "confidence": "medium"},
                          {"kanda": "bala", "sarga": "66-67", "confidence": "medium"}]},
                None, None),
    "dor-020": ({"refs": [{"kanda": "sundara", "sarga": "14-16", "confidence": "medium"}]},
                None, None),
}


def convert() -> int:
    records = [
        json.loads(line)
        for line in SRC.read_text().splitlines()
        if line.strip()
    ]
    entries = []
    for r in records:
        cid = r["id"]
        corr = CORRECTIONS.get(cid)
        if not corr:
            print(f"no correction entry for {cid}", file=sys.stderr)
            return 1
        refs = corr[0]["refs"]
        for ref in refs:
            ref.setdefault("notes", None)
        notes = r.get("notes") or ""
        extra = corr[2]
        if extra:
            notes = f"{notes} {extra}".strip()
        entry = {
            "id": cid,
            "source_id": "dor",
            "kind": r["kind"],
            "locator": f"p. {r['page']}",
            "source_lines": r["lines"],
            "quote": r["quote"],
            "episode": r["episode"],
            "refs": refs,
            "beyond_valmiki": bool(r.get("beyond_valmiki")),
            "source_citation_in_text": corr[0].get("source_citation_in_text") or corr[1],
            "notes": notes or None,
        }
        entries.append(entry)

    dataset = {
        "schema": "correspondences/v1",
        "dataset": "dream-of-ravan",
        "description": "Ramayana correspondences in 'The Dream of Ravan: A Mystery' "
                       "(Dublin University Magazine serial 1853-54; 1895 Theosophical "
                       "reprint, preface G.R.S.M.). The work retells Ramayana episodes "
                       "as a Vedantic dream of Ravan — usually without citation; when "
                       "it does cite, it cites other numberings (Adhyatma Ramayana "
                       "Aranya-kanda V; Schlegel/Gorresio Adi-kanda XXIX/XXX).",
        "target": {
            "work": "Valmiki-Ramayana",
            "numbering": "gita-press-vulgate",
            "numbering_notes": "kanda/sarga in the Gita Press 1970s reprint numbering "
                               "(= ramayana.info numbering); GP scans are the bindery archive.",
        },
        "sources": [{
            "id": "dor",
            "title": "The Dream of Ravan: A Mystery",
            "source_type": "text",
            "publication": "Dublin University Magazine 1853-54 (serial); reprint London: "
                           "Theosophical Publishing Society, 1895, 262 pp.",
            "url": "https://archive.org/details/dreamofravanmyst00mead",
            "locator_type": "page",
            "notes": "anonymous; preface signed G.R.S.M. Locators are 1895-edition page "
                     "anchors from the djvu.txt OCR (source_lines = same file's line numbers; "
                     "OCR pages may lag the printed edition by the front matter).",
        }],
        "entries": entries,
        "provenance": {
            "inventory": "dor-inventory.jsonl / dor-inventory.md (raw deep-read, all 8543 OCR lines)",
            "verification": "sarga anchors spot-checked against ramayana.info (GP-numbered) 2026-10-02",
        },
    }
    OUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(entries)} entries -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(convert())
