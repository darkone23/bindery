# M5 fixture tests (HOL-264): the committed page slices (21, 59, 68, 1190,
# 2159, 2160) run through the real parse/assemble pipeline. No PDF needed;
# slices are raw -layout output, cleaned exactly like the pipeline does.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extract_english as ex

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "english"
DATASET = Path(__file__).resolve().parents[1] / "dataset"


def fixture_raw(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def clean(raw: str) -> str:
    text, _flags = ex.strip_page_chrome(raw)
    return ex.normalize(text)


def pages21_59_68() -> dict[int, str]:
    return {n: clean(fixture_raw(f"page-{n}.txt")) for n in (21, 59, 68)}


def test_toc_entries_from_page21_slice():
    toc = ex.toc_entries(pages21_59_68())
    assert [k["kanda"] for k in toc["kandas"]] == [1]
    k1 = toc["kandas"][0]
    assert k1["part"] == 1 and k1["name"] == "Bālakāṇḍa"
    sargas = k1["sargas"]
    assert [s["canto_no"] for s in sargas] == list(range(1, 18))
    assert sargas[0]["printed_page"] == 59 and sargas[0]["archive_page"] == 59
    assert sargas[1]["archive_page"] == 68
    assert toc["quirks"] == []


def test_assemble_boundary_between_sarga_1_and_2():
    toc = ex.toc_entries(pages21_59_68())
    sargas = ex.assemble_sargas(pages21_59_68(), toc)
    by_no = {s["sarga"]: s for s in sargas}
    s1, s2 = by_no[1], by_no[2]
    assert (s1["archive_start"], s1["archive_end"]) == (59, 67)
    assert s2["archive_end"] == 71           # ToC slice: sarga 3 starts at 72
    # sarga 1: opener summary + closer from p68 pre-heading
    assert "The celestial sage" in s1["text"]
    assert "Thus ends Canto One" in s1["text"]
    assert s1["closers"] == [68]
    assert "Canto II" not in s1["text"]
    # sarga 2: p68 post-heading segment
    assert "Canto II" in s2["text"]
    assert "Story of" not in s2["text"]       # s1's summary stayed with s1
    assert s1["flags"] == []
    assert s2["flags"] == ["closer_not_found"]


def test_english_prose_filtering():
    toc = ex.toc_entries(pages21_59_68())
    sargas = ex.assemble_sargas(pages21_59_68(), toc)
    s1 = next(s for s in sargas if s["sarga"] == 1)
    prose = s1["english_prose"]
    assert "Story of Śrī Rāma in a nutshell" in prose   # normalized summary kept
    assert all(ex.line_is_english(ln) or not ln.strip()
               for ln in prose.splitlines())
    assert "Who has subdued his self?" in prose          # verse translation kept
    # pure devanagari rows are dropped; mixed rows keep their tail (flagged)
    assert "üÊË◊mÊÀ◊Ë∑§Ëÿ⁄UÊ◊ÊÿáÊ◊˜" not in prose
    assert "conquered anger? Who is possessed of" in prose


def test_reconcile_uttara_committed_map():
    committed = json.loads(
        (DATASET / "uttara-sarga-pages.json").read_text(encoding="utf-8"))
    toc = ex.toc_entries(pages21_59_68())
    # synthetic kanda-7 ToC mirroring the committed M2 map for sargas 42-44
    toc = dict(toc)
    toc["kandas"] = toc["kandas"] + [{
        "part": 2, "kanda": 7, "name": "Uttarakāṇḍa",
        "sargas": [
            {"canto_no": int(n), "title": f"sarga {n}",
             "printed_page": v["start_page"] - 1167,
             "archive_page": v["start_page"]}
            for n, v in sorted(committed["sargas"].items(), key=lambda kv: int(kv[0]))
            if int(n) in (42, 43)
        ] + [{"canto_no": 44, "title": "sarga 44", "printed_page": 997,
              "archive_page": 2164}],
    }]
    report = ex.reconcile_uttara(toc, committed)
    assert report["mismatches"] == []
    assert report["matched"] == 3
    # a deliberate disagreement is flagged, never repaired
    toc["kandas"][-1]["sargas"][0]["archive_page"] = 2160
    report = ex.reconcile_uttara(toc, committed)
    assert len(report["mismatches"]) == 1
    assert report["mismatches"][0]["sarga"] == 42


def test_sarga_index_for_pages():
    toc = ex.toc_entries(pages21_59_68())
    sargas = ex.assemble_sargas(pages21_59_68(), toc)
    idx = ex.sarga_index_for_pages(sargas)
    assert idx[59] == {"kanda": 1, "sarga": 1}
    assert idx[67] == {"kanda": 1, "sarga": 1}
    assert idx[68] == {"kanda": 1, "sarga": 2}
    assert 21 not in idx          # ToC page unmapped
    assert 1 not in idx           # front matter unmapped


def test_write_pages_sidecars(tmp_path):
    pages_raw = {n: fixture_raw(f"page-{n}.txt") for n in (21, 59, 68)}
    chrome_flags = {n: ex.strip_page_chrome(pages_raw[n])[1] for n in pages_raw}
    unmapped = {n: ex.unmapped_english_glyphs(ex.strip_page_chrome(pages_raw[n])[0])
                for n in pages_raw}
    pages = {n: ex.normalize(ex.strip_page_chrome(pages_raw[n])[0])
             for n in (21, 59, 68)}
    toc = ex.toc_entries(pages)
    sargas = ex.assemble_sargas(pages, toc)
    idx = ex.sarga_index_for_pages(sargas)
    sidecars = ex.write_pages(tmp_path, pages, idx, chrome_flags, unmapped)
    assert (tmp_path / "pages" / "page-0059.txt").exists()
    assert (tmp_path / "pages" / "page-0059.json").exists()
    s59 = json.loads((tmp_path / "pages" / "page-0059.json").read_text())
    assert s59["archive_page"] == 59
    assert s59["printed_page"] == 59
    assert s59["sarga"] == 1 and s59["kanda"] == 1
    assert s59["unmapped_glyphs"] == {}
    s21 = sidecars[21]
    assert s21["sarga"] is None and s21["printed_page"] == 21
    assert "chrome:om" in s21["flags"]


def test_toc_dataset_envelope(tmp_path):
    toc = ex.toc_entries(pages21_59_68())
    pdf = Path(__file__).resolve().parents[1] / "dataset" / \
        "Valmiki_Ramayana_Gita_Press.pdf"
    env = ex.toc_dataset_envelope(toc, pdf)
    assert env["schema_version"] == 1
    assert env["mapping_version"] == ex.MAPPING_VERSION
    assert env["part_offsets"] == {"1": 0, "2": 1167}
    assert env["source"]["pages"] == 2303
    assert len(env["source"]["sha256"]) == 64
    assert env["kandas"][0]["name"] == "Bālakāṇḍa"
    assert env["source"]["url"].endswith(".pdf")
