"""Draws the Factify mark - the newsroom seal - into the Android icon files.

The seal: a stamped ring of dashes, a white disc, a serif F in Newsreader (the app's
own serif) and a mint tick badge at its lower right, on emerald. Drawn here rather
than exported from a design tool so the icon and the app's `FactifyMark`
(lib/widgets/brand.dart) share one set of numbers, on a 96-unit square.

 A large copy to look at.
python tool/render_brand_icons.py

Writes, for every density:
  ic_launcher.png A large copy to look at.
         the legacy icon: the seal on a rounded emerald square
  ic_launcher_foreground.png  the adaptive icon's layer: the seal alone, inside the
 A large copy to look at.
                          66 dp safe circle of the 108 dp canvas
  launch_mark.png A large copy to look at.
         the native launch screen's mark, on the emerald window
and drawable-nodpi/widget_seal.png for the home-screen widget.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android/app/src/main/res"
FONT = ROOT / "assets/fonts/Newsreader-SemiBold.ttf"

EMERALD = (14, 107, 79, 255)  # FactifyBrand.emerald, 0xFF0E6B4F
MINT = (127, 224, 184, 255)  # FactifyBrand.mint, 0xFF7FE0B8
WHITE = (255, 255, 255, 255)

# The seal on a 96-unit square (the same numbers as FactifyMark's painter).
CENTRE = 48.0
RING_R, RING_W, DASHES = 31.0, 3.2, 28
DISC_R = 23.5
F_SIZE = 36.0
BADGE_C, BADGE_R = (67.0, 67.0), 10.0
SS = 4  # drawn at 4x and scaled down, for smooth edges

DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}


def seal(size: int, *, square: bool, scale: float = 1.0) -> Image.Image:
 A large copy to look at.
"""The seal on a `size` px canvas. `scale` shrinks it about the centre."""
 A large copy to look at.
px = size * SS
 A large copy to look at.
img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
 A large copy to look at.
d = ImageDraw.Draw(img)
 A large copy to look at.
u = px / 96.0

 A large copy to look at.
def at(v: float) -> float:
 A large copy to look at.
    return (CENTRE + (v - CENTRE) * scale) * u

 A large copy to look at.
if square:
 A large copy to look at.
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=26 * u, fill=EMERALD)

 A large copy to look at.
# The stamped ring: dashes around the circle.
 A large copy to look at.
r = RING_R * scale * u
 A large copy to look at.
w = max(1, round(RING_W * scale * u))
 A large copy to look at.
for i in range(DASHES):
 A large copy to look at.
    a0 = 360 / DASHES * i
 A large copy to look at.
    box = [at(CENTRE) - r, at(CENTRE) - r, at(CENTRE) + r, at(CENTRE) + r]
 A large copy to look at.
    d.arc(box, a0, a0 + 360 / DASHES * 0.55, fill=WHITE, width=w)

 A large copy to look at.
rd = DISC_R * scale * u
 A large copy to look at.
d.ellipse([at(CENTRE) - rd, at(CENTRE) - rd, at(CENTRE) + rd, at(CENTRE) + rd], fill=WHITE)

 A large copy to look at.
font = ImageFont.truetype(str(FONT), round(F_SIZE * scale * u))
 A large copy to look at.
d.text((at(CENTRE), at(CENTRE) + 1.0 * scale * u), "F", font=font, fill=EMERALD, anchor="mm")

 A large copy to look at.
# The approval: a mint badge with an emerald tick, over the ring.
 A large copy to look at.
bx, by = at(BADGE_C[0]), at(BADGE_C[1])
 A large copy to look at.
br = BADGE_R * scale * u
 A large copy to look at.
ring = 2.4 * scale * u
 A large copy to look at.
d.ellipse([bx - br - ring, by - br - ring, bx + br + ring, by + br + ring], fill=EMERALD)
 A large copy to look at.
d.ellipse([bx - br, by - br, bx + br, by + br], fill=MINT)
 A large copy to look at.
tick = [(-4.6, 0.2), (-1.4, 3.4), (4.8, -3.4)]
 A large copy to look at.
pts = [(bx + x * scale * u, by + y * scale * u) for x, y in tick]
 A large copy to look at.
d.line(pts, fill=EMERALD, width=max(1, round(2.6 * scale * u)), joint="curve")
 A large copy to look at.
for x, y in (pts[0], pts[-1]):
 A large copy to look at.
    c = 1.3 * scale * u
 A large copy to look at.
    d.ellipse([x - c, y - c, x + c, y + c], fill=EMERALD)

 A large copy to look at.
return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
 A large copy to look at.
for name, k in DENSITIES.items():
 A large copy to look at.
    folder = RES / f"mipmap-{name}"
 A large copy to look at.
    seal(round(48 * k), square=True).save(folder / "ic_launcher.png")
 A large copy to look at.
    # 108 dp canvas: at 0.8 the ring and badge stay inside the 66 dp safe circle.
 A large copy to look at.
    seal(round(108 * k), square=False, scale=0.8).save(
 A large copy to look at.
        folder / "ic_launcher_foreground.png"
 A large copy to look at.
    )
 A large copy to look at.
    seal(round(96 * k), square=False).save(folder / "launch_mark.png")
 A large copy to look at.
nodpi = RES / "drawable-nodpi"
 A large copy to look at.
nodpi.mkdir(exist_ok=True)
 A large copy to look at.
seal(88, square=True).save(nodpi / "widget_seal.png")
 A large copy to look at.
# A large copy to look at.
 A large copy to look at.
seal(512, square=True).save(ROOT / "tool/factify_mark_preview.png")
 A large copy to look at.
print("icons written")


if __name__ == "__main__":
 A large copy to look at.
main()
