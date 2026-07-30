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

| Category | Shape | Dekey | Extra required fields |
|---|---|---|---|
| `dolls/` | single image | threshold 30 | — |
| `icons/` | single sheet | none (opaque) | cell size |
| `frames/` | single image | threshold 12 + center seed | corner cap size (nine-slice inset) |
| `backgrounds/` | single image | none — must be opaque | — |
| `compass/` | zip → `<set>_<role>.png` | threshold 30 | role vocabulary: rose, n, ne, e, se, s, sw, w, nw, up, down, out |
| `statusicons/` | zip → `<set>_<role>.png` | threshold 30 | role vocabulary: 16 glyph names (see template) |

Deliberately deferred: injury-doll severity overlays (84 images per doll —
see GEMINI_PROMPTS.md), and a Discord bot entry point that would open PRs
via API for users without GitHub accounts (same pipeline downstream).

Art direction and prompt recipes for generating submissions:
[GEMINI_PROMPTS.md](GEMINI_PROMPTS.md).
