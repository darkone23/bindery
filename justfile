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
