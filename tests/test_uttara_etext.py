"""Uttara e-text tests (HOL-259 M4a): RSC payload parsing, transliteration,
gap-fill extraction, and dataset integrity."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fetch_mod():
    return load("fetch_uttara_etext")


@pytest.fixture(scope="module")
def gaps_mod():
    return load("fill_uttara_gaps")


@pytest.fixture(scope="module")
def data():
    return json.loads(
        (REPO / "dataset" / "uttara-eText-ramayana-info.json").read_text())


PARSE_FIXTURE = (
    'x],"$","L25","1",{\\"shloka\\":{\\"number\\":1,\\"reference\\":\\"Uttara Kanda 9.1\\",'
    '\\"text_devanagari\\":\\"ततो गच्छति विप्रेन्द्रं ।। 7.9.1 ।।\\",'
    '\\"text_devanagari_alt\\":\\"ततो गच्छति विप्रेन्द्रं ।। ७.९.१ ॥\\",'
    '\\"transliteration\\":\\"tato gacchati viprendraṃ || 7.9.1 ||\\",'
    '\\"translation\\":\\"Then, as the lord of Brahmans went...\\",'
    '\\"explanation\\":null,\\"comments\\":null,\\"text_telugu\\":\\"IGNORE\\"}}],'
    '"$","L25","2",{\\"shloka\\":{\\"number\\":2,'
    '\\"text_devanagari\\":\\"इत्यार्षे श्रीमद्रामायणे सप्तमः सर्गः ।। 9.2 ।।\\",'
    '\\"transliteration\\":\\"ityārṣe ...\\",\\"translation\\":null}}],'
)


# --- RSC payload parsing -----------------------------------------------------

def test_parse_sarga_extracts_and_strips(fetch_mod):
    verses = fetch_mod.parse_sarga(PARSE_FIXTURE, 9)
    assert set(verses.keys()) == {1}  # colophon object (number 2) stripped
    v = verses[1]
    assert v["text_devanagari"] == "ततो गच्छति विप्रेन्द्रं ।। 7.9.1 ।।"
    assert v["transliteration"] == "tato gacchati viprendraṃ || 7.9.1 ||"
    assert v["translation"] == "Then, as the lord of Brahmans went..."
    assert v["explanation"] is None


def test_parse_sarga_strips_danda_padded_markers(fetch_mod):
    raw = PARSE_FIXTURE.replace(
        '\\"number\\":2,', '\\"number\\":2,').replace(
        'इत्यार्षे श्रीमद्रामायणे सप्तमः सर्गः',
        '।। इत्युत्तरकाण्डः समाप्तः ।।')
    verses = fetch_mod.parse_sarga(raw, 9)
    assert set(verses.keys()) == {1}


# --- transliteration ----------------------------------------------------------

def test_transliterate_known_words(gaps_mod):
    assert gaps_mod.transliterate("सीतामादायं") == "sītāmādāyaṃ"
    assert gaps_mod.transliterate("कुशास्तरणसंस्तीर्णे") == "kuśāstaraṇasaṃstīrṇe"
    assert gaps_mod.transliterate("वाल्मीकिः") == "vālmīkiḥ"
    assert gaps_mod.transliterate("ततो गच्छति") == "tato gacchati"
    assert gaps_mod.transliterate("क्षयम्") == "kṣayam"
    assert gaps_mod.transliterate("रामः ॥") == "rāmaḥ ||"


def test_transliteration_agreement_with_site(data, gaps_mod):
    """Generated IAST must closely match the site's own transliteration on
    the verses where the site provides both (style-normalized)."""
    def norm(s):
        s = re.sub(r"(।।|\|\|)\s*7\.\d+\.\d+\s*(।।|\|\|)$", "", s.strip())
        return re.sub(r"[\s|।॥]+", "", s).lower()
    total = exact = 0
    for verses in data.values():
        for f in verses.values():
            if f.get("text_devanagari") and f.get("transliteration"):
                total += 1
                if norm(gaps_mod.transliterate(f["text_devanagari"])) == \
                        norm(f["transliteration"]):
                    exact += 1
    assert total > 1600
    assert exact / total >= 0.88


# --- gap-fill extraction -------------------------------------------------------

def test_normalize_alt(gaps_mod):
    assert gaps_mod.normalize_alt("अ ब ।ग ह ।। इति ।।") == "अ ब । ग ह ।। इति ।।"
    assert gaps_mod.normalize_alt("  x  ") == "x"


def test_extract_translation_block_order(gaps_mod):
    ocr = """+ VALMIKI-RAMAYANA
1127
T42ddH: H;
Canto CVIII
स त्वं मनोमयः पुत्रः
ITIMT AT gl fowj
“Earlier you were born as Manu,
the son of Vivasvan. (10)
ततः प्रबुद्धो राजर्षिः
qd: Welgl WS q ST
“On waking, the king heard the
curse. (11)
"""
    text, marker = gaps_mod.extract_translation(ocr, 11, 108)
    assert marker == "(11)"
    assert text.startswith("“On waking, the king heard")


def test_extract_translation_range_and_emdash(gaps_mod):
    ocr = """Canto LXXI
alpha beta gamma. (21)
the scion of the Raghus then having saluted
the great sage, started for his apartment.
(22—24)
"""
    text, marker = gaps_mod.extract_translation(ocr, 24, 71)
    assert marker == "(22-24)"
    assert "saluted the great sage" in text


def test_extract_translation_page_head_filtered(gaps_mod):
    ocr = """Canto CIII
verse eleven text
goes here speaking of welfare. (11)
+ VALMIKI-RAMAYANA
1120
dṛṣṭvā tu āśramam āsīnam
“Then the mighty Rama worshipped him
with offerings. (12)
"""
    text, marker = gaps_mod.extract_translation(ocr, 12, 103)
    assert marker == "(12)"
    assert "VALMIKI-RAMAYANA" not in text
    assert text.startswith("“Then the mighty Rama worshipped")


# --- dataset integrity ----------------------------------------------------------

def test_dataset_complete(data):
    assert set(data.keys()) == {str(s) for s in range(42, 112)}
    total = sum(len(v) for v in data.values())
    assert total == 1668
    incomplete = [(s, n) for s, vv in data.items() for n, f in vv.items()
                  if not (f.get("text_devanagari") and f.get("transliteration")
                          and f.get("translation"))]
    assert incomplete == []


def test_dataset_no_colophons(data):
    for verses in data.values():
        for f in verses.values():
            deva = f.get("text_devanagari") or ""
            assert not re.sub(r"^[।॥\s]+", "", deva).startswith("इत्यार्षे")


def test_sarga_page_map(data_path=REPO / "dataset" / "uttara-sarga-pages.json"):
    m = json.loads(data_path.read_text())
    assert set(m["sargas"].keys()) == {str(s) for s in range(42, 112)}
    for s in m["sargas"].values():
        assert s["start_page"] <= s["end_page"]
