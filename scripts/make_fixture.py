#!/usr/bin/env python3
"""Generate the committed fixture PDFs used by the bindery tests.

fixture3.pdf: 3 pages for the ingest tests (dependency-free raw PDF).
fixture8.pdf: 8 pages at the source trim (444 x 667.44 pt) for the M1
trim+impose tests. Each page carries a unique gray tint (page identity),
a spine-side dot (orientation probe: odd pages = recto, dot top-left;
even = verso, dot top-right) and a big page number.

Run:  nix develop -c python3 scripts/make_fixture.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tests" / "fixtures" / "fixture3.pdf"
DEST8 = ROOT / "tests" / "fixtures" / "fixture8.pdf"


def build() -> bytes:
    objs: list[bytes] = []

    def add(n: int, body: bytes) -> None:
        assert n == len(objs) + 1
        objs.append(b"%d 0 obj\n" % n + body + b"\nendobj\n")

    def stream(n: int, content: bytes) -> None:
        add(n, b"<< /Length %d >>\nstream\n" % len(content) + content +
            b"\nendstream")

    # 1 catalog, 2 page tree, 3-5 pages, 6-8 content streams, 9 font
    add(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add(2, b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>")
    for i, (page, content) in enumerate(zip((3, 4, 5), (6, 7, 8)), start=1):
        add(page, (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 594] "
            b"/Contents %d 0 R /Resources << /Font << /F1 9 0 R >> >> >>" % content
        ))
    for i in range(1, 4):
        text = f"bindery fixture - page {i} of 3".encode("latin-1")
        stream(5 + i, b"BT /F1 24 Tf 36 500 Td (" + text + b") Tj ET\n")
    add(9, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for body in objs:
        offsets.append(len(out))
        out += body
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objs) + 1, xref_pos)
    )
    return bytes(out)


def build8(n_pages: int = 8, w: float = 444.0, h: float = 667.44) -> None:
    """Build fixture8.pdf with reportlab: tinted pages with orientation probes."""
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(DEST8), pagesize=(w, h))
    c.setTitle("bindery fixture8")
    for n in range(1, n_pages + 1):
        tint = 235 - 7 * n
        c.setFillColor(Color(tint / 255, tint / 255, tint / 255))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setStrokeColor(Color(0, 0, 0))
        c.setLineWidth(1)
        c.rect(10, 10, w - 20, h - 20)
        # spine-side dot: recto (odd) = top-left; verso (even) = top-right
        c.setFillColor(Color(0, 0, 0))
        dot_x = 18 if n % 2 == 1 else w - 18 - 30
        c.rect(dot_x, h - 18 - 30, 30, 30, fill=1, stroke=0)
        # head rule + big page number
        c.setLineWidth(2)
        c.line(60, h - 70, w - 60, h - 70)
        c.setFont("Helvetica-Bold", 120)
        c.drawCentredString(w / 2, h / 2 - 60, str(n))
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, 40, f"fixture page {n} of {n_pages}")
        c.showPage()
    c.save()


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(build())
    print(f"wrote {DEST} ({DEST.stat().st_size} bytes)")
    build8()
    print(f"wrote {DEST8} ({DEST8.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
