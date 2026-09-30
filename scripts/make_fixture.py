#!/usr/bin/env python3
"""Generate the committed 3-page fixture PDF used by the ingest tests.

Deterministic, dependency-free (raw PDF assembly with computed xref).
Run:  python3 scripts/make_fixture.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "tests" / "fixtures" / "fixture3.pdf"


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


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(build())
    print(f"wrote {DEST} ({DEST.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
