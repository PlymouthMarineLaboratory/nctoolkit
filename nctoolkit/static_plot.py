import os

from nctoolkit.session import session_info

try:
    import matplotlib as mpl

    from netCDF4 import Dataset
    import numpy as np

    import matplotlib.pyplot as plt

    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    import sys

    # this is to fix some bug in themodules that should be solved with the right version of modules loaded
    from matplotlib.axes import Axes
    from cartopy.mpl.geoaxes import GeoAxes
except:
    session_info["static_plot"] = False

from textwrap import wrap

from difflib import SequenceMatcher


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


from math import radians, sin, cos, asin, sqrt, ceil


def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def fix_long(x):
    if "$" in x:
        return x
    new_x = x
    new_x = new_x.replace("N2O", "N$_2$O")
    new_x = new_x.replace("hlorophyll a", "hlorophyll $a$")
    return new_x


def fix_label(x):
    if "$" in x:
        return x
    new_x = "(" + x + ")"
    new_x = new_x.replace("/m**3", "m$^{-3}$")
    new_x = new_x.replace("/m^3", "m$^{-3}$")
    new_x = new_x.replace("/m^2", "m$^{-2}$")
    new_x = new_x.replace("/yr", "year$^{-1}$")
    new_x = new_x.replace("/m2", "m$^{-2}$")
    new_x = new_x.replace("/d)", "d$^{-1}$)")
    new_x = new_x.replace("/s)", "s$^{-1}$)")
    new_x = new_x.replace("/kg)", "kg$^{-1}$)")
    new_x = new_x.replace("O_2", "O$_2$")
    new_x = new_x.replace("N2O", "N$_2$O")
    new_x = new_x.replace("mmol", "mmol ")
    new_x = new_x.replace("umol", "$\mu$mol ")
    new_x = new_x.replace("  ", " ")
    new_x = new_x.replace("(m2s", "(m$^2$s")
    if new_x == "(1/m)":
        new_x = "(m$^{-1}$)"
    if new_x == "(degC)":
        new_x = "(°C)"
    return new_x[1:-1]


def _legend_label(ds):
    """Colourbar label from a single-variable dataset's long name and units"""
    ds_contents = ds.contents
    try:
        label = fix_long(ds_contents.long_name.values[0])
        if ds_contents.unit.values[0] is not None:
            label = label + " (" + fix_label(ds_contents.unit.values[0]) + ")"
    except:
        print("Unable to parse legend from dataset contents. Check long names and units")
        label = ""
    return label


def _coord_score(x, axis):
    """How much netCDF variable x looks like a longitude (axis="lon") or latitude (axis="lat")"""
    standard_name = getattr(x, "standard_name", None)
    # rotated pole and projected coordinates are not longitudes or latitudes
    if standard_name in [
        "grid_longitude",
        "grid_latitude",
        "projection_x_coordinate",
        "projection_y_coordinate",
    ]:
        return 0
    if standard_name == {"lon": "longitude", "lat": "latitude"}[axis]:
        return 3
    units = str(getattr(x, "units", "")).lower().replace(" ", "").replace("_", "")
    direction = {"lon": ["east", "e"], "lat": ["north", "n"]}[axis]
    if units in [f"degree{s}{d}" for s in ["s", ""] for d in direction]:
        return 2
    if axis in x.name.lower():
        return 1
    return 0


def _coords_from_grid_mapping(nc, x):
    """
    2D lon/lat for a variable on a projected or rotated pole grid without them,
    using its CF grid_mapping and 1D x/y coordinates
    """
    gm = getattr(x, "grid_mapping", None)
    if gm not in nc.variables:
        return None
    axes = dict()
    for d in x.dimensions:
        if d in nc.variables and nc.variables[d].ndim == 1:
            sn = getattr(nc.variables[d], "standard_name", "")
            if sn in ["projection_x_coordinate", "grid_longitude"]:
                axes["x"] = d
            if sn in ["projection_y_coordinate", "grid_latitude"]:
                axes["y"] = d
    if len(axes) < 2:
        return None
    try:
        import pyproj

        gm = nc.variables[gm]
        crs = pyproj.CRS.from_cf({k: gm.getncattr(k) for k in gm.ncattrs()})
        xx = np.asarray(nc.variables[axes["x"]][:], dtype=float)
        yy = np.asarray(nc.variables[axes["y"]][:], dtype=float)
        if crs.is_projected:
            units = str(getattr(nc.variables[axes["x"]], "units", "m")).lower()
            scale = {"km": 1000.0, "kilometres": 1000.0, "kilometers": 1000.0}
            xx = xx * scale.get(units, 1.0)
            yy = yy * scale.get(units, 1.0)
        xx, yy = np.meshgrid(xx, yy)
        transformer = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(xx, yy)
    except Exception:
        return None
    if [d for d in x.dimensions if d in axes.values()] != [axes["y"], axes["x"]]:
        lon = lon.T
        lat = lat.T
    return np.ma.masked_invalid(lon), np.ma.masked_invalid(lat)


def _find_triangles(nc, node_dim, n_nodes, var=None):
    """
    Triangles (n, 3), with 0-based node indices, of an unstructured mesh with values
    on its nodes. These come from the UGRID face_node_connectivity, or from an
    integer variable of 3 or 4 node indices per element (e.g. FVCOM nv, ADCIRC
    element). Quadrilaterals are split into two triangles
    """
    conn = None
    mesh = getattr(nc.variables[var], "mesh", None) if var in nc.variables else None
    if mesh in nc.variables:
        name = getattr(nc.variables[mesh], "face_node_connectivity", None)
        if name in nc.variables:
            conn = nc.variables[name]
    if conn is None:
        for name in nc.variables:
            v = nc.variables[name]
            if (
                v.ndim == 2
                and np.issubdtype(v.dtype, np.integer)
                and node_dim not in v.dimensions
                and min(v.shape) in [3, 4]
                and max(v.shape) > 4
            ):
                conn = v
                break
    if conn is None:
        return None

    start = getattr(conn, "start_index", None)
    tri = np.ma.filled(conn[:], -1).astype(np.int64)
    if tri.shape[0] in [3, 4] and tri.shape[1] not in [3, 4]:
        tri = tri.T
    fill = getattr(conn, "_FillValue", None)
    if fill is not None:
        tri[tri == fill] = -1
    if start is None:
        # Fortran models (FVCOM, ADCIRC, SCHISM, SHYFEM) number their nodes from 1
        valid = tri[tri >= 0]
        if valid.size == 0:
            return None
        start = 1 if valid.max() >= n_nodes or valid.min() > 0 else 0
    tri = np.where(tri >= start, tri - int(start), -1)
    tri[tri >= n_nodes] = -1

    if tri.shape[1] == 4:
        quad = tri[:, 3] >= 0
        tri = np.concatenate([tri[:, :3], tri[quad][:, [0, 2, 3]]])
    return tri[(tri >= 0).all(axis=1)]


