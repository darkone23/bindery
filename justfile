set shell := ["bash", "-cu"]

# list recipes
default:
    @just --list

# build the bindery package with nix (produces ./result)
build:
    nix build

# fixture pytest suite: proves the ingest stage on a tiny committed PDF
ingest-fixture:
    nix develop -c python3 -m pytest -q tests

# M2 structure pass over the archive (docling layout + tesseract OCR).
# Tooling lives in the stage's devenv (devenv.nix: docling-slim +
# tesseract + poppler; unfree confined to this env — see devenv.yaml).
# First run downloads docling layout models to ~/.cache/docling
# (network needed once).
structure stage="all":
    devenv shell -- python3 structure.py {{stage}} \
        --archive archive --out build/structure

# per-page inspector: "what does page N contain?" (per-page mode)
page n:
    devenv shell -- python3 structure.py page {{n}} --out build/structure

# pytest for the structure stage: pure unit tests + the committed
# 7-page fixture slice (pages 283-289: Ayodhya title, Canto I -> II
# boundary) run through the real docling+tesseract pipeline
structure-fixture:
    devenv shell -- python3 -m pytest -q \
        tests/test_structure_units.py tests/test_structure_fixture.py

# build order.json for the book.toml slice (validates against the manifest)
assemble:
    nix develop -c bindery assemble --book book.toml --out build

# crop ordered pages to the trim profile (build/trim/ + trim.json)
trim: assemble
    nix develop -c bindery trim --book book.toml --out build

# signature-impose onto duplex Letter: press.pdf + proof-screen.pdf.
# "just impose --full" runs the complete M3 chain on the book profile.
impose mode="":
    @if [ "{{mode}}" = "--full" ]; then just supplement; else just impose-m1; fi

impose-m1: trim
    nix develop -c bindery impose --book book.toml --out build

# apply [enhance] profile ops -> build/enhance/ (originals untouched;
# near-no-op expected on the clean vector body)
enhance:
    nix develop -c bindery enhance --book book.toml --out build

# render the apparatus leaves -> build/apparatus/
apparatus:
    nix develop -c bindery apparatus --book book.toml --out build

# complete M3 chain on the book.toml profile (targeted supplement:
# ToC + Uttara 42-111): enhance -> apparatus -> assemble -> trim -> impose
supplement: enhance
    nix develop -c bindery apparatus --book book.toml --out build
    nix develop -c bindery assemble --book book.toml --archive build/enhance --out build
    nix develop -c bindery trim --book book.toml --archive build/enhance --out build
    nix develop -c bindery impose --book book.toml --out build
    @echo "supplement outputs: build/press.pdf build/proof-screen.pdf (see PRINTING.md)"

# full M1 chain: order -> trim -> press + proof
proof: impose
    @echo "M1 outputs: build/press.pdf build/proof-screen.pdf (see PRINTING.md)"

# full ingest: download-free; expects the PDF already at dataset/ (gitignored)
ingest:
    nix develop -c bindery ingest dataset/Valmiki_Ramayana_Gita_Press.pdf \
        --source-url "https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/Valmiki_Ramayana_Gita_Press.pdf" \
        --out archive --gray

# recheck an existing archive against its manifest
verify:
    nix develop -c bindery verify archive

# M4 gate (HOL-259): profile-check sample scans of the 1970s edition
# before the board commits to scanning the whole book. Per-page dpi /
# page-size / tonal report -> build/sample-qa/report.{json,md};
# exit 1 on WARN findings (rescan advised).
sample-qa DIR:
    nix develop -c bindery sample-qa {{DIR}} --out build

# --- durable storage (HOL-258) — runbook: docs/STORAGE.md ---

# paperclip VM staging bundle (frozen M3 outputs; rsync-able from the tailnet)
VM_STAGING := "orpheus@paperclip.elf-lizard.ts.net:bindery-m3-storage/"
# TrueNAS dataset path the board's runbook creates (docs/STORAGE.md)
NAS_TARGET := "orpheus@truenas.local:/mnt/flash/household/bindery/m3"
# >=10 pages incl. the supplement boundary (2159) and the colophon (2303)
SPOT_PAGES := "1,2,300,700,1169,1500,1900,2159,2200,2259,2303"

# two-hop sync: paperclip VM staging -> laptop scratch -> TrueNAS dataset.
# Run on the laptop (it holds both SSH trusts; the NAS has no route to the VM).
# First run: create the dataset + fix ownership first — docs/STORAGE.md §1.
storage-sync TARGET=NAS_TARGET TMP="/tmp/bindery-sync-tmp":
    rsync -aH --info=stats2 {{VM_STAGING}} {{TMP}}/
    rsync -aH --info=stats2 {{TMP}}/ {{TARGET}}/
    rm -rf {{TMP}}

# checksum spot-set of a synced tree, run on any host that sees it locally
storage-verify ROOT:
    nix develop -c bindery verify {{ROOT}}/archive --pages {{SPOT_PAGES}}
    nix develop -c bindery verify {{ROOT}}/enhance --pages {{SPOT_PAGES}}

