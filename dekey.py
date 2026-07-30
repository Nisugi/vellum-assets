#!/usr/bin/env python3
"""Give AI-generated skin art a REAL alpha channel.

Image models cannot emit transparency - they paint solid backgrounds (or fake
checkerboards). This removes a solid dark background by flood-filling from
the image edges, so black ink lines and dark clothing INSIDE the figure are
untouched; only background connected to the border becomes transparent.

Usage:
    python dekey.py input.png                 -> input_alpha.png + input_grey.png
    python dekey.py input.png --threshold 40  -> raise if halo remains
    python dekey.py input.png --no-grey       -> skip the greyscale variant
    python dekey.py frame.png --seed 1024,1024 --threshold 10
        also flood from an interior point - required for closed frames,
        whose center pocket the edge flood cannot reach (repeatable)

The greyscale variant is derived from the de-keyed color image so the two are
pixel-identical apart from saturation - ideal as an injury-doll base where
colored wound dots must pop.
"""

import argparse
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageOps


def dekey(img: Image.Image, threshold: int, seeds: list[tuple[int, int]] = ()) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    def is_bg(x: int, y: int) -> bool:
        r, g, b, _ = px[x, y]
        return r <= threshold and g <= threshold and b <= threshold

    seen = bytearray(w * h)
    queue = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if is_bg(x, y) and not seen[y * w + x]:
                seen[y * w + x] = 1
                queue.append((x, y))
    for x, y in seeds:
        if not (0 <= x < w and 0 <= y < h):
            raise SystemExit(f"seed {x},{y} outside {w}x{h} image")
        if not is_bg(x, y):
            raise SystemExit(f"seed {x},{y} is not background (RGB {px[x, y][:3]})")
        if not seen[y * w + x]:
            seen[y * w + x] = 1
            queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        px[x, y] = (0, 0, 0, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and is_bg(nx, ny):
                seen[ny * w + nx] = 1
                queue.append((nx, ny))
    return img


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--threshold", type=int, default=30,
                    help="max RGB channel value treated as background (default 30)")
    ap.add_argument("--no-grey", action="store_true", help="skip greyscale variant")
    ap.add_argument("--seed", action="append", default=[], metavar="X,Y",
                    help="extra interior flood seed (repeatable); needed for "
                         "closed frames whose center the edge flood cannot reach")
    args = ap.parse_args()

    seeds = []
    for spec in args.seed:
        try:
            x, y = (int(part) for part in spec.split(","))
        except ValueError:
            ap.error(f"--seed wants X,Y integers, got {spec!r}")
        seeds.append((x, y))

    img = dekey(Image.open(args.input), args.threshold, seeds)
    out_alpha = args.input.with_name(args.input.stem + "_alpha.png")
    img.save(out_alpha)
    print(f"wrote {out_alpha}")

    if not args.no_grey:
        grey = ImageOps.grayscale(img).convert("RGBA")
        grey.putalpha(img.getchannel("A"))
        out_grey = args.input.with_name(args.input.stem + "_grey.png")
        grey.save(out_grey)
        print(f"wrote {out_grey}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
