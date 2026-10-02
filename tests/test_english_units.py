# M5 unit tests (HOL-264): diacritics mapping, chrome stripper, glyph
# classifier, ToC parser, roman/word numerals, offsets. All fixtures are
# committed page slices (pdftotext -layout output); no PDF needed.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extract_english as ex

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "english"


def fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# --- diacritics normalization: known vocabulary (issue-verified + probed) ---

def test_normalize_known_vocabulary():
    cases = {
        "BålakåƒŒa": "Bālakāṇḍa",
        "Da‹aratha": "Daśaratha",
        "La∆kå": "Laṅkā",
        "§R¶ya‹æ∆ga": "Ṛṣyaśṛṅga",
        "§R¶i": "Ṛṣi",
        "Vålm∂ki": "Vālmīki",
        "›r∂ Råmåyaƒa": "Śrī Rāmāyaṇa",
        "Vi¶ƒu": "Viṣṇu",
        "Lak¶maƒa": "Lakṣmaṇa",
        "Ja¢åyu": "Jaṭāyu",
        "Citrakµu¢a": "Citrakūṭa",
        "Krau¤ca": "Krauñca",
        "A¤janå": "Añjanā",
        "Uccai¨‹ravå": "Uccaiḥśravā",
        "Vi‹wåmitra": "Viśwāmitra",  # print spells `w`; extraction is faithful
        "Bæhaspati": "Bṛhaspati",
        "Smæti": "Smṛti",
        "Vætra": "Vṛtra",
        "GaruŒa": "Garuḍa",  # print uses the diacritic form
        "Tak¶a‹ilå": "Takṣaśilā",
        "›µurpaƒakhå": "Śūrpaṇakhā",
        "Jåmbavån": "Jāmbavān",
        "Sugr∂va": "Sugrīva",
        "Kaikey∂": "Kaikeyī",
        "Hanumån": "Hanumān",
        "Råvaƒa": "Rāvaṇa",
        "S∂tå": "Sītā",
        "A‹oka-grove": "Aśoka-grove",
        "›atrughna": "Śatrughna",
        "DaƒŒaka": "Daṇḍaka",
        "Kumbhakarƒa": "Kumbhakarṇa",
        "Varuƒa": "Varuṇa",
        "draviƒa≈": "draviṇaṃ",
        "sarva≈h": "sarvaṃh",
        "mama sarva≈ mama": "mama sarvaṃ mama",
    }
    for src, want in cases.items():
        assert ex.normalize(src) == want, f"{src!r} -> {ex.normalize(src)!r}, want {want!r}"


def test_normalize_quotes_dashes():
    assert ex.normalize("ëRåmaí") == "‘Rāma’"
    assert ex.normalize("oneís") == "one’s"
    assert ex.normalize("you.î") == "you.”"
    assert ex.normalize('ìSo be itî') == "“So be it”"
    assert ex.normalize("Kåmaóthe") == "Kāma—the"
    assert ex.normalize("(8ñ10)") == "(8–10)"
    # already-correct unicode passes through untouched
    for s in ("—", "–", "‘", "’", "“", "”", "…", "†", "×"):
        assert ex.normalize(s) == s


def test_normalize_caps_context_running_heads():
    assert ex.normalize("VÅLM∫KI-RÅMÅYA°NA") == "VĀLMĪKI-RĀMĀYAṆA"
    assert ex.normalize("UTTARAKÅ°NœA") == "UTTARAKĀṆḌA"
    assert ex.normalize("ARA°NYAKÅ°NœA") == "ARAṆYAKĀṆḌA"
    assert ex.normalize("GA°NE›A") == "GAṆEŚA"
    assert ex.normalize("KI®KINDHÅKÅ°NœA") == "KIṢKINDHĀKĀṆḌA"
    assert ex.normalize("SARASWAT∫") == "SARASWATĪ"
    assert ex.normalize("∫‹åna") == "īśāna"


# --- glyph classification: english zone vs devanagari encoding ---

def test_word_classifier():
    assert ex.word_is_devanagari("∑§Á⁄Ucÿ,")            # pure encoding
    assert ex.word_is_devanagari("üÊË‚ËÃÊ⁄U◊ÊÿáÊ◊˜")
    assert ex.word_is_devanagari("¬ÈL§·ÊÕ¸øÃÈCÔUÿÁ‚hKÕZ")  # encoding + stray ascii
    assert not ex.word_is_devanagari("Råmåyaƒa")          # english diacritics
    assert not ex.word_is_devanagari("Da‹aratha")
    assert not ex.word_is_devanagari("the")
    assert not ex.word_is_devanagari("Uccai¨‹ravå")       # adjacent mapped glyphs
    assert not ex.word_is_devanagari("§R¶i")


