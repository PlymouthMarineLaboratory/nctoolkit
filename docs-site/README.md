# NCToolkit website

Source for the NCToolkit marketing/documentation site (`docs-site/` in the
main nctoolkit repository), published to GitHub Pages. Plain static
HTML/CSS/JS — no build step to author or preview it (the only generated
artifact is the search index, built in CI - see "Search" below). Layout, theming and the
archiving approach are carried over from the sister project
[OceanVal's docs site](https://github.com/PlymouthMarineLaboratory/oceanVal/tree/main/docs-site),
for a consistent look across PML's Marine Systems Modelling group tools.

## Structure

```
index.html            Landing page
installing.html         \
quickstart.html           \
guide.html                  Card-grid index for the User Guide (16 topics)
datasets.html                \
exporting.html                 \
visualization.html               \
subsetting.html                    \
interpolation.html                   \
temporals.html                        User Guide subpages - one per topic,
ensembles.html                         each mirroring one docs/source/*.rst
matchpoint.html                         or *.ipynb file 1:1. Linked from
variables.html                          guide.html's card grid, in this
verticals.html                          order (matching the original
adding.html                             Sphinx toctree) - see "Updating
parallel.html                           content" below for the file mapping
hacks.html                           /
globals.html                       /
backends.html                    /   (also linked from the header's Data
                                /      dropdown - it predates the User Guide)
troubleshoot.html             /
gallery.html               Card-grid index for the Gallery - see "Gallery" below
gallery-transects.html          \
gallery-ocean-temperature.html   Gallery example pages, one per
gallery-nitrate.html            /  worked example
api.html                     |
data-formats.html            |
qa.html                      |
about.html                   |
news.html                 Release highlights; full history lives on GitHub
version-history.html      Links to archive/vX.Y.Z/ snapshots - see "Archived
                           versions" below
assets/
  css/style.css      Design system (design tokens, components) - includes
                      .guide-grid/.guide-card for the User Guide index
  js/main.js         Nav + dropdowns, copy-to-clipboard, FAQ accordion,
                      table search/filter, scrollspy
  img/               Wordmark (NC in ink, Toolkit in teal), PML logo, favicon
  plots/             Interactive HoloViews/Bokeh plot exports, embedded via
                      static PNG + "open interactive" link (.plot-embed in
                      style.css) - see "Interactive plots" below
archive/             Per-release snapshots of the pages above (minus
                      version-history.html itself) + assets/, written by
                      .github/workflows/docs-archive.yml. Don't hand-edit it.
```

The header nav's "Guide" item is a single link to `guide.html`, not a
dropdown — with 16 subpages a dropdown menu doesn't scale, so discovery goes
through the card grid instead (and each subpage's breadcrumb reads
`Home / User Guide / <page>`, linking back to `guide.html`). Only "Data" and
"About" still use the `nav-dropdown` component (2-3 items each, where a
dropdown still works fine).

## Gallery

`gallery.html` is a card-grid index, reusing the `.guide-grid`/`.guide-card`
components `guide.html` uses, with one subpage per worked example. Where the
User Guide covers one topic at a time and mirrors `docs/source/*.rst` 1:1, a
gallery page is a single end-to-end example that cuts across topics: a real
question, the code that answers it, and the figures it produces. Gallery pages
have no upstream Sphinx equivalent — they are this site's own thing.

To add an example:

1. Write a generator script in `website-scripts/` that saves its figures into
   `assets/plots/`, following the conventions of the existing ones
   (`transect_example.py` is the closest model: it inserts the repo at
   `sys.path[0]` so it documents the working copy rather than whatever
   nctoolkit is installed, uses the `Agg` backend, and reads a local download
   of the dataset the page opens over THREDDS). Note that `website-scripts/`
   is gitignored, so these scripts stay local — they hardcode an absolute path
   to a large local download. Only the PNGs they produce are committed.
2. Add the subpage, copying an existing gallery page's shell (`<head>`, header,
   `page-hero`, `docs-layout`, footer) verbatim.
3. Add a `.guide-card` to `gallery.html`'s `.guide-grid`, with a
   Feather-icon-style inline SVG matching the others.

Gallery figures are static matplotlib output, so they use the plain bordered
`<img>` pattern (`border:1px solid var(--line)` + `--radius-md` + `--shadow-sm`)
that `visualization.html` uses for its `pub_plot` figures — **not** the
`.plot-embed` wrapper, which exists specifically for the interactive Bokeh
exports described below and carries an "Open interactive" link.

## Interactive plots

`quickstart.html`, `interpolation.html`, `verticals.html` and
`visualization.html` illustrate NCToolkit's output using the same plots the
Sphinx build injects into the Read the Docs pages via
`.. raw:: html :file: ...` (e.g. `docs/source/intro_plot1.html`,
`interpolate_plot3.html`, `visualization_plot2.html`). Those originals are
full, standalone HTML documents (up to ~4.6MB each) that load
Bokeh/Panel/GeoViews from CDN and render a chart client-side from embedded
JSON. Two things went wrong with them here, in order:

