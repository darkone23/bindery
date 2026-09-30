"""Ingest-stage fixture tests.

Proves `bindery ingest` end-to-end on a tiny committed 3-page PDF
(tests/fixtures/fixture3.pdf) so the stage is verified without the
2303-page Ramayana run.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "fixture3.pdf"
SOURCE_URL = "fixture://tests/fixtures/fixture3.pdf"


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
    bindery.ingest(
        FIXTURE, out, dpi=600, source_url=SOURCE_URL, gray=True
    )
    return out


def test_fixture_has_three_pages(bindery):
    assert bindery.page_count(FIXTURE) == 3


def test_ingest_renders_three_canonical_pages(archive):
    names = sorted(p.name for p in archive.glob("page-*.png"))
    assert names == ["page-0001.png", "page-0002.png", "page-0003.png"]


def test_manifest_source_block(archive, bindery):
    manifest = json.loads((archive / "manifest.json").read_text())
    assert manifest["stage"] == "ingest"
    src = manifest["source"]
    assert src["pages"] == 3
    assert src["url"] == SOURCE_URL
    assert src["file"] == "fixture3.pdf"
    assert src["sha256"] == bindery.sha256_file(FIXTURE)
    assert src["size_bytes"] == FIXTURE.stat().st_size
    assert int(src["pdfinfo"]["Pages"]) == 3


def test_manifest_render_block(archive):
    manifest = json.loads((archive / "manifest.json").read_text())
    assert manifest["render"]["dpi"] == 600
    assert manifest["render"]["format"] == "png"
    assert manifest["schema_version"] == 1


def test_manifest_page_hashes_match_files(archive, bindery):
    manifest = json.loads((archive / "manifest.json").read_text())
    assert [p["page"] for p in manifest["pages"]] == [1, 2, 3]
    for entry in manifest["pages"]:
        f = archive / entry["file"]
        assert f.is_file(), entry["file"]
        assert bindery.sha256_file(f) == entry["sha256"]
        assert entry["size_bytes"] == f.stat().st_size


def test_pages_have_distinct_content(archive, bindery):
    manifest = json.loads((archive / "manifest.json").read_text())
    hashes = {p["sha256"] for p in manifest["pages"]}
    assert len(hashes) == 3


def test_verify_reports_ok(archive, bindery, capsys):
    assert bindery.verify(archive) == 0
    assert "OK" in capsys.readouterr().out


def test_resume_restores_missing_page(archive, bindery, tmp_path):
    # fresh ingest into a second dir, then delete one page and resume
    out = tmp_path / "resume-archive"
    bindery.ingest(FIXTURE, out, dpi=600, source_url=SOURCE_URL, gray=True)
    victim = out / "page-0002.png"
    victim.unlink()
    bindery.ingest(
        FIXTURE, out, dpi=600, source_url=SOURCE_URL, gray=True, resume=True
    )
    assert victim.is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert [p["page"] for p in manifest["pages"]] == [1, 2, 3]
    assert bindery.verify(out) == 0
