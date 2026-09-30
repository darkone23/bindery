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

# push main to GitHub origin + the sync-hub mirror on the paperclip VM (HOL-254)
push:
    git push origin main
    git push mirror main

# fetch the source PDF into dataset/ (public URL, no auth; run once)
dataset-fetch:
    mkdir -p dataset
    curl -fL --retry 3 -o dataset/Valmiki_Ramayana_Gita_Press.pdf \
        "https://ebooks.iskcondesiretree.com/pdf/Valmiki_Ramayan/Valmiki_Ramayana_Gita_Press.pdf"
    pdfinfo dataset/Valmiki_Ramayana_Gita_Press.pdf
