#!/usr/bin/env python3
"""Spot-check a synced bindery storage tree against its page manifests (HOL-258).

Verifies sha256 + size for the storage spot-set of archive/ and enhance/,
cross-checks that each enhance page derives from the matching archive page
(source_sha256), and prints the compare table.

Runs anywhere the tree is visible. Over ssh to the TrueNAS (no repo needed):

    ssh orpheus@truenas.local "python3 - /mnt/flash/household/bindery/m3" \
        < scripts/storage-spot-check.py

Locally (same output):

    python3 scripts/storage-spot-check.py /mnt/flash/household/bindery/m3

Exit 0 iff every check passes.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# >=10 pages incl. the supplement boundary (2159) and the colophon (2303);
# matches SPOT_PAGES in the justfile and the table in docs/STORAGE.md.
SPOT_PAGES = [1, 2, 300, 700, 1169, 1500, 1900, 2159, 2200, 2259, 2303]

REQUIRED = (2159, 2303)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(prog="storage-spot-check")
    ap.add_argument("root", type=Path, help="synced storage tree (has archive/ + enhance/)")
    args = ap.parse_args()
    root: Path = args.root

    failures = 0
    manifests = {}
    for tree in ("archive", "enhance"):
        mpath = root / tree / "manifest.json"
        try:
            manifests[tree] = {e["page"]: e for e in json.loads(mpath.read_text())["pages"]}
        except FileNotFoundError:
            print(f"MISSING manifest: {mpath}")
            failures += 1
            manifests[tree] = {}

    if failures == 0 and not set(REQUIRED) <= set(SPOT_PAGES):
        print(f"CONFIG ERROR: spot set must include {REQUIRED}")
        return 2

    print(f"spot-set: {SPOT_PAGES} (required {list(REQUIRED)})")
    for tree in ("archive", "enhance"):
        print(f"-- {tree}/ vs {tree}/manifest.json --")
        for n in SPOT_PAGES:
            entry = manifests[tree].get(n)
            if entry is None:
                print(f"FAIL {tree} {n}: not in manifest")
                failures += 1
                continue
            f = root / tree / entry["file"]
            if not f.is_file():
                print(f"FAIL {tree} {n}: missing {entry['file']}")
                failures += 1
                continue
            size = f.stat().st_size
            digest = sha256_file(f)
            problems = []
            if size != entry["size_bytes"]:
                problems.append(f"size {size} != {entry['size_bytes']}")
            if digest != entry["sha256"]:
                problems.append(f"sha256 {digest} != {entry['sha256']}")
            if problems:
                print(f"FAIL {tree} {n} {entry['file']}: " + "; ".join(problems))
                failures += 1
            else:
                extra = ""
                if tree == "enhance" and n in manifests.get("archive", {}):
                    src = manifests["archive"][n]["sha256"]
                    if entry.get("source_sha256") == src:
                        extra = f" (source_sha256 == archive {src[:12]}…)"
                    else:
                        extra = f" (source_sha256 {entry.get('source_sha256')} != archive {src})"
                        failures += 1
                print(f"OK {tree} {n} {entry['sha256']} {entry['size_bytes']}B{extra}")

    print(f"storage-spot-check {root}: " + ("OK" if failures == 0 else f"FAILED ({failures})"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