def test_unmapped_glyphs_in_english_words():
    # known vocabulary: zero unmapped
    assert ex.unmapped_english_glyphs(
        "BålakåƒŒa Da‹aratha La∆kå ›r∂ Råmåyaƒa Vi¶ƒu") == {}
    # encoding-only words are excluded from the scan
    assert ex.unmapped_english_glyphs("∑§Ê‹ ﬂ·¸ÁÃ ¬¡¸ãÿ— ¬ÊÃÿãŸ◊ÎÃ¢ ¬ÿ—H 20H") == {}
    # a truly unmapped glyph inside an english word is reported
    # (Ω: synthetic, absent from every glyph population)
    assert ex.unmapped_english_glyphs("strångeΩword") == {"Ω": 1}


def test_line_is_english():
    assert ex.line_is_english("      ìMay no obstruction hinder you as you")
    assert ex.line_is_english("wander in all directions at your sweet will.î")
    assert ex.line_is_english("‡ÊÒ‹oÎXÁ‡Ê‹Ùà¬ÊÃSÃŒÊ÷ÍÃ˜˜ ‚ ◊„ÔÊÁªÁ⁄U—H 46H") is False
    assert ex.line_is_english("H 19H") is False          # verse-number noise
    # mixed row (english left column + devanagari right) is kept
    assert ex.line_is_english(
        "retired to the woods in order to implement Œﬂªãœﬂ¸‚¢∑§Ê‡ÊÊSÃòÊ Ã ãÿﬂ‚Ÿ˜ ‚Èπ◊˜–")


# --- chrome stripper ---

def test_strip_page_left_header():
    text = fixture("page-2159.txt")
    clean, flags = ex.strip_page_chrome(text)
    lines = [ln for ln in clean.splitlines() if ln.strip()]
    assert lines[0].startswith("¡ËáÊÊ¸ŸÊ◊Á¬")           # header line gone
    assert not any("VÅLM∫KI" in ln for ln in lines)
    assert "chrome:header" in flags
    # content markers survive
    assert any("Thus ends Canto Forty-one" in ln for ln in lines)
    assert any("Canto XLII" in ln for ln in lines)
    assert any("(20)" in ln for ln in lines)             # verse-range marker kept
    assert any("pu¶paka" in ln.lower() for ln in lines)


def test_strip_paren_header_and_folio():
    text = fixture("page-1190.txt")
    clean, flags = ex.strip_page_chrome(text)
    lines = [ln for ln in clean.splitlines() if ln.strip()]
    assert not any(ln.strip() == "(23)" for ln in lines)
    assert not any(ln.strip() == "U" for ln in lines)    # folio mark gone
    assert "chrome:header" in flags and "chrome:folio" in flags
    assert any("096." in ln for ln in lines)


def test_strip_title_left_header():
    text = fixture("page-2160.txt")
    clean, flags = ex.strip_page_chrome(text)
    lines = clean.splitlines()
    assert not any("UTTARAKÅ°NœA" in ln for ln in lines[:2])
    assert any("fragrant flowers" in ln for ln in lines)


def test_strip_keeps_body_when_no_header():
    text = "plain body line\nsecond line\n"
    clean, flags = ex.strip_page_chrome(text)
    assert clean == text
    assert "chrome:header" not in flags


def test_strip_om_mark_and_bare_number():
    text = "                                        OÀ\n\n453\n›r∂mad Vålm∂ki-Råmåyaƒa\n"
    clean, flags = ex.strip_page_chrome(text)
    lines = [ln for ln in clean.splitlines() if ln.strip()]
    assert lines == ["›r∂mad Vålm∂ki-Råmåyaƒa"]
    assert "chrome:om" in flags and "chrome:header" in flags


# --- numerals ---

def test_roman_numerals():
    assert ex.roman_to_int("I") == 1
    assert ex.roman_to_int("II") == 2
    assert ex.roman_to_int("XLII") == 42
    assert ex.roman_to_int("CVI") == 106
    assert ex.roman_to_int("LXXXIV") == 84


def test_word_number_from_closer():
    assert ex.word_number("One") == 1
    assert ex.word_number("Forty-one") == 41
    assert ex.word_number("one hundred and eleven") == 111
    assert ex.word_number("Twenty-two") == 22


# --- ToC parsing ---

def test_toc_parse_page21():
    entries, leading = ex.parse_toc_page(fixture("page-21.txt"))
    assert leading == []          # kanda header block, no orphan continuation
    nums = [e["canto_no"] for e in entries]
    assert nums == list(range(1, 18))
    pages = [e["printed_page"] for e in entries]
    assert pages[:8] == [59, 68, 72, 77, 80, 83, 85, 88]
    assert pages[14:] == [111, 114, 117]
    e1 = entries[0]
    assert "The celestial sage Nårada narrates to Vålm∂ki the Story of" in e1["title_raw"]
    assert e1["title_raw"].endswith("in a nutshell.")
    e8 = entries[7]
    assert "horse-sacrifice" in e8["title_raw"]
    # multi-line entries closed on a later line carry the leader page
    assert entries[13]["printed_page"] == 105


