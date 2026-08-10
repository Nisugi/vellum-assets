#!/usr/bin/env python3
"""Process a community asset submission issue into repo files.

Runs in GitHub Actions on issues labeled `submission` + `category:<x>`.
Reads the issue-form body from $ISSUE_BODY, downloads the attached image
(or zip, for set categories), validates it, de-keys the black background
where the category calls for it, and writes the finished PNG(s) plus a
gallery sidecar <name>.toml into the category folder. The workflow then
commits the result to a branch and opens a PR — this script never touches
git.

Exit 0: files written; summary in $SUBMISSION_OUT/submission_summary.md
        and PR title in $SUBMISSION_OUT/submission_title.txt.
Exit 1: rejected; reason in $SUBMISSION_OUT/submission_error.md.

Everything in the issue body is untrusted input: names are sanitized to a
strict slug before they touch a path, attachment URLs must live on GitHub's
own domains, and images are decoded under a pixel cap.
"""

import io
import os
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import requests
from PIL import Image

REPO_ROOT = Path(os.environ.get("REPO_ROOT", ".")).resolve()
sys.path.insert(0, str(REPO_ROOT))
from dekey import dekey  # noqa: E402  (repo-root import by design)

OUT_DIR = Path(os.environ.get("SUBMISSION_OUT", "."))

# Decompression-bomb guard: PIL raises before allocating anything huge.
Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_DIMENSION = 6000

COMPASS_ROLES = frozenset(
    "rose n ne e se s sw w nw up down out".split())
STATUS_ROLES = frozenset(
    "standing kneeling sitting prone dead stunned bleeding hidden "
    "invisible webbed poisoned diseased joined".split())
HAND_ROLES = frozenset("lefthand righthand spellhand".split())

# kind: 'single' (one image -> <name>.png) or 'set' (zip -> <name>_<role>.png
# per entry). dekey: flood threshold, or None to keep the image as-is.
CATEGORIES = {
    "dolls":       dict(kind="single", dekey=30),
    "icons":       dict(kind="single", dekey=None, require=["cell"]),
    "frames":      dict(kind="single", dekey=12, seed_center=True,
                        measure_slice=True),
    "backgrounds": dict(kind="single", dekey=None, opaque=True),
    "compass":     dict(kind="set", dekey=30, roles=COMPASS_ROLES),
    "statusicons": dict(kind="set", dekey=30, roles=STATUS_ROLES),
    "hands":       dict(kind="set", dekey=30, roles=HAND_ROLES),
}

# Issue-form heading -> field key. Headings must match the templates.
FIELD_MAP = {
    "asset name": "name",
    "set name": "name",
    "author credit": "author",
    "description": "description",
    "tags": "tags",
    "image": "image",
    "image set (zip)": "image",
    "cell size (px)": "cell",
    "corner cap size (px)": "slice",
    "on-screen scale": "scale",
    "background threshold (advanced)": "threshold",
    "image or zip": "image",
    "role (single image only)": "role",
}

ATTACHMENT_URL = re.compile(
    r"https://(?:github\.com/user-attachments/(?:assets|files)/[^\s)\"'<>]+"
    r"|[A-Za-z0-9.-]+\.githubusercontent\.com/[^\s)\"'<>]+)")

NAME_RE = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,39}\Z")


class Reject(Exception):
    """Submission is invalid; the message is shown to the submitter."""


def parse_issue_form(body: str) -> dict:
    """Issue forms render as '### <Heading>\n\n<value>' blocks."""
    fields = {}
    current = None
    lines = []
    for line in body.splitlines():
        m = re.match(r"###\s+(.*)", line)
        if m:
            if current:
                fields[current] = "\n".join(lines).strip()
            current = FIELD_MAP.get(m.group(1).strip().lower())
            lines = []
        elif current:
            lines.append(line)
    if current:
        fields[current] = "\n".join(lines).strip()
    return {k: "" if v == "_No response_" else v for k, v in fields.items()}


def slugify(raw: str) -> str:
    slug = re.sub(r"[\s]+", "_", raw.strip().lower())
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    if not NAME_RE.match(slug):
        raise Reject(
            f"`{raw}` isn't a usable name. Use 1-40 characters: lowercase "
            "letters, numbers, `_` or `-`, starting with a letter or number.")
    return slug


def download(url: str) -> bytes:
    resp = requests.get(url, timeout=60, stream=True,
                        headers={"User-Agent": "vellum-assets-submission"})
    resp.raise_for_status()
    data = b""
    for chunk in resp.iter_content(1024 * 256):
        data += chunk
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise Reject(f"Attachment exceeds "
                         f"{MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB.")
    return data


def decode_image(data: bytes, label: str) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise Reject(f"`{label}` could not be read as an image "
                     "(PNG, JPEG, or WebP).")
    if img.format not in ("PNG", "JPEG", "WEBP"):
        raise Reject(f"`{label}` is {img.format or 'unknown'}; "
                     "submit PNG, JPEG, or WebP.")
    if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
        raise Reject(f"`{label}` is {img.width}x{img.height}; "
                     f"the limit is {MAX_DIMENSION}px per side.")
    return img.convert("RGBA")


def has_alpha(img: Image.Image) -> bool:
    return img.getchannel("A").getextrema()[0] < 255


def is_prekeyed(img: Image.Image) -> bool:
    """True when the image already carries MEANINGFUL transparency.

    A genuinely keyed image has a substantial transparent background. A
    handful of stray transparent pixels (an export artifact — seen in the
    wild at 0.4%) must NOT count, or the submission silently skips keying
    and no threshold can ever fix it.
    """
    alpha = np.asarray(img.getchannel("A"))
    return float((alpha == 0).mean()) >= 0.05


def process_image(img: Image.Image, cfg: dict, label: str) -> Image.Image:
    if cfg.get("opaque"):
        if has_alpha(img):
            raise Reject(f"`{label}`: backgrounds must be fully opaque — "
                         "no transparency.")
        return img
    if cfg["dekey"] is None:
        return img
    if is_prekeyed(img) and not cfg.get("force_dekey"):
        # Already meaningfully transparent — trust it. An explicit
        # threshold from the form overrides this and re-keys anyway.
        return img
    seeds = []
    if cfg.get("seed_center"):
        seeds = [(img.width // 2, img.height // 2)]
    try:
        return dekey(img, cfg["dekey"], seeds)
    except SystemExit as e:
        raise Reject(f"`{label}`: de-keying failed ({e}). Frames need a "
                     "pure-black center pocket; check the background is "
                     "solid black.")


def measure_slice(img: Image.Image) -> int:
    """Estimate a frame's nine-slice inset from its alpha channel.

    The inset is the side of the smallest corner-anchored square that
    contains the corner ornament. Caps announce themselves two ways, and
    either alone can undersell them (the iron frame's brass caps stop
    bulging past the run depth well before the brass itself ends):

    - silhouette: opaque art reaching deeper than the runs' steady depth
    - appearance: the band's color differing from the run material

    Along each edge we take the extent of both signals out from each
    corner. A cap's depth from THIS edge shows up as its extent along
    the ADJACENT edge, so four edge scans cover every corner fully.
    """
    arr = np.asarray(img).astype(np.int32)
    views = [arr, arr[::-1], arr.transpose(1, 0, 2),
             arr.transpose(1, 0, 2)[::-1]]  # top / bottom / left / right
    best = 0
    run_depths = []
    for v in views:
        limit = v.shape[0] // 2
        opaque = v[:limit, :, 3] > 8
        # Per position along the edge: how deep opaque art extends inward.
        depth = np.where(opaque.any(axis=0),
                         limit - np.argmax(opaque[::-1], axis=0), 0)
        n = depth.size
        third = slice(n // 3, 2 * n // 3)
        run = float(np.median(depth[third]))
        run_depths.append(run)
        bulge = run * 1.15 + 2
        # Mean color of the band strip at each position, vs mid-run norm.
        band = max(int(run), 1)
        colmean = v[:band, :, :3].mean(axis=0)
        ref = np.median(colmean[third], axis=0)
        dist = np.abs(colmean - ref).sum(axis=1)
        # Run texture (rivets, grain) sets the noise floor.
        cthresh = max(float(np.percentile(dist[third], 95)) * 1.6, 40.0)
        half = n // 2
        # A cap is a SUSTAINED exceedance from the corner outward; stray
        # blemishes mid-run (single rivets, glint artifacts) must not
        # drag the extent out. Rolling-mean the mask so only regions
        # mostly above threshold count.
        w_len = max(8, n // 100)
        kernel = np.ones(w_len) / w_len

        def extent(corner, thresh, adaptive):
            for _ in range(2):
                sustained = np.convolve((corner > thresh).astype(float),
                                        kernel, mode="same") >= 0.5
                past = np.nonzero(sustained)[0]
                if not past.size:
                    return 0
                e = int(past.max()) + 1
                if not adaptive:
                    return e
                # Re-threshold at a fraction of the cap's own contrast so
                # a strong cap's faint gradient tail doesn't count.
                adaptive = False
                new = max(thresh, 0.3 * float(corner[:e].max()))
                if new <= thresh * 1.01:
                    return e
                thresh = new
            return e

        # depth is saturated near corners by the perpendicular side band,
        # so peak-relative thresholding only suits the color profile.
        for profile, thresh, adaptive in ((depth, bulge, False),
                                          (dist, cthresh, True)):
            for corner in (profile[:half], profile[half:][::-1]):
                best = max(best, extent(corner, thresh, adaptive))
    if best == 0:
        # No distinct caps — a uniform band; the inset is the band itself.
        best = int(max(run_depths))
    best = int(best * 1.02) + 1  # small safety margin; oversize is harmless
    return max(1, min(best, min(img.size) // 2 - 1))


def toml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_sidecar(path: Path, fields: dict, extra: dict) -> None:
    lines = []
    if fields.get("title"):
        lines.append(f"title       = {toml_str(fields['title'])}")
    if fields.get("author"):
        lines.append(f"author      = {toml_str(fields['author'])}")
    if fields.get("description"):
        desc = " ".join(fields["description"].split())
        lines.append(f"description = {toml_str(desc)}")
    tags = [t.strip().lower() for t in fields.get("tags", "").split(",")
            if t.strip()]
    if tags:
        lines.append("tags        = ["
                     + ", ".join(toml_str(t) for t in tags) + "]")
    for key, value in extra.items():
        lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def require_number(fields: dict, key: str, kind, what: str):
    raw = fields.get(key, "").strip()
    try:
        return kind(raw)
    except ValueError:
        raise Reject(f"{what} is required and must be a number "
                     f"(got `{raw or 'nothing'}`).")


def main() -> int:
    body = os.environ["ISSUE_BODY"]
    issue = os.environ["ISSUE_NUMBER"]
    labels = os.environ.get("ISSUE_LABELS", "").split(",")

    category = next((l.removeprefix("category:") for l in labels
                     if l.startswith("category:")), None)
    if category not in CATEGORIES:
        raise Reject("No `category:<name>` label found — submit through one "
                     "of the issue templates rather than a blank issue.")
    cfg = CATEGORIES[category]
    cat_dir = REPO_ROOT / category

    fields = parse_issue_form(body)

    # Optional dekey tuning: submitters retry by editing the issue with a
    # different threshold (higher kills halos, lower spares dark detail).
    if fields.get("threshold", "").strip():
        if cfg["dekey"] is None:
            raise Reject("This category doesn't use background removal, so "
                         "the threshold field does nothing — clear it.")
        t = require_number(fields, "threshold", int,
                           "Background threshold (advanced)")
        if not 5 <= t <= 80:
            raise Reject(f"Background threshold must be between 5 and 80 "
                         f"(got {t}).")
        cfg = dict(cfg, dekey=t, force_dekey=True)
    if not fields.get("author", "").strip():
        raise Reject("Author credit is required.")
    name = slugify(fields.get("name", ""))
    fields["title"] = fields.get("name", "").strip()

    urls = ATTACHMENT_URL.findall(fields.get("image", ""))
    if not urls:
        raise Reject("No attachment found in the Image field. Drag and drop "
                     "the file into that text box so GitHub uploads it.")

    extra = {}
    if "cell" in cfg.get("require", ()):
        extra["cell"] = require_number(fields, "cell", int, "Cell size (px)")
    if cfg.get("measure_slice"):
        # Cap size is auto-measured from the alpha channel when blank;
        # a filled-in value is an explicit override.
        if fields.get("slice", "").strip():
            extra["slice"] = require_number(fields, "slice", int,
                                            "Corner cap size (px)")
        if fields.get("scale", "").strip():
            extra["scale"] = require_number(fields, "scale", float,
                                            "On-screen scale")

    written = []  # (relative path, note)

    if cfg["kind"] == "single":
        data = download(urls[0])
        img = process_image(decode_image(data, name), cfg, name)
        target = cat_dir / f"{name}.png"
        if target.exists():
            raise Reject(f"The name `{name}` is already taken in "
                         f"`{category}/` — pick another and edit the issue.")
        note = f"{img.width}x{img.height}"
        if cfg.get("measure_slice"):
            if "slice" not in extra:
                extra["slice"] = measure_slice(img)
                note += f", cap {extra['slice']}px (auto-measured)"
            else:
                note += f", cap {extra['slice']}px"
        img.save(target)
        write_sidecar(cat_dir / f"{name}.toml", fields, extra)
        written.append((f"{category}/{name}.png", note))
    else:
        data = download(urls[0])
        # out_stem -> (Image, display title)
        outputs = {}

        def add_output(stem_prefix, role, img):
            out = f"{stem_prefix}_{role}"
            if out in outputs:
                raise Reject(f"Two files would both publish as `{out}.png`.")
            # Every member of a set carries the SAME title — the client
            # reads set metadata off the first member it sees.
            title = fields["title"] if stem_prefix == name else stem_prefix
            outputs[out] = (img, title)

        if data[:4] == b"PK\x03\x04":
            zf = zipfile.ZipFile(io.BytesIO(data))
            for info in zf.infolist():
                base = os.path.basename(info.filename)
                if (info.is_dir() or not base or base.startswith(".")
                        or "__MACOSX" in info.filename):
                    continue
                stem = os.path.splitext(base)[0].lower()
                if stem in cfg["roles"]:
                    # Bare role name -> the form's set name is the prefix.
                    prefix, role = name, stem
                else:
                    # Prefixed entries keep their own prefix, so one zip can
                    # carry many differently-named assets of the same role
                    # (e.g. ember_spellhand.png + frost_spellhand.png).
                    prefix, _, role = stem.rpartition("_")
                    if role not in cfg["roles"] or not prefix:
                        raise Reject(
                            f"`{base}` doesn't match any {category} role. "
                            f"Files must be named `<role>.png` or "
                            f"`<anything>_<role>.png` where role is one of: "
                            f"{', '.join(sorted(cfg['roles']))}.")
                    prefix = slugify(prefix)
                if info.file_size > MAX_DOWNLOAD_BYTES:
                    raise Reject(f"`{base}` exceeds the size limit.")
                img = decode_image(zf.read(info), base)
                add_output(prefix, role, process_image(img, cfg, base))
            if not outputs:
                raise Reject("The zip contained no usable images.")
        else:
            # Single bare image: the Role dropdown says what it is.
            role = fields.get("role", "").strip().lower()
            if role not in cfg["roles"]:
                raise Reject(
                    "For a single-image submission, pick the file's role in "
                    "the **Role** dropdown (or attach a .zip of "
                    "`<anything>_<role>.png` files instead).")
            # A set name that already ends in the role would double it
            # (x_spellhand + spellhand -> x_spellhand_spellhand) — strip it.
            prefix = name
            if prefix.endswith(f"_{role}") and len(prefix) > len(role) + 1:
                prefix = prefix[:-(len(role) + 1)]
            img = decode_image(data, name)
            add_output(prefix, role, process_image(img, cfg, name))

        conflicts = [f"{out}.png" for out in outputs
                     if (cat_dir / f"{out}.png").exists()]
        if conflicts:
            raise Reject("These names are already taken in "
                         f"`{category}/`: {', '.join(sorted(conflicts))} — "
                         "rename and edit the issue.")
        for out, (img, title) in sorted(outputs.items()):
            img.save(cat_dir / f"{out}.png")
            write_sidecar(cat_dir / f"{out}.toml",
                          dict(fields, title=title), extra)
            written.append((f"{category}/{out}.png",
                            f"{img.width}x{img.height}"))

    summary = [
        f"Processed submission from #{issue} — **{fields['title']}** "
        f"by {fields['author']} (`{category}`).",
        "",
        "| File | Size |",
        "|---|---|",
        *[f"| `{p}` | {note} |" for p, note in written],
        "",
        "Review the images in the Files tab, then merge to publish.",
        "",
        f"Closes #{issue}",
    ]
    (OUT_DIR / "submission_summary.md").write_text(
        "\n".join(summary), encoding="utf-8")
    (OUT_DIR / "submission_title.txt").write_text(
        f"Submission: {category}/{name} (#{issue})\n", encoding="utf-8")
    print(f"wrote {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Reject as e:
        (OUT_DIR / "submission_error.md").write_text(
            f"**Submission rejected:** {e}\n\nEdit this issue to fix the "
            "problem and it will be re-processed automatically.",
            encoding="utf-8")
        print(f"rejected: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — always leave a comment behind
        (OUT_DIR / "submission_error.md").write_text(
            f"**Processing failed unexpectedly** ({type(e).__name__}). A "
            "maintainer will take a look; you don't need to do anything.",
            encoding="utf-8")
        raise
