# Uttara e-text — provenance (HOL-259 M4a)

Source: ramayana.info/story/uttara/{42..111}/ — board-directed (card
rejection reason + plan rev 3/4 acceptance, 2026-10-01). The site's Next.js
pages embed an RSC payload with one escaped-JSON object per verse
("shloka"): text_devanagari (samhita), text_devanagari_alt (alternate
rendering), transliteration (IAST), translation (English). Extraction:
`just uttara-eText` (fetch_uttara_etext.py — parses the escaped payload,
strips sarga-colophon and kanda-end marker objects).

Dataset: 70 sargas (42–111), 1668 verses, numbering identical to the Gita
Press volume (verified against printed headings at sargas 42, 44, 107–108,
110; the GRETIL vulgate numbers the same content 41–100 — its Uttara ends
at sarga 100).

Gaps closed by `just uttara-gapfill` (fill_uttara_gaps.py), every fill
recorded in dataset/uttara-eText-QC.md:
- 4× text_devanagari reconstructed from the site's alt rendering;
- 6× transliteration generated from the Devanagari (deterministic charmap;
  90.9% exact agreement with the site's own IAST across all 1668 verses —
  the remainder is site-side deva/iast drift near page breaks);
- 7× translation lifted from the Gita Press archive scans (pp. 2159–2303,
  the printed translation this fascicle continues) by verse-marker search
  over tesseract eng OCR; read-through QC happens at typesetting time.

References (consulted, not bulk sources):
- GRETIL Tokunaga/Smith Rāmāyaṇa (CC BY-NC-SA 4.0) — Sanskrit cross-check
  for sargas 42–100.
- Baroda critical edition, vol. VII (U. P. Shah, 1975), archive.org
  `RmyaaCriticalEdition7EDUPShah1975` — editorial note: the critical text
  reconstructs a 100-sarga Uttara; this fascicle deliberately follows the
  Gita Press vulgate (111 sargas), the text of the book it completes.

Board sample scans (layout reference only) live in `srcA-sample/`.