def test_toc_parse_page1190_zero_padded():
    entries, leading = ex.parse_toc_page(fixture("page-1190.txt"))
    assert leading == []
    nums = [e["canto_no"] for e in entries]
    assert nums == list(range(96, 112))
    assert entries[0]["printed_page"] == 1106
    assert entries[-1]["canto_no"] == 111
    assert entries[-1]["title_raw"].startswith("Mention of the consequences")


def test_toc_kanda_header_detection():
    # detector contract: normalized (cleaned) page text; full block shape
    text, _ = ex.strip_page_chrome(fixture("page-21.txt"))
    k = ex.toc_kanda_header(ex.normalize(text))
    assert k == {"name_raw": "Bālakāṇḍa", "book": "One", "kanda": 1,
                 "line": 2, "with_title": True}
    # short block shape (kanda 3 style: no title line)
    assert ex.toc_kanda_header("Araṇyakāṇḍa\nBook Three") == {
        "name_raw": "Araṇyakāṇḍa", "book": "Three", "kanda": 3,
        "line": 0, "with_title": False}


# --- printed -> archive offsets ---

def test_offsets():
    assert ex.archive_page_for(59, part=1) == 59
    assert ex.archive_page_for(1155, part=1) == 1155
    assert ex.archive_page_for(2, part=2) == 1169
    assert ex.archive_page_for(1106, part=2) == 2273
    assert ex.part_for_archive(59) == 1
    assert ex.part_for_archive(1167) == 1
    assert ex.part_for_archive(1168) == 1
    assert ex.part_for_archive(1169) == 2
    assert ex.part_for_archive(2303) == 2


# --- regression: last entry before a kanda header keeps its leader ---

def test_toc_entry_before_kanda_header():
    # p1185 shape: entry 128's title continues, leader, then the NEXT
    # kanda's header block + column header; nothing may be appended after
    # the leader and entry 128 must resolve to printed 834.
    text = (
        "126.    Hanumān recounts to Bharata broad details relating to the sojourn of\n"
        "        Śrī Rāma, Sītā and Lakṣmaṇa in the forest. ...................... 823\n"
        "127.    Arrangements for the reception of Śrī Rāma in Ayodhyā; the de-\n"
        "        parture of Bharata with all others for Nandigrāma. ................ 828\n"
        "128.    Bharata renders back the kingdom of Ayodhyā to Śrī Rāma, who drives in\n"
        "        a procession to the city; his consecration on the throne of Ayodhyā; His\n"
        "        farewell to the monkeys and the glory of the epic. .................... 834\n"
        "\n"
        "                                                    Uttarakāṇḍa\n"
        "                                                       Book Seven\n"
        "Number of Cantos:                                                                          \n"
        "01.    Great seers meet Śrī Rāma in the audience hall, his conversation with them\n"
        "       and the questions he addresses to them. ...................................... 845\n"
    )
    entries, leading = ex.parse_toc_page(text)
    by_no = {e["canto_no"]: e for e in entries}
    assert by_no[128]["printed_page"] == 834
    assert "Uttarakāṇḍa" not in by_no[128]["title_raw"]
    assert by_no[1]["printed_page"] == 845
    assert leading == []


# --- duplicate canto-number band (kanda 6 print anomaly) ---

def test_duplicate_band_resolution():
    kandas = [{
        "part": 2, "kanda": 6, "name": "Yuddhakāṇḍa",
        "sargas": (
            [{"canto_no": 1, "title": "s1", "printed_page": 293, "archive_page": 1460}]
            + [{"canto_no": n, "title": f"bandA-{n}", "printed_page": p,
                "archive_page": p + 1167}
               for n, p in zip(range(12, 20), (295, 297, 301, 311, 314, 316, 318, 320))]
            + [{"canto_no": n, "title": f"s{n}", "printed_page": p,
                "archive_page": p + 1167}
               for n, p in zip(range(10, 21), (323, 326, 329, 333, 336, 339, 341,
                                               344, 350, 354, 358, 373))]
        ),
    }]
    toc = {"kandas": kandas, "quirks": [], "unattributed": []}
    resolved, quirks = ex.resolve_duplicate_bands(toc)
    k6 = resolved["kandas"][0]
    nos = [s["canto_no"] for s in k6["sargas"]]
    assert nos == list(range(1, 21))
    s2 = next(s for s in k6["sargas"] if s["canto_no"] == 2)
    assert s2["title"] == "bandA-12" and s2["printed_page"] == 295
    assert s2.get("printed_as") == 12
    s12 = next(s for s in k6["sargas"] if s["canto_no"] == 12)
    assert s12["printed_page"] == 329 and "printed_as" not in s12
    assert any("renumbered_band" in q for q in quirks)
    assert k6.get("anomalies")