1. The first version of these pages carried over the code samples but not
   the plots at all — a `<pre>` code sample was written without the
   `.. raw:: html` output next to it, so there was nothing to show.
2. Embedding the original files live via `<iframe>` (to fix (1)) rendered
   inconsistently across browsers/screen sizes — reliable on a quick local
   check, but broken (tiny/undersized frame, oversized fallback icon) for at
   least one real user. Multi-megabyte third-party-JS-dependent iframes are
   just a fragile thing to embed inline.

The current approach: `assets/plots/*.png` are static renders of each
`assets/plots/*.html` file (both live side by side — the `.html` files are
kept as the interactive originals, only linked out to, not embedded), wrapped
in a `.plot-embed` card that shows the image plus an "Open interactive ↗"
link to the live version in a new tab. This is both more reliable (a `<img>`
either loads or doesn't — no JS/CDN/cross-browser iframe-sizing behaviour to
get wrong) and much lighter (each PNG is 60–420KB, versus 500KB–4.6MB for
the HTML original).

The PNGs were generated with Playwright/Chromium: load the local `.html`
file, wait for it to render, find the bounding box of the rendered chart
(`document.querySelectorAll('body *')`, unioned — these apps render inside a
shadow-DOM host, so only the outermost element is visible to a plain
`querySelector`), and screenshot that box at a 1100×device_scale_factor=2
viewport (`/tmp` scratch scripts used to generate the current set are not
checked in; re-derive similarly if the plots ever need regenerating — the
`document.querySelectorAll('body *')` bounding-box trick is the part worth
keeping, plain "screenshot the whole page" includes a lot of surrounding
whitespace since these apps size themselves responsively but keep a fixed
height).

If the underlying notebooks/rst are ever regenerated with new plot exports,
re-copy the relevant files from `docs/source/` into `assets/plots/` (same
filenames, so existing references keep working) and regenerate the matching
`.png` files the same way.

Unlike OceanVal's docs site, this one *does* have an `index.html` landing
page — NCToolkit is a general-purpose library with many more doc pages than
OceanVal, so a proper landing page (and the User Guide's card-grid index,
`guide.html`) make sense here. Don't remove it by analogy with OceanVal;
that omission was specific to OceanVal's report-output pages, not something
to copy blindly.

## Search

