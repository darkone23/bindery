# M5 QC unit tests (HOL-264): coverage stats + page-gap logic for the QC
# report builder. Pure functions over synthetic records.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extract_english as ex


def sarga(k, s, start, end, flags=(), text="english words here"):
    return {"part": 1 if k <= 4 else 2, "kanda": k, "sarga": s,
            "archive_start": start, "archive_end": end,
            "flags": list(flags), "text": text,
            "english_prose": text, "closers": [end], "heading_pages": [start]}


def test_kanda_coverage_counts_and_textless():
    sargas = [
        sarga(1, 1, 59, 67),
        sarga(1, 2, 68, 71),
        sarga(1, 3, 72, 75, flags=("closer_not_found",), text=""),
        sarga(4, 67, 1160, 1168),
    ]
    cov = ex.kanda_coverage(sargas)
    k1 = next(k for k in cov if k["kanda"] == 1)
    assert k1["sargas"] == 3
    assert k1["textless"] == 1
    assert k1["flag_counts"] == {"closer_not_found": 1}
    assert k1["archive_span"] == (59, 75)
    k4 = next(k for k in cov if k["kanda"] == 4)
    assert k4["archive_span"] == (1160, 1168)


LONG = " ".join(f"word{i}" for i in range(30))


def test_page_gaps_detects_empty_and_thin_pages():
    pages = {1: "", 2: LONG, 3: ""}
    gaps = ex.page_gaps(pages, first=1, last=3, min_english=25)
    assert 1 in gaps and 3 in gaps
    assert 2 not in gaps


def test_qc_spot_checks_all_present():
    pages = {59: "Thus ends Canto Forty-one in the Uttarakāṇḍa of the glorious",
             2303: "THE END OF THE RĀMĀYAṆA OF VĀLMĪKI"}
    checks = ex.spot_check_report(pages, toc=None, sargas=None)
    names = [c["name"] for c in checks]
    assert "toc_p21_entry1" in names and "colophon_2303" in names
    ok = {c["name"]: c["ok"] for c in checks}
    assert ok["colophon_2303"] is True