# checksum spot-set over ssh straight on the TrueNAS (no repo needed there)
storage-verify-nas NAS_PATH="/mnt/flash/household/bindery/m3" NAS_HOST="orpheus@truenas.local":
    ssh {{NAS_HOST}} "python3 - {{NAS_PATH}}" < scripts/storage-spot-check.py

# push main to GitHub origin + the sync-hub mirror on the paperclip VM (HOL-254)
push:
    git push origin main
    git push mirror main

# --- M4 typeset supplement (HOL-259) -----------------------------------------

# M4a: re-harvest the Uttara e-text (sargas 42-111) from ramayana.info
# (board-directed source) into dataset/uttara-eText-ramayana-info.json.
# Idempotent; network needed.
uttara-eText:
    nix develop -c python3 fetch_uttara_etext.py --out dataset/uttara-eText-ramayana-info.json

# M4a: close the dataset's field gaps — devanagari from the site's alt
# rendering, IAST generated from Devanagari, translations lifted from the
# Gita Press archive scans (printed translation the fascicle continues).
# Writes dataset/uttara-eText-QC.md; needs tesseract (devenv shell).
uttara-gapfill:
    devenv shell -- python3 fill_uttara_gaps.py --archive archive

# M4b/c: full fascicle chain — typeset sargas 42-111 (WeasyPrint, 70s-
# mirror profile) -> trim -> impose. Outputs build/press.pdf (66 duplex
# Letter sheets, 17 signatures) + proof-screen.pdf + build/typeset/
# (raster archive + manifest) + build/order.json. Needs the typeset
# devshell (nix develop .#typeset).
fascicle:
    mkdir -p build
    nix develop .#typeset -c python3 uttara_typeset.py --sargas 42-111 --out build
    nix develop -c bindery trim --book book-fascicle.toml --archive build/typeset
    nix develop -c bindery impose --book book-fascicle.toml --out build
    @echo "fascicle outputs: build/press.pdf build/proof-screen.pdf (see PRINTING.md)"

# fetch the source PDF into dataset/ (public URL, no auth; run once)
dataset-fetch:
    mkdir -p dataset
    curl -fL --retry 3 -o dataset/Valmiki_Ramayana_Gita_Press.pdf \
        "https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/Valmiki_Ramayana_Gita_Press.pdf"
    pdfinfo dataset/Valmiki_Ramayana_Gita_Press.pdf

# --- M5 English extraction + ToC mapping (HOL-264) ----------------------------

# per-page -layout extraction -> chrome cleanup -> diacritics normalization;
# ToC dataset (archive 21-58 / 1170-1190), per-sarga prose, QC report.
# Outputs build/english/{pages,sargas,toc.json,sargas-index.json,qc.*}.
# Needs the source PDF at dataset/ (gitignored; `just dataset-fetch`).
extract-english PDF="dataset/Valmiki_Ramayana_Gita_Press.pdf" OUT="build/english":
    nix develop -c python3 extract_english.py --pdf {{PDF}} --out {{OUT}}

# stage the M5 outputs to the paperclip-VM staging dir (HOL-258 pattern):
# per-page + per-sarga text, datasets, QC + a provenance manifest (source
# url/sha256, extraction commit, mapping version). TrueNAS sync = laptop
# two-hop (`just storage-sync` pattern; see docs/ENGLISH-EXTRACTION.md).
m5-stage OUT="build/english" ROOT="$HOME/bindery-m5-storage/english" PDF="dataset/Valmiki_Ramayana_Gita_Press.pdf":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{ROOT}}
    rsync -a --delete {{OUT}}/pages {{OUT}}/sargas {{OUT}}/toc.json \
        {{OUT}}/sargas-index.json {{OUT}}/qc.json {{OUT}}/qc.md {{ROOT}}/
    cp dataset/toc-gita-press-english.json dataset/english-extraction-QC.md {{ROOT}}/ 2>/dev/null || true
    COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    SHA="$(sha256sum {{PDF}} | cut -d' ' -f1)"
    nix develop -c python3 scripts/m5_manifest.py {{ROOT}} "$COMMIT" "$SHA"

# HOL-263: validate dataset/correspondences/*.json against the
# correspondences/v1 schema (enum/id/sarga hygiene; see dataset/correspondences/README.md)
correspondences-validate:
    python3 scripts/validate_correspondences.py

# HOL-263: rebuild dream-of-ravan.json from the raw episode inventory
# (run after editing scripts/build_dor_dataset.py corrections)
correspondences-build:
    python3 scripts/build_dor_dataset.py
    python3 scripts/validate_correspondences.py

# HOL-263: render the correspondences as a board-viewable HTML page
# (self-contained, no assets/JS) — also --format md for issue documents
correspondences-html:
    python3 scripts/render_correspondences.py --format html \
        --out dataset/correspondences/correspondences.html
