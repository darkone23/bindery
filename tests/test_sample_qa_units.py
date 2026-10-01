"""Sample-QA unit tests (HOL-259 M4 gate): scan profiling, findings, and
report writing against synthetic scan images."""

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


def make_scan(path, size=(3700, 5562), dpi=(600, 600), mode="L",
              flat=None, paint=None):
    """Write a synthetic scan: wide tonal range unless flat, optional
    color paint (RGB tuple) as a left-edge block."""
    from PIL import Image, ImageDraw

    img = Image.new(mode, size, 128 if mode == "L" else (255, 255, 255))
    d = ImageDraw.Draw(img)
    if flat is None:
        if mode == "L":
            d.rectangle([0, 0, size[0] // 5, size[1] - 1], fill=0)
            d.rectangle([size[0] * 4 // 5, 0, size[0] - 1, size[1] - 1],
                        fill=255)
        else:
            d.rectangle([size[0] * 4 // 5, 0, size[0] - 1, size[1] - 1],
                        fill=(0, 0, 0))
    if paint:
        d.rectangle([0, 0, 800, size[1] - 1], fill=paint)
    kw = {"dpi": dpi} if dpi else {}
    img.save(path, **kw)
    return path


def run_qa(b, tmp_path, *names_kwargs):
    scan = tmp_path / "scans"
    scan.mkdir(exist_ok=True)
    for name, kwargs in names_kwargs:
        make_scan(scan / name, **kwargs)
    rc = b.sample_qa(scan, tmp_path / "build")
    report = json.loads(
        (tmp_path / "build" / "sample-qa" / "report.json").read_text())
    return rc, report


def findings_messages(report, level=None):
    return [f["message"] for f in report["findings"]
            if level is None or f["level"] == level]


# --- clean sample -----------------------------------------------------------

def test_clean_sample_ok(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("page-01.png", {}),
                        ("page-02.png", {}))
    assert rc == 0
    assert report["verdict"] == "ok"
    assert findings_messages(report, "WARN") == []
    assert report["pages"][0]["dpi"] == 600.0
    # 3700x5562 px at 600 dpi -> source-B trim geometry
    assert report["pages"][0]["pt"] == [444.0, 667.4]
    assert report["stage"] == "sample-qa"
    assert (tmp_path / "build" / "sample-qa" / "report.md").is_file()


def test_color_plate_is_info_only(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("plate-01.png", {"mode": "RGB",
                                          "paint": (200, 30, 30)}))
    assert rc == 0
    assert report["verdict"] == "ok"
    assert report["pages"][0]["channel_spread"] > 3.0
    assert any("color content" in m for m in findings_messages(report, "INFO"))


# --- WARN findings ----------------------------------------------------------

def test_low_dpi_warns(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("page-01.png", {"dpi": (300, 300)}))
    assert rc == 1
    assert report["verdict"] == "rescan-advised"
    assert any("dpi below" in m for m in findings_messages(report, "WARN"))


def test_missing_dpi_warns(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("page-01.png", {"dpi": None}))
    assert rc == 1
    assert report["pages"][0]["pt"] is None
    assert any("no dpi metadata" in m for m in findings_messages(report, "WARN"))


def test_flat_tonal_warns(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("page-01.png", {"flat": True}))
    assert rc == 1
    assert any("narrow tonal" in m for m in findings_messages(report, "WARN"))


def test_mixed_sizes_warn(b, tmp_path):
    rc, report = run_qa(b, tmp_path,
                        ("page-01.png", {}),
                        ("page-02.png", {"size": (3000, 5000)}))
    assert rc == 1
    msgs = findings_messages(report, "WARN")
    assert any("mixed pixel sizes" in m for m in msgs)
    assert any("mixed physical page sizes" in m for m in msgs)


# --- edges ------------------------------------------------------------------

def test_empty_dir_fails(b, tmp_path):
    scan = tmp_path / "empty"
    scan.mkdir()
    assert b.sample_qa(scan, tmp_path / "build") == 1


def test_only_nonimages_fails(b, tmp_path):
    scan = tmp_path / "notes"
    scan.mkdir()
    (scan / "readme.txt").write_text("not a scan")
    assert b.sample_qa(scan, tmp_path / "build") == 1
