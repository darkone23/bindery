#!/usr/bin/env python3
"""validate dataset/correspondences/*.json against the correspondences/v1 schema.

Checks dataset shape, id hygiene, kanda/sarga formats, enums, and the
refs-required-unless-beyond_valmiki rule. Exit 0 = all datasets clean.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "dataset" / "correspondences"

SCHEMA = "correspondences/v1"
KANDAS = ("bala", "ayodhya", "aranya", "kishkindha", "sundara", "yuddha", "uttara")
KINDS = ("summary", "narrative", "gloss", "scene")
CONFIDENCE = ("high", "medium", "low")
SARGA_RE = r"^\d+(-\d+)?$"

PROBLEM = 0


def err(dataset: str, where: str, msg: str) -> None:
    global PROBLEM
    PROBLEM += 1
    print(f"{dataset}: {where}: {msg}")


def check_ref(dataset: str, eid: str, i: int, ref: dict) -> None:
    where = f"entry {eid} refs[{i}]"
    if ref.get("kanda") not in KANDAS:
        err(dataset, where, f"kanda must be one of {KANDAS}")
    sarga = ref.get("sarga")
    if not isinstance(sarga, str) or not (
        sarga == "various" or re.fullmatch(SARGA_RE, sarga)
    ):
        err(dataset, where, f"sarga {sarga!r} must match {SARGA_RE} or 'various'")
    if ref.get("confidence") not in CONFIDENCE:
        err(dataset, where, f"confidence must be one of {CONFIDENCE}")
    if "verified_against" in ref and not isinstance(ref["verified_against"], str):
        err(dataset, where, "verified_against must be a string when present")


def check_dataset(path: Path) -> None:
    name = path.name
    d = json.loads(path.read_text())

    if d.get("schema") != SCHEMA:
        err(name, "top", f"schema must be {SCHEMA!r}")
    ds = d.get("dataset")
    if not ds:
        err(name, "top", "dataset id required")

    target = d.get("target") or {}
    if target.get("work") != "Valmiki-Ramayana":
        err(name, "target", "work must be Valmiki-Ramayana")
    if target.get("numbering") != "gita-press-vulgate":
        err(name, "target", "numbering must be gita-press-vulgate")

    sources = d.get("sources") or []
    if not sources:
        err(name, "sources", "at least one source required")
    sids = set()
    for s in sources:
        sid = s.get("id")
        if not sid or sid in sids:
            err(name, "sources", f"source id missing/duplicate: {sid!r}")
        sids.add(sid)
        if s.get("source_type") not in ("text", "film"):
            err(name, f"source {sid}", "source_type must be text|film")
        if not s.get("title") or not s.get("url"):
            err(name, f"source {sid}", "title and url required")

    seen = set()
    for e in d.get("entries") or []:
        eid = e.get("id", "<missing>")
        where = f"entry {eid}"
        sid = e.get("source_id")
        if not (sid and eid.startswith(f"{sid}-")):
            err(name, where, f"id must start with its source_id prefix ('{sid}-')")
        if eid in seen:
            err(name, where, "duplicate entry id")
        seen.add(eid)
        if e.get("source_id") not in sids:
            err(name, where, f"unknown source_id {e.get('source_id')!r}")
        if e.get("kind") not in KINDS:
            err(name, where, f"kind must be one of {KINDS}")
        if not e.get("episode"):
            err(name, where, "episode required")
        quote = e.get("quote")
        refs = e.get("refs") or []
        if refs:
            for i, ref in enumerate(refs):
                check_ref(name, eid, i, ref)
        elif not e.get("beyond_valmiki"):
            err(name, where, "refs required unless beyond_valmiki is true")
        if quote is None:
            for s in sources:
                if s.get("id") == e.get("source_id") and s.get("source_type") == "text":
                    err(name, where, "quote required for text sources")


def main(argv=None) -> int:
    files = sorted(HERE.glob("*.json"))
    if not files:
        print(f"no datasets found in {HERE}")
        return 1
    for p in files:
        check_dataset(p)
    if PROBLEM:
        print(f"FAILED: {PROBLEM} problem(s)")
        return 1
    print(f"OK: {len(files)} dataset(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
