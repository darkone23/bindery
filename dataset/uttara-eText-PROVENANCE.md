# Uttara e-text — provenance (HOL-259 M4a)

Source: ramayana.info/story/uttara/{42..111}/ — board-directed (card
rejection reason + plan rev 3/4 acceptance, 2026-10-01). The site's Next.js
pages embed an RSC payload with one escaped-JSON object per verse
("shloka"): text_devanagari (samhita), text_devanagari_alt (alternate
rendering), transliteration (IAST), translation (English). Extraction:
`just uttara-eText` (fetch_uttara_etext.py — parses the escaped payload,
strips sarga-colophon and kanda-end marker objects).

Dataset: 70 sargas (42–111), 1672 verses, numbering identical to the Gita
Press volume (verified against printed headings at sargas 42, 44, 107–108,
110; the GRETIL vulgate numbers the same content 41–100 — its Uttara ends
at sarga 100).

Harvest notes (M4b re-harvest): Next.js streams the payload in fragments —
the seams sit inside escaped-JSON strings and must be stripped before
parsing (`strip_rsc_seams`); the strip recovered 4 seam-split verses
(51, 53, 92, 100) and closed all 17 field gaps site-natively, so the
gap-fill pass now reports 0 fills (the script remains as fallback and
for scan-anchored QC). Site markdown artifacts (LaTeX-style verse
markers `\( n\)`, double-escaped quotes) are unescaped in the parser;
no backslashes reach the data. Sarga 111 verse 26 is absent on the site.
The generated-IAST cross-validation (90.9% exact vs the site's own
transliteration across all verses) remains as a dataset test floor.

References (consulted, not bulk sources):
- GRETIL Tokunaga/Smith Rāmāyaṇa (CC BY-NC-SA 4.0) — Sanskrit cross-check
  for sargas 42–100.
- Baroda critical edition, vol. VII (U. P. Shah, 1975), archive.org
  `RmyaaCriticalEdition7EDUPShah1975` — editorial note: the critical text
  reconstructs a 100-sarga Uttara; this fascicle deliberately follows the
  Gita Press vulgate (111 sargas), the text of the book it completes.

Board sample scans (layout reference only) live in `srcA-sample/`.