def test_duplicate_band_unresolvable_left_flagged():
    # same number twice, but no missing numbers to pair with -> no invention
    kandas = [{
        "part": 1, "kanda": 1, "name": "Bālakāṇḍa",
        "sargas": [
            {"canto_no": 1, "title": "a", "printed_page": 59, "archive_page": 59},
            {"canto_no": 2, "title": "b", "printed_page": 68, "archive_page": 68},
            {"canto_no": 2, "title": "b2", "printed_page": 69, "archive_page": 69},
            {"canto_no": 3, "title": "c", "printed_page": 72, "archive_page": 72},
        ],
    }]
    toc = {"kandas": kandas, "quirks": [], "unattributed": []}
    resolved, quirks = ex.resolve_duplicate_bands(toc)
    nos = [s["canto_no"] for s in resolved["kandas"][0]["sargas"]]
    assert nos == [1, 2, 2, 3]          # untouched
    assert any("unresolved_duplicates" in q for q in quirks)


def test_word_number_ordinals():
    # the print mixes cardinal and ordinal closer styles (k7: p2075
    # "Thus ends Canto Nineteenth", p2085 "Twenty-two")
    assert ex.word_number("Nineteenth") == 19
    assert ex.word_number("Forty-fifth") == 45   # k7 closer at p2168
    assert ex.word_number("Twentieth") == 20
    assert ex.word_number("Fortieth") == 40
    assert ex.word_number("Seventieth") == 70
    assert ex.word_number("Twenty-first") == 21
    assert ex.word_number("First") == 1
    assert ex.word_number("second") == 2
    assert ex.word_number("one hundred and eleventh") == 111


def test_closer_both_word_orders():
    # k5 prints "of the Sundarakāṇḍa in the glorious"; other kandas print
    # "in the Uttarakāṇḍa of the glorious" — both must parse
    m = ex.CLOSER_RE.match(
        "    Thus ends Canto One of the Sundarakāṇḍa in the glorious Rāmāyaṇa of")
    assert m and ex.word_number(m.group(1)) == 1
    assert ex.KANDA_BY_NAME.get(m.group(2)) == 5
    m = ex.CLOSER_RE.match(
        " Thus ends Canto one hundred and eleven in the Uttarakāṇḍa of the glorious")
    assert m and ex.word_number(m.group(1)) == 111
    assert ex.KANDA_BY_NAME.get(m.group(2)) == 7


def test_bare_mu_typos_and_private_use():
    # print typos: the macron carrier µ lands inside plain words
    assert ex.normalize("lifµe-breath") == "life-breath"
    assert ex.normalize("Sumitrµå)") == "Sumitrā)"
    # \uf8ff (private-use vocalic-r) is encoding-zone, never transliterated
    assert ex.word_is_devanagari("\uf8ffUH")
    assert ex.unmapped_english_glyphs("lifµe-breath Sumitrµå \uf8ffUH") == {}


def test_closer_print_variants():
    # every closer shape the print actually uses (probed across the corpus)
    variants = {
        "Thus ends Canto Twenty-two in the Yuddhakāṇḍa of the glorious": (22, 6),
        "Thus ends Canto One of the Sundarakāṇḍa in the glorious Rāmāyaṇa of": (1, 5),
        "Thus ends of Canto Seventy-two in the Bālakāṇḍa of the glorious": (72, 1),
        "Thus ends Canto Twenty-two the Yuddhakāṇḍa of the glorious": (22, 6),
        "Thus ends canto Forty-four in the Yuddhakāṇḍa of the glorious": (44, 6),
        "Thus ends the Canto Fifty-three in the Uttarakāṇḍa of the glorious": (53, 7),
        "Thus end Canto One hundred and seventeen in the Ayodhyākāṇḍa of": (117, 2),
        "Thus ends Canto Forty-eight in Uttarakāṇḍa of the glorious": (48, 7),
    }
    for line, (num, kanda) in variants.items():
        m = ex.CLOSER_RE.match(line)
        assert m, line
        assert ex.word_number(m.group(1)) == num, line
        assert ex.KANDA_BY_NAME.get(m.group(2)) == kanda, line
    # a corrupted closer (print typo "Sixty-sevem") must NOT parse
    m = ex.CLOSER_RE.match(
        "Thus ends Canto Sixty-sevem in the Yuddhakāṇḍa of the glorious")
    assert m is None or ex.word_number(m.group(1)) != 67
