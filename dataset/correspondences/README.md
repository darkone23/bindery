# Correspondences — Ramayana reference spine

Cross-reference datasets mapping passages in derivative works (novels, films,
retellings) back to the Valmiki Ramayana kandas/sargas they paraphrase,
interpolate, or draw on — without the derivative work saying so itself.

Pilot ask (HOL-263): *The Dream of Ravan: A Mystery* (DUM serial 1853–54;
1895 Theosophical reprint) and the film *Bajrangbali* (1976, dir. Chandrakant).

## Numbering policy (the spine)

- `kanda` + `sarga` follow the **Gita Press vulgate numbering** — the 1970s
  Gita Press *Valmiki-Ramayana* edition whose scans are the bindery archive
  (`~/src/bindery/archive`, 2303 pages). This is the household's primary
  English text per board direction; the ramayana.info harvest
  (`dataset/uttara-eText-ramayana-info.json`) already matches this numbering
  sarga-for-sarga (verified in HOL-259).
- Kanda slugs match ramayana.info URL slugs: `bala ayodhya aranya
  kishkindha sundara yuddha uttara`.
- Sarga strings are `"N"` or `"N-M"`; `"various"` marks whole-work or
  unplaceable spans. Verse-level anchoring is future work (GP scans +
  ramayana.info give verse numbers once needed).
- When a derivative text cites a *different* edition's numbering (e.g. the
  Schlegel/Gorresio Bala-kanda), record it in `source_citation_in_text` and
  translate to spine numbers in `refs` + `notes`.

## Dataset file format (`correspondences/v1`)

```json
{
  "schema": "correspondences/v1",
  "dataset": "<short-id>",
  "description": "...",
  "target": {
    "work": "Valmiki-Ramayana",
    "numbering": "gita-press-vulgate",
    "numbering_notes": "..."
  },
  "sources": [{
    "id": "<source-id>", "title": "...", "source_type": "text|film",
    "publication": "...", "url": "...", "locator_type": "page|timestamp",
    "notes": "..."
  }],
  "entries": [{
    "id": "<source_id>-NNN",        // source-scoped, zero-padded 3+ digits,
                                    // unique within the dataset; matches the
                                    // raw inventory ids (dor-001, baj-001)
    "source_id": "<source-id>",
    "kind": "summary|narrative|gloss|scene",
    "locator": "p. 121 | TBD",      // page (text) or timestamp (film)
    "source_lines": "4392-4565",    // optional; OCR/source-file line anchor
    "quote": "...",                 // verbatim from the source (text sources)
    "episode": "what the passage retells",
    "refs": [{                      // >=1 unless beyond_valmiki is true
      "kanda": "<slug>", "sarga": "N|N-M|various",
      "confidence": "high|medium|low",
      "verified_against": "ramayana.info aranya/33,34"  // when checked
    }],
    "beyond_valmiki": false,        // motif absent from Valmiki (later
                                    // vernacular/Puranic/author invention)
    "source_citation_in_text": null,// the source's own citation, if any
    "notes": "..."
  }]
}
```

Confidence is about the *mapping*, not the scene: `high` = episode uniquely
identifies the sarga range; `medium` = match but approximate; `low` = generic
motif or synopsis-derived scaffold. `verified_against` is recorded only when
the anchor was actually checked against a GP-numbered text (ramayana.info
pages fetched per sarga). `beyond_valmiki: true` flags material Valmiki does
not have (Lakshmana-rekha, Sulochana, Adhyatma-style motives) — the mapping
then points to the nearest contextual sarga or is omitted.

## Method

1. Read the derivative work end to end (OCR text via archive.org
   `…/download/<id>/<id>_djvu.txt` where available); inventory every
   Ramayana-drawing passage with line + page anchors (the intermediate
   inventory ships beside the dataset: `dor-inventory.jsonl` / `.md`).
2. Anchor each passage to kanda/sarga against the GP-numbered spine —
   spot-verify by fetching `https://ramayana.info/story/<kanda>/<sarga>/`
   and matching distinctive tokens in the embedded translations.
3. Validate with `just correspondences-validate` (schema + enum + id
   hygiene; pytest pins it in `tests/test_correspondences.py`).

## Datasets

| file | source | entries |
|------|--------|---------|
| `dream-of-ravan.json` | *The Dream of Ravan: A Mystery* (1895 ed.) | 20 |
| `bajrangbali-1976.json` | *Bajrangbali* (1976 film) | 7 (scaffold) |
