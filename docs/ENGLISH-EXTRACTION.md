# M5 — Gita Press English extraction + ToC mapping (HOL-264)

The board directive (HOL-250 comment 305927ca, 2026-10-02) names **Gita Press
English prose as canonical** for the household. This stage extracts it in
full from the source PDF and maps the printed Table of Contents into
structured per-sarga data. Fascicle re-rendering with this translation is
NOT in scope (the board may ask later).

## Source

- `dataset/Valmiki_Ramayana_Gita_Press.pdf` (gitignored; `just dataset-fetch`)
  — 2303 pages, text layer present (PageMaker 6.5 / Distiller 5.0.5).
- sha256 `cc2d7668b77dd36830cb2ba8e7b90d9e94b4e6d6b38bd1a34f19bc5ec74a7804`
  (same file as the M0 ingest — `archive/manifest.json`).
- Sanskrit text, where needed, comes from GRETIL / ramayana.info (M4
  pipeline); this stage is **English-only**.

## Pipeline (`just extract-english` → `extract_english.py`)

1. `pdftotext -layout` over the whole PDF (one pass), pages split on form
   feeds. `-layout` reproduces the two-column body (English prose left,
   Sanskrit verse + English metrical translation right) and the dotted-leader
   ToC pages faithfully.
2. **Chrome strip** (`strip_page_chrome`): running heads (`NNN * TITLE *`,
   `* TITLE * NNN`, `(NNN)` on ToC pages), bare folio numbers, `OÀ`/`O°À` Om
   marks, lone `U` folio marks. Everything stripped is enumerated in the
   page sidecar's `flags`; content lines are never dropped.
3. **Diacritics normalization** (`normalize`): the print encodes IAST in a
   legacy 8-bit glyph set. The mapping (below) is built empirically from the
   full-document glyph inventory and verified against known vocabulary.
   Devanagari-body text (a separate custom-encoded population, ~60 glyphs)
   is flagged by a deterministic word classifier and left untouched — never
   transliterated.
