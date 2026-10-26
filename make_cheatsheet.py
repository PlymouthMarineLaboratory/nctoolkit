#!/usr/bin/env python3
"""
Generate the NCToolkit cheat sheet PDF from structured content below.

Replaces the old hand-maintained cheatsheet/nctoolkit_cheatsheet.pptx: run
this script whenever the version bumps or the cheat sheet content changes,
instead of hand-editing a PowerPoint file. The version number is read
directly from setup.py, so it never needs updating here.

Usage:
    python3 make_cheatsheet.py

Requires weasyprint (not a runtime dependency of nctoolkit itself):
    pip install weasyprint

Output:
    docs-site/assets/cheatsheet/nctoolkit_cheatsheet.pdf
"""

import pathlib
import re
import html as html_escape_mod

try:
    from weasyprint import HTML
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "This script needs weasyprint to render the PDF.\n"
        "Install it with: pip install weasyprint"
    ) from exc

ROOT = pathlib.Path(__file__).resolve().parent
SETUP_PY = ROOT / "setup.py"
OUT_PATH = ROOT / "docs-site" / "assets" / "cheatsheet" / "nctoolkit_cheatsheet.pdf"
WORDMARK = ROOT / "docs-site" / "assets" / "img" / "nctoolkit_wordmark.svg"
PML_LOGO = ROOT / "docs-site" / "assets" / "img" / "pml_logo.jpg"


def get_version() -> str:
    text = SETUP_PY.read_text()
    match = re.search(r"version\s*=\s*'([^']+)'", text)
    if not match:
        raise SystemExit(f"Could not find version='...' in {SETUP_PY}")
    return match.group(1)


def esc(s: str) -> str:
    return html_escape_mod.escape(s)


# ---------------------------------------------------------------------------
# Content. Each section is (title, intro_or_None, entries), where entries is
# a list of (code, description) pairs. `code` may contain simple HTML (e.g.
# for the closing "see the website" line, which isn't a code entry at all -
# handled via section-level `note` instead).
# ---------------------------------------------------------------------------

PAGE_1 = [
    ("Creating datasets", None, [
        ('ds = nc.open_data("foo.nc")', "Open a local file as a dataset."),
        ('ds = nc.open_url("https://foo.foo.nc")', "Open/download a file as a dataset."),
        ('ds = nc.open_thredds("https://foo.foo.nc")', "Use a thredds/OPeNDAP file as a dataset."),
    ]),
    ("Subsetting data", None, [
        ("ds.subset(lon=[lon_min, lon_max],\n          lat=[lat_min, lat_max])", "Crop to a lon/lat box."),
        ('ds.subset(variables=[var1, var2])', "Select a list of variables."),
        ("ds.subset(years=[2000, 2001])", "Select a list of years."),
        ("ds.subset(months=[5, 6])", "Select a list of months."),
        ('ds.drop(variables=["var1", "var2"])', "Remove a list of variables."),
    ]),
    ("Visualizing data", None, [
        ("ds.plot()", "Plot all data in a dataset."),
        ("ds.pub_plot()", "Create a publication-quality static map."),
    ]),
    ("Merging methods", None, [
        ('ds.merge("variable")', "Merge a dataset of files with different variables."),
        ('ds.merge("time")', "Merge a dataset of files with different timesteps."),
    ]),
    ("Rolling methods", "Rolling methods require a window to average over.", [
        ("ds.rolling_mean(20)", "Calculate rolling mean using a window of 20."),
        ("ds.rolling_min(10)", "Calculate rolling min using a window of 10."),
        ("ds.rolling_max(5)", "Calculate rolling max using a window of 5."),
        ("ds.rolling_sum(20)", "Calculate rolling sum using a window of 20."),
    ]),
    ("Exporting datasets", None, [
        ("ds.to_xarray()", "Export as an xarray dataset."),
        ("ds.to_dataframe()", "Export as a pandas dataframe."),
        ('ds.to_nc("foo/foo.nc")', "Export as a netCDF file."),
    ]),
    ("Accessing attributes", None, [
        ("ds.variables", "List dataset variables."),
        ("ds.years", "List dataset years."),
        ("ds.months", "List dataset months."),
        ("ds.times", "List dataset times."),
        ("ds.size", "Display dataset size."),
        ("ds.current", "Display dataset files."),
    ]),
    ("Temporal methods",
     "Temporal averaging methods take a list specifying the time periods to "
     "average over &mdash; elements must be “year”, “month” or “day”. "
     "Defaults to an average over all time steps.", [
        ('ds.tmean("year")', "Calculate the annual mean."),
        ('ds.tmean(["year", "month"])', "Calculate the mean for each month in each year."),
        ("ds.tmin()", "Calculate the temporal minimum."),
        ("ds.tmax()", "Calculate the temporal maximum."),
        ("ds.tmedian()", "Calculate the temporal median."),
        ("ds.trange()", "Calculate the temporal range."),
        ("ds.tpercentile(95)", "Calculate the 95th percentile."),
        ("ds.tvariance()", "Calculate the temporal variance."),
        ("ds.shift(hours=-1)", "Shift time back 1 hour. Also takes days, months, years."),
        ("ds.tcumsum()", "Temporal cumulative sum."),
        ("ds.first_above(0)", "Identify the 1st time step where values are positive."),
        ("ds.first_below(0)", "Identify the 1st time step where values are negative."),
    ]),
    ("Copying a dataset", None, [
        ("ds_copy = ds.copy()", "Copy a dataset."),
    ]),
]

