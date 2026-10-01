"""M1 impose fixture tests: trim+impose end-to-end on the committed 8-page
fixture, verified by a virtual fold (print -> duplex -> fold -> book view).

The oracle lives in tests/virtfold.py and shares no code with bindery.py.
Page identity comes from per-page gray tints; orientation from a spine-side
dot (odd pages = recto, dot top-left; even = verso, dot top-right).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from virtfold import SHEET_H, SHEET_W, physical_rect, region_to_book, virtfold

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "fixture8.pdf"
sys.path.insert(0, str(Path(__file__).parent))


def load_bindery():
    spec = importlib.util.spec_from_file_location("bindery", REPO / "bindery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def render_page(pdf: Path, page: int, dpi: int, outdir: Path) -> Image.Image:
    prefix = outdir / f"r{page}"
    run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", str(page),
         "-l", str(page), str(pdf), str(prefix)])
    (img,) = sorted(outdir.glob(f"r{page}-*.png"))
    return Image.open(img)


def pdftotext_page(pdf: Path, page: int) -> str:
    return run(["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"]).stdout


def box_mean(img: Image.Image, x0_pt, y0_pt, x1_pt, y1_pt, page_h_pt, dpi) -> float:
    """Mean gray of a pt-space box (y up from page bottom) on a rendered page."""
    f = dpi / 72.0
    hp = img.size[1]
    box = (round(x0_pt * f), round(hp - y1_pt * f), round(x1_pt * f), round(hp - y0_pt * f))
    stat = ImageStat.Stat(img.convert("L").crop(box))
    return stat.mean[0]


# independent first-principles derivation of the sheet layout (does NOT call
# bindery.signature_plan): sheet j of a signature with S pages carries
# front top 2j+2, front bottom S-2j-1, back top 2j+1, back bottom S-2j.
def expected_sheet_pages(sig_start: int, sig_pages: int, j: int):
    s = sig_pages
    return {
        "front": {"top": sig_start + 2 * j + 1, "bottom": sig_start + s - 2 * j - 2},
        "back": {"top": sig_start + 2 * j, "bottom": sig_start + s - 2 * j - 1},
    }


def expected_plan(n_pages: int, sig_pages: int):
    """-> list of (sig_start, sig_pages_real, sheets) with blank padding."""
    sigs = []
    pos = 1
    while pos <= n_pages:
        real = min(sig_pages, n_pages - pos + 1)
        padded = (real + 3) // 4 * 4
        sheets = padded // 4
        sigs.append((pos, real, sheets))
        pos += real
    return sigs


@pytest.fixture(scope="module")
def b():
    return load_bindery()


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    out = tmp_path_factory.mktemp("build")
    b = load_bindery()
    archive = out / "archive"
    b.ingest(FIXTURE, archive, dpi=96, source_url="fixture://fixture8.pdf", gray=True)
    book = {"book": {"title": "fixture8"}, "order": {"slice": {"first": 1, "last": 8}}}
    b.build_order(book, archive, out / "order.json")
    b.trim(book, archive, out)
    b.impose(book, out)
    return {"out": out, "bindery": b}


def test_press_page_counts(build):
    out = build["out"]
    b = build["bindery"]
    assert b.page_count(out / "press.pdf") == 4  # 8 pages, sig 8 -> 2 sheets
    assert b.page_count(out / "proof-screen.pdf") == 8


def test_press_labels_pairing(build):
    out = build["out"]
    # sheet 0 (outermost): front top = p2, front bottom = p7; back = p1|p8
    assert "pages 2|7" in pdftotext_page(out / "press.pdf", 1)
    assert "pages 1|8" in pdftotext_page(out / "press.pdf", 2)
    # sheet 1 (inner): front = p4|p5; back = p3|p6
    assert "pages 4|5" in pdftotext_page(out / "press.pdf", 3)
    assert "pages 3|6" in pdftotext_page(out / "press.pdf", 4)
    assert "SIG1" in pdftotext_page(out / "press.pdf", 1)
    assert "SIG1" in pdftotext_page(out / "press.pdf", 4)


def test_registration_block_on_both_sides(build):
    out = build["out"]
    for page in (1, 2):  # sheet 0 front and back
        img = render_page(out / "press.pdf", page, 100, out)
        assert box_mean(img, 300, 390, 312, 402, SHEET_H, 100) < 120


def test_fold_ticks(build):
    img = render_page(build["out"] / "press.pdf", 1, 100, build["out"])
    assert box_mean(img, 2, 394.5, 9, 397.5, SHEET_H, 100) < 150
    assert box_mean(img, 603, 394.5, 610, 397.5, SHEET_H, 100) < 150


def test_crop_marks_present(build):
    out = build["out"]
    impose = json.loads((out / "impose.json").read_text())
    img = render_page(out / "press.pdf", 1, 100, out)
    sheet = impose["sheets"][0]
    rect = sheet["front"]["top"]["rect"]  # placed page rect, y up
    # vertical crop mark above the head edge corner (x1,y1)
    x, y1 = rect[2], rect[3]
    assert box_mean(img, x - 1.0, y1 + 2.0, x + 1.0, y1 + 6.0, SHEET_H, 100) < 150
    # horizontal mark right of the same corner
    assert box_mean(img, x + 2.0, y1 - 1.0, x + 6.0, y1 + 1.0, SHEET_H, 100) < 150


def test_impose_json_structure(build):
    impose = json.loads((build["out"] / "impose.json").read_text())
    assert impose["flip"] == "long-edge"
    assert len(impose["sheets"]) == 2
    sh = impose["sheets"][0]
    assert sh["signature"] == 1 and sh["sheet_in_sig"] == 1 and sh["depth"] == 0
    assert sh["front"]["top"]["page"] == 2 and sh["front"]["bottom"]["page"] == 7
    assert sh["back"]["top"]["page"] == 1 and sh["back"]["bottom"]["page"] == 8
    assert sh["front"]["top"]["rect"] and len(sh["front"]["top"]["rect"]) == 4


def test_virtual_fold_pairing_and_orientation(build):
    """The crown jewel: simulate print->duplex->fold->book and verify that
    every slot lands as the correct page, upright, unmirrored, spine toward
    the crease."""
    out = build["out"]
    impose = json.loads((out / "impose.json").read_text())
    dpi = 100
    for sheet in impose["sheets"]:
        fi = render_page(out / "press.pdf", 2 * sheet["global_index"] - 1, dpi, out)
        bi = render_page(out / "press.pdf", 2 * sheet["global_index"], dpi, out)
        faces = virtfold(fi, bi)
        sig_start = 1 if sheet["signature"] == 1 else 9
        exp = expected_sheet_pages(sig_start, 8, sheet["sheet_in_sig"] - 1)
        for face, slot in (("T_back", "back_top"), ("T_front", "front_top"),
                           ("B_front", "front_bottom"), ("B_back", "back_bottom")):
            side, pos = slot.split("_")
            want = exp[side][pos]
            rect = physical_rect(side, sheet[side][pos]["rect"])
            book_rect = region_to_book("A" if pos == "top" else "B", rect)
            img = faces[face]
            f = dpi / 72.0
            hp = img.size[1]
            px = (round(book_rect[0] * f), round(hp - book_rect[3] * f),
                  round(book_rect[2] * f), round(hp - book_rect[1] * f))
            live = img.convert("L").crop(px)
            mean = ImageStat.Stat(live).mean[0]
            # tint identifies the page: tint(n) = 235 - 7n
            want_tint = 235 - 7 * want
            assert abs(mean - want_tint) < 8, \
                (face, sheet["global_index"], want, mean)
            # dot probes: dark at the spine-head corner, light at the other three
            w_pt = book_rect[2] - book_rect[0]
            h_pt = book_rect[3] - book_rect[1]
            corners = {
                "top_left": (0, h_pt - 60, 60, h_pt),
                "top_right": (w_pt - 60, h_pt - 60, w_pt, h_pt),
                "bot_left": (0, 0, 60, 60),
                "bot_right": (w_pt - 60, 0, w_pt, 60),
            }
            # spine side: recto (odd pages) = left, verso (even) = right
            spine = "top_left" if want % 2 == 1 else "top_right"

            def px_box(r):
                # pt (y up) -> px (y down) within the live crop
                lh = live.size[1]
                return (round(r[0] * f), round(lh - r[3] * f),
                        round(r[2] * f), round(lh - r[1] * f))

            means = {k: ImageStat.Stat(live.crop(px_box(r))).mean[0]
                     for k, r in corners.items()}
            assert means[spine] < means["bot_left" if spine == "top_left"
                                        else "bot_right"] - 30, \
                (face, want, means)
            for k in corners:
                if k != spine and k != ("bot_right" if spine == "top_left"
                                        else "bot_left"):
                    assert means[k] > means[spine] + 30, (face, want, k, means)


def test_proof_is_single_page_sequence(build):
    out = build["out"]
    b = build["bindery"]
    info = b.pdfinfo(out / "proof-screen.pdf")
    assert info["Pages"] == "8"
    # page size follows the actual rasters (pdfinfo's stated 667.44 pt
    # disagrees with the render by rounding; the rasters are the input)
    assert info["Page size"].startswith("444 x 667.5")


def test_blank_slots_survive_impose(b, tmp_path):
    """6 pages, sig 8 -> one signature, 2 sheets, last two slots blank."""
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    src = tmp_path / "fixture6.pdf"
    w, h = 444.0, 667.44
    c = canvas.Canvas(str(src), pagesize=(w, h))
    for n in range(1, 7):
        tint = 235 - 7 * n
        c.setFillColor(Color(tint / 255, tint / 255, tint / 255))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColor(Color(0, 0, 0))
        c.rect(18 if n % 2 == 1 else w - 48, h - 48, 30, 30, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 120)
        c.drawCentredString(w / 2, h / 2 - 60, str(n))
        c.showPage()
    c.save()

    out = tmp_path / "build"
    archive = tmp_path / "archive"
    b.ingest(src, archive, dpi=72, source_url="fixture://fixture6.pdf", gray=True)
    book = {"book": {"title": "fixture6"}, "order": {"pages": [1, 2, 3, 4, 5, 6]}}
    b.build_order(book, archive, out / "order.json")
    b.trim(book, archive, out)
    b.impose(book, out)
    assert b.page_count(out / "press.pdf") == 4  # 6 pages -> 2 sheets
    impose = json.loads((out / "impose.json").read_text())
    # padded sig of 8: sheet 0 carries blanks (positions 7, 8)
    sheet0 = impose["sheets"][0]
    assert sheet0["front"]["bottom"]["page"] is None
    assert sheet0["back"]["bottom"]["page"] is None
    assert "blank" in pdftotext_page(out / "press.pdf", 1).lower()
    # blank slots render as empty paper: probe the slot's interior
    img = render_page(out / "press.pdf", 2, 100, tmp_path)  # sheet 0 back
    assert box_mean(img, 100, 100, 500, 300, SHEET_H, 100) > 240