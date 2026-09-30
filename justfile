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
# Impure/unfree tooling is confined to this recipe's nix shell; first run
# downloads docling layout models to ~/.cache/docling (network needed once).
structure stage="all":
    nix develop .#structure -c python3 structure.py {{stage}} \
        --archive archive --out build/structure

# pytest for the structure stage: pure unit tests + the committed
# 7-page fixture slice (pages 283-289: Ayodhya title, Canto I -> II
# boundary) run through the real docling+tesseract pipeline
structure-fixture:
    nix develop .#structure -c python3 -m pytest -q \
        tests/test_structure_units.py tests/test_structure_fixture.py

# build order.json for the book.toml slice (validates against the manifest)
assemble:
    nix develop -c bindery assemble --book book.toml --out build

# crop ordered pages to the trim profile (build/trim/ + trim.json)
trim: assemble
    nix develop -c bindery trim --book book.toml --out build

# signature-impose onto duplex Letter: press.pdf + proof-screen.pdf
impose: trim
    nix develop -c bindery impose --book book.toml --out build

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

# fetch the source PDF into dataset/ (public URL, no auth; run once)
dataset-fetch:
    mkdir -p dataset
    curl -fL --retry 3 -o dataset/Valmiki_Ramayana_Gita_Press.pdf \
        "https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/Valmiki_Ramayana_Gita_Press.pdf"
    pdfinfo dataset/Valmiki_Ramayana_Gita_Press.pdf
