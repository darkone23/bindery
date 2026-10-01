"""Enhance-stage tests: profile-driven per-page ops (border/rail removal,
levels normalization).

Unit tests prove `enhance_page` op math on synthetic rasters; the fixture
test proves `bindery enhance` end-to-end on a tiny committed 3-page PDF
archive (tests/fixtures/fixture3.pdf) — near-no-op expected on the clean
vector body, with per-page ops + diffs recorded in the enhanced manifest.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "fixture3.pdf"
SOURCE_URL = "fixture://tests/fixtures/fixture3.pdf"
DEFAULT_OPS = {
    "border_pt": {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
    "levels": {"black_pct": 0.5, "white_pct": 99.5},
}


def load_bindery():
    spec = importlib.util.spec_from_file_location("bindery", REPO / "bindery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bindery():
    return load_bindery()


@pytest.fixture(scope="module")
def archive(tmp_path_factory, bindery):
    out = tmp_path_factory.mktemp("archive")
    bindery.ingest(FIXTURE, out, dpi=150, source_url=SOURCE_URL, gray=True)
    return out


# --- unit: enhance_page op math -------------------------------------------

def test_levels_noop_on_full_range(bindery):
    # page-like histogram: black text rows + full white field, spanning 0..255
    img = Image.new("L", (32, 32), 255)
    for y in range(0, 32, 4):          # dense text rows, darkest pixels at 0
        for x in range(0, 32, 2):
            img.putpixel((x, y), x * 8 % 255)
    for x in range(0, 32, 2):
        img.putpixel((x, 0), 0)
    out, applied, details = bindery.enhance_page(img, DEFAULT_OPS, dpi=72)
    assert "levels:no-op" in applied
    assert out.tobytes() == img.tobytes()
    assert details["levels"] == {"black": 0, "white": 255}


def test_levels_stretches_compressed_range(bindery):
    img = Image.new("L", (8, 8), 0)
    for y in range(8):
        for x in range(8):
            img.putpixel((x, y), 100 + (x * 4 + y * 4))  # values 100..156
    out, applied, _ = bindery.enhance_page(img, DEFAULT_OPS, dpi=72)
    assert "levels" in applied
    lo, hi = out.getextrema()
    assert lo == 0 and hi == 255


def test_levels_keeps_dark_pixel_at_zero(bindery):
    img = Image.new("L", (8, 8), 255)
    for x in range(8):
        img.putpixel((x, 0), 40)  # dark row well under the 0.5 pct tail
    out, applied, _ = bindery.enhance_page(img, DEFAULT_OPS, dpi=72)
    assert "levels" in applied
    assert out.getpixel((0, 0)) == 0


def test_border_crop_removes_rail(bindery):
    img = Image.new("L", (20, 20), 255)
    for x in range(20):
        for y in range(20):
            if x < 3 or x >= 17 or y < 2 or y >= 18:
                img.putpixel((x, y), 0)  # black rail/border frame
    ops = {
        "border_pt": {"left": 3.0, "right": 3.0, "top": 2.0, "bottom": 2.0},
        "levels": {"black_pct": 0.5, "white_pct": 99.5},
    }
    out, applied, details = bindery.enhance_page(img, ops, dpi=72)
    assert "border" in applied
    assert out.size == (14, 16)
    assert details["border_px"] == [3, 2, 17, 18]
    assert out.getextrema() == (255, 255)  # rails fully gone


def test_border_zero_pt_is_recorded_noop(bindery):
    img = Image.new("L", (10, 10), 128)
    out, applied, details = bindery.enhance_page(img, DEFAULT_OPS, dpi=72)
    assert "border" not in applied
    assert details["border_px"] is None


# --- fixture: bindery enhance end-to-end ----------------------------------

def test_enhance_builds_enhanced_archive(archive, bindery):
    book = {"enhance": DEFAULT_OPS}
    meta = bindery.enhance(book, archive, Path("build-enh-test"))
    out = Path("build-enh-test") / "enhance"
    try:
        names = sorted(p.name for p in out.glob("page-*.png"))
        assert names == ["page-0001.png", "page-0002.png", "page-0003.png"]
        man = json.loads((out / "manifest.json").read_text())
        assert man["stage"] == "enhance"
        assert len(man["pages"]) == 3
        for entry in man["pages"]:
            f = out / entry["file"]
            assert f.is_file(), entry["file"]
            assert bindery.sha256_file(f) == entry["sha256"]
            assert "ops" in entry and "details" in entry
            assert entry["ops"], "every page records its op list"
    finally:
        import shutil
        shutil.rmtree("build-enh-test", ignore_errors=True)


def test_enhance_records_ops_on_fixture_body(archive, bindery):
    # the 150dpi fixture renders antialiased light text (no pixel darker
    # than ~115), so levels normalization legitimately applies — the
    # point is that every page records its ops + levels diff
    book = {"enhance": DEFAULT_OPS}
    out = Path("build-enh-test2")
    meta = bindery.enhance(book, archive, out)
    try:
        man = json.loads((out / "enhance" / "manifest.json").read_text())
        ops_seen = {tuple(e["ops"]) for e in man["pages"]}
        assert all("border" not in ops for ops in ops_seen)
        assert man["enhance"]["touched_pages"] == len(man["pages"])
        for e in man["pages"]:
            lv = e["details"]["levels"]
            bands = lv if isinstance(lv, list) else [lv]
            assert all(b["white"] == 255 for b in bands)
            assert all(b["black"] < 120 for b in bands)
    finally:
        import shutil
        shutil.rmtree(out, ignore_errors=True)


def test_enhance_is_near_noop_on_clean_body(bindery, tmp_path):
    # synthetic clean vector body: full-range pages -> levels recorded no-op
    arch = tmp_path / "clean-archive"
    arch.mkdir()
    (arch / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "stage": "ingest",
        "source": {"pages": 2, "url": "fixture://synthetic", "file": "synthetic.pdf",
                   "sha256": "0" * 64, "size_bytes": 1, "pdfinfo": {"Pages": 2}},
        "render": {"dpi": 600, "format": "png", "gray": True},
        "pages": [
            {"page": 1, "file": "page-0001.png", "sha256": "0" * 64, "size_bytes": 1},
            {"page": 2, "file": "page-0002.png", "sha256": "0" * 64, "size_bytes": 1},
        ],
    }))
    for i in (1, 2):
        img = Image.new("L", (64, 64), 255)
        for y in range(0, 64, 4):       # text rows spanning full range
            for x in range(0, 64, 2):
                img.putpixel((x, y), x * 4 % 255)
        for x in range(0, 64, 2):
            img.putpixel((x, 0), 0)
        img.save(arch / f"page-{i:04d}.png")
    meta = bindery.enhance({"enhance": DEFAULT_OPS}, arch, tmp_path / "out")
    man = json.loads((tmp_path / "out" / "enhance" / "manifest.json").read_text())
    assert man["enhance"]["near_noop_pages"] == 2
    assert all(e["ops"] == ["levels:no-op"] for e in man["pages"])
    for e in man["pages"]:
        # enhanced raster is pixel-identical to source for a no-op page
        src = Image.open(arch / e["file"]).tobytes()
        got = Image.open(tmp_path / "out" / "enhance" / e["file"]).tobytes()
        assert got == src


def test_enhance_manifest_feeds_verify_and_order(archive, bindery, tmp_path):
    book = {"enhance": DEFAULT_OPS}
    out = tmp_path / "enh"
    bindery.enhance(book, archive, out)
    # enhanced dir is a first-class archive: verify + order both consume it
    assert bindery.verify(out / "enhance") == 0
    book_full = {"source": {"archive": str(out / "enhance")},
                 "order": {"slice": {"first": 1, "last": 3}}}
    order = bindery.build_order(book_full, out / "enhance", tmp_path / "order.json")
    assert [p["archive_page"] for p in order["pages"]] == [1, 2, 3]