PAGE_2 = [
    ("Vertical methods", None, [
        ("ds.vertical_mean()", "Calculate the vertical mean per grid cell."),
        ("ds.vertical_min()", "Calculate the vertical minimum per grid cell."),
        ("ds.vertical_max()", "Calculate the vertical maximum per grid cell."),
        ("ds.top()", "Extract the top cell, e.g. the sea surface."),
        ("ds.bottom()", "Extract the bottom cell."),
        ("ds.vertical_interp([10, 20, 30])", "Interpolate to a list of vertical depths."),
    ]),
    ("Ensemble methods",
     "Ensemble methods compare files with the same timesteps and grid. "
     "Calculations are done per grid cell.", [
        ("ds.ensemble_mean()", "Calculate the mean across an ensemble."),
        ("ds.ensemble_max()", "Calculate the maximum across an ensemble."),
        ("ds.ensemble_min()", "Calculate the minimum across an ensemble."),
        ("ds.ensemble_range()", "Calculate the range across an ensemble."),
    ]),
    ("Global settings", None, [
        ("nc.options(lazy=False)", "Set evaluation to eager/non-lazy."),
        ('nc.options(temp_dir="/foo")', "Set the temporary directory to use in this session."),
        ("nc.options(cores=6)", "Set the number of cores to use when processing multi-file datasets."),
        ("nc.options(parallel=True)", "Tell NCToolkit multiple datasets will be processed in parallel."),
    ]),
    ("Spatial methods", "Spatial methods are calculated per time step.", [
        ("ds.spatial_mean()", "Calculate the spatial mean."),
        ("ds.spatial_min()", "Calculate the spatial minimum."),
        ("ds.spatial_max()", "Calculate the spatial maximum."),
        ("ds.spatial_sum()", "Calculate the spatial sum."),
        ("ds.zonal_mean()", "Calculate the zonal mean."),
        ("ds.meridonial_mean()", "Calculate the meridonial mean."),
        ("ds.to_transect(start=[lon1, lat1],\n               end=[lon2, lat2], nsteps=100)", "Extract a straight-line transect between two points."),
    ]),
    ("Multi-dataset methods",
     "Add, subtract or compare one dataset with another, so long as their "
     "grids and timesteps are compatible. Calculations are carried out per "
     "timestep and grid cell.", [
        ("ds + ds1", "Add one dataset to another."),
        ("ds - ds1", "Subtract one dataset from another."),
        ("ds * ds1", "Multiply a dataset by another."),
        ("ds / ds1", "Divide a dataset by another."),
        ("ds > ds1", "Do a dataset's values exceed another's?"),
        ("ds < ds1", "Are a dataset's values less than another's?"),
    ]),
    ("Random hacks", None, [
        ("ds.zip()", "Zip dataset files."),
        ('ds.format("nc4")', "Change the netCDF format of dataset files."),
        ("ds.as_missing([0, 100])", "Set values within a range to missing."),
        ('ds.rename({"old_foo": "new_foo"})', "Change the name of a variable."),
        ('ds.set_units({"var": "foo/s"})', "Set the units for a variable."),
        ('ds.set_longnames({"foo": "a long foo"})', "Set the long name for a variable."),
    ]),
]

CREATING_VARIABLES = (
    "Creating variables",
    "New variables can be created using the <code>assign</code> method. This "
    "requires a lambda function. Operations are carried out per grid cell "
    "and timestep.",
    [
        ("ds.assign(new=lambda x: x.old + 10)", "Calculate a new variable, which is just an old one plus 10."),
        ("ds.assign(new=lambda x: x.old > spatial_mean(x.old))", "Create a variable identifying whether a grid cell exceeds the spatial mean."),
    ],
)

REGRIDDING = (
    "Regridding", None, [
        ('ds.regrid("foo.nc")', "Regrid to a file's grid."),
        ("ds.regrid(ds2)", "Regrid to another dataset's grid."),
        ("ds.to_latlon(lon=[lon_min, lon_max],\n              lat=[lat_min, lat_max],\n              res=[lon_res, lat_res])", "Regrid to a regular lon/lat grid with a specified extent and resolution."),
        ("ds.resample_grid(2)", "Resample, selecting every other lon/lat grid cell."),
    ]
)

# Explicit column assignment (rather than relying on CSS multi-column /
# auto-balancing, which weasyprint handles unreliably across page breaks -
# see git history for the column-count attempt this replaced). Each page is
# a fixed 3-column flex row; sections are hand-balanced by entry count so no
# column overflows a single landscape A4 page.
PAGE_1_COLUMNS = [
    [PAGE_1[0], PAGE_1[1], PAGE_1[2], PAGE_1[3]],   # Creating, Subsetting, Visualizing, Merging
    [PAGE_1[4], PAGE_1[5], PAGE_1[6]],              # Rolling, Exporting, Attributes
    [PAGE_1[7], PAGE_1[8]],                         # Temporal methods (tall), Copying
]
PAGE_2_COLUMNS = [
    [PAGE_2[0], PAGE_2[1], PAGE_2[2]],              # Vertical, Ensemble, Global settings
    [PAGE_2[3], PAGE_2[4]],                         # Spatial, Multi-dataset
    [PAGE_2[5], CREATING_VARIABLES, REGRIDDING],    # Random hacks, Creating variables, Regridding
]


def render_section(title, intro, entries, note=None) -> str:
    intro_html = f'<p class="intro">{intro}</p>' if intro else ""
    note_html = f'<p class="note">{note}</p>' if note else ""
    rows = []
    for code, desc in entries:
        code_html = esc(code).replace("\n", "<br>")
        rows.append(
            f'<div class="entry"><div class="code">{code_html}</div>'
            f'<div class="desc">{esc(desc)}</div></div>'
        )
    return (
        f'<section class="box"><h2>{esc(title)}</h2>{intro_html}'
        f'{"".join(rows)}{note_html}</section>'
    )


CREATING_VARIABLES_NOTE = (
    'For more examples, see the '
    '<a href="https://plymouthmarinelaboratory.github.io/nctoolkit/guide.html">NCToolkit website</a>.'
)


def render_columns(columns) -> str:
    # A plain CSS table, not flexbox/multi-column: weasyprint 69's page
    # fragmentation for flex rows and CSS multi-column both misbehave badly
    # (each overflowing column spawns its own extra page, header repeated
    # each time - see git history). Table-row fragmentation is much older
    # and better supported: all three cells stay aligned and break together
    # at the same point if they ever need to spill onto a second page.
    cols_html = []
    for col in columns:
        boxes = []
        for section in col:
            if section is CREATING_VARIABLES:
                boxes.append(render_section(*section, note=CREATING_VARIABLES_NOTE))
            else:
                boxes.append(render_section(*section))
        cols_html.append(f'<td class="col">{"".join(boxes)}</td>')
    return f'<table class="page-columns"><tr>{"".join(cols_html)}</tr></table>'