def _find_coords(nc_file, var, mesh_files=None):
    """
    Find the lon/lat coordinates of var. Returns a dict with lon, lat, lon_bnds,
    lat_bnds, triangles and the grid kind: "regular", "curvilinear", "unstructured"
    (cells with bounds) or "nodes" (values on the nodes of a triangular mesh).
    If the mesh connectivity of "nodes" grids is missing from nc_file, mesh_files
    are searched for it
    """
    grid = dict(lon_bnds=None, lat_bnds=None, triangles=None)
    with Dataset(nc_file) as nc:
        x = nc.variables[var]
        # look at the variable's coordinates first, then anything on its dimensions
        candidates = getattr(x, "coordinates", "").split() + list(x.dimensions)
        candidates += [c for c in nc.variables if c not in candidates and c != var]
        candidates = [c for c in candidates if c in nc.variables]
        found = dict()
        for axis in ["lon", "lat"]:
            best = 0
            for c in candidates:
                coord = nc.variables[c]
                # coordinates must lie on the dimensions of the variable
                if coord.ndim > 0 and set(coord.dimensions).issubset(x.dimensions):
                    score = _coord_score(coord, axis)
                    if score > best:
                        found[axis] = coord
                        best = score

        if "lon" not in found or "lat" not in found:
            coords = _coords_from_grid_mapping(nc, x)
            if coords is None:
                raise ValueError(
                    "Unable to parse coordinates. Please check if dataset has a lonlat grid!"
                )
            grid.update(lon=coords[0], lat=coords[1], kind="curvilinear")
            return grid

        lon_var = found["lon"]
        lat_var = found["lat"]
        grid["lon"] = lon_var[:]
        grid["lat"] = lat_var[:]

        if lon_var.ndim == 1 and lat_var.ndim == 1:
            if lon_var.dimensions != lat_var.dimensions:
                grid["kind"] = "regular"
                return grid
            for coord, key in [(lon_var, "lon_bnds"), (lat_var, "lat_bnds")]:
                b = getattr(coord, "bounds", None)
                grid[key] = nc.variables[b][:] if b in nc.variables else None
            if grid["lon_bnds"] is not None and grid["lat_bnds"] is not None:
                grid["kind"] = "unstructured"
                return grid
            grid["kind"] = "nodes"
            node_dim = lon_var.dimensions[0]
            n_nodes = len(nc.dimensions[node_dim])
            grid["triangles"] = _find_triangles(nc, node_dim, n_nodes, var)

        elif lon_var.ndim == 2 and lat_var.ndim == 2:
            # match the order of the variable's horizontal dimensions
            if [d for d in x.dimensions if d in lon_var.dimensions] != list(
                lon_var.dimensions
            ):
                grid["lon"] = grid["lon"].T
                grid["lat"] = grid["lat"].T
            grid["kind"] = "curvilinear"
            return grid
        else:
            raise ValueError(
                "Unable to parse coordinates. Please check if dataset has a lonlat grid!"
            )

    # CDO drops the mesh connectivity, so look for it in the files the data came from
    for ff in mesh_files or []:
        if grid["triangles"] is not None:
            break
        try:
            with Dataset(ff) as nc:
                for name, dim in nc.dimensions.items():
                    if len(dim) == n_nodes:
                        grid["triangles"] = _find_triangles(nc, name, n_nodes, var)
                        if grid["triangles"] is not None:
                            break
        except Exception:
            pass
    return grid


def _bad_coords(lon, lat):
    """
    Mask of grid points with unusable coordinates: missing, out of range, or a
    lon/lat pair shared by many points (e.g. land points all set to -1)
    """
    bad = np.ma.getmaskarray(lon) | np.ma.getmaskarray(lat)
    lon = np.ma.filled(lon, np.nan).astype(float)
    lat = np.ma.filled(lat, np.nan).astype(float)
    with np.errstate(invalid="ignore"):
        bad |= ~np.isfinite(lon) | ~np.isfinite(lat)
        bad |= (np.abs(lat) > 90) | (np.abs(lon) > 720)
    key = np.round(lon[~bad], 5) * 1000 + np.round(lat[~bad], 5)
    if key.size > 0:
        unique, counts = np.unique(key, return_counts=True)
        repeated = unique[counts > max(10, 0.001 * lon.size)]
        if len(repeated) > 0:
            bad[~bad] = np.isin(key, repeated)
    return bad


def _cell_corners(x):
    """Cell corners from cell centres, as the mean of the 4 surrounding centres"""
    x = np.pad(x, 1, mode="reflect", reflect_type="odd")
    return 0.25 * (x[:-1, :-1] + x[1:, :-1] + x[:-1, 1:] + x[1:, 1:])


def _curvilinear_mesh(ax, proj, lon, lat, values, **kwargs):
    """
    Plot values on a curvilinear grid. Cell centres are projected first, so that
    cells crossing the edge of the map can be removed, rather than smeared across it
    """
    from scipy import ndimage

    bad = np.ma.getmaskarray(lon)
    lon = np.where(bad, 0.0, np.ma.filled(lon, 0.0))
    lat = np.where(bad, 0.0, np.ma.filled(lat, 0.0))
    xy = proj.transform_points(ccrs.PlateCarree(), lon, lat)
    x = xy[..., 0]
    y = xy[..., 1]
    bad = bad | ~np.isfinite(x) | ~np.isfinite(y)
    if bad.all():
        raise ValueError("No data can be shown with this projection")
    if bad.any():
        # give unusable points the position of the nearest usable one
        idx = ndimage.distance_transform_edt(
            bad, return_distances=False, return_indices=True
        )
        x = x[tuple(idx)]
        y = y[tuple(idx)]
        values = np.ma.masked_where(bad, values)

    x = _cell_corners(x)
    y = _cell_corners(y)

    # remove cells that span the edge of the map
    def span(z):
        z = np.stack([z[:-1, :-1], z[1:, :-1], z[:-1, 1:], z[1:, 1:]])
        return z.max(axis=0) - z.min(axis=0)

    x_size = proj.x_limits[1] - proj.x_limits[0]
    y_size = proj.y_limits[1] - proj.y_limits[0]
    values = np.ma.masked_where(
        (span(x) > 0.1 * x_size) | (span(y) > 0.1 * y_size), values
    )

    return Axes.pcolormesh(ax, x, y, values, shading="flat", **kwargs)


def _unstructured_cells(
    ax, proj, lon, lat, lon_bnds, lat_bnds, values, vmin=None, vmax=None, **kwargs
):
    """Plot values on an unstructured grid, drawing each cell as a polygon"""
    from matplotlib.collections import PolyCollection

    if lon_bnds is None or lat_bnds is None:
        raise ValueError(
            "Unstructured grids can only be plotted if they have cell bounds"
        )

    keep = ~np.ma.getmaskarray(values)
    lon = np.ma.filled(lon, np.nan).astype(float)[keep]
    lon_bnds = np.ma.filled(lon_bnds, np.nan).astype(float)[keep]
    lat_bnds = np.ma.filled(lat_bnds, np.nan).astype(float)[keep]
    values = np.ma.filled(values, np.nan)[keep]

    # vertices on the same side of the dateline as the cell centre
    lon = lon[:, None]
    lon_bnds = lon + ((lon_bnds - lon + 180) % 360) - 180

    xy = proj.transform_points(ccrs.PlateCarree(), lon_bnds.ravel(), lat_bnds.ravel())
    xy = xy[:, :2].reshape(lon_bnds.shape + (2,))

    # remove cells that span the edge of the map
    x_size = proj.x_limits[1] - proj.x_limits[0]
    with np.errstate(invalid="ignore"):
        span = xy[..., 0].max(axis=1) - xy[..., 0].min(axis=1)
        ok = np.isfinite(xy).all(axis=(1, 2)) & (span < 0.5 * x_size)

    cells = PolyCollection(
        xy[ok], edgecolors="face", linewidths=0.2, antialiaseds=False, **kwargs
    )
    cells.set_array(values[ok])
    if vmin is not None or vmax is not None:
        cells.set_clim(vmin, vmax)
    ax.add_collection(cells)
    ax.autoscale_view()
    return cells


