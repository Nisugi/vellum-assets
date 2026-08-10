# Community submissions — how the pipeline works

Contributors submit art through the repo's **issue templates** (Issues → New
issue), one template per category. Each template applies `submission` +
`category:<x>` labels, which trigger
[`submission.yml`](.github/workflows/submission.yml). That workflow runs
[`process_submission.py`](.github/scripts/process_submission.py), which:

1. parses the issue form and sanitizes the asset name (`[a-z0-9_-]`, path-safe)
2. downloads the attachment (GitHub-hosted URLs only, 25 MB cap, decode caps)
3. **rejects name conflicts** against the existing category folder
4. de-keys solid-black backgrounds via [`dekey.py`](dekey.py) where the
   category calls for it (`--no-grey` always — VellumFE desaturates at
   runtime; images that already carry real alpha are left untouched)
5. writes `<name>.png` + a gallery sidecar `<name>.toml` into the category
   folder and **opens a PR**

Nothing publishes without a human merging that PR. Rejections are posted as
issue comments; the submitter edits the issue and it re-processes
automatically.

De-keyed categories expose an optional **Background threshold (advanced)**
form field (5-80) that overrides the category preset — the tuning loop is:
inspect the processed images in the PR, edit the issue with a new threshold
(higher kills halos, lower spares dark detail), and the PR force-updates.
Images that arrive with meaningful transparency (>=5% fully-transparent
pixels) are trusted as pre-keyed and left alone — unless a threshold is
set explicitly, which always forces a re-key.

| Category | Shape | Dekey | Extra required fields |
|---|---|---|---|
| `dolls/` | single image | threshold 30 | — |
| `icons/` | single sheet | none (opaque) | cell size |
| `frames/` | single image | threshold 12 + center seed | cap size auto-measured from alpha+color profiles; form field overrides |
| `backgrounds/` | single image | none — must be opaque | — |
| `compass/` | image or zip → `<set>/<role>.png` | threshold 30 | role vocabulary: rose, n, ne, e, se, s, sw, w, nw, up, down, out |
| `statusicons/` | image or zip → `<set>/<role>.png` | threshold 30 | role vocabulary: 13 glyph names (see template) |
| `hands/` | image or zip → `<set>/<role>.png` | threshold 30 | role vocabulary: lefthand, righthand, spellhand |

**Manifest key semantics** (the client contract): `type` — and its copy
`vellum.category` — is a singular *kind* noun (`hand`, `compass`, `frame`)
for type dispatch. `vellum.pool` is a *place*: the shared-image-pool folder
name, guaranteed to match the on-disk category directory and URL path
segment (`hands/`, `compass/`). Use `pool` for anything path-shaped,
`type`/`category` for kind dispatch. `vellum.set` equals the set folder
name, constrained to `[a-z0-9_-]`. Names are unique within a category
(pipeline-enforced); reuse across categories is intentional — same name
means same visual theme.

Set categories publish one folder per set with bare `<role>.png` pieces
inside and a single shared `meta.toml`. Submissions accept a single bare
image (role picked via form dropdown) or a zip. Zip entries named
`<role>.png` land in the set named by the form; entries named
`<anything>_<role>.png` land in a set named by their own prefix, so one zip
can carry pieces for many sets. Adding a piece to an existing set is
allowed and leaves that set's metadata untouched.

Deliberately deferred: injury-doll severity overlays (84 images per doll —
see GEMINI_PROMPTS.md), and a Discord bot entry point that would open PRs
via API for users without GitHub accounts (same pipeline downstream).

Art direction and prompt recipes for generating submissions:
[GEMINI_PROMPTS.md](GEMINI_PROMPTS.md).
