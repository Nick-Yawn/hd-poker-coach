"""Card reader: recognize rank + suit of cards in a frame region.

OCR can't read suits (pips), so we split the job:
  - RANK  -> OCR the glyph (RapidOCR reads single rank chars reliably).
  - SUIT  -> colour (red/black, from the glyph) + the centre pip's SHAPE.

Suit shape is classified by two geometric features of the largest ink blob in
the card (template-free, calibrated on real HD Poker cards):
  - solidity (area / convex-hull area): a club's three lobes cut its solidity
    well below a spade's; used to split black suits.
  - extent (area / bounding-box area): a diamond is a rhombus filling ~half its
    box (~0.46), a heart fills much more (~0.64); used to split red suits.

Returns standard notation, e.g. ['Jc', '8d', '4s', '2s', '8h']. Heavy deps
(cv2, numpy) and OCR are imported lazily behind the [capture] extra.
"""

from __future__ import annotations

RANKS = "23456789TJQKA"

# Reference (solidity, extent) centroids per suit, from real cards.
_SUIT_REF = {
    "c": (0.76, 0.51),
    "s": (0.92, 0.61),
    "d": (0.90, 0.46),
    "h": (0.95, 0.64),
}


def _norm_rank(text: str) -> str | None:
    """Normalize an OCR token to a single rank char, or None if not a rank."""
    t = text.upper().strip()
    t = t.replace("O", "0").replace("I", "1").replace("L", "1")
    t = t.replace("10", "T")
    for ch in t:
        if ch in RANKS:
            return ch
    return None


def _classify_suit(color: str, solidity: float, extent: float) -> str:
    candidates = ("c", "s") if color == "black" else ("d", "h")
    feat = (solidity, extent)
    return min(
        candidates,
        key=lambda k: (feat[0] - _SUIT_REF[k][0]) ** 2 + (feat[1] - _SUIT_REF[k][1]) ** 2,
    )


def _glyph_color(np, cv2, img, tok) -> str:
    """Red vs black, sampled at the rank glyph's box."""
    H, W = img.shape[:2]
    rb = img[int(tok.top * H):int(tok.bottom * H), int(tok.left * W):int(tok.right * W)]
    if rb.size == 0:
        return "black"
    hsv = cv2.cvtColor(rb, cv2.COLOR_BGR2HSV)
    red = (((hsv[..., 0] < 12) | (hsv[..., 0] > 168)) & (hsv[..., 1] > 90)).mean()
    return "red" if red > 0.04 else "black"


def _pip_features(np, cv2, img, cx: float, color: str):
    """Largest ink blob in the card column at `cx`; return (solidity, extent)."""
    H, W = img.shape[:2]
    x0, x1 = int((cx - 0.085) * W), int((cx + 0.085) * W)
    strip = img[:, max(0, x0):min(W, x1)]
    if strip.size == 0:
        return None
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    if color == "red":
        mask = ((hsv[..., 0] < 12) | (hsv[..., 0] > 168)) & (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
    else:
        mask = (hsv[..., 2] < 95) & (hsv[..., 1] < 130)
    mask = (mask.astype(np.uint8)) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Ignore the top quarter (rank corner); the centre pip is the biggest blob.
    sh = strip.shape[0]
    cnts = [c for c in cnts if cv2.moments(c)["m00"] and
            (cv2.moments(c)["m01"] / cv2.moments(c)["m00"]) > 0.30 * sh]
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 30:
        return None
    hull_area = cv2.contourArea(cv2.convexHull(c)) or 1.0
    _, _, w, h = cv2.boundingRect(c)
    solidity = area / hull_area
    extent = area / (w * h) if w * h else 0.0
    return solidity, extent


# Approximate card width as a fraction of the card-row, for drawing boxes.
_CARD_W = 0.16


def locate_card_row(row_bgr, *, upscale: int = 4, min_score: float = 0.3):
    """Like read_card_row but also returns each card's box in ROW fractions.

    Returns a list of ``(card, (x, y, w, h))`` left to right, boxes in [0, 1].
    """
    import cv2
    import numpy as np

    from .ocr import read_tokens

    up = cv2.resize(row_bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    tokens = read_tokens(up, min_score=min_score)
    out: list[tuple[str, tuple[float, float, float, float]]] = []
    for tok in sorted(tokens, key=lambda t: t.cx):
        rank = _norm_rank(tok.text)
        if rank is None:
            continue
        color = _glyph_color(np, cv2, up, tok)
        feats = _pip_features(np, cv2, up, tok.cx, color)
        suit = _classify_suit(color, *feats) if feats else "?"
        # Rank glyph sits top-left of the card; bias the box right toward centre.
        bx = max(0.0, min(1.0 - _CARD_W, tok.cx - _CARD_W * 0.35))
        out.append((rank + suit, (bx, 0.02, _CARD_W, 0.96)))
    return out


def read_card_row(row_bgr, *, upscale: int = 4, min_score: float = 0.3) -> list[str]:
    """Read a horizontal row of cards (board or hole cards), left to right.

    Card detection is implicit: OCR returns a rank token only where a face-up
    card exists, so a flop yields 3, a full board 5, etc.
    """
    return [c for c, _ in locate_card_row(row_bgr, upscale=upscale, min_score=min_score)]


_BOARD_REGION = (0.37, 0.49, 0.28, 0.12)


def read_board(frame, board_region=None) -> list[str]:
    """Read the community cards from a full table frame."""
    return [c for c, _ in read_board_located(frame, board_region)]


def read_board_located(frame, board_region=None):
    """Community cards with each card's box in FRAME fractions.

    Returns ``[(card, (x, y, w, h)), ...]`` for drawing recognition in place.
    """
    from .layout import crop

    rx, ry, rw, rh = board_region if board_region is not None else _BOARD_REGION
    out = []
    for card, (bx, by, bw, bh) in locate_card_row(crop(frame, (rx, ry, rw, rh))):
        out.append((card, (rx + bx * rw, ry + by * rh, bw * rw, bh * rh)))
    return out