def _unstructured_nodes(
    ax, proj, lon, lat, triangles, values, vmin=None, vmax=None, **kwargs
):
    """
    Plot values on the nodes of an unstructured triangular mesh (e.g. FVCOM,
    SCHISM, ADCIRC). If the mesh triangles are unknown, they are recreated by
    Delaunay triangulation, removing triangles much larger than the mesh spacing
    """
    import matplotlib.tri as mtri

    bad = np.ma.getmaskarray(lon) | np.ma.getmaskarray(lat)
    lon = np.where(bad, 0.0, np.ma.filled(lon, 0.0))
    lat = np.where(bad, 0.0, np.ma.filled(lat, 0.0))
    xy = proj.transform_points(ccrs.PlateCarree(), lon, lat)
    x = xy[:, 0]
    y = xy[:, 1]
    values = np.ma.filled(np.ma.masked_invalid(values).astype(float), np.nan)
    bad = bad | ~np.isfinite(x) | ~np.isfinite(y)
    x[bad] = 0.0
    y[bad] = 0.0

    if triangles is None:
        from scipy.spatial import cKDTree

        # only triangulate the points with data, so that land is not filled in
        keep = np.where(~bad & np.isfinite(values))[0]
        if len(keep) < 3:
            raise ValueError("No data can be shown with this projection")
        tri = mtri.Triangulation(x[keep], y[keep])
        triangles = keep[tri.triangles]
        # remove triangles with edges much longer than the spacing of their nodes
        points = np.column_stack([x[keep], y[keep]])
        spacing = np.full(len(x), np.inf)
        spacing[keep] = cKDTree(points).query(points, k=2)[0][:, 1]
        edges = np.stack(
            [
                np.hypot(
                    x[triangles[:, i]] - x[triangles[:, j]],
                    y[triangles[:, i]] - y[triangles[:, j]],
                )
                for i, j in [(0, 1), (1, 2), (2, 0)]
            ]
        )
        too_long = edges.max(axis=0) > 4 * spacing[triangles].max(axis=1)
    else:
        too_long = False

    # remove triangles with missing data, or that span the edge of the map
    x_size = proj.x_limits[1] - proj.x_limits[0]
    x_tri = x[triangles]
    hide = (
        too_long
        | bad[triangles].any(axis=1)
        | ~np.isfinite(values[triangles]).all(axis=1)
        | (x_tri.max(axis=1) - x_tri.min(axis=1) > 0.5 * x_size)
    )
    triangles = triangles[~hide]
    if len(triangles) == 0:
        raise ValueError("No data can be shown with this projection")

    # only keep the nodes that are used, to save memory with large meshes
    used, triangles = np.unique(triangles, return_inverse=True)
    triangles = triangles.reshape(-1, 3)
    tri = mtri.Triangulation(x[used], y[used], triangles)
    # values vary linearly across each triangle, as in finite element models
    im = Axes.tripcolor(ax, tri, values[used], shading="gouraud", **kwargs)
    if vmin is not None or vmax is not None:
        im.set_clim(vmin, vmax)
    ax.autoscale_view()
    return im