4. **ToC parse** (`parse_toc_page`, `toc_entries`): archive pages 21–58
   (Part I = kandas 1–4) and 1170–1190 (Part II = kandas 5–7). Entries may
   wrap lines (hanging indent); each closes at its dotted leader + printed
   page number. Kanda attribution is line-position aware (a kanda's ToC can
   start mid-page, under the previous kanda's last entries).
5. **Sarga assembly** (`assemble_sargas`): canonical sequence walk (kanda k
   sarga n → k+1 …). Both printed markers can advance it in line order:
   `Canto <Roman>` headings (within 40 pages of the ToC start) and
   `Thus ends Canto <words> … <Kanda>kāṇḍa` closers (they name their own
   kanda). Pre-heading lines on a heading page go to the previous sarga when
   they carry its closer, to the new sarga on kanda-opener pages, else to
   the previous owner. Non-matching markers are flagged, never used; a
   sarga reached by neither marker gets its ToC page range appended whole
   (`range_fallback`) plus a stall-recovery path.

## Printed → archive page offsets

- **Part I: printed = archive (offset 0)** — derived from body folios
  `(57)`, `349`, `350`, `669`, `670`, `1167`, `1168` and the ToC p.21 entry
  "Canto 1 … 59" landing on archive 59.
- **Part II: printed = archive − 1167** — derived from body folios
  `992`@2159, `333`@1500, `1033`@2200, `1136`@2303 and ToC folio `(23)`@1190.
  Part II restarts at archive 1169 (title page); its ToC pages carry fresh
  printed numbering 2–23.

## Mapping table (MAPPING_VERSION 1)

Built from the low-frequency legacy-diacritic inventory (English-zone
glyphs); the high-frequency Devanagari-body glyphs (Ê Ã ◊ Á ﬂ ÿ Ÿ ⁄ ‚ ¢? …)
are a separate population, flagged never mapped.

| glyph | → | evidence |
|---|---|---|
| å | ā | Råmå→Rāmā, BålakåƒŒa |
| ∂ | ī | Vålm∂ki, Kaikey∂, Sugr∂va |
| µu | ū | Citrakµu¢a→Citrakūṭa, ›µurpaƒakhå, Sarayµu (ligature) |
| µ (bare) | *(dropped)* | 2 print typos: lifµe→life, Sumitrµå→Sumitrā |
| æ / Æ | ṛ | Bæhaspati, Smæti, Vætra |
| ƒ | ṇ | Råmåyaƒa, Kumbhakarƒa, DaƒŒaka |
| ∆ | ṅ | La∆kå, A∆gada, Ga∆gå |
| ¢ | ṭ | Ja¢åyu, Citrakµu¢a |
| ¶ | ṣ | Lak¶maƒa, Vi¶ƒu, Tak¶a‹ilå |
| ¤ | ñ | Krau¤ca, Pa¤cava¢∂, A¤janå |
| ‹ | ś | Da‹aratha, A‹oka, Vi‹wåmitra |
| › | Ś | ›r∂, ›iva, ›atrughna |
| Œ | ḍ | GaruŒa (print uses the diacritic form) |
| ¨ | ḥ | Uccai¨‹ravå, Mana¨‹ilå, Sµurya¨ |
| ≈ | ṃ | sarva≈, draviƒa≈ (≈h→ṃh falls out) |
| í / ë | ’ / ‘ | oneís, ëRåmaí |
| ì / î | “ / ” | ìSo be itî, you.î |
| ó / ñ | — / – | Kåmaóthe, (8ñ10) |
| §R | Ṛ | §R¶i→Ṛṣi, §R¶ya‹æ∆ga (ligature pair) |
| °N | Ṇ | RÅMÅYA°NA→RĀMĀYAṆA (dot precedes the letter) |
| °{2,} | *(leader dots)* | caps ToC kanda headers |
| Å / ∫ | Ā / ī·Ī | caps running heads; ∫ case-aware (∫tis→ītis, SARASWAT∫) |
| œ / ® | Ḍ / Ṣ | UTTARAKÅ°NœA, KI®KINDHÅKÅ°NœA (caps heads/colophons) |

Already-correct Unicode passes through untouched: `— – ‘ ’ “ ” … † ×`.

## Outputs

| path | git? | what |
|---|---|---|
| `build/english/pages/page-NNNN.{txt,json}` | no | per-page cleaned+normalized text + sidecar (archive page, printed page, sarga/kanda ref from the ToC ranges, chrome flags, unmapped-glyph counts) |
| `build/english/toc.json` | **yes** → `dataset/toc-gita-press-english.json` | structured ToC: per kanda `{part, kanda, name, sargas:[{canto_no, title, printed_page, archive_page}]}` + quirks + unattributed |
| `build/english/sargas-index.json` | **yes** | per-sarga metadata (ranges, flags, closers, heading pages — no text) |
| `build/english/sargas/kKK-sNNN.txt` | no | per-sarga English prose (lines whose words are not Devanagari-encoding; mixed rows keep their Devanagari tail) |
| `build/english/qc.{json,md}` | **yes** → `dataset/english-extraction-QC.md` | coverage, gaps, spot checks, reconciliation |

Large text outputs stage to `~/bindery-m5-storage/english/` on the paperclip
VM (`just m5-stage`, writes a provenance manifest with the extraction
commit) and reach the TrueNAS dataset by the HOL-258 two-hop
(`just storage-sync` pattern from the laptop; the NAS has no route to the VM).

## Schema

```jsonc
// toc.json (extract)
{ "schema_version": 1, "source": {"url": "...", "sha256": "...", "pages": 2303},
  "mapping_version": "1",
  "part_offsets": {"1": 0, "2": 1167},
  "kandas": [ { "part": 1, "kanda": 1, "name": "Bālakāṇḍa",
                "sargas": [ { "canto_no": 1, "title": "...",
                              "printed_page": 59, "archive_page": 59 } ] } ],
  "quirks": [ "..." ], "unattributed": [] }

// page sidecar (page-NNNN.json)
{ "archive_page": 59, "printed_page": 59, "kanda": 1, "sarga": 1,
  "flags": ["chrome:header"], "unmapped_glyphs": {} }

// sargas-index.json (extract per sarga)
{ "part": 2, "kanda": 7, "sarga": 42, "title": "...",
  "printed_page": 992, "archive_start": 2159, "archive_end": 2161,
  "pages": [2159, 2160, 2161], "closers": [2159], "heading_pages": [2159],
  "flags": [] }
```

## Print quirks (flagged, not repaired)

Found by this extraction; all carried as flags/quirks in the datasets:

- **Kanda 6 ToC band (p1177)**: entries for true sargas 2–9 are printed with
  the numbers 12–19 (between sargas 1 and 10); their page refs (295–320) slot
  monotonically. Resolved by page-order pairing, flagged
  `renumbered_band`, each record keeps `printed_as`.
- **Kanda 7 @2168**: heading printed `Canto LVI` where XLVI (46) belongs —
  a dropped `X` (the M2 "numeral omission at 2168" zone).
- **Kanda 4 @~1156**: heading printed `Canto XLIII` where LXIII (63) belongs
  (dropped `L`; the M2 "numeral omission at 1154" zone).
- **Corrupted closer** (k6 s67, p1740): `Thus ends Canto Sixty-sevem` (m for
  n) — unparseable by design; flagged.
- **Closer variants tolerated**: `Thus end(s)` ± `of`/`the`, lowercase
  `canto`, dropped `in`/`the`, and k5's `of the Sundarakāṇḍa in the…`
  word order.
- **Dropped-glyph closers** (k2 s12/s91, k4 s49): `kåƒda` / `kaƒŒa` shapes
  that don't resolve — flagged `closer_not_found`.
- **Uttara reconciliation vs the committed M2 map**: 70/71 sarga starts
  agree; s95 disagrees (ToC + body heading agree on archive 2271 =
  `Canto LXXXXV`; the M2 map says 2273 = s96's heading page). The M2 map
  is the outlier; left as-is per flag-not-repair.
- Shared heading pages (a closer and the next heading on one page) and
  heading pages ±few pages off their ToC start are normal here; flagged
  `heading_before/after_start_page` when they drift.

## Verification

- `nix develop -c pytest -q tests/` — 142 tests incl. mapping-vs-vocabulary,
  chrome stripper, ToC parser on the committed page-21/1190 slices, closer
  variants, band resolution, assembler boundaries, QC units.
- `nix build` — flake check + pytest gate.
- `just extract-english` — 2303/2303 pages, 645/645 sargas, zero unmapped
  glyphs in English zones, 12/12 word-for-word spot checks (see
  `dataset/english-extraction-QC.md`).
