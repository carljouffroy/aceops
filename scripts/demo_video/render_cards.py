#!/usr/bin/env python3
"""Render the caption bars and the end card for final_cut.sh.

The Homebrew ffmpeg on this Mac is built without drawtext (no freetype), so the
text is rendered here with Pillow and overlaid by ffmpeg as PNGs.

    render_cards.py OUT_DIR SOCIAL_PREVIEW_PNG

Writes OUT_DIR/cap-NN.png (one translucent lower-third per caption, in the order
of CAPTIONS below) and OUT_DIR/endcard.png (1920x1080), and prints one line per
caption with its pixel size so the shell script can check nothing overlaps.
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
for f in (BOLD, REGULAR):
    if not os.path.exists(f):
        BOLD = REGULAR = "/System/Library/Fonts/Helvetica.ttc"

GOLD = (243, 217, 164)      # #f3d9a4
RING = (232, 194, 144)      # #e8c290
COPPER = (201, 149, 90)     # #c9955a
CREAM = (246, 239, 228)     # #f6efe4
BG = (18, 12, 8)            # #120c08

# Lower thirds, in playback order: 3 over the GB10 shots, 10 over the product windows.
CAPTIONS = [
    "Dell Pro Max GB10 · Nemotron 3 Nano 30B, local",
    "NemoClaw · OpenShell · OpenClaw",
    "Intake → BRD → board, on the box",
    "G1 · The owner approves the spec",
    "G2 · Accepted · the agent drafts from the client's figures",
    "Submit · every number traces or is marked ≈",
    "409 · the reviewer must differ from the builder",
    "G3 · a second person approves",
    "Break-even: seasonal decor needs 3.4×",
    "G4 · release needs the client's sign-off",
    "G5 · client update, one question per gap",
    "Data room · 9,994 order lines → a promotion plan",
    "Autopilot · seven isolated agents",
]

CAP_SIZE = 44          # px, as the drawtext spec
CAP_BORDER = 18        # boxborderw
CAP_MAX_W = 1380       # canvas 1920 - 48 right margin - 48 gap - 428 (circle's right edge)


def caption(text, path):
    size = CAP_SIZE
    while True:
        font = ImageFont.truetype(BOLD, size)
        l, _, r, _ = font.getbbox(text)
        w = r - l
        if w + 2 * CAP_BORDER <= CAP_MAX_W or size <= 30:
            break
        size -= 2
    ascent, descent = font.getmetrics()
    h = ascent + descent
    img = Image.new("RGBA", (w + 2 * CAP_BORDER, h + 2 * CAP_BORDER), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=8, fill=BG + (191,))  # 0.75 alpha
    d.text((CAP_BORDER - l, CAP_BORDER), text, font=font, fill=GOLD, anchor="la")
    img.save(path)
    return img.width, img.height, size


def endcard(art_path, path):
    card = Image.new("RGBA", (1920, 1080), BG + (255,))
    art = Image.open(art_path).convert("RGB").crop((0, 64, 1280, 576))   # drop the letterbox bars
    art = art.resize((1600, 640), Image.LANCZOS)
    art = ImageEnhance.Brightness(art).enhance(0.6)
    # feathered edges so the art sits in the dark background instead of on it
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((28, 28, art.width - 29, art.height - 29), radius=40, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(22))
    card.paste(art, (160, 84), mask)

    d = ImageDraw.Draw(card)
    d.rectangle((760, 772, 1160, 774), fill=RING)
    f1 = ImageFont.truetype(BOLD, 58)
    f2 = ImageFont.truetype(REGULAR, 40)
    f3 = ImageFont.truetype(REGULAR, 24)
    d.text((960, 806), "github.com/carljouffroy/aceops", font=f1, fill=CREAM, anchor="ma")
    d.text((960, 892), "vnmoorthy.github.io/aceops  ·  Carl  ·  Tyler  ·  Moorthy", font=f2, fill=CREAM, anchor="ma")
    d.text((960, 1004), "Music: “Inspired” by Kevin MacLeod (incompetech.com) · CC BY 4.0",
           font=f3, fill=COPPER, anchor="ma")
    card.convert("RGB").save(path)


def disc_and_ring(out, size=380, ring=5):
    """disc.png: L mask of a filled disc (alpha for the presenters' circle, via alphamerge).
    ring.png: RGBA gold ring, `ring` px wide, on the disc's edge. Both anti-aliased (4x)."""
    s = 4
    big = size * s
    r = big / 2.0
    outer = Image.new("L", (big, big), 0)
    ImageDraw.Draw(outer).ellipse((0, 0, big - 1, big - 1), fill=255)
    inner = Image.new("L", (big, big), 0)
    ImageDraw.Draw(inner).ellipse((ring * s, ring * s, big - 1 - ring * s, big - 1 - ring * s), fill=255)
    outer.resize((size, size), Image.LANCZOS).save(os.path.join(out, "disc.png"))
    ring_mask = ImageChops.subtract(outer, inner).resize((size, size), Image.LANCZOS)
    ring_img = Image.new("RGBA", (size, size), RING + (0,))
    ring_img.putalpha(ring_mask)
    ring_img.save(os.path.join(out, "ring.png"))


def main():
    out, art = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for i, text in enumerate(CAPTIONS, 1):
        w, h, size = caption(text, os.path.join(out, "cap-%02d.png" % i))
        print("cap-%02d  %4dx%-3d  %dpx  %s" % (i, w, h, size, text))
    endcard(art, os.path.join(out, "endcard.png"))
    disc_and_ring(out)
    print("endcard 1920x1080 · disc.png + ring.png 380x380")


if __name__ == "__main__":
    main()