def pub_plot(
    ds,
    var=None,
    extent=None,
    title=None,
    legend=None,
    size="auto",
    land="auto",
    colours="auto",
    norm=None,
    limits=None,
    projection="auto",
    coast="auto",
    scale="auto",
    grid=True,
    grid_colour="auto",
    legend_position="auto",
    robust=False,
    out=None,
    breaks=None,
    dpi = "figure",
    font = None,
    grid_labels = True,
    **kwargs,
):
    """
    pub_plot: Static, publication-quality map of a single variable.

    Drawn with matplotlib and cartopy (cartopy must be installed). The dataset
    must contain one variable (or select one with var), one time step and one
    vertical level. Regular lon/lat, curvilinear (e.g. NEMO, HYCOM, ROMS, rotated
    pole and projected grids), unstructured grids with cell bounds (e.g. FESOM,
    ICON) and unstructured meshes with values on their nodes (e.g. FVCOM, SCHISM,
    ADCIRC) are plotted on their native grid, without regridding. The figure is
    displayed inline in Jupyter;
    use out to save it to a file.

    Parameters
    -------------
    var: str
        Variable to plot, e.g. var="sst". Only needed if the dataset contains
        more than one variable.
    extent: list
        [lon_min, lon_max, lat_min, lat_max] in degrees, e.g. [-15, 10, 45, 62].
        Default: the full extent of the data (the whole globe for global data).
    title: str
        Plot title. Supports matplotlib mathtext, e.g. "CO$_2$ flux".
        Default: no title.
    legend: str
        Colourbar label. Supports matplotlib mathtext. Default: built from the
        variable's long name and units, with common units tidied up (e.g. degC
        becomes °C, /m^3 becomes m^-3, umol becomes µmol) and wrapped onto
        several lines. Use legend="" for no label.
    size: list
        [width, height] of the figure in inches, e.g. [8, 6]. Default "auto":
        5 inches tall, with the width matched to the map's aspect ratio
        (8 x 8 for polar stereographic projections, 12 x 8 for azimuthal
        equidistant). Ignored when drawing into an existing figure with fig.
    land: str
        Colour to fill land with, as any matplotlib colour: a name such as
        "grey", "lightgrey" or "tan", or a hex code such as "#d9d9d9". Land is
        drawn over the data, so it hides values on land. Resolution is set by
        scale. Default "auto": no land fill, except on NEMO model grids, which
        use light grey. None: no land fill.
    colours: str or matplotlib Colormap
        Matplotlib colour map, e.g. "viridis", "plasma", "cividis" or "RdBu_r".
        Add "_r" to reverse any colour map. See
        https://matplotlib.org/stable/gallery/color/colormap_reference.html
        Default "auto": "viridis", or the diverging "RdBu_r" when the colour
        scale spans zero.
    norm: str or matplotlib.colors normalisation
        "log" (or "log10") for a logarithmic colour scale, or any
        matplotlib.colors normalisation object, e.g.
        matplotlib.colors.PowerNorm(gamma=0.5, vmin=0, vmax=10). Log scales need
        strictly positive values: if the data contain zeros, set a positive
        lower limit, e.g. limits=[0.01, None]. limits is not applied to norm
        objects, so set vmin and vmax on the object itself. Default: linear.
    limits: list
        [min, max] limits of the colour scale. Each end can be a number, e.g.
        [0, 30]; None, to use the data minimum or maximum, e.g. [0, None]; or a
        percentile string, e.g. ["2%", "98%"]. Values outside the limits take
        the end colours, and the colourbar gets an arrow at that end. If the
        range spans zero, the scale is made symmetric around zero using the
        larger absolute limit, so [-1, 5] becomes [-5, 5], and a diverging
        colour map is used by default. Default: the data minimum and maximum.
        Ignored when robust=True.
    projection: cartopy projection
        A cartopy CRS, e.g. ccrs.Robinson(), ccrs.Mollweide(),
        ccrs.NorthPolarStereo() or
        ccrs.Orthographic(central_longitude=-20, central_latitude=50), after
        import cartopy.crs as ccrs. See
        https://scitools.org.uk/cartopy/docs/latest/reference/projections.html
        Default "auto": Robinson for global data; plain lon/lat (PlateCarree)
        if the data cross the equator or span more than 200 degrees of
        longitude; otherwise Lambert conformal, centred on the data.
        None: plain lon/lat.
    coast: str
        "auto" (default): Natural Earth coastline, with the level of detail
        chosen automatically for the map extent. "coarse", "low",
        "intermediate", "high" or "full": GSHHS coastline at that resolution,
        from least to most detailed. "full" can be slow over large areas.
        cartopy downloads GSHHS data on first use. None: no coastline.
    scale: str
        Resolution of the land fill, used when land is set: "low" (1:110m),
        "medium" (1:50m) or "high" (1:10m) Natural Earth polygons.
        Default "auto", the same as "medium". If coast is "auto", setting scale
        also switches the coastline to GSHHS, with the resolution chosen
        automatically.
    grid: bool
        Draw dashed lon/lat grid lines. Default True. Lon/lat labels are
        controlled separately by grid_labels.
    grid_colour: str
        Colour of the grid lines, as any matplotlib colour, e.g. "grey".
        Default "auto": black, with a white dashed overlay when most of the map
        sits at the low (dark) end of the colour scale.
    legend_position: str
        "right" (default; "auto" is the same) for a vertical colourbar,
        "bottom" for a horizontal colourbar under the map, or None for no
        colourbar.
    robust: bool
        If True, set the colour limits to the 2nd and 98th percentiles of the
        data, so a few extreme values don't wash out the scale. Overrides
        limits. Default False.
    out: str
        File to save the figure to, e.g. "sst.png". The format comes from the
        extension: .png, .pdf, .svg, .jpg, .eps or any other format matplotlib
        supports. Default: display only.
    breaks: list
        Tick positions on the colourbar, e.g. [0, 10, 20, 30]. Labels show
        exactly these values. This only sets the ticks; colours stay continuous.
        Default: automatic ticks.
    dpi: int
        Resolution of the saved file in dots per inch, e.g. 300 for print. Only
        used with out. Default "figure": the figure's own resolution
        (matplotlib's default is 100).
    font: float or str
        Font size for the title and colourbar label, in points (e.g. 14) or
        as a matplotlib size name ("small", "large", "x-large"). Tick labels
        are unchanged. Default: matplotlib's default.
    grid_labels: bool
        Show the lon/lat labels around the edges of the map. Set to False to
        hide them. Default True.
    **kwargs:
        fig and gs: draw into an existing matplotlib figure, and optionally a
        GridSpec cell, to build multi-panel figures, e.g.
        fig = plt.figure(figsize=[12, 5]); gs = fig.add_gridspec(1, 2);
        ds1.pub_plot(fig=fig, gs=gs[0]); ds2.pub_plot(fig=fig, gs=gs[1]).
        gs requires fig.
        relief=True: add a shaded-relief background, visible where the data
        are missing.
        Aliases and close misspellings are accepted: colors for colours, trans
        for norm, and names starting with "proj" or "var" for projection and
        var. Any other unrecognised argument raises an error suggesting the
        closest valid name.
    """
    mid_point = None

    relief = False
    # check if relief is in kwargs
    if "relief" in kwargs.keys():
        relief = kwargs["relief"]
        kwargs.pop("relief")

    if projection is False:
        projection = None

    axis = None

    if legend_position not in ["auto", "right", "bottom"]:
        if legend_position is not None:
            raise ValueError("legend_position must be one of right/bottom or None")

    land_auto = land == "auto"

    if land is not None:
        if not isinstance(land, str):
            raise TypeError("land must be str")

    if not isinstance(grid_labels, bool):
        raise TypeError("grid_labels must be True or False")

    if scale not in ["auto", "low", "medium", "high"]:
        text = ",".join(["low", "medium", "high", "auto"])
        raise ValueError(f"scale is '{scale}'. It should be one of {text}!")

    globe = False

    if "static_plot" in session_info.keys():
        raise ValueError("Unable to import cartopy properly")

    if coast not in ["auto", "coarse", "low", "intermediate", "high", "full", None]:
        the_options = ",".join(
            ["auto", "coarse", "low", "intermediate", "high", "full", "None"]
        )
        raise ValueError(f"coast must be one of {the_options}")

    options = [
        "extent",
        "title",
        "legend",
        "size",
        "land",
        "colours",
        "norm",
        "limits",
        "projection",
        "grid",
        "grid_colour",
        "grid_labels",
        "legend_position",
    ]

    n_rows = 1
    n_cols = 1

    if "fig" not in kwargs.keys():
        fig = None
    if "gs" not in kwargs.keys():
        gs = None

    if "quiver" in kwargs:
        quiver = True
        u = kwargs["u"]
        v = kwargs["v"]
        kwargs.pop("quiver")
        kwargs.pop("u")
        kwargs.pop("v")
    else:
        quiver = False

    # internal: used by panel_plot to get the axes and mappable back
    panel = kwargs.pop("_panel", False)

    for kk in kwargs:
        fixed = False

        if kk == "fig":
            fig = kwargs[kk]
            fixed = True

        if kk == "gs":
            gs = kwargs[kk]
            fixed = True

        if var is None:
            if kk.lower().startswith("var"):
                var = kwargs[kk]
                fixed = True
        if kk.lower().startswith("col") and kk.lower().endswith("rs"):
            if colours == "auto":
                colours = kwargs[kk]
                fixed = True

        if kk.lower().startswith("trans"):
            if norm is None:
                norm = kwargs[kk]
                fixed = True

        # if kk.lower().startswith("mid") and kk.lower().endswith("nt"):
        #    if mid_point is None:
        #        mid_point = kwargs[kk]
        #        fixed = True

        if kk.lower().startswith("proj"):
            if projection == "auto":
                projection = kwargs[kk]
                fixed = True

        if kk.lower().startswith("norm"):
            if norm is None:
                norm = kwargs[kk]
                fixed = True

        if kk.lower().startswith("nrow"):
            if n_rows == 1:
                n_rows = kwargs[kk]
        if kk.lower().startswith("ncol"):
            if n_cols == 1:
                n_cols = kwargs[kk]

        if kk.lower().startswith("ax"):
            if axis is None:
                axis = kwargs[kk]
                fixed = True

        if not fixed:
            possible = []

            for x in options:
                if similar(x.lower(), kk.lower()) > 0.6:
                    possible.append(x)

            if len(possible) > 0:
                part2 = ",".join(possible)
                raise ValueError(
                    f"{kk} is not a valid argument. Did you mean one of these? {part2}"
                )
            else:
                raise ValueError(f"{kk} is not a valid argument")

    if gs is not None:
        if fig is None:
            raise ValueError("If you specify gs, you must also specify fig")

    # the files the data comes from, before any processing (copy runs the dataset)
    source_files = list(ds.current)[:1]

    ds1 = ds.copy()

    if not quiver:
        if var is not None:
            ds1.subset(variables=var)
        ds1.run()

        if len(ds1.variables) > 1:
            raise ValueError("Only one variable wanted")
        if len(ds1.times) > 1:
            raise ValueError("Only one timestep wanted")

    ds_xr = ds1.to_xarray(decode_times=False)

    if "nav_lon" in ds_xr.coords and "nav_lat" in ds_xr.coords:
        # NEMO grids. Regional NEMO-ERSEM grids can be converted to regular grids,
        # otherwise they are plotted as curvilinear grids
        if len([x for x in ds_xr.dims if "lon" in x]) == 0:
            if np.min(ds_xr["nav_lon"]) > -23.5 and np.max(ds_xr["nav_lon"]) < 24.0:
                try:
                    ds2 = ds1.copy()
                    ds2.fix_nemo_ersem_grid()
                    ds2.run()
                    ds1 = ds2
                except:
                    pass
        if land == "auto":
            land = "lightgrey"

    if land == "auto":
        land = None

    GeoAxes._pcolormesh_patched = Axes.pcolormesh

    # read the coordinates. Mesh connectivity may only be in the original files
    var_name = u if quiver else ds1.variables[0]
    try:
        grid = _find_coords(ds1[0], var_name, mesh_files=source_files)
    except ValueError:
        # CDO drops coordinates it does not recognise (e.g. on some unstructured
        # meshes), so use the original file's, if they match the data
        if len(source_files) == 0 or source_files[0] == ds1[0]:
            raise
        grid = _find_coords(source_files[0], var_name)
        with Dataset(ds1[0]) as nc_file:
            n_values = np.prod([n for n in nc_file.variables[var_name].shape if n > 1])
        n_coords = grid["lon"].size
        if grid["kind"] == "regular":
            n_coords = n_coords * grid["lat"].size
        if n_values != n_coords:
            raise
    lon = grid["lon"]
    lat = grid["lat"]
    grid_kind = grid["kind"]

    if grid_kind != "regular":
        # mask unusable coordinates, and use -180 to 180 longitudes, or 0 to 360
        # if that gives a smaller longitude range, e.g. in the Pacific
        bad = _bad_coords(lon, lat)
        lat = np.ma.masked_where(bad, np.ma.filled(lat, 0.0))
        lon = np.ma.masked_where(bad, (np.ma.filled(lon, 0.0) + 180) % 360 - 180)
        if lon.max() - lon.min() > 340 and lat.max() - lat.min() < 160:
            lon_360 = lon % 360
            if lon_360.max() - lon_360.min() < lon.max() - lon.min():
                lon = lon_360

    # set globe to True if lon lat spread is big enough

    if np.max(lon) - np.min(lon) > 340:
        if np.max(lat) - np.min(lat) > 160:
            globe = True

    # proj=ccrs.LambertConformal(central_longitude=np.mean(lon), central_latitude=np.mean(lat), false_easting=0.0, false_northing=0.0,  cutoff=38)

    # check coord type
    lambert = False
    polar = False

    if projection == "auto":
        if lat.min() < 0 and lat.max() > 0:
            proj = ccrs.PlateCarree()
        else:
            if (lon.max() - lon.min()) < 200:
                proj = ccrs.LambertConformal(
                    central_longitude=np.mean(lon), central_latitude=np.mean(lat)
                )
            elif not globe and lat.min() > 0:
                # polar regions, e.g. the Arctic
                proj = ccrs.NorthPolarStereo()
                polar = True
            elif not globe and lat.max() < 0:
                proj = ccrs.SouthPolarStereo()
                polar = True
            else:
                proj = ccrs.PlateCarree()
    else:
        proj = projection
    data_crs = ccrs.PlateCarree()

    if globe and projection == "auto":
        proj = ccrs.Robinson()

    if projection == None:
        proj = ccrs.PlateCarree()

    if (isinstance(projection, ccrs.NorthPolarStereo) or polar) and size == "auto":
        size = [8,8]
    if isinstance(projection, ccrs.SouthPolarStereo) and size == "auto":
        size = [8,8]
    if isinstance(projection, ccrs.AzimuthalEquidistant) and size == "auto":
        size  = [12, 8]
    if size == "auto":
        size = [10, 10]
        if proj == ccrs.PlateCarree() or globe:
            size[1] = (
                size[0]
                * float((np.max(lat) - np.min(lat)))
                / float((np.max(lon) - np.min(lon)))
                / 1.1
            )
        else:
            size[1] = (
                size[0]
                * haversine(
                    float(np.min(lon)),
                    float(np.min(lat)),
                    float(np.min(lon)),
                    float(np.max(lat)),
                )
                / haversine(
                    float(np.min(lon)),
                    0.4 * float(np.min(lat) + np.max(lat)),
                    float(np.max(lon)),
                    0.4 * float(np.min(lat) + np.max(lat)),
                )
                / 1.1
            )
        # rescale to vertical height of 5
        max_size = max(size)
        size = [5 * size[0] / size[1], 5]

    # regular grids need the full lon/lat grid
    if grid_kind == "regular":
        lon, lat = np.meshgrid(lon, lat)

    # read the values. the array is squeezed to remove the temporal dimension that has length 1
    if quiver:
        with Dataset(ds1[0]) as input_file:
            u = input_file.variables[u][:].squeeze()
            v = input_file.variables[v][:].squeeze()

    if limits is None:
        limits = [None, None]

    if not quiver:
        with Dataset(ds1[0]) as input_file:
            values = input_file.variables[ds1.variables[0]][:].squeeze()

        if grid_kind != "regular":
            # hide values at unusable coordinates
            bad_values = bad | np.ma.getmaskarray(values)
            values = np.ma.masked_invalid(
                np.where(bad_values, np.nan, np.ma.filled(values, np.nan))
            )

        if limits is not None:
            if limits[0] is None:
                limits[0] = np.min(values)
            if limits[1] is None:
                limits[1] = np.max(values)

        if grid_colour == "auto":
            value_10 = values.min() + (values.max() - values.min()) * 0.3
            if np.mean(values.data < value_10) < 0.7:
                grid_colour = "black"

        r_min = None
        r_max = None

        if limits is not None:
            if isinstance(limits[0], str):
                if "%" in limits[0]:
                    r_min = float(limits[0].split("%")[0])
            if isinstance(limits[1], str):
                if "%" in limits[1]:
                    r_max = float(limits[1].split("%")[0])

        if mid_point is None and limits is None:
            min_value = np.min(values)
            max_value = np.max(values)
            if robust:
                min_value = np.nanpercentile(np.ma.filled(values, np.nan), 2)
                max_value = np.nanpercentile(np.ma.filled(values, np.nan), 98)
            if r_min is not None:
                min_value = np.nanpercentile(np.ma.filled(values, np.nan), r_min)
            if r_max is not None:
                max_value = np.nanpercentile(np.ma.filled(values, np.nan), r_max)

    # generate the figure and the axes where to plot the map. When the axes are generated (either with add_subplot or add_axes, or any other way), the projection to be used need to be specified
    # the axes generated show the entire globe up to the cutoff latitude
    if fig is None:
        if size is not None:
            fig = plt.figure(figsize=size)
        else:
            fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(projection=proj)
    else:
        if gs is None:
            ax = fig.add_subplot(projection=proj)
        else:
            ax = fig.add_subplot(gs, projection=proj)

    if globe:
        ax.set_global()

    # set the extension of the actual domain (i.e. the lat lon limits)
    # notice how the range is larger than the actual domain. this is due because with the chosen projection a larger canvas is needed to encompass the whole domain
    if extent is not None:
        ax.set_extent(extent)

    # plot the map. the critical bit is the "transform" option, where the projection of the data is specified. In this case spherical coordinates
    # the shading option is to let pcolormesh understand that the coordinates passed are the cell centre, see https://matplotlib.org/stable/gallery/images_contours_and_fields/pcolormesh_grids.html

    if not quiver:
        if limits is None:
            vmin = None
            vmax = None
        else:
            vmin = limits[0]
            vmax = limits[1]
            if r_min is not None:
                vmin = np.nanpercentile(np.ma.filled(values, np.nan), r_min)
            if r_max is not None:
                vmax = np.nanpercentile(np.ma.filled(values, np.nan), r_max)

        if robust:
            vmin = np.nanpercentile(np.ma.filled(values, np.nan), 2)
            vmax = np.nanpercentile(np.ma.filled(values, np.nan), 98)
            limits = [0,0]
            limits[0] = vmin
            limits[1] = vmax

        if limits is None:
            if r_min is not None:
                vmin = np.nanpercentile(np.ma.filled(values, np.nan), r_min)
            if r_max is not None:
                vmax = np.nanpercentile(np.ma.filled(values, np.nan), r_max)

        if mid_point is None:
            if vmin < 0 and vmax > 0:
                mid_point = 0
                limits[0] = vmin
                limits[1] = vmax
                try:
                    if limits[0] < 0 and limits[1] > 0:
                        min_value = limits[0]
                        max_value = limits[1]
                        if mid_point is None:
                            mid_point = 0
                        if colours == "auto":
                            colours = "RdBu_r"
                            if land_auto and land is not None:
                                if land != "auto":
                                    land = "grey"
                except:
                    pass

        if mid_point is not None and limits is not None:
            try:
                if colours == "auto":
                    colours = "RdBu_r"
                    if land_auto and land is not None:
                        if land != "auto":
                            land = "grey"
            except:
                pass

        if mid_point is not None:
            val_min = values.min()
            val_max = values.max()

            if mid_point == 0.0:
                if limits is not None:
                    val_min = limits[0]
                    val_max = limits[1]
            if robust and limits is None:
                val_min = np.nanpercentile(np.ma.filled(values, np.nan), 2)
                val_max = np.nanpercentile(np.ma.filled(values, np.nan), 98)
            if mid_point < val_min:
                raise ValueError("mid_point is outside value range")
            if mid_point > val_max:
                raise ValueError("mid_point is outside value range")
            adjustment = max(val_max - mid_point, mid_point - val_min)
            vmin = mid_point - adjustment
            vmax = mid_point + adjustment

        norm_plot = False
        if norm in ["log", "log10"]:
            norm = mpl.colors.LogNorm(vmin=vmin, vmax=vmax)
            norm_plot = True
        if norm is not None:
            vmin = None
            vmax = None

        if limits is not None and colours == "auto":
            try:
                if limits[0] < 0 and limits[1] > 0:
                    min_value = limits[0]
                    max_value = limits[1]
                    if mid_point is None:
                        mid_point = 0
                    if colours == "auto":
                        colours = "RdBu_r"
                        if land_auto and land is not None:
                            if land != "auto":
                                land = "grey"
                else:
                    colours = "viridis"
            except:
                pass

        if colours == "auto":
            colours = "viridis"

        if norm is None:
            if vmin < 0 and vmax > 0:
                # ensure vmin and vmax are symmetric
                vmax = max(abs(vmin), abs(vmax))
                vmin = -vmax

        if grid_kind == "curvilinear":
            im = _curvilinear_mesh(
                ax, proj, lon, lat, values, cmap=colours, norm=norm, vmin=vmin, vmax=vmax
            )
        elif grid_kind == "unstructured":
            im = _unstructured_cells(
                ax,
                proj,
                lon,
                lat,
                grid["lon_bnds"],
                grid["lat_bnds"],
                values,
                cmap=colours,
                norm=norm,
                vmin=vmin,
                vmax=vmax,
            )
        elif grid_kind == "nodes":
            im = _unstructured_nodes(
                ax,
                proj,
                lon,
                lat,
                grid["triangles"],
                values,
                cmap=colours,
                norm=norm,
                vmin=vmin,
                vmax=vmax,
            )
        else:
            im = ax.pcolormesh(
                lon,
                lat,
                values,
                cmap=colours,
                transform=data_crs,
                shading="nearest",
                norm=norm,
                vmin=vmin,
                vmax=vmax,
            )

    # add coastline and land colour. More options, including about resolution of coastline, colour and so on can be found here
    # https://scitools.org.uk/cartopy/docs/v0.14/matplotlib/feature_interface.html
    #
    # add grid lineshttp://localhost:8890/notebooks/Untitled4.ipynb?kernel_name=python3#
    # first define the gridliner object
    # crs define the units of the values (here spehric coorindates)
    # the other options are for grpahics, more details can be found here
    # https://scitools.org.uk/cartopy/docs/v0.13/matplotlib/gridliner.html
    # note that if x_inline and y_inline are not set to False, the labels of the axis could be written inside the map

    if quiver:
        im = ax.quiver(lon, lat, u, v, units="width", transform=data_crs)

    if not quiver:
        if grid_colour == "auto" and norm_plot:
            grid_colour = "black"

    if grid:
        if grid_colour == "auto":
            g_colours = "black"
        else:
            g_colours = grid_colour
        g_alpha = 0.5
    else:
        g_colours = None
        g_alpha = 0

    if True:
        gl = ax.gridlines(
            crs=ccrs.PlateCarree(),
            draw_labels=True,
            color=g_colours,
            alpha=g_alpha,
            linestyle="--",
            linewidth=0.5,
            x_inline=False,
            y_inline=False,
        )

        gl.top_labels = grid_labels
        gl.bottom_labels = False
        gl.right_labels = False
        gl.left_labels = grid_labels
        # labels on curved map edges, e.g. Robinson
        gl.geo_labels = grid_labels

        if grid_colour == "auto":
            gl = ax.gridlines(
                crs=ccrs.PlateCarree(),
                draw_labels=False,
                color="white",
                alpha=g_alpha,
                linestyle="--",
                linewidth=0.5,
                x_inline=False,
                y_inline=False,
            )

        # here you can select on which side to write the labels for the grid

    # add title
    if title is not None:
        ax.set_title(title)

    # add colorbar
    if not quiver:
        if legend_position == "auto":
            l_location = "right"
        else:
            l_location = legend_position

        if l_location == "bottom":
            fraction = 0.046 * size[0] / size[1] * 0.8
        else:
            fraction = 0.046 * size[1] / size[0]

        min_value = np.min(values)
        max_value = np.max(values)

        min_arrow = False

        if vmin is not None:
            if vmin > min_value:
                min_arrow = True
        max_arrow = False
        if vmax is not None:
            if vmax < max_value:
                max_arrow = True
        
        if min_arrow and max_arrow:
            extend = "both"
        else:
            if min_arrow:
                extend = "min"
            else:
                if max_arrow:
                    extend = "max"
                else:
                    extend = "neither"

        if l_location == "bottom":
            cb = plt.colorbar(im, fraction=fraction, pad=0.04, location=l_location, extend = extend)
        else:
            cb = plt.colorbar(im, fraction=fraction, pad=0.04, extend = extend)

        # add breaks to colorbar cb
        if breaks is not None:
            cb.set_ticks(breaks)
            cb.set_ticklabels(breaks)

        cbax = cb.ax
        if relief:
            ax.stock_img()
    if land is not None:
        # ax.add_feature(cfeature.LAND, facecolor = land, zorder=10)
        if scale == "low":
            l_scale = "110m"
        if scale == "medium":
            l_scale = "50m"
        if scale == "auto":
            l_scale = "50m"
        if scale == "high":
            l_scale = "10m"

        if relief:
            ax.stock_img()
        ax.add_feature(
            cfeature.NaturalEarthFeature(
                category="physical", scale=l_scale, name="land", facecolor=land
            )
        )
    if coast is not None:
        if coast == "auto" and scale == "auto":
            ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        else:
            g_scale = "auto" if coast == "auto" else coast
            ax.add_feature(cfeature.GSHHSFeature(scale=g_scale), linewidth=0.5)

    if not quiver:
        if legend is not None:
            label = legend
        else:
            label = _legend_label(ds1)

            if l_location == "bottom":
                label = "\n".join(wrap(label, 120))
            else:
                label = "\n".join(wrap(label, 30))

        if l_location == "bottom":
            cbax.set_xlabel(label)
        else:
            cbax.set_ylabel(label)

        if legend_position is None:
            cb.remove()
    
    if font is not None:
        for text in [ax.title, ax.xaxis.label, ax.yaxis.label, cb.ax.yaxis.label, cb.ax.xaxis.label]:
            text.set_fontsize(font)
        for item in ([ax.title, ax.xaxis.label, ax.yaxis.label, cb.ax.yaxis.label, cb.ax.xaxis.label] +
                 ax.get_xticklabels() + ax.get_yticklabels()):
            item.set_fontsize(font)

    # cartopy only creates the lon/lat labels while drawing, so draw once for the
    # title to be placed above them when the figure is shown
    if title is not None and not panel:
        fig.canvas.draw()

    if out is not None:
        print("saving as file")
        plt.savefig(out, dpi = dpi)
        plt.savefig(out, dpi = dpi)

    if panel:
        return ax, im


