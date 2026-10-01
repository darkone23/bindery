"""M2 structure-stage fixture test: the real pipeline (docling layout +
tesseract OCR) over a committed 7-page slice of the archive.

The slice is archive pages 283–289 at 300 dpi grayscale — Ayodhya
Kanda's title page + Canto I (page 283) through the Canto II heading
(page 289) — so one slice exercises a kanda title, a canto boundary,
verse-number runs and the two-column body layout.

Skipped unless docling + tesseract are importable/on PATH, i.e. run it
via `just structure-fixture` (the structure shell); the pure `nix build`
check skips it. First run downloads the docling layout models to
~/.cache/docling (network needed once).
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "structure-slice"
PAGES = list(range(283, 290))

pytest.importorskip("docling.document_converter")
if shutil.which("tesseract") is None:
    pytest.skip("tesseract not on PATH (use `just structure-fixture`)", allow_module_level=True)

spec = importlib.util.spec_from_file_location("structure", REPO / "structure.py")
structure = importlib.util.module_from_spec(spec)
sys.modules["structure"] = structure
spec.loader.exec_module(structure)


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("structure")
    structure.docling_layout_pass(FIXTURE, out, PAGES, chunk=8)
    structure.tesseract_ocr_pass(FIXTURE, out, PAGES, workers=2)
    structure.map_step(FIXTURE, out, PAGES[0], PAGES[-1])
    return out


def test_raw_pass_outputs_present(out_dir):
    for p in PAGES:
        assert (out_dir / "pages" / f"page-{p:04d}.layout.json").is_file()
        assert (out_dir / "pages" / f"page-{p:04d}.ocr.json").is_file()


def test_passes_are_resumable(out_dir):
    # rerunning both passes over the same output is a no-op (cached)
    structure.docling_layout_pass(FIXTURE, out_dir, PAGES)
    structure.tesseract_ocr_pass(FIXTURE, out_dir, PAGES)
    assert len(list((out_dir / "pages").glob("*.layout.json"))) == len(PAGES)
    assert len(list((out_dir / "pages").glob("*.ocr.json"))) == len(PAGES)


def test_records_written(out_dir):
    for p in PAGES:
        assert (out_dir / "records" / f"page-{p:04d}.json").is_file()


def test_kanda_title_page_signals(out_dir):
    import json
    rec = json.loads((out_dir / "records" / "page-0283.json").read_text())
    d = rec["derived"]
    assert d["canto_heading"] is not None
    assert d["canto_heading"]["numeral"] == "I"
    assert d["title_book_token"] == "two" or d["kanda_title"] == "ayodhya"


def test_canto_boundary_page(out_dir):
    import json
    rec = json.loads((out_dir / "records" / "page-0289.json").read_text())
    d = rec["derived"]
    assert d["canto_heading"] is not None
    assert d["canto_heading"]["numeral"] == "II"


def test_body_pages_locate_columns_and_verses(out_dir):
    import json
    for p in range(284, 289):
        rec = json.loads((out_dir / "records" / f"page-{p:04d}.json").read_text())
        d = rec["derived"]
        assert d["english_bbox"] is not None, f"page {p}: no English column"
        assert d["devanagari_bbox"] is not None, f"page {p}: no Devanagari block"
        assert d["english_word_count"] > 50, f"page {p}: too few English words"
        assert len(d["verse_numbers"]) >= 2, f"page {p}: no verse-number run"
        # Devanagari verses interleave with the English column: the block
        # unions overlap vertically on a two-column page.
        assert d["english_bbox"][3] > d["devanagari_bbox"][1]


def test_vector_pages_are_clean(out_dir):
    import json
    for p in PAGES:
        rec = json.loads((out_dir / "records" / f"page-{p:04d}.json").read_text())
        st = rec["image_stats"]
        assert st["blur_lapvar"] > structure.BLUR_FLAG_THRESHOLD, \
            f"page {p}: unexpectedly soft (vector render should be sharp)"
        assert abs(st["skew_deg"]) <= structure.SKEW_FLAG_DEG, \
            f"page {p}: unexpectedly skewed"


def test_sarga_map_from_slice(out_dir):
    import json
    smap = json.loads((out_dir / "sarga-map.json").read_text())
    assert len(smap["kandas"]) == 1
    k = smap["kandas"][0]
    assert k["kanda"] == 2 and k["name"] == "Ayodhya"
    assert k["start_page"] == 283
    starts = {s["sarga"]: s["start_page"] for s in k["sargas"]}
    assert starts.get(1) == 283
    assert starts.get(2) == 289


def test_artifacts_written(out_dir):
    md = (out_dir / "toc-draft.md").read_text()
    assert "Book Two — Ayodhya Kanda" in md
    fid = (out_dir / "fidelity-report.md").read_text()
    assert "kanda 2 Ayodhya" in fid
    assert "## ToC spot-check" in fid
