"""correspondences/v1 dataset checks (HOL-263).

The shipped datasets must pass the validator; the validator itself must
actually reject malformed data (kind/enum/sarga/refs-rule probes).
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import validate_correspondences as vc  # noqa: E402

CORR = REPO / "dataset" / "correspondences"


def test_shipped_datasets_validate():
    assert vc.PROBLEM == 0
    files = sorted(CORR.glob("*.json"))
    assert files, "no correspondence datasets found"
    vc.PROBLEM = 0
    for p in files:
        vc.check_dataset(p)
    assert vc.PROBLEM == 0, f"validator problems: {vc.PROBLEM}"


def _tmp_dataset(tmp_path, **entry_overrides):
    base = {
        "schema": "correspondences/v1",
        "dataset": "t",
        "description": "t",
        "target": {"work": "Valmiki-Ramayana", "numbering": "gita-press-vulgate"},
        "sources": [{"id": "s", "title": "T", "source_type": "text",
                     "publication": "P", "url": "https://example.org",
                     "locator_type": "page"}],
        "entries": [{
            "id": "s-001", "source_id": "s", "kind": "narrative",
            "locator": "p. 1", "quote": "q", "episode": "e",
            "refs": [{"kanda": "bala", "sarga": "1-2", "confidence": "high"}],
            "beyond_valmiki": False, "source_citation_in_text": None, "notes": None,
        }],
    }
    base["entries"][0].update(entry_overrides)
    p = tmp_path / "t.json"
    p.write_text(json.dumps(base))
    return p


def _problems(tmp_path, **entry_overrides):
    vc.PROBLEM = 0
    vc.check_dataset(_tmp_dataset(tmp_path, **entry_overrides))
    n, vc.PROBLEM = vc.PROBLEM, 0
    return n


def test_validator_rejects_bad_sarga(tmp_path):
    assert _problems(tmp_path, refs=[{"kanda": "bala", "sarga": "27..28",
                                      "confidence": "high"}]) > 0


def test_validator_rejects_bad_kanda(tmp_path):
    assert _problems(tmp_path, refs=[{"kanda": "ramcharitmanas", "sarga": "1",
                                      "confidence": "low"}]) > 0


def test_validator_rejects_bad_confidence(tmp_path):
    assert _problems(tmp_path, refs=[{"kanda": "bala", "sarga": "1",
                                      "confidence": "sure"}]) > 0


def test_validator_rejects_refs_without_beyond_valmiki(tmp_path):
    assert _problems(tmp_path, refs=[]) > 0


def test_validator_allows_refs_empty_when_beyond_valmiki(tmp_path):
    assert _problems(tmp_path, refs=[], beyond_valmiki=True) == 0


def test_validator_rejects_missing_quote_on_text_source(tmp_path):
    assert _problems(tmp_path, quote=None) > 0


def test_validator_rejects_wrong_source_id_prefix(tmp_path):
    assert _problems(tmp_path, id="x-001") > 0


def test_validator_rejects_bad_numbering(tmp_path):
    p = tmp_path / "n.json"
    p.write_text(json.dumps({
        "schema": "correspondences/v1", "dataset": "t", "description": "t",
        "target": {"work": "Valmiki-Ramayana", "numbering": "gorresio"},
        "sources": [{"id": "s", "title": "T", "source_type": "text",
                     "publication": "P", "url": "https://example.org",
                     "locator_type": "page"}],
        "entries": [],
    }))
    vc.PROBLEM = 0
    vc.check_dataset(p)
    assert vc.PROBLEM > 0
    vc.PROBLEM = 0
