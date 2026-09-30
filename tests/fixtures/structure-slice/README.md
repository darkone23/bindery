# structure-slice fixture

Seven pages of the HOL-251 ingest archive (`archive/page-0283.png` …
`page-0289.png`), deterministically downscaled 2× to 300 dpi grayscale
(PIL LANCZOS) to keep the repo light. The slice spans Ayodhya Kanda's
title page + Canto I (page 283) through the Canto II heading (page 289),
so one committed slice exercises a kanda title page, a canto boundary,
verse-number runs and the two-column body layout.

Regenerate from a fresh ingest with:

```sh
python3 - <<'EOF'
from PIL import Image
from pathlib import Path
out = Path("tests/fixtures/structure-slice")
out.mkdir(parents=True, exist_ok=True)
for p in range(283, 290):
    im = Image.open(f"archive/page-{p:04d}.png")
    w, h = im.size
    im.convert("L").resize((w // 2, h // 2), Image.LANCZOS).save(out / f"page-{p:04d}.png", optimize=True)
EOF
```

Consumed by `tests/test_structure_fixture.py` (run via `just
structure-fixture`), which drives the real docling + tesseract pipeline
over this slice.
