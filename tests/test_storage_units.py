"""Storage spot-check unit tests (HOL-258): page sampling, page lists,
and verify --spot/--pages against a synthetic manifest."""

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


# --- spot sampling --------------------------------------------------------

def test_spot_indices_first_last_always(b):
    assert b.spot_indices(2303, 11)[0] == 1
    assert b.spot_indices(2303, 11)[-1] == 2303


def test_spot_indices_deterministic_sorted(b):
    assert b.spot_indices(2303, 11) == sorted(b.spot_indices(2303, 11))
    assert len(b.spot_indices(2303, 11)) == 11


def test_spot_indices_count_clamped(b):
    assert b.spot_indices(5, 99) == [1, 2, 3, 4, 5]
    assert b.spot_indices(5, 1) == [1]
    assert b.spot_indices(1, 10) == [1]


# --- page list parsing ----------------------------------------------------

def test_parse_page_list(b):
    assert b.parse_page_list("1,2,300") == [1, 2, 300]
    assert b.parse_page_list("2303,1,2303") == [1, 2303]
    with pytest.raises(SystemExit):
        b.parse_page_list("")
    with pytest.raises(SystemExit):
        b.parse_page_list("0,5")


# --- verify spot/pages mode ----------------------------------------------

@pytest.fixture()
def mini_archive(tmp_path):
    """A 4-page synthetic archive with a manifest, sized for spot checks."""
    arch = tmp_path / "archive"
    arch.mkdir()
    import hashlib

    entries = []
    for n in range(1, 5):
        f = arch / f"page-{n:04d}.png"
        f.write_bytes(f"page-{n}".encode())
        entries.append({
            "page": n,
            "file": f.name,
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "size_bytes": f.stat().st_size,
        })
    (arch / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "stage": "ingest",
        "source": {"pages": 4, "sha256": "x", "size_bytes": 1},
        "render": {"dpi": 600, "format": "png", "color": False},
        "pages": entries,
    }))
    return arch


def test_verify_pages_mode_ok_and_table(b, mini_archive, capsys):
    rc = b.verify(mini_archive, pages=[1, 4])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK 1 page-0001.png" in out
    assert "OK 4 page-0004.png" in out
    assert "[pages(2)]" in out


def test_verify_spot_mode_table(b, mini_archive, capsys):
    rc = b.verify(mini_archive, spot=3)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[spot(3)]" in out
    # first and last always in the sample
    assert "OK 1 " in out and "OK 4 " in out


def test_verify_pages_unknown_page_exits(b, mini_archive):
    with pytest.raises(SystemExit):
        b.verify(mini_archive, pages=[99])


def test_verify_size_mismatch_detected(b, mini_archive, tmp_path, capsys):
    p = mini_archive / "page-0002.png"
    saved = p.read_bytes()
    p.write_bytes(saved + b"!")
    rc = b.verify(mini_archive, pages=[2])
    out = capsys.readouterr().out
    assert rc == 1
    assert "SIZE MISMATCH" in out and "HASH MISMATCH" in out
