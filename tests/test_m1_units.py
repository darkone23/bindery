"""M1 unit tests: signature plan, trim crop math, creep, order building."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_bindery():
    spec = importlib.util.spec_from_file_location("bindery", REPO / "bindery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def b():
    return load_bindery()


# --- signature plan -------------------------------------------------------

def test_plan_20_pages_sig8(b):
    plan = b.signature_plan(20, 8)
    assert [sig["pages"] for sig in plan] == [8, 8, 4]
    sheets = [s for sig in plan for s in sig["sheets"]]
    assert len(sheets) == 5
    # sheet j (0=outermost) of a signature with S pages:
    # front top 2j+2, front bottom S-2j-1, back top 2j+1, back bottom S-2j
    s0 = plan[0]["sheets"][0]
    assert s0["front"]["top"] == 2 and s0["front"]["bottom"] == 7
    assert s0["back"]["top"] == 1 and s0["back"]["bottom"] == 8
    s1 = plan[0]["sheets"][1]
    assert s1["front"]["top"] == 4 and s1["front"]["bottom"] == 5
    assert s1["back"]["top"] == 3 and s1["back"]["bottom"] == 6
    # second signature continues at page 9
    p20 = plan[1]["sheets"][0]
    assert p20["back"]["top"] == 9 and p20["back"]["bottom"] == 16
    # last signature (4 pages) is a single sheet
    s4 = plan[2]["sheets"][0]
    assert s4["front"]["top"] == 18 and s4["front"]["bottom"] == 19
    assert s4["back"]["top"] == 17 and s4["back"]["bottom"] == 20


def test_plan_padding_blanks(b):
    plan = b.signature_plan(6, 8)
    sig = plan[0]
    assert sig["pages"] == 8  # padded to a foldable multiple of 4
    assert len(sig["sheets"]) == 2
    slots = [v for s in sig["sheets"] for v in
             (s["front"]["top"], s["front"]["bottom"],
              s["back"]["top"], s["back"]["bottom"])]
    assert sorted(v for v in slots if v) == [1, 2, 3, 4, 5, 6]
    assert slots.count(None) == 2
    # blanks fill the outermost sheet's bottom slots (positions 7, 8)
    assert sig["sheets"][0]["front"]["bottom"] is None
    assert sig["sheets"][0]["back"]["bottom"] is None


def test_plan_sig4_two_signatures(b):
    plan = b.signature_plan(8, 4)
    assert [sig["pages"] for sig in plan] == [4, 4]
    assert sum(len(sig["sheets"]) for sig in plan) == 2
    assert plan[1]["sheets"][0]["back"]["top"] == 5


def test_plan_every_page_once(b):
    for n, sig in ((20, 8), (7, 8), (6, 4), (1, 8), (23, 8)):
        plan = b.signature_plan(n, sig)
        seen = []
        for s in plan:
            for sheet in s["sheets"]:
                for face in ("front", "back"):
                    seen.extend(sheet[face].values())
        real = [p for p in seen if p]
        assert sorted(real) == list(range(1, n + 1)), (n, sig)


# --- trim crop math -------------------------------------------------------

def test_trim_crop_default_full_page(b):
    rect = b.crop_rect(page_w=444.0, page_h=667.44, verso=False,
                       depth=0, cfg={})
    assert rect == (0.0, 0.0, 444.0, 667.44)


def test_trim_crop_margins_recto_verso(b):
    cfg = {"inside_pt": 10.0, "outside_pt": 5.0, "top_pt": 2.0, "bottom_pt": 3.0}
    # recto (odd position): inside edge = left
    assert b.crop_rect(444.0, 667.44, verso=False, depth=0, cfg=cfg) == \
        (10.0, 2.0, 439.0, 664.44)
    # verso: inside edge = right
    assert b.crop_rect(444.0, 667.44, verso=True, depth=0, cfg=cfg) == \
        (5.0, 2.0, 434.0, 664.44)


def test_trim_crop_gutter_grows_with_depth(b):
    cfg = {"inside_pt": 10.0, "inside_growth_per_sheet_pt": 2.0}
    d0 = b.crop_rect(444.0, 667.44, verso=False, depth=0, cfg=cfg)
    d2 = b.crop_rect(444.0, 667.44, verso=False, depth=2, cfg=cfg)
    assert d0[0] == 10.0 and d2[0] == 14.0  # inside crop grows on the spine side
    v0 = b.crop_rect(444.0, 667.44, verso=True, depth=0, cfg=cfg)
    v2 = b.crop_rect(444.0, 667.44, verso=True, depth=2, cfg=cfg)
    assert v0[2] == 434.0 and v2[2] == 430.0  # verso: right edge recedes


def test_trim_crop_clamped_to_page(b):
    cfg = {"inside_pt": 100.0, "outside_pt": 100.0, "top_pt": 400.0}
    rect = b.crop_rect(444.0, 667.44, verso=False, depth=0, cfg=cfg)
    assert rect == (100.0, 400.0, 344.0, 667.44)


def test_trim_crop_rejects_degenerate(b):
    with pytest.raises(ValueError):
        b.crop_rect(444.0, 667.44, verso=False, depth=0,
                    cfg={"top_pt": 700.0, "bottom_pt": 0.0})


# --- creep ----------------------------------------------------------------

def test_creep_formula(b):
    # shift toward the crease = depth * 2 * caliper (pt conversion)
    assert b.creep_pt(0, caliper_mm=0.10) == pytest.approx(0.0)
    assert b.creep_pt(2, caliper_mm=0.10) == pytest.approx(2 * 2 * 0.10 * 72 / 25.4)


# --- order building -------------------------------------------------------

def _fake_archive(tmp_path, n=5):
    import hashlib

    def fake(page_no, data):
        f = tmp_path / f"page-{page_no:04d}.png"
        f.write_bytes(data)
        return {"page": page_no, "file": f.name,
                "sha256": hashlib.sha256(data).hexdigest()}

    entries = [fake(1, b"x"), fake(3, b"y")]
    manifest = {"source": {"pages": n}, "render": {"dpi": 600},
                "pages": entries}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


def test_order_from_slice(b, tmp_path):
    archive = _fake_archive(tmp_path)
    book = {"order": {"slice": {"first": 3, "last": 3}}}
    order = b.build_order(book, archive, tmp_path / "order.json")
    assert [p["position"] for p in order["pages"]] == [1]
    assert order["pages"][0]["archive_page"] == 3
    assert order["pages"][0]["file"] == "page-0003.png"
    import hashlib
    assert order["pages"][0]["sha256"] == hashlib.sha256(b"y").hexdigest()


def test_order_from_explicit_list(b, tmp_path):
    archive = _fake_archive(tmp_path)
    book = {"order": {"pages": [3, 1]}}
    order = b.build_order(book, archive, tmp_path / "order.json")
    assert [p["archive_page"] for p in order["pages"]] == [3, 1]


def test_order_rejects_missing_page(b, tmp_path):
    archive = _fake_archive(tmp_path)
    with pytest.raises(SystemExit):
        b.build_order({"order": {"slice": {"first": 1, "last": 5}}}, archive,
                      tmp_path / "order.json")


# --- book config ----------------------------------------------------------

def test_load_book_defaults(b, tmp_path):
    p = tmp_path / "book.toml"
    p.write_text("[book]\ntitle = 'x'\n")
    cfg = b.load_book(p)
    assert cfg["book"]["title"] == "x"
    imp = cfg["impose"]
    assert imp["paper"] == "letter"
    assert imp["signature_pages"] == 8
    assert imp["slot_margin_pt"] == 14.0
    assert imp["caliper_mm"] == 0.10
    assert imp["marks"] is True
    assert imp["proof_dpi"] == 150
    assert cfg["trim"] == {}  # defaults mean "no crop"