"""correspondences renderer checks (HOL-263 board view)."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "render_correspondences", REPO / "scripts" / "render_correspondences.py")
rc = importlib.util.module_from_spec(_spec)
sys.modules["render_correspondences"] = rc
_spec.loader.exec_module(rc)


def _mini_dataset():
    return {
        "schema": "correspondences/v1",
        "dataset": "t",
        "description": "A <script>alert(1)</script> description",
        "sources": [{"id": "s", "title": "T <b>bold</b>", "source_type": "text",
                     "publication": "P", "url": "https://example.org",
                     "locator_type": "page"}],
        "entries": [{
            "id": "s-001", "source_id": "s", "kind": "narrative",
            "locator": "p. 3", "quote": 'he said "hello" & <left>',
            "episode": "e", "refs": [{"kanda": "bala", "sarga": "27-28",
                                      "confidence": "high",
                                      "verified_against": "ramayana.info bala/27"}],
            "beyond_valmiki": False, "source_citation_in_text": None,
            "notes": "n",
        }, {
            "id": "s-002", "source_id": "s", "kind": "gloss",
            "locator": "p. 9", "quote": None, "episode": "e2",
            "refs": [], "beyond_valmiki": True,
            "source_citation_in_text": None, "notes": None,
        }],
    }


def test_html_renders_and_escapes():
    page = rc.render_html([_mini_dataset()])
    assert "s-001" in page and "s-002" in page
    assert "bala 27-28" in page and "✓" in page
    assert "beyond Valmiki" in page
    # raw angle brackets and quotes must not survive un-escaped
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "<left>" not in page
    assert "chip hi" in page


def test_markdown_renders_table():
    md = rc.render_markdown([_mini_dataset()])
    assert md.count("| entry | source locator | what it retells | Ramayana ref |") == 1
    assert "`bala 27-28` (high) ✓" in md
    assert "**beyond Valmiki**" in md
    assert "s-001" in md and "s-002" in md


def test_renders_real_datasets():
    files = sorted((REPO / "dataset" / "correspondences").glob("*.json"))
    datasets = [json.loads(p.read_text()) for p in files]
    page = rc.render_html(datasets)
    n = sum(len(d.get("entries", [])) for d in datasets)
    assert page.count("<tr id=") == n
    assert n >= 27  # dream-of-ravan 20 + bajrangbali 7
