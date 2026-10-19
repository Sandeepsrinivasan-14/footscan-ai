"""Generate synthetic, non-clinical demo photographs for the browser tests and README screenshots.

Each image is a skin-toned foot-like shape on a neutral background with a red wound ellipse of a
chosen size. They are NOT real wounds and the real model is not expected to segment them well;
they exist so the UI can be exercised (with scripts/e2e_server.py's fake model) without patient data.

    python scripts/make_demo_images.py e2e/fixtures
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 512


def make_image(wound_rx: int, wound_ry: int, seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)

    background = np.zeros((SIZE, SIZE, 3), np.float32)
    background[:] = (196, 200, 208)
    background += (yy[..., None] / SIZE) * np.array([-26, -22, -14], np.float32)

    foot = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(foot)
    draw.ellipse((120, 40, 392, 470), fill=255)  # heel/midfoot
    draw.ellipse((150, 20, 380, 220), fill=255)  # forefoot
    foot = foot.filter(ImageFilter.GaussianBlur(5))
    mask = np.asarray(foot, np.float32)[..., None] / 255.0

    skin = np.zeros((SIZE, SIZE, 3), np.float32)
    skin[:] = (222, 178, 148)
    skin += ((xx - SIZE / 2) / SIZE)[..., None] * np.array([-14, -12, -10], np.float32)
    skin += rng.normal(0, 4, (SIZE, SIZE, 1)).astype(np.float32)

    img = background * (1 - mask) + skin * mask

    wound = Image.new("L", (SIZE, SIZE), 0)
    cx, cy = 262, 330
    ImageDraw.Draw(wound).ellipse((cx - wound_rx, cy - wound_ry, cx + wound_rx, cy + wound_ry), fill=255)
    wound = wound.filter(ImageFilter.GaussianBlur(3))
    wmask = np.asarray(wound, np.float32)[..., None] / 255.0
    tissue = np.zeros_like(img)
    tissue[:] = (178, 36, 44)
    tissue += rng.normal(0, 9, (SIZE, SIZE, 1)).astype(np.float32) * np.array([1.6, 0.8, 0.8], np.float32)
    img = img * (1 - wmask) + tissue * wmask

    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    make_image(70, 52).save(args.out_dir / "wound-baseline.jpg", quality=86)
    make_image(46, 34).save(args.out_dir / "wound-followup.jpg", quality=86)
    make_image(0, 0).save(args.out_dir / "no-wound.jpg", quality=86)
    (args.out_dir / "not-an-image.txt").write_text("this is not an image\n")
    print(f"wrote demo images to {args.out_dir}")


if __name__ == "__main__":
    main()
