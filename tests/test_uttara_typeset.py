"""Uttara typeset tests (HOL-259 M4b): HTML generation, verse-ref
conversion, profile invariants, and the WeasyPrint render smoke."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_typeset():
    spec = importlib.util.spec_from_file_location(
        "uttara_typeset", REPO / "uttara_typeset.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ts():
    return load_typeset()


@pytest.fixture(scope="module")
def data():
    p = REPO / "dataset" / "uttara-eText-ramayana-info.json"
    if not p.is_file():  # checks run from the committed tree
        pytest.skip("dataset not present")
    return json.loads(p.read_text())


def mini_data():
    return {
        "9": {
            "1": {
                "text_devanagari": "ततो गच्छति विप्रेन्द्रं ।। 7.9.1 ।।",
                "translation": "Then, as the lord of Brahmans went, the",
            },
            "2": {
                "text_devanagari": "द्वितीयं वाक्यमाह ऽस्मै ।। 7.9.2 ।।",
                "translation": "Second saying, told to him again.",
            },
            "3": {
                "text_devanagari": "तृतीयमपि चाऽकरोत् ।। 7.9.3 ।।",
                "translation": "And he did the third likewise.",
            },
        }
    }


# --- helpers ------------------------------------------------------------------

def test_to_devanagari_digits(ts):
    assert ts.to_devanagari_digits(42) == "४२"
    assert ts.to_devanagari_digits(111) == "१११"


def test_verse_ref_tail(ts):
    assert ts.verse_ref_devanagari(42, 1) == "॥४२.१॥"


def test_clean_deva_strips_ascii_ref(ts):
    out = ts.clean_deva("ततो गच्छति ।। 7.9.1 ।।", 9, 1)
    assert "7.9.1" not in out
    assert out.endswith("॥९.१॥")


# --- HTML generation -----------------------------------------------------------

def test_sarga_html_structure(ts):
    html = ts.sarga_html(mini_data(), 9)
    assert 'class="flow-page"' in html
    assert "उत्तरकाण्डे सर्गः ९" in html
    assert "UTTARA-KĀṆḊA · SARGA 9" in html
    assert "॥९.१॥" in html
    assert "Then, as the lord of Brahmans went, the (1)" in html
    assert html.count('class="trans"') == 1  # 3 verses -> one chunk


def test_sarga_html_chunks(ts):
    d = mini_data()
    extra = ts.VERSE_CHUNK + 1 - 3  # 3 verses already in mini_data
    for n in range(4, 4 + extra):  # -> chunks [1..VERSE_CHUNK], [last]
        d["9"][str(n)] = {"text_devanagari": f"पाठः {n} ।। 7.9.{n} ।।",
                          "translation": f"Verse {n}."}
    html = ts.sarga_html(d, 9)
    assert html.count('class="trans"') == 2
    assert f"Verse {ts.VERSE_CHUNK + 1}. ({ts.VERSE_CHUNK + 1})" in html


def test_build_html_front_matter(ts):
    html = ts.build_html(mini_data(), [9])
    assert "श्रीमद्वाल्मीकिरामायण" in html
    assert "Editorial note — on the sarga count." in html
    assert "CONTENTS" in html
    assert "Sarga 9 — 3 verses" in html
    assert 'class="flow-page"' in html


def test_build_html_no_front_matter(ts):
    html = ts.build_html(mini_data(), [9], with_front_matter=False)
    assert "श्रीमद्वाल्मीकिरामायण" not in html
    assert "CONTENTS" not in html


def test_profile_invariants(ts):
    assert ts.CONTENT_W == ts.PAGE_W - 2 * ts.MARGIN_SIDE
    assert 0 < ts.MARGIN_BOTTOM < ts.MARGIN_TOP < ts.PAGE_H / 3
    assert ts.VERSE_CHUNK >= 2


# --- render smoke (needs weasyprint + poppler: flake checks.typeset) ----------

def test_render_smoke(ts, tmp_path):
    weasyprint = pytest.importorskip("weasyprint")
    html = ts.build_html(mini_data(), [9])
    pdf = tmp_path / "mini.pdf"
    ts.render_pdf(html, pdf)
    assert pdf.stat().st_size > 2000
    pngs = ts.rasterize(pdf, tmp_path / "pg", dpi=150)
    assert len(pngs) >= 2  # title/ToC + at least one content page
    manifest = ts.write_archive(pngs, tmp_path / "typeset", 150,
                                {"book": "mini fixture",
                                 "text_source": "test"})
    assert len(manifest["pages"]) == len(pngs)
    for e in manifest["pages"]:
        assert (tmp_path / "typeset" / e["file"]).is_file()
        assert len(e["sha256"]) == 64
    order = json.loads((tmp_path / "order.json").read_text())
    assert [p["position"] for p in order["pages"]] == \
        list(range(1, len(pngs) + 1))
    assert order["archive"] == str(tmp_path / "typeset")