def render_page(heading_title, heading_sub, version, columns) -> str:
    wordmark_uri = WORDMARK.resolve().as_uri()
    pml_uri = PML_LOGO.resolve().as_uri()
    return f"""<div class="page">
<header>
  <div class="brand">
    <img class="wordmark" src="{wordmark_uri}" alt="NCToolkit">
    <div class="titles">
      <h1>{esc(heading_title)}</h1>
      <p>{heading_sub}</p>
    </div>
  </div>
  <div class="header-right">
    <span class="version">v{esc(version)}</span>
    <img class="pml-logo" src="{pml_uri}" alt="Plymouth Marine Laboratory">
  </div>
</header>
{render_columns(columns)}
</div>"""


def build_html(version: str) -> str:
    page1_html = render_page("Cheat Sheet", "A quick two-page overview of NCToolkit's most-used methods.", version, PAGE_1_COLUMNS)
    page2_html = render_page("Cheat Sheet", "Continued &mdash; vertical, spatial, ensemble and multi-dataset methods.", version, PAGE_2_COLUMNS)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4 landscape;
    margin: 14mm 12mm 10mm 12mm;
    @bottom-right {{
      content: "nctoolkit v{esc(version)} \\2014 plymouthmarinelaboratory.github.io/nctoolkit";
      font-size: 7.5pt;
      color: #7c94a0;
      font-family: "Helvetica Neue", Arial, sans-serif;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    color: #123044;
    margin: 0;
    font-size: 8.0pt;
    line-height: 1.26;
  }}
  header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2.2mm;
    border-bottom: 1.5px solid #087f8c;
    padding-bottom: 1.5mm;
  }}
  header .brand {{ display: flex; align-items: center; gap: 4mm; }}
  header img.wordmark {{ height: 7.5mm; }}
  header .titles h1 {{
    font-size: 13pt;
    margin: 0;
    color: #0b2530;
    letter-spacing: -0.01em;
  }}
  header .titles p {{
    margin: 0;
    font-size: 7.8pt;
    color: #56717d;
  }}
  header .version {{
    font-family: "Courier New", monospace;
    font-size: 9pt;
    font-weight: bold;
    color: #087f8c;
    background: #eafbfb;
    padding: 1.2mm 3mm;
    border-radius: 3mm;
    white-space: nowrap;
  }}
  .header-right {{
    display: flex;
    align-items: center;
    gap: 4mm;
    flex-shrink: 0;
  }}
  img.pml-logo {{ height: 8mm; width: auto; }}
  .page {{ break-after: page; }}
  .page:last-child {{ break-after: auto; }}
  table.page-columns {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  table.page-columns td.col {{
    width: 33.333%;
    vertical-align: top;
    padding: 0 1.8mm;
  }}
  table.page-columns td.col:first-child {{ padding-left: 0; }}
  table.page-columns td.col:last-child {{ padding-right: 0; }}
  section.box {{
    break-inside: avoid;
    border: 0.75pt solid #dde8ea;
    border-radius: 2mm;
    margin: 0 0 2.4mm;
    overflow: hidden;
    display: block;
  }}
  section.box h2 {{
    background: #087f8c;
    color: #ffffff;
    font-size: 7.8pt;
    font-weight: bold;
    margin: 0;
    padding: 1.1mm 2.6mm;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }}
  section.box .intro {{
    margin: 1.3mm 2.6mm 0.6mm;
    color: #56717d;
    font-size: 7.1pt;
  }}
  section.box .note {{
    margin: 0.8mm 2.6mm 1.3mm;
    color: #56717d;
    font-size: 6.9pt;
    font-style: italic;
  }}
  section.box .note a {{ color: #087f8c; }}
  .entry {{
    padding: 1.0mm 2.6mm;
    border-top: 0.5pt solid #ecf3f4;
  }}
  .entry:first-of-type {{ border-top: none; margin-top: 0.6mm; }}
  .code {{
    font-family: "Courier New", monospace;
    font-size: 7.1pt;
    font-weight: bold;
    color: #075c68;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .desc {{
    color: #56717d;
    margin-top: 0.4mm;
  }}
</style>
</head>
<body>

{page1_html}
{page2_html}

</body>
</html>
"""


def main() -> None:
    version = get_version()
    html_doc = build_html(version)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_doc, base_url=str(ROOT)).write_pdf(str(OUT_PATH))
    print(f"Wrote {OUT_PATH} (nctoolkit v{version})")


if __name__ == "__main__":
    main()
