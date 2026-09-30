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