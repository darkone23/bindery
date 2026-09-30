"""Virtual-fold oracle for the bindery M1 imposition (test-side spec).

Independent re-implementation of the physical pipeline: duplex print ->
long-edge flip -> fold top-half-down -> spin 90 deg CCW -> leaf turns.
Nothing here imports bindery.py — this is the physics reference the
imposition must satisfy.

Geometry (pt): sheet = US Letter portrait 612 x 792; fold line horizontal
at y=396 (PDF coords, y up). Region A = top slot, region B = bottom slot.

Scheme: fold region A onto region B; spin packet 90 deg CCW (crease ->
book-left); page 1 = packet's +z face (= region A's back).

Per sheet of a signature (S pages, sheet j, 0=outermost):
  T_back  = page 2j+1    (back PDF, top slot)    recto
  T_front = page 2j+2    (front PDF, top slot)   verso
  B_front = page S-2j-1  (front PDF, bottom slot) recto
  B_back  = page S-2j    (back PDF, bottom slot)  verso

Winning PDF placements (derived & brute-forced): back slots CCW (rho=90),
front slots CW (rho=270); spine edges all toward the crease.
"""

from PIL.Image import FLIP_LEFT_RIGHT, FLIP_TOP_BOTTOM
from PIL import Image

# sheet constants in pt
SHEET_W = 612.0
SHEET_H = 792.0
CREASE = 396.0


def physical_rect(side: str, rect):
    """PDF-space placed rect -> physical front-frame rect (long-edge duplex
    mirrors x for back-side content)."""
    x0, y0, x1, y1 = rect
    if side == "back":
        return [SHEET_W - x1, y0, SHEET_W - x0, y1]
    return [x0, y0, x1, y1]


def region_to_book(region: str, rect):
    """Transform a PDF-space rect [x0,y0,x1,y1] (pt, y up) into book-frame
    coords for its region (fold A->B + spin CCW). Returns [x0,y0,x1,y1]."""
    x0, y0, x1, y1 = rect
    corners = [(x0, y0), (x1, y1)]
    bc = []
    for (x, y) in corners:
        if region == "A":
            y_pkt = 792.0 - y  # folded material moves
        else:
            y_pkt = y
        bc.append((396.0 - y_pkt, x))
    xs = sorted(p[0] for p in bc)
    ys = sorted(p[1] for p in bc)
    return [xs[0], ys[0], xs[1], ys[1]]


def virtfold(front_img: Image.Image, back_img: Image.Image) -> dict:
    """Simulate print + duplex(long-edge) + fold(A->B) + spin(CCW) +
    leaf-turns; return the four book faces as reading-view images.

    front_img/back_img: renders of the imposition PDF's front/back pages
    (image coords, y down). Returns dict with keys T_back/T_front/B_front/
    B_back -> PIL images (396x612 pt worth of pixels, portrait).
    """
    wp, hp = front_img.size
    half = hp // 2
    back_ff = back_img.transpose(FLIP_LEFT_RIGHT)  # duplex long-edge flip
    # folded region-A strips land vertically flipped at the packet
    a_back = back_ff.crop((0, 0, wp, half)).transpose(FLIP_TOP_BOTTOM)
    a_front = front_img.crop((0, 0, wp, half)).transpose(FLIP_TOP_BOTTOM)
    b_front = front_img.crop((0, half, wp, hp))
    b_back = back_ff.crop((0, half, wp, hp))

    def book(img, turned):
        out = img.rotate(90, expand=True)
        if turned:
            out = out.transpose(FLIP_LEFT_RIGHT)
        return out

    return {
        "T_back": book(a_back, False),
        "T_front": book(a_front, True),
        "B_front": book(b_front, False),
        "B_back": book(b_back, True),
    }