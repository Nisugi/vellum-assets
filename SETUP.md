# vellum-assets — Repository Setup Guide

How to set up `github.com/Nisugi/vellum-assets` so VellumFE's `.jinx` asset
manager can install skins, icon maps, and layouts from it.

The `.jinx` client speaks the Jinx protocol: for each category it fetches
`{base_url}/manifest.json`, then downloads each listed file and verifies its
digest. So the repo's job is simply: **host the asset files + a generated
`manifest.json` per category, served over GitHub Pages.**

---

## 1. Target folder layout

The client seeds **three category repos**, each a sub-path of this one repo
served by GitHub Pages:

```
nisugi.github.io/vellum-assets/icons     -> vellum-icons
nisugi.github.io/vellum-assets/skins     -> vellum-skins
nisugi.github.io/vellum-assets/layouts   -> vellum-layouts
```

So the repo should be laid out with **`icons/`, `skins/`, `layouts/` at the top
level** (not nested under `assets/`), each containing its assets plus a
generated `manifest.json`:

```
vellum-assets/
├── .github/workflows/manifest.yml   # regenerates manifests on push (§4)
├── build_manifest.rb                # the generator (§3)
├── icons/
│   ├── manifest.json                # GENERATED — do not hand-edit
│   ├── wow1.png                      # each PNG = one installable iconmap
│   ├── wow2.png
│   ├── bg1.png
│   ├── eso.png
│   └── meta.toml                     # optional: gallery info for the icons (§5)
├── skins/
│   ├── manifest.json                # GENERATED
│   └── parchment/                    # each skin = a folder -> zipped to .vellumpack
│       ├── skin.toml
│       ├── meta.toml
│       ├── preview.png
│       └── bg/paper.png
└── layouts/
    ├── manifest.json                # GENERATED
    └── combat-hud.vellumpack + meta.toml
```

### Migrating your current repo

You currently have `assets/icons/*.png`. Move them up one level:

```bash
git mv assets/icons icons
git rm -r assets            # if assets/ is now empty
```

Each of `wow1.png … wow6.png`, `bg1.png`, `bg2.png`, `eso.png` becomes its own
installable **iconmap** — `.jinx install wow1.png` drops it into the user's
`~/.vellum-fe/global/icons/` pool next to their other icon maps.

---

## 2. How each category is packaged

| Category | What one asset is | Distributed as | Lands in |
|----------|-------------------|----------------|----------|
| **icons** | a single PNG icon map | the PNG itself (no zip) | `~/.vellum-fe/global/icons/<name>.png` |
| **skins** | a folder (`skin.toml` + art) | a `.vellumpack` zip (generator builds it) | `~/.vellum-fe/skins/<name>/` |
| **layouts** | a UI pack | a `.vellumpack` (from `.uiexport`) | applied by the client |

Icons are the simple case — single files. Skins are folders the generator
zips into `<name>.vellumpack`. Layouts are already `.vellumpack` files.

---

## 3. The manifest generator (`build_manifest.rb`)

A Ruby script (Ruby is already in GitHub Actions runners) that, for each
category, writes `<category>/manifest.json`. For every asset it records:

- `file` — the path the client fetches
- `type` — `iconmap` / `skin` / `layout`
- `md5` — **base64(SHA1(bytes))** of the delivered file. Despite the name this
  is SHA1, and it MUST match `Digest::SHA1.base64digest` exactly (the Rust
  client recomputes and compares — a mismatch reads as "modified").
- `last_commit` — from `git log -1 --format=%ct <path>` (needs full history:
  set `fetch-depth: 0` in the Action)
- `vellum` — optional gallery block lifted from `meta.toml` (§5)

A working, tested prototype exists (produced during development). Drop it in the
repo root as `build_manifest.rb`. Its behavior:

- **icons/**: each file is listed as-is, `type: iconmap`.
- **skins/**: each subdirectory is zipped reproducibly (sorted entries, zeroed
  timestamps — so the digest is stable across rebuilds) into
  `<name>.vellumpack`, listed `type: skin`.
- **layouts/**: existing `.vellumpack` files listed as-is, `type: layout`.

Run locally to preview:

```bash
ruby build_manifest.rb --root .
cat icons/manifest.json
```

> **Reproducible zips matter:** if the generator zipped skins non-
> deterministically, every CI run would produce a new digest and the client
> would show every skin as "update available." The generator sorts entries and
> zeroes timestamps so identical source → identical bytes → identical digest.

Example `icons/manifest.json` the client expects:

```json
{
  "available": [
    { "file": "/wow1.png", "type": "iconmap",
      "md5": "tTlDyYmoTBaStnB6prIyKYNDh94=", "last_commit": 1699999999 },
    { "file": "/bg1.png", "type": "iconmap",
      "md5": "4L/xAByw+VxkpOIryZVdZE9bMXQ=", "last_commit": 1699999999 }
  ]
}
```

**Important — `file` has NO category prefix.** It is relative to the
**category** base URL (`.../vellum-assets/icons`), so `/wow1.png` resolves to
`nisugi.github.io/vellum-assets/icons/wow1.png`. Writing `/icons/wow1.png` here
would double it (`.../icons/icons/wow1.png`) and 404. The generator handles
this correctly.

---

## 4. GitHub Pages + the Action

### 4a. Enable Pages

Repo → Settings → Pages → Build and deployment → Source: **GitHub Actions**.
(Not "Deploy from a branch" — the Action below publishes.)

### 4b. The workflow (`.github/workflows/manifest.yml`)

```yaml
name: Build manifests and deploy
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # full history for accurate last_commit times
      - uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.3'
      - run: ruby build_manifest.rb --root .
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .               # publish the whole repo (files + manifests)
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

On every push to `main`: regenerate all three manifests, then publish the repo
to Pages. Contributors just PR a skin folder or a PNG; merge makes it live.

### 4c. Verify

After the first successful run, these must return JSON (not 404):

```
https://nisugi.github.io/vellum-assets/icons/manifest.json
https://nisugi.github.io/vellum-assets/skins/manifest.json
https://nisugi.github.io/vellum-assets/layouts/manifest.json
```

Then in VellumFE: `.jinx repo add vellum-icons https://nisugi.github.io/vellum-assets/icons`
(or wait for the client to re-seed them — see §7).

---

## 5. `meta.toml` (optional gallery info)

Contributors write one small file; the generator lifts it into the manifest's
`vellum` block, which the GUI gallery renders (title, author, description,
tags, preview image). Everything else (digest, timestamps) is generated.

For a **skin** (`skins/parchment/meta.toml`):

```toml
title       = "Parchment"
author      = "Nisugi"
description = "Warm aged-paper theme."
version     = "1.2.0"           # bump when you change the skin
tags        = ["warm", "fantasy"]
preview     = "preview.png"     # path inside the skin, shown in the gallery
```

For **icons**, a single `icons/meta.toml` can describe the set, or add
per-file entries later. Icons work fine with no meta — they just show as
filename + age in the gallery.

---

## 6. Adding assets later (the contributor flow)

1. **An icon map:** drop `newicons.png` into `icons/`. Push. Done — it's in the
   next `.jinx list`.
2. **A skin:** create `skins/<name>/` with `skin.toml`, a `preview.png`, a
   `meta.toml`, and any art. Push. The generator zips + lists it.
3. **A layout:** run `.uiexport <name>` in VellumFE, drop the resulting
   `<name>.vellumpack` into `layouts/` with a `meta.toml`. Push.

No manifest editing ever — the Action regenerates it.

---

## 7. VellumFE client side (already done)

The client (branch `feat/asset-manager`) is ready:

- It installs `iconmap` (→ global/icons pool), `skin` (extracted to
  `skins/<name>/`), and `layout` (via the UI-pack importer).
- The `vellum-skins/icons/layouts` seed URLs were **temporarily removed** from
  the client (they 404'd while this repo had no manifests). Once the three
  `manifest.json` URLs in §4c return 200, re-add the seeds in `repo.rs`
  (`SEEDS`) and drop them from `PRUNE`, in the same commit — then every user
  gets them automatically.

Until then you can test locally with `.jinx repo add`.

---

## Setup checklist

- [ ] Move `assets/icons/*` → `icons/` (top level)
- [ ] Add `build_manifest.rb` to repo root
- [ ] Add `.github/workflows/manifest.yml`
- [ ] Settings → Pages → Source: GitHub Actions
- [ ] Push; confirm the Action runs green
- [ ] Verify the three `manifest.json` URLs return JSON
- [ ] (later) Add `skins/` and `layouts/` folders with real assets
- [ ] (later) Re-add seeds to VellumFE `repo.rs`, remove from `PRUNE`
