"""Unit tests for the M2 structure stage builders (pure, no docling).

These run everywhere (including the pure `nix build` check): the
structure stage's heavy imports are lazy, so structure.py imports
cleanly with the stdlib only.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("structure", REPO / "structure.py")
structure = importlib.util.module_from_spec(spec)
sys.modules["structure"] = structure
spec.loader.exec_module(structure)


# --- roman numerals -------------------------------------------------------

def test_roman_round_trip():
    for n in [1, 4, 9, 14, 42, 63, 77, 111, 128]:
        assert structure.roman_to_int(structure.int_to_roman(n)) == n


def test_roman_multiset_catches_transposition():
    # the edition prints "XLIII" where "LXIII" belongs (Kishkindha c. 63)
    assert structure.roman_multiset("XLIII") == structure.roman_multiset("LXIII")
    assert structure.roman_multiset("XLII") != structure.roman_multiset("LXIII")


def test_normalize_canto_numeral():
    assert structure.normalize_canto_numeral("|") == "I"
    assert structure.normalize_canto_numeral("l|") == "II"
    assert structure.normalize_canto_numeral("11") == "II"
    assert structure.normalize_canto_numeral("1V") == "IV"
    assert structure.normalize_canto_numeral("xiv") == "XIV"


# --- word classification --------------------------------------------------

def test_is_english_word():
    assert structure.is_english_word("forest")
    assert structure.is_english_word("(14)")
    assert structure.is_english_word("Rama's")
    assert not structure.is_english_word("AYODHYĀKĀṆḌA")  # IAST header
    assert not structure.is_english_word("ÃÊË‚ËÃÊ")  # custom-encoding mojibake
    assert not structure.is_english_word("@|¢§")


# --- derive_record on a synthetic page ------------------------------------

def make_synthetic_page(page=401):
    """A minimal two-column body page: English column + Devanagari verse
    blocks, a header, a canto heading and verse numbers, in 1000x1500 px."""
    layout = {
        "page": page,
        "file": f"page-{page:04d}.png",
        "size_px": [1000, 1500],
        "layout_score": 0.9,
        # docling bboxes are y-up: [l, t(bottom-up), r, b(bottom-up)]
        "items": [
            {"label": "TEXT", "bbox": [20, 1250, 480, 1050]},           # English col
            {"label": "SECTION_HEADER", "bbox": [20, 1000, 480, 900]},  # Devanagari
            {"label": "SECTION_HEADER", "bbox": [200, 1450, 800, 1400]},  # "Canto IV"
        ],
    }
    words = []
    # English words inside the TEXT item (y-down 250..450)
    for i, w in enumerate(["Thus", "spoke", "the", "sage"]):
        words.append({"text": w, "conf": 92.0, "l": 30 + i * 60, "t": 300,
                      "r": 90 + i * 60, "b": 330})
    # verse number at the column edge
    words.append({"text": "(4)", "conf": 90.0, "l": 430, "t": 380, "r": 470, "b": 405})
    # Devanagari mojibake inside the SECTION_HEADER item (y-down 500..600)
    for i, w in enumerate(["ÃÊË‚ËÃÊ", "⁄UÊ◊ÊÿáÊ◊˜"]):
        words.append({"text": w, "conf": 41.0, "l": 40 + i * 150, "t": 520,
                      "r": 170 + i * 150, "b": 570})
    # big canto heading (y-down 50..100)
    words.append({"text": "Canto", "conf": 95.0, "l": 380, "t": 55, "r": 560, "b": 95})
    words.append({"text": "IV", "conf": 95.0, "l": 570, "t": 55, "r": 620, "b": 95})
    # running header: kanda token + printed page number
    words.append({"text": "*", "conf": 80.0, "l": 200, "t": 10, "r": 215, "b": 30})
    words.append({"text": "AYODHYĀKĀṆḌA", "conf": 70.0, "l": 250, "t": 10, "r": 700, "b": 30})
    words.append({"text": "401", "conf": 90.0, "l": 900, "t": 10, "r": 970, "b": 30})

    lines = [
        {"t": 10, "text": "* AYODHYĀKĀṆḌA * 401", "conf": 75.0},
        {"t": 55, "text": "Canto IV", "conf": 95.0},
        {"t": 300, "text": "Thus spoke the sage", "conf": 92.0},
        {"t": 380, "text": "(4)", "conf": 90.0},
        {"t": 520, "text": "ÃÊË‚ËÃÊ ⁄UÊ◊ÊÿáÊ◊˜", "conf": 41.0},
        {"t": 1400, "text": "Thus ends Canto Three in the Ayodhyā Kāṇḍa", "conf": 88.0},
    ]
    ocr = {
        "page": page,
        "file": f"page-{page:04d}.png",
        "size_px": [1000, 1500],
        "engine": "tesseract",
        "lang": "eng",
        "words": words,
        "lines": lines,
        "image_stats": {"blur_lapvar": 512.3, "skew_deg": 0.05},
    }
    return layout, ocr


def test_derive_record_fields():
    layout, ocr = make_synthetic_page()
    rec = structure.derive_record(401, layout, ocr)
    d = rec["derived"]
    assert d["header_kanda"] == "ayodhya"
    assert d["printed_page"] == 401
    assert d["canto_heading"]["numeral"] == "IV"
    assert d["canto_end"] and d["canto_end"].startswith("Thus ends Canto Three")
    assert d["verse_numbers"] == [4]
    assert d["english_word_count"] >= 5
    assert d["devanagari_word_count"] == 2
    # english bbox sits above (smaller y) the devanagari block in its column
    assert d["english_bbox"][1] < d["devanagari_bbox"][1]
    assert rec["ocr"]["mean_word_conf"] > 0.5
    assert rec["image_stats"]["blur_lapvar"] == 512.3


# --- sarga map builder on synthetic records -------------------------------

def rec_for(page, **derived):
    base = {
        "page": page, "file": f"page-{page:04d}.png", "size_px": [1000, 1500],
        "docling": {"layout_score": 0.9, "n_items": 3, "labels": {"TEXT": 3}},
        "ocr": {"engine": "tesseract", "lang": "eng", "mean_word_conf": 0.9,
                "n_words": 100},
        "image_stats": {"blur_lapvar": 500.0, "skew_deg": 0.0},
        "derived": {
            "header_kanda": None, "printed_page": None, "canto_heading": None,
            "canto_end": None, "kanda_end_marker": None, "title_book_token": None,
            "kanda_title": None, "verse_numbers": [1], "english_bbox": [0, 0, 1, 1],
            "devanagari_bbox": None, "english_word_count": 100,
            "devanagari_word_count": 10,
        },
    }
    base["derived"].update(derived)
    return base


def test_sarga_map_two_kandas_and_transposition():
    records = [
        rec_for(1),
        rec_for(2, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="one", kanda_title="bala"),
        rec_for(3),
        rec_for(4, canto_heading={"numeral": "II", "text": "Canto II", "t": 0.05}),
        rec_for(5),
        rec_for(6, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="five", kanda_title="sundara"),
        rec_for(7),
    ]
    smap = structure.build_sarga_map(records, 1, 7)
    assert [k["kanda"] for k in smap["kandas"]] == [1, 5]
    k1, k5 = smap["kandas"]
    assert (k1["start_page"], k1["end_page"]) == (2, 5)
    assert [s["sarga"] for s in k1["sargas"]] == [1, 2]
    assert (k1["sargas"][0]["start_page"], k1["sargas"][0]["end_page"]) == (2, 3)
    assert (k1["sargas"][1]["start_page"], k1["sargas"][1]["end_page"]) == (4, 5)
    assert (k5["start_page"], k5["end_page"]) == (6, 7)
    assert smap["interstitial_blocks"] == [{"start_page": 1, "end_page": 1}]


def test_sarga_map_numeral_transposition_flagged():
    records = [
        rec_for(10, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="four", kanda_title="kishkindha"),
        rec_for(11, canto_heading={"numeral": "LXII", "text": "Canto LXII", "t": 0.04}),
        rec_for(13, canto_heading={"numeral": "XLIII", "text": "Canto XLIII", "t": 0.04}),
        rec_for(14, canto_heading={"numeral": "LXIV", "text": "Canto LXIV", "t": 0.04},
                kanda_end_marker="END OF KISKINDHAKANDA"),
        rec_for(15),
    ]
    smap = structure.build_sarga_map(records, 10, 15)
    k = smap["kandas"][0]
    assert k["kanda"] == 4 and k["name"] == "Kishkindha"
    nums = [s["sarga"] for s in k["sargas"]]
    assert nums == [1, 62, 63, 64]
    kinds = [f["kind"] for f in k["flags"]]
    assert "sequence_gap" in kinds          # LXII right after Canto I
    assert "numeral_transposition" in kinds  # XLIII where LXIII belongs
    s63 = next(s for s in k["sargas"] if s["sarga"] == 63)
    assert s63["printed_numeral"] == "XLIII"
    assert s63["start_page"] == 13
    assert s63["end_page"] == 13
    # END OF marker pulls the kanda end back to page 14; page 15 is
    # interstitial (the next part's title/ToC run)
    assert k["end_page"] == 14
    assert smap["interstitial_blocks"] == [{"start_page": 15, "end_page": 15}]


def test_sarga_map_missing_heading():
    records = [
        rec_for(20, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="two"),
        rec_for(21, canto_heading={"numeral": "V", "text": "Canto V", "t": 0.04}),
        rec_for(22, canto_heading={"numeral": "VII", "text": "Canto VII", "t": 0.04}),
    ]
    smap = structure.build_sarga_map(records, 20, 22)
    k = smap["kandas"][0]
    nums = [s["sarga"] for s in k["sargas"]]
    assert nums == [1, 5, 6, 7]
    s6 = next(s for s in k["sargas"] if s["sarga"] == 6)
    assert s6["flags"] == ["missing_heading"]
    assert "missing_heading" in [f["kind"] for f in k["flags"]]


# --- toc draft / fidelity report / spot checks ----------------------------

def test_toc_draft_contains_tables():
    records = [
        rec_for(2, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="one"),
        rec_for(4, canto_heading={"numeral": "II", "text": "Canto II", "t": 0.04}),
        rec_for(5),
    ]
    smap = structure.build_sarga_map(records, 1, 5)
    md = structure.build_toc_draft(smap)
    assert "# ToC draft" in md
    assert "Book One — Bala Kanda" in md
    assert "| 1 | 2–3 |" in md
    assert "| 2 | 4–5 |" in md


def test_fidelity_report_flags_and_spot_checks():
    records = [
        rec_for(2, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04},
                title_book_token="one"),
        rec_for(3),
        rec_for(4, canto_heading={"numeral": "II", "text": "Canto II", "t": 0.04}),
        rec_for(5),
    ]
    records[1]["image_stats"] = {"blur_lapvar": 12.0, "skew_deg": 1.4}
    records[1]["ocr"]["mean_word_conf"] = 0.4
    smap = structure.build_sarga_map(records, 1, 5)
    spot = [
        {"label": "bk1 c1", "toc_ref": 2, "detected_page": 2, "ok": True,
         "verdict": "match"},
        {"label": "bk1 c2", "toc_ref": 4, "detected_page": 4, "ok": True,
         "verdict": "match"},
    ]
    md = structure.build_fidelity_report(records, smap, spot)
    assert "blur (lapvar 12.0)" in md
    assert "askew (+1.40 deg)" in md
    assert "low OCR conf (0.40)" in md
    assert "## ToC spot-check" in md
    assert "Mismatches: 0" in md


def test_parse_toc_entries_multiline_and_filter():
    records = [rec_for(21), rec_for(22), rec_for(60)]
    lines = {
        21: [
            {"t": 100, "text": "The Vålm∂ki-Råmåyaƒa", "conf": 90},
            {"t": 120, "text": "Book One", "conf": 95},
            {"t": 140, "text": "1. The celestial sage Nårada narrates to Vålm∂ki", "conf": 90},
            {"t": 160, "text": "the Story of ›r∂ Råma ...... 59", "conf": 90},
            {"t": 180, "text": "2. Brahmå's visit ...... 68", "conf": 92},
            {"t": 200, "text": "3. A brief outline of the Råmåyaƒa ...... 72", "conf": 91},
        ],
        22: [
            {"t": 100, "text": "(22)", "conf": 90},
            {"t": 120, "text": "4. After his ascension to the throne of Ayodhyå", "conf": 90},
            {"t": 140, "text": "(Ku‹a and Lava). ...... 77", "conf": 89},
        ],
        60: [
            {"t": 100, "text": "Canto I", "conf": 95},
            {"t": 120, "text": "1. The celestial sage", "conf": 90},
            {"t": 140, "text": "end of verse ...... 1", "conf": 90},
            {"t": 160, "text": "2. another ...... 2", "conf": 90},
            {"t": 180, "text": "3. yet another ...... 3", "conf": 90},
        ],
    }
    # page 60 is a body page (Canto I heading): its dotted lines must not
    # be mistaken for ToC entries even though it has three of them.
    records[2] = rec_for(60, canto_heading={"numeral": "I", "text": "Canto I", "t": 0.04})
    entries = structure.parse_toc_entries(records, lines)
    got = {(e["book"], e["canto"], e["printed_page"]) for e in entries}
    assert ("one", 1, 59) in got
    assert ("one", 2, 68) in got
    assert ("one", 3, 72) in got
    assert ("one", 4, 77) in got
