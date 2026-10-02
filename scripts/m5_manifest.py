#!/usr/bin/env python3
"""m5_manifest — provenance manifest for the M5 English-extraction staging.

Usage: m5_manifest.py ROOT COMMIT PDF_SHA256
Writes ROOT/manifest.json (source url/sha256, extraction commit, mapping
version, output inventory) per the HOL-258 staging pattern.
"""
import datetime
import json
import sys

SOURCE_URL = ("https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/"
              "Valmiki_Ramayana_Gita_Press.pdf")


def main() -> int:
    root, commit, sha = sys.argv[1], sys.argv[2], sys.argv[3]
    manifest = {
        "schema_version": 1,
        "stage": "m5-english-extraction",
        "created_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "source": {"url": SOURCE_URL, "sha256": sha, "pages": 2303},
        "extraction": {
            "commit": commit, "mapping_version": "1",
            "pipeline": "pdftotext -layout + extract_english.py "
                        "(deterministic, flag-no-repair)",
        },
        "outputs": {
            "pages": "per-page cleaned+normalized text + sidecars",
            "sargas": "per-sarga English prose (kKK-sNNN.txt)",
            "toc.json": "structured ToC dataset (committed copy in git)",
            "sargas-index.json": "per-sarga metadata (committed copy in git)",
            "qc.json/qc.md": "QC report (committed copy in git)",
        },
    }
    with open(f"{root}/manifest.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=1) + "\n")
    print("manifest ->", f"{root}/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