def quiver_plot(ds, u=None, v=None, **kwargs):
    """
    Quiver plot using u and v velocities

    Parameters
    ----------
    ds : nctoolkit Dataset
        dataset containing u and v velocities
    u : str
        u velocity
    v : str
        v velocity
    **kwargs : dict
        kwargs to pass to pub_plot

    Returns
    -------
    fig : matplotlib figure
        figure object


    """

    ds.run()

    # check only one time step in ds

    if len(ds.times) > 1:
        raise ValueError("ds must contain only one time step for quiver_plot")

    # some type checks for u and v

    if u is None:
        raise ValueError("u must be specified")

    if v is None:
        raise ValueError("v must be specified")

    # check u and v are str

    if not isinstance(u, str):
        raise TypeError("u must be a string")

    if not isinstance(v, str):
        raise TypeError("v must be a string")

    vars = ds.variables

    if u not in vars:
        raise ValueError("u not in dataset")

    if v not in vars:
        raise ValueError("v not in dataset")

    pub_plot(ds, quiver=True, u=u, v=v, **kwargs)


def panel_plot(
    panels,
    ncol=None,
    nrow=None,
    shared_colourbar=True,
    var=None,
    extent=None,
    legend=None,
    size="auto",
    land="auto",
    colours="auto",
    norm=None,
    limits=None,
    projection="auto",
    coast="auto",
    scale="auto",
    grid=True,
    grid_colour="auto",
    grid_labels=True,
    legend_position="auto",
    robust=False,
    out=None,
    breaks=None,
    dpi="figure",
    font=None,
    **kwargs,
):
    """
    panel_plot: Grid of pub_plot maps, sharing one colour scale and colour bar by default.

    Each dataset is drawn as one panel, in pub_plot style. By default all
    panels use the same colour limits, worked out from the data of every panel
    together, so the panels can be compared directly. Set
    shared_colourbar=False to give each panel its own colour scale and colour
    bar instead.

    Per-panel values: each pub_plot argument can be one value, which applies to
    every panel, or a list with one value per panel, in the order of panels,
    e.g. land=["grey", "tan"]. Arguments that are already lists in pub_plot
    (extent, limits, breaks) take a list of lists, e.g.
    limits=[[0, 10], [5, 20]], with None for a panel that should use the
    default. With a shared colour bar, the colour bar arguments (colours, norm,
    limits, robust, legend, legend_position, breaks, font) must be single
    values; set shared_colourbar=False to vary them per panel. size, out and
    dpi always apply to the whole figure.

    Parameters
    -------------
    panels: dict
        Panel titles as keys and nctoolkit datasets as values, e.g.
        {"1990s": ds1, "2000s": ds2}. Panels are drawn row by row in the
        order of the dict. Each dataset must contain one variable (or select
        one with var), one time step and one vertical level.
    ncol: int
        Number of panel columns. Default: chosen automatically.
    nrow: int
        Number of panel rows. Default: chosen automatically. With neither
        ncol nor nrow, the grid is as close to square as possible, e.g. 2 x 2
        for 4 panels and 3 x 2 for 6. With one of them, the other is derived.
        ncol x nrow must be at least the number of panels.
    shared_colourbar: bool
        True (default): all panels share one colour scale and one colour bar.
        False: each panel gets its own colour scale and colour bar, as in
        pub_plot, and the colour bar arguments can be given per panel.
    size: list
        [width, height] of the whole figure in inches. Default "auto": about
        3 inches of map per row, with the width matched to the maps' aspect
        ratio and room for titles, labels and the colour bar(s).
    limits: list
        [min, max] colour scale limits, in the same formats as pub_plot:
        numbers, None or percentile strings such as "2%". With a shared colour
        bar, None and percentiles are worked out from all panels together.
        Default: the minimum and maximum across all panels (or of each panel
        with shared_colourbar=False).
    robust: bool
        If True, set the colour limits to the 2nd and 98th percentiles of all
        panels together (or of each panel with shared_colourbar=False).
        Overrides limits. Default False.
    legend: str
        Colour bar label. Default: built from the first dataset's long name
        and units (each panel's own with shared_colourbar=False). Use
        legend="" for no label.
    legend_position: str
        "right" (default; "auto" is the same) or "bottom" for the colour
        bar(s), or None for no colour bar.
    breaks: list
        Tick positions on the colour bar(s), e.g. [0, 10, 20, 30].
    out: str
        File to save the whole figure to, e.g. "panels.png". The format comes
        from the extension. Default: display only.
    dpi: int
        Resolution of the saved file in dots per inch, e.g. 300. Only used
        with out. Default "figure".
    font: float or str
        Font size for the panel titles and colour bar label, in points or as
        a matplotlib size name such as "large".
    colours, norm:
        Colour map and colour normalisation. See pub_plot.
    var, extent, land, projection, coast, scale, grid, grid_colour, grid_labels:
        One value for every panel, or a list of one value per panel, with a
        shared colour bar or without, e.g. var=["chl", "chlor_a"]. See pub_plot.
    **kwargs:
        Passed to every panel, e.g. relief=True. See pub_plot.
    """
    from nctoolkit.api import DataSet

    if "static_plot" in session_info.keys():
        raise ValueError("Unable to import cartopy properly")

    if not isinstance(panels, dict):
        raise TypeError("panels must be a dict of {title: dataset}")
    if len(panels) == 0:
        raise ValueError("panels is empty")
    for key, ds in panels.items():
        if not isinstance(ds, DataSet):
            raise TypeError(f"Panel '{key}' is not an nctoolkit dataset")

    for arg in ["fig", "gs", "title"]:
        if arg in kwargs:
            raise ValueError(f"{arg} cannot be used with panel_plot")

    if not isinstance(shared_colourbar, bool):
        raise TypeError("shared_colourbar must be True or False")

    n = len(panels)

    # Each argument is one value for every panel, or a list of one value per panel.
    # extent, limits and breaks are already lists, so theirs are lists of lists.
    colourbar_args = [
        "colours", "norm", "limits", "robust", "legend", "legend_position", "breaks", "font"
    ]

    def per_panel(name, value):
        if name == "limits":
            # a single [min, max] can contain None, so only nested lists are per panel
            is_list = isinstance(value, (list, tuple)) and any(
                isinstance(x, (list, tuple)) for x in value
            )
        elif name in ["extent", "breaks"]:
            is_list = isinstance(value, (list, tuple)) and any(
                x is None or isinstance(x, (list, tuple)) for x in value
            )
        else:
            is_list = isinstance(value, (list, tuple))
        if not is_list:
            return [value] * n
        if shared_colourbar and name in colourbar_args:
            raise ValueError(
                f"{name} must be a single value when shared_colourbar=True. "
                "Set shared_colourbar=False for per-panel values"
            )
        if len(value) != n:
            values = "value" if len(value) == 1 else "values"
            raise ValueError(f"{name} has {len(value)} {values} but there are {n} panels")
        return list(value)

    args = {
        name: per_panel(name, value)
        for name, value in [
            ("var", var),
            ("extent", extent),
            ("land", land),
            ("colours", colours),
            ("norm", norm),
            ("limits", limits),
            ("projection", projection),
            ("coast", coast),
            ("scale", scale),
            ("grid", grid),
            ("grid_colour", grid_colour),
            ("grid_labels", grid_labels),
            ("legend", legend),
            ("legend_position", legend_position),
            ("robust", robust),
            ("breaks", breaks),
            ("font", font),
        ]
    }

    for position in args["legend_position"]:
        if position not in ["auto", "right", "bottom", None]:
            raise ValueError("legend_position must be one of right/bottom or None")

    for panel_limits in args["limits"]:
        if panel_limits is not None and len(panel_limits) != 2:
            raise ValueError("limits must be a list of [min, max]")

    for name, value in [("ncol", ncol), ("nrow", nrow)]:
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
    if ncol is None and nrow is None:
        ncol = ceil(sqrt(n))
    if ncol is None:
        ncol = ceil(n / nrow)
    if nrow is None:
        nrow = ceil(n / ncol)
    if ncol * nrow < n:
        raise ValueError(f"A {nrow} x {ncol} grid cannot hold {n} panels")

    # check every panel and pool the values, before drawing anything
    pooled = []
    first = None
    for i, (key, ds) in enumerate(panels.items()):
        ds1 = ds.copy()
        if args["var"][i] is not None:
            ds1.subset(variables=args["var"][i])
        ds1.run()
        if len(ds1.variables) > 1:
            raise ValueError(
                f"Panel '{key}' has more than one variable. Select one with var"
            )
        if len(ds1.times) > 1:
            raise ValueError(f"Panel '{key}' has more than one time step")
        ds_xr = ds1.to_xarray(decode_times=False)
        values = np.asarray(ds_xr[ds1.variables[0]].values, dtype=float)
        pooled.append(values[np.isfinite(values)])
        if first is None:
            first = (ds1, ds_xr)

    pooled = np.concatenate(pooled)
    if pooled.size == 0:
        raise ValueError("The panels contain no valid data")

    def resolve(end, default):
        if end is None:
            return default
        if isinstance(end, str) and "%" in end:
            return np.percentile(pooled, float(end.split("%")[0]))
        return end

    if shared_colourbar:
        if robust:
            shared = [np.percentile(pooled, 2), np.percentile(pooled, 98)]
        elif limits is None:
            shared = [pooled.min(), pooled.max()]
        else:
            shared = [resolve(limits[0], pooled.min()), resolve(limits[1], pooled.max())]
        shared = [float(x) for x in shared]

    if size == "auto":
        aspect = 1.5
        ds_xr = first[1]
        first_extent = args["extent"][0]
        try:
            if first_extent is not None:
                lon_span = first_extent[1] - first_extent[0]
                lat_span = first_extent[3] - first_extent[2]
                mid_lat = 0.5 * (first_extent[2] + first_extent[3])
            else:
                lon = np.asarray(ds_xr[[x for x in ds_xr.coords if "lon" in x][0]])
                lat = np.asarray(ds_xr[[x for x in ds_xr.coords if "lat" in x][0]])
                lon_span = np.nanmax(lon) - np.nanmin(lon)
                lat_span = np.nanmax(lat) - np.nanmin(lat)
                mid_lat = 0.5 * (np.nanmax(lat) + np.nanmin(lat))
            if lon_span > 340 and lat_span > 160:
                aspect = 2.0
            else:
                aspect = lon_span * cos(radians(mid_lat)) / lat_span
            aspect = min(max(aspect, 0.6), 2.5)
        except Exception:
            pass
        # map height plus room around each map for its title and lon/lat labels
        map_height = 3.0
        extra_w = 0.8 if any(args["grid_labels"]) else 0.2
        extra_h = 0.9 if any(args["grid_labels"]) else 0.4
        size = [
            ncol * (map_height * aspect + extra_w),
            nrow * (map_height + extra_h),
        ]
        # one colour bar for the figure, or one per column/row of panels
        positions = args["legend_position"]
        if any(p in ["auto", "right"] for p in positions):
            size[0] += 1.2 if shared_colourbar else 1.0 * ncol
        if "bottom" in positions:
            size[1] += 0.9 if shared_colourbar else 0.8 * nrow

    # constrained layout leaves room for the lon/lat labels and the lifted titles
    fig = plt.figure(figsize=size, layout="constrained")
    gs = fig.add_gridspec(nrow, ncol)

    axes = []
    for i, (key, ds) in enumerate(panels.items()):
        panel_args = {
            name: args[name][i]
            for name in [
                "var", "extent", "land", "colours", "norm", "projection", "coast",
                "scale", "grid", "grid_colour", "grid_labels", "font",
            ]
        }
        if shared_colourbar:
            # panels draw no colour bar of their own; one is added for all below
            scale_args = dict(
                limits=list(shared), robust=False, legend="", legend_position=None
            )
        else:
            panel_limits = args["limits"][i]
            scale_args = dict(
                # pub_plot modifies limits in place, so give each panel its own copy
                limits=None if panel_limits is None else list(panel_limits),
                robust=args["robust"][i],
                legend=args["legend"][i],
                legend_position=args["legend_position"][i],
                breaks=args["breaks"][i],
            )
        ax, im = pub_plot(
            ds,
            title=str(key),
            **panel_args,
            **scale_args,
            fig=fig,
            gs=gs[i // ncol, i % ncol],
            _panel=True,
            **kwargs,
        )
        axes.append(ax)

    if shared_colourbar and legend_position is not None:
        location = "bottom" if legend_position == "bottom" else "right"
        vmin, vmax = im.get_clim()
        below = vmin is not None and pooled.min() < vmin
        above = vmax is not None and pooled.max() > vmax
        if below and above:
            extend = "both"
        elif below:
            extend = "min"
        elif above:
            extend = "max"
        else:
            extend = "neither"

        cb = fig.colorbar(
            im,
            ax=axes,
            location=location,
            extend=extend,
            shrink=0.8 if location == "right" else 0.6,
            pad=0.05 if location == "right" else 0.08,
        )

        if breaks is not None:
            cb.set_ticks(breaks)
            cb.set_ticklabels(breaks)

        label = legend if legend is not None else _legend_label(first[0])
        if location == "bottom":
            cb.ax.set_xlabel("\n".join(wrap(label, 120)), fontsize=font)
        else:
            cb.ax.set_ylabel("\n".join(wrap(label, 40)), fontsize=font)

    # cartopy only creates the lon/lat labels while drawing, so draw once for the
    # layout and title placement in the final render to see them
    fig.canvas.draw()

    if out is not None:
        fig.savefig(os.path.expanduser(out), dpi=dpi)