# Printing the M1 proof (build/press.pdf)

This prints the 20-page proof slice (archive pages 400–419) as **3
signatures of 8+8+4 pages = 5 duplex US-Letter sheets**. Fold + nest +
sew (or clip) to check the geometry by hand.

## Print settings

| Setting | Value |
|---|---|
| Paper | US Letter, portrait, plain |
| Duplex | **ON — flip on LONG edge** |
| Scaling | **100% / "Actual size"** — never "fit to page" |
| Auto-rotate | OFF |
| Pages | all 10 PDF pages (5 sheets × 2 sides) |

The imposition assumes **long-edge duplex on portrait paper** (the
sheet flips left-right, like turning a page). If your driver exposes
"flip on short edge" for portrait jobs, that is the wrong mode — the
back sides will land upside down. The registration block makes this
visible immediately (below).

## How the sheets are organized

Each physical sheet carries 4 book pages (2 per side). PDF page order =
print order: sheet 1 front, sheet 1 back, sheet 2 front, sheet 2 back, …

- **SIG1** (book pages 1–8): sheets 1–2. Fold both, nest sheet 1
  outside sheet 2.
- **SIG2** (book pages 9–16): sheets 3–4. Same nesting.
- **SIG3** (book pages 17–20): sheet 5, a single sheet.

Assembled book: SIG1, then SIG2, then SIG3, all folded the same way.

## Folding

1. Fold each sheet along the horizontal **fold marks** (the short ticks
   at the sheet edges, center of the sheet) — top half down onto the
   bottom half, printed side out.
2. Rotate the folded packet 90° **counterclockwise**: the spine (fold)
   is now on the left and the pages read upright.
3. Nest: SIG1's sheet 1 wraps sheet 2; SIG2 the same; SIG3 is alone.
4. Stack SIG1 + SIG2 + SIG3 in order and clip or sew at the fold.

## Verifying with the registration block

- Every sheet has a small **black block with a white cross** centered
  on the fold line. On front and back it sits at the same position:
  hold a sheet up to the light — the two blocks must coincide. Offset
  blocks = duplex registration drift (note it; drift beyond ~1 mm needs
  printer calibration before the mass run).
- The margin label on every side reads e.g.
  `SIG1 SHEET1/2 FRONT pages 2|7` — check the pairing against the list
  above while collating.
- After folding, every page should be **upright with its spine at the
  fold**. Page 1 is the outer face of SIG1's sheet 1; pages 2|7 form
  its center spread; the last sheet's center spread is 18|19.
- Cut marks (short line pairs at each page corner) show the trim box if
  you want to trim the block flush: cut on the marks, keeping the fold
  side intact.

## Regenerating

Everything is reproducible from the repo (archive pages 400–419 of the
HOL-251 dataset):

```sh
just proof     # assemble -> trim -> impose: build/press.pdf + proof-screen.pdf
```

`build/proof-screen.pdf` is the same 20 pages in reading order for
on-screen checking; `build/press.pdf` is the print file.
---

# M3 full-volume proof (HOL-256)

`just impose --full` (or `just full`) runs the complete chain on **all
2303 archive pages + the apparatus leaves**:

```sh
just full          # enhance -> apparatus -> assemble -> trim -> impose
```

Outputs (build/):

| Artifact | What it is |
|---|---|
| `enhance/` | profile-ops result; originals untouched, per-page diffs in its manifest |
| `apparatus/` | preface + ToC + errata leaves, typeset at trim geometry |
| `order.json` | the full-volume sequence: apparatus first, then archive 1–2303 |
| `trim/` | trimmed pages (uncropped body pages pass through untouched) |
| `press.pdf` | 16-page signatures, duplex Letter, ~580 sheets — the print file |
| `proof-screen.pdf` | the same pages in reading order for on-screen proofing |

## Trim profile (documented default)

The source page of source B is 444 x 667.44 pt; the default trim profile
keeps it whole and scales it to Letter with working margins. The board's
trim-size confirmation remains open — it can override this profile in
`book.toml` before any physical run.

## What is different from the M1 proof

- **16-page signatures** (4 nested sheets each) instead of 8.
- **Apparatus leaves in front** (positions 1–N): preface, ToC (sarga
  rows from the structure map, with the Part-Two printed-numbering
  offset note), errata (print quirks recorded, not corrected). Positions
  N+1…N+2303 are archive pages 1–2303 in order.
- Near-no-op **enhance** pass sits in front of assemble; its manifest
  records every per-page op and diff.

---

# M4 — the Uttara-kanda fascicle (HOL-259, plan rev 4, typeset)

This is the current deliverable: the missing cantos, **typeset to mirror
the 1970s edition** (the scanned M3 supplement is superseded). One
command rebuilds everything:

```sh
just fascicle     # typeset sargas 42-111 -> trim -> impose
```

Outputs (build/):

| Artifact | What it is |
|---|---|
| `typeset/` | the rendered raster archive (600 dpi) + manifest; page 1 is the title page (editorial note), page 2 the ToC, pages 3+ the sargas |
| `order.json` | the fascicle sequence (pages-mode) |
| `trim/` | pass-through trims (the typeset canvas IS the page: 444 × 667.44 pt) |
| `press.pdf` | **66 duplex US-Letter sheets in 17 signatures** — the print file |
| `proof-screen.pdf` | all 262 pages in reading order for on-screen proofing |

## Print settings

Same as the M1 proof (see the first section above): US Letter portrait,
**duplex ON, flip on LONG edge**, 100% scale, auto-rotate off, all 132
PDF pages (66 sheets × 2 sides).

## Sheet organization

16-page signatures (4 nested sheets each) for signatures 1–16; the last
signature (pages 259–262) is a single nested pair (2 sheets). Every side
carries a margin label — `SIGn SHEETm/k FRONT|BACK pages a|b` — collate
against the labels, not against arithmetic. Folding is identical to the
M1 proof: fold top half down, rotate 90° CCW (spine left), nest per
signature, stack signatures in order.

## Reading-order proofing

`build/proof-screen.pdf` shows the pages at trim size in reading order —
check the Devanagari verse blocks (conjuncts, matras), the two-column
translation with per-verse `(n)` anchors, the running head + folio, the
canto headings, and the title page's editorial note before printing.

## Sourcing and provenance

Text: ramayana.info (Sanskrit + English), cross-checked against GRETIL
(Tokunaga/Smith, sargas 42–100 = vulgate 41–100) — see
`dataset/uttara-eText-PROVENANCE.md` and `dataset/uttara-eText-QC.md`.
The vulgate's 111-sarga Uttara is followed deliberately; the editorial
note on the title page explains the relationship to the Baroda critical
edition (Shah 1975). Regenerate the text data with `just uttara-eText`.