Site search uses [Pagefind](https://pagefind.app): a static, client-side
index, so there's no server or third-party service involved. The index lives
in `pagefind/` (gitignored) and is built by a step in
`.github/workflows/pages.yml` right before the site is uploaded:

```sh
npx -y pagefind@1.5.2 --site docs-site --glob "*.html" \
  --exclude-selectors ".docs-toc" --exclude-selectors ".back-to-top"
```

- `--glob "*.html"` indexes only the top-level pages. `archive/` snapshots
  (stale copies of `api.html`) and the multi-MB `assets/plots/*.html` exports
  are deliberately left out.
- Pagefind skips `<nav>`, `<header>` and `<footer>` by default; the extra
  selectors drop the in-page TOC and the back-to-top button.
- The search button isn't in the page markup. `assets/js/main.js` injects it
  into `.nav-actions` (so a header change doesn't need a 27-file edit), and
  only if `pagefind/pagefind-entry.json` is actually being served. It also
  opens with `/` or Ctrl/Cmd+K, loads Pagefind's UI lazily on first use, and
  does nothing under `/archive/`.
- Styling is the `.search-dialog` block in `style.css` (Pagefind's UI
  variables mapped onto the site's design tokens).

## Previewing locally

```sh
cd docs-site
python3 -m http.server 8000
# then open http://localhost:8000
```

The search button stays hidden in a plain preview because the index doesn't
exist yet. To try search, build it first (from the repo root, the command in
"Search" above), then serve as above.

## Deploying to GitHub Pages

Deployment is automated by `.github/workflows/pages.yml` (at the repository
root, not under `docs-site/`), which publishes this directory as-is (no build
step) whenever a push to `master` touches `docs-site/**`.

To turn it on:

1. In the repo's **Settings → Pages**, set **Source** to **GitHub Actions**
   (not "Deploy from a branch").
2. Push to `master` (or run the workflow manually from the **Actions** tab —
   it has `workflow_dispatch` enabled). The site publishes to
   `https://plymouthmarinelaboratory.github.io/nctoolkit/`.

The included `.nojekyll` file stops GitHub Pages from running its default
Jekyll processing, which isn't needed here and can interfere with files/paths
starting with an underscore.

**`pages.yml` must stay the only Pages-deploying workflow.** It replaces an
earlier `static.yml` that uploaded the whole repository root (`path: '.'`) on
every push to `master`, sharing the same `concurrency: group: "pages"` this
workflow uses — a second such workflow will race this one, and whichever
finishes last "wins" and publishes whatever it uploaded, silently. If you're
troubleshooting a deploy, check `.github/workflows/` for exactly one Pages
workflow before assuming anything else is wrong.

## Version badge

Every page shows the latest NCToolkit release next to the header logo
(`<span id="nctoolkit-docs-version" class="brand-version">`). It's entirely
client-side: `assets/js/main.js` fetches `https://pypi.org/pypi/nctoolkit/json`
on page load and fills in the placeholder `v&hellip;` with the current
version. Don't hardcode a version number here — it needs that literal
placeholder text to find and replace.

This is a plain "what's the latest release" indicator, not a version
switcher — only one version of the site is served at the root. See "Archived
versions" below for the version-history page instead.

## Archived versions

`.github/workflows/docs-archive.yml` runs whenever a GitHub Release is
created. It reads the version from `setup.py` (the source of truth — not the
release's tag name, not PyPI, since PyPI's publish can race this workflow),
copies this directory's pages plus `assets/` into `archive/vX.Y.Z/`
(excluding `version-history.html` itself, and rewriting its links to point
back at the live, shared copy two levels up), and freezes the header badge in
the snapshot to a plain "vX.Y.Z (archived)" span — it must never update
again, unlike the live badge. It then updates `archive/versions.json` (newest
first) and rewrites the list between the
`<!-- NCTOOLKIT_VERSION_HISTORY_START -->` /
`<!-- NCTOOLKIT_VERSION_HISTORY_END -->` markers in `version-history.html` to
match. Finally it commits and pushes that to `master` and explicitly
dispatches `pages.yml` (a `GITHUB_TOKEN` push doesn't trigger other workflows
on its own, so this can't just rely on the normal push trigger).

Existing snapshots are never touched by a later release — only a brand new
`archive/vX.Y.Z/` directory gets created each time. If that directory already
exists (e.g. the workflow re-ran for some reason), it's left alone rather
than overwritten.

`version-history.html` itself is a normal hand-authored page (same header,
nav, and footer as the rest of the site — keep it in sync with the other 26
pages if you change shared markup) with one auto-generated `<ul>` in the
middle, plus a small "no archived snapshots yet" message that
`assets/js/main.js` hides automatically once the list has entries. Don't
hand-edit between the markers; everything else on the page is yours to edit
like any other.

`archive/versions.json` starts as `[]` — nothing has been archived yet. The
first entry is created automatically the next time a GitHub Release is
published.

## Updating content

Page content is authored by hand to match the current nctoolkit docs
(`docs/source/*.rst`, `docs/source/*.ipynb` and the package README) — there's
no templating engine, so if the underlying package docs change, update the
corresponding `.html` file(s) directly. Shared header/nav/footer markup is
duplicated across pages (no static-site generator), so a nav or footer change
should be applied to all 27 `.html` files.

The User Guide (`guide.html` plus its 16 subpages) mirrors the "User Guide"
section of `docs/source/index.rst`'s toctree 1:1, same order, one page per
topic — this was a deliberate rewrite from an earlier three-page
`guide-basics.html` / `guide-analysis.html` / `guide-advanced.html` layout
that consolidated too much per page relative to the original Read the Docs
site. Don't re-consolidate them without being asked; the whole point was
finer granularity, matching upstream page-for-page. If a new topic is added
to that toctree, add both a new subpage (matching the existing page shell:
copy an existing subpage's `<head>`, header, `page-hero`, `docs-layout`, and
footer verbatim) and a new card to `guide.html`'s `.guide-grid` (pick an
`icon()` entry from the small set already defined inline in that file, or
add a new one following the same Feather-icon-style inline SVG paths).

Rough mapping from Sphinx source to site pages:

| `docs/source/*.rst` / `*.ipynb`                                    | `docs-site/*.html`     |
| -------------------------------------------------------------------- | ------------------------ |
| `installing.rst`                                                     | `installing.html`        |
| `introduction.rst`                                                   | `quickstart.html`        |
| `datasets.ipynb`                                                     | `datasets.html`          |
| `exporting.rst`                                                      | `exporting.html`         |
| `visualization.rst`                                                  | `visualization.html`     |
| `subsetting.rst`                                                     | `subsetting.html`        |
| `interpolation.rst`                                                  | `interpolation.html`     |
| `temporals.rst`                                                      | `temporals.html`         |
| `ensembles.rst`                                                      | `ensembles.html`         |
| `matchpoint.ipynb`                                                   | `matchpoint.html`        |
| `variables.rst`                                                      | `variables.html`         |
| `verticals.ipynb`                                                    | `verticals.html`         |
| `adding.ipynb`                                                       | `adding.html`            |
| `parallel.rst`                                                       | `parallel.html`          |
| `hacks.rst`                                                          | `hacks.html`             |
| `globals.rst`                                                        | `globals.html`           |
| `backends.rst`                                                       | `backends.html`          |
| `troubleshoot.rst`                                                   | `troubleshoot.html`      |
| `api.rst`                                                            | `api.html`               |
| `supported.rst`                                                      | `data-formats.html`      |
| `troubleshoot.rst`, `hacks.rst` (as FAQs)                            | `qa.html`                 |
| `info.rst`, `citation.rst`, `contributing.rst`                       | `about.html`              |
| `news.rst`                                                           | `news.html`                |
| (n/a — this site's own thing)                                       | `guide.html`                |
| (n/a — this site's own thing)                                       | `gallery.html`, `gallery-*.html` |
| `examples.ipynb`                                                     | `gallery-ocean-temperature.html` |
