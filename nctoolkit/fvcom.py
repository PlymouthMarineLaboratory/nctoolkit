"""
Support for FVCOM output.

FVCOM writes its output on an unstructured triangular mesh that CDO cannot read:
the sigma coordinates are 2D variables named after their own dimension, and the
horizontal coordinates have no cell bounds. open_fvcom extracts the variables a
user asks for, and writes them to files that CDO reads as an unstructured grid:

* values on the nodes have the median-dual control volumes (FVCOM's tracer
  control volumes, whose areas are art1) as their cells
* values on the elements have their triangles as their cells
* the sigma layers become a vertical axis of layer numbers, 1 at the surface
* the thickness of each layer, (siglev[k] - siglev[k + 1]) * (h + zeta), is
  added as a variable, so the vertical methods can weight by it

Because every cell has bounds, CDO works out true cell areas, so spatial means
are area weighted. Bilinear and nearest neighbour regridding use weights worked
out on the mesh itself, which CDO then applies.
"""

import glob
import os
import subprocess
import warnings

import netCDF4
import numpy as np
import pandas as pd

from nctoolkit.session import append_safe, remove_safe, session_info
from nctoolkit.temp_file import temp_file


THICKNESS = "layer_thickness"
# CDO will not use weights from a file if the data has missing values, as it
# then works out new weights. So missing values are set to a huge value before
# remapping, and anything that took in a huge value is missing afterwards
FVCOM_REMAP = "-setrtomiss,1e25,1e38 -remap,{grid},{weights} -setmisstoc,1e35"
MJD_UNITS = "days since 1858-11-17 00:00:00"
FILL = 1.0e20
# values read at once when converting, about 80 MB of float32
BLOCK_VALUES = 20_000_000
NODE = "node"
NELE = "nele"
SIGLAY = "siglay"
SIGLEV = "siglev"

# FVCOM's mesh, time and model-state variables, which are never data
MESH_VARIABLES = {
    "nprocs", "partition", "x", "y", "lon", "lat", "xc", "yc", "lonc", "latc",
    "siglay", "siglev", "siglay_center", "siglev_center", "nv",
    "iint", "time", "Itime", "Itime2", "Times", "file_date", "nbe", "ntsn",
    "nbsn", "ntve", "nbve", "a1u", "a2u", "aw0", "awx", "awy", "art1", "art2",
}

ATTRIBUTES_KEPT = ["long_name", "standard_name", "units"]


# ---------------------------------------------------------------------------
# the mesh
# ---------------------------------------------------------------------------


def _wrap(lon):
    """Longitudes in -180 to 180, or 0 to 360 if the mesh straddles the dateline"""
    lon = np.asarray(lon, dtype="float64")
    lon = np.where(lon > 180, lon - 360, lon)
    if lon.size > 0 and lon.max() - lon.min() > 180:
        lon = np.where(lon < 0, lon + 360, lon)
    return lon


def _counter_clockwise(lon, lat, nv):
    """Order the corners of each triangle counter-clockwise. FVCOM's are clockwise"""
    a, b, c = nv[:, 0], nv[:, 1], nv[:, 2]
    signed = (lon[b] - lon[a]) * (lat[c] - lat[a]) - (lon[c] - lon[a]) * (lat[b] - lat[a])
    nv = nv.copy()
    flip = signed < 0
    nv[flip, 1], nv[flip, 2] = c[flip], b[flip]
    return nv


class Mesh:
    """
    The horizontal mesh of an FVCOM file: lon and lat of the nodes, the
    triangles (nele, 3) as 0-based, counter-clockwise node numbers, and the
    centres of the elements
    """

    def __init__(self, lon, lat, nv, lonc=None, latc=None):
        self.lon = _wrap(lon)
        self.lat = np.asarray(lat, dtype="float64")
        self.nv = _counter_clockwise(self.lon, self.lat, np.asarray(nv, dtype="int64"))
        if lonc is None or latc is None:
            lonc = self.lon[self.nv].mean(axis=1)
            latc = self.lat[self.nv].mean(axis=1)
        self.lonc = _wrap(lonc)
        self.latc = np.asarray(latc, dtype="float64")
        # keep the element centres on the same side of the dateline as the nodes
        if self.lon.max() > 180:
            self.lonc = np.where(self.lonc < 0, self.lonc + 360, self.lonc)

    @property
    def n_node(self):
        return len(self.lon)

    @property
    def n_nele(self):
        return len(self.nv)

    def cells(self, location):
        """lon and lat of the cells on node or nele"""
        if location == NODE:
            return self.lon, self.lat
        return self.lonc, self.latc

    def triangle_areas(self):
        """Areas of the triangles in m^2, on a sphere of radius 6371 km"""
        earth = 6_371_000.0

        def unit(lon, lat):
            lon, lat = np.radians(lon), np.radians(lat)
            return np.stack(
                [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=-1
            )

        a, b, c = (unit(self.lon[self.nv[:, k]], self.lat[self.nv[:, k]]) for k in range(3))
        triple = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
        below = 1 + np.einsum("ij,ij->i", a, b) + np.einsum("ij,ij->i", b, c) + np.einsum("ij,ij->i", c, a)
        return 2 * np.arctan2(triple, below) * earth**2

    def element_bounds(self):
        """The corners of each triangle, (nele, 3)"""
        return self.lon[self.nv], self.lat[self.nv]

    def node_bounds(self):
        """
        The median-dual control volume of each node: the polygon through the
        centroids of the triangles round it and the mid-points of its edges,
        with the node itself on the edge of the mesh. Polygons are counter-
        clockwise, and padded to the same number of corners by repeating
        their last corner
        """
        lon, lat, nv = self.lon, self.lat, self.nv
        n = self.n_node
        cen_lon = lon[nv].mean(axis=1)
        cen_lat = lat[nv].mean(axis=1)

        # for corner a of triangle (a, b, c), its piece of the control volume
        # runs from the middle of a-b, through the centroid, to the middle of a-c
        first = nv.ravel()
        after = np.roll(nv, -1, axis=1).ravel()
        before = np.roll(nv, -2, axis=1).ravel()
        triangle = np.repeat(np.arange(len(nv)), 3)
        order = np.argsort(first, kind="stable")
        first, after, before, triangle = first[order], after[order], before[order], triangle[order]
        starts = np.searchsorted(first, np.arange(n + 1))

        polygons = []
        for i in range(n):
            rows = range(starts[i], starts[i + 1])
            if len(rows) == 0:
                polygons.append([(lon[i], lat[i])])
                continue
            following = {after[r]: r for r in rows}
            preceded = {before[r] for r in rows}
            # pieces with nothing before them start on the edge of the mesh
            heads = [r for r in rows if after[r] not in preceded]
            used = set()

            def walk(r):
                chain = []
                while r is not None and r not in used:
                    used.add(r)
                    chain.append(r)
                    r = following.get(before[r])
                return chain

            chains = [(walk(r), True) for r in heads]
            chains += [(walk(r), False) for r in rows if r not in used]
            corners = []
            for chain, on_edge in chains:
                if len(chain) == 0:
                    continue
                for r in chain:
                    j = after[r]
                    corners.append((0.5 * (lon[i] + lon[j]), 0.5 * (lat[i] + lat[j])))
                    corners.append((cen_lon[triangle[r]], cen_lat[triangle[r]]))
                if on_edge:
                    j = before[chain[-1]]
                    corners.append((0.5 * (lon[i] + lon[j]), 0.5 * (lat[i] + lat[j])))
                    corners.append((lon[i], lat[i]))
            polygons.append(corners)

        size = max(len(p) for p in polygons)
        bounds_lon = np.empty((n, size))
        bounds_lat = np.empty((n, size))
        for i, p in enumerate(polygons):
            p = p + [p[-1]] * (size - len(p))
            bounds_lon[i], bounds_lat[i] = zip(*p)
        return bounds_lon, bounds_lat

    def bounds(self, location):
        if location == NODE:
            return self.node_bounds()
        return self.element_bounds()

    def save(self, path):
        """Write the mesh to a netCDF file, for use when regridding"""
        with netCDF4.Dataset(path, "w") as nc:
            nc.createDimension(NODE, self.n_node)
            nc.createDimension(NELE, self.n_nele)
            nc.createDimension("three", 3)
            for name, dim, values in [
                ("lon", NODE, self.lon),
                ("lat", NODE, self.lat),
                ("lonc", NELE, self.lonc),
                ("latc", NELE, self.latc),
            ]:
                nc.createVariable(name, "f8", (dim,))[:] = values
            nc.createVariable("nv", "i4", (NELE, "three"))[:] = self.nv

    @classmethod
    def load(cls, path):
        with netCDF4.Dataset(path) as nc:
            mesh = cls.__new__(cls)
            mesh.lon = nc["lon"][:].data.astype("float64")
            mesh.lat = nc["lat"][:].data.astype("float64")
            mesh.lonc = nc["lonc"][:].data.astype("float64")
            mesh.latc = nc["latc"][:].data.astype("float64")
            mesh.nv = nc["nv"][:].data.astype("int64")
        return mesh


def read_mesh(handle):
    """The Mesh of an open FVCOM netCDF4.Dataset"""
    v = handle.variables
    for name in ["lon", "lat", "nv"]:
        if name not in v:
            raise ValueError(f"This does not look like an FVCOM file: it has no {name} variable")
    lon = np.ma.filled(v["lon"][:], np.nan).astype("float64")
    lat = np.ma.filled(v["lat"][:], np.nan).astype("float64")
    if np.ptp(lon) == 0 and np.ptp(lat) == 0:
        raise ValueError(
            "The FVCOM file has no longitudes and latitudes, only Cartesian x and y. "
            "nctoolkit needs longitudes and latitudes"
        )
    nv = np.ma.filled(v["nv"][:], -1).astype("int64")
    if nv.shape[0] == 3 and nv.shape[1] != 3:
        nv = nv.T
    # FVCOM numbers its nodes from 1
    if nv.min() >= 1:
        nv = nv - 1
    lonc = latc = None
    if "lonc" in v and "latc" in v:
        lonc = np.ma.filled(v["lonc"][:], np.nan).astype("float64")
        latc = np.ma.filled(v["latc"][:], np.nan).astype("float64")
        if np.ptp(lonc) == 0 and np.ptp(latc) == 0:
            lonc = latc = None
    return Mesh(lon, lat, nv, lonc, latc)


_mesh_cache = dict()


def load_mesh(path):
    if path not in _mesh_cache:
        _mesh_cache[path] = Mesh.load(path)
    return _mesh_cache[path]


# ---------------------------------------------------------------------------
# reading FVCOM files
# ---------------------------------------------------------------------------


def _location(handle, var):
    dims = handle.variables[var].dimensions
    if NODE in dims:
        return NODE
    if NELE in dims:
        return NELE
    raise ValueError(f"{var} is neither on the nodes nor on the elements of the FVCOM mesh")


def _vertical(handle, var):
    dims = handle.variables[var].dimensions
    for axis in [SIGLAY, SIGLEV]:
        if axis in dims:
            return axis
    return None


def _times(handle):
    """FVCOM's times as double precision days since 1858-11-17, and their units"""
    v = handle.variables
    if "Itime" in v and "Itime2" in v:
        days = np.asarray(v["Itime"][:], dtype="float64")
        msec = np.asarray(v["Itime2"][:], dtype="float64")
        return days + msec / 86_400_000.0, getattr(v["Itime"], "units", MJD_UNITS)
    if "time" in v:
        return np.asarray(v["time"][:], dtype="float64"), getattr(v["time"], "units", MJD_UNITS)
    if "Times" in v:
        stamps = pd.to_datetime([str(x).strip() for x in netCDF4.chartostring(v["Times"][:])])
        days = (stamps - pd.Timestamp("1858-11-17")) / pd.Timedelta(days=1)
        return np.asarray(days, dtype="float64"), MJD_UNITS
    raise ValueError("Unable to find the times in the FVCOM file")


def _sigma_levels(handle, location, mesh):
    """
    The sigma levels (siglev, cells), 0 at the surface and -1 at the seabed,
    or None if the file has none
    """
    v = handle.variables
    levels = None
    if location == NELE and "siglev_center" in v:
        levels = np.asarray(v["siglev_center"][:], dtype="float64")
    elif "siglev" in v:
        levels = np.asarray(v["siglev"][:], dtype="float64")
    elif "siglay" in v:
        # the levels are half way between the layers
        layers = np.asarray(v["siglay"][:], dtype="float64")
        if layers.ndim == 1:
            layers = layers[:, None]
        levels = np.zeros((layers.shape[0] + 1, layers.shape[1]))
        for k in range(layers.shape[0]):
            levels[k + 1] = 2 * layers[k] - levels[k]
        levels[-1] = -1.0
    if levels is None:
        return None
    if levels.ndim == 1:
        levels = levels[:, None]
    if location == NELE and levels.shape[1] == mesh.n_node:
        levels = levels[:, mesh.nv].mean(axis=2)
    return levels


def _depth(handle, location, mesh):
    """The bathymetry, h, on the cells, or None"""
    v = handle.variables
    if location == NELE and "h_center" in v:
        return np.asarray(v["h_center"][:], dtype="float64")
    if "h" not in v:
        return None
    h = np.asarray(v["h"][:], dtype="float64")
    if location == NELE:
        h = h[mesh.nv].mean(axis=1)
    return h


def _surface(handle, location, mesh, start, stop):
    """zeta for times start to stop on the cells, or None"""
    v = handle.variables
    if "zeta" not in v:
        return None
    zeta = np.ma.filled(v["zeta"][start:stop], 0.0).astype("float64")
    if location == NELE:
        zeta = zeta[:, mesh.nv].mean(axis=2)
    return zeta


# ---------------------------------------------------------------------------
# converting FVCOM files
# ---------------------------------------------------------------------------


def _check_variables(handle, variables):
    """
    The location (node or nele) and vertical axis of the variables, which must
    be the same for all of them
    """
    missing = [x for x in variables if x not in handle.variables]
    if len(missing) > 0:
        raise ValueError(f"These variables are not in the FVCOM file: {', '.join(missing)}")
    mesh_vars = [x for x in variables if x in MESH_VARIABLES]
    if len(mesh_vars) > 0:
        raise ValueError(
            f"These are FVCOM mesh or time variables, not data: {', '.join(mesh_vars)}"
        )

    locations = {x: _location(handle, x) for x in variables}
    if len(set(locations.values())) > 1:
        on_nodes = [x for x in variables if locations[x] == NODE]
        on_elements = [x for x in variables if locations[x] == NELE]
        raise ValueError(
            "Variables on the nodes and elements of the FVCOM mesh cannot be opened together. "
            f"On the nodes: {', '.join(on_nodes)}. On the elements: {', '.join(on_elements)}. "
            "Please open them with separate calls to open_fvcom"
        )
    verticals = {x: _vertical(handle, x) for x in variables}
    axes = {x for x in verticals.values() if x is not None}
    if len(axes) > 1:
        raise ValueError(
            "Variables on the sigma layers (siglay) and the sigma levels (siglev) cannot be "
            "opened together. Please open them with separate calls to open_fvcom"
        )
    for x in variables:
        dims = handle.variables[x].dimensions
        others = [d for d in dims if d not in ["time", SIGLAY, SIGLEV, NODE, NELE]]
        if len(others) > 0:
            raise ValueError(f"{x} has dimensions nctoolkit cannot handle: {', '.join(others)}")
    return list(locations.values())[0], (list(axes)[0] if len(axes) == 1 else None)


def _default_variables(handle):
    """
    The variables opened when none are given: every data variable on the nodes
    that is on the sigma layers or has no vertical axis. Returns these and the
    data variables that cannot go in the same Dataset
    """
    kept, skipped = [], []
    for name, var in handle.variables.items():
        if name in MESH_VARIABLES or name == THICKNESS:
            continue
        try:
            location = _location(handle, name)
        except ValueError:
            continue
        others = [d for d in var.dimensions if d not in ["time", SIGLAY, SIGLEV, NODE, NELE]]
        if len(others) > 0:
            skipped.append(name)
        elif location == NODE and _vertical(handle, name) in [SIGLAY, None]:
            kept.append(name)
        else:
            skipped.append(name)
    if len(kept) == 0:
        raise ValueError(
            "There are no variables on the nodes of the FVCOM mesh to open. "
            "Please supply the variables, e.g. variables = ['u', 'v']"
        )
    return kept, skipped


def convert_file(path, variables, out, mesh=None, bounds=None, thickness=True):
    """
    Write the variables of the FVCOM file at path to out, a netCDF file CDO
    reads as an unstructured grid. Returns whether the layer thickness was added
    """
    with netCDF4.Dataset(path) as src:
        location, axis = _check_variables(src, variables)
        if mesh is None:
            mesh = read_mesh(src)
        if bounds is None:
            bounds = mesh.bounds(location)
        lon, lat = mesh.cells(location)
        bounds_lon, bounds_lat = bounds
        n_cells = len(lon)
        if src.dimensions[location].size != n_cells:
            raise ValueError(f"{path} does not have the same mesh as the first file")

        times, time_units = _times(src)
        n_times = len(times)

        add_thickness = thickness and axis == SIGLAY
        if add_thickness:
            levels = _sigma_levels(src, location, mesh)
            h = _depth(src, location, mesh)
            if levels is None or h is None:
                warnings.warn(
                    "The FVCOM file has no sigma levels or bathymetry, so the layer thickness cannot be worked out"
                )
                add_thickness = False
            else:
                shares = np.abs(levels[:-1] - levels[1:])
                if "zeta" not in src.variables:
                    warnings.warn(
                        "The FVCOM file has no zeta, so the layer thickness ignores the free surface"
                    )

        with netCDF4.Dataset(out, "w", format="NETCDF4") as dst:
            dst.createDimension("time", None)
            if axis is not None:
                dst.createDimension(axis, src.dimensions[axis].size)
            dst.createDimension(location, n_cells)
            dst.createDimension("nvertex", bounds_lon.shape[1])

            t = dst.createVariable("time", "f8", ("time",))
            t.setncatts(
                {"standard_name": "time", "long_name": "time", "units": time_units,
                 "calendar": "standard", "axis": "T"}
            )
            t[:] = times

            if axis is not None:
                z = dst.createVariable(axis, "f8", (axis,))
                kind = "layer" if axis == SIGLAY else "level"
                z.setncatts(
                    {"long_name": f"sigma {kind} number, 1 at the surface", "units": "level",
                     "positive": "down", "axis": "Z"}
                )
                z[:] = np.arange(1, src.dimensions[axis].size + 1)

            where = "node" if location == NODE else "element centre"
            for name, values, attrs in [
                ("lon", lon, {"standard_name": "longitude", "long_name": f"{where} longitude",
                              "units": "degrees_east", "bounds": "lon_bnds"}),
                ("lat", lat, {"standard_name": "latitude", "long_name": f"{where} latitude",
                              "units": "degrees_north", "bounds": "lat_bnds"}),
            ]:
                var = dst.createVariable(name, "f8", (location,))
                var.setncatts(attrs)
                var[:] = values
            dst.createVariable("lon_bnds", "f8", (location, "nvertex"))[:] = bounds_lon
            dst.createVariable("lat_bnds", "f8", (location, "nvertex"))[:] = bounds_lat

            outputs = dict()
            for x in variables:
                source = src.variables[x]
                dtype = "f8" if source.dtype == np.float64 else "f4"
                var = dst.createVariable(x, dtype, source.dimensions, fill_value=FILL)
                for att in ATTRIBUTES_KEPT:
                    if att in source.ncattrs():
                        var.setncattr(att, source.getncattr(att))
                var.setncattr("missing_value", np.array(FILL, dtype=dtype))
                var.setncattr("coordinates", "lat lon")
                outputs[x] = var

            if add_thickness:
                dims = ("time", SIGLAY, location)
                var = dst.createVariable(THICKNESS, "f4", dims, fill_value=FILL)
                var.setncatts(
                    {"standard_name": "cell_thickness", "long_name": "sigma layer thickness",
                     "units": "m", "missing_value": np.float32(FILL), "coordinates": "lat lon"}
                )
                outputs[THICKNESS] = var

            n_layers = src.dimensions[axis].size if axis is not None else 1
            block = max(1, int(BLOCK_VALUES // (n_cells * n_layers)))
            for x in variables:
                source = src.variables[x]
                if "time" not in source.dimensions:
                    outputs[x][:] = np.ma.filled(np.ma.masked_invalid(source[:]), FILL)
            for start in range(0, n_times, block):
                stop = min(n_times, start + block)
                for x in variables:
                    source = src.variables[x]
                    if "time" in source.dimensions:
                        values = np.ma.masked_invalid(source[start:stop])
                        outputs[x][start:stop] = np.ma.filled(values, FILL)
                if add_thickness:
                    total = np.repeat(h[None, :], stop - start, axis=0)
                    zeta = _surface(src, location, mesh, start, stop)
                    if zeta is not None:
                        total = total + zeta
                    total = np.clip(total, 0, None)
                    outputs[THICKNESS][start:stop] = shares[None, :, :] * total[:, None, :]

            for att in ["title", "institution", "source", "references"]:
                if att in src.ncattrs():
                    dst.setncattr(att, src.getncattr(att))
            dst.setncattr("Conventions", "CF-1.6")
            dst.setncattr("nctoolkit_fvcom", location)
            dst.setncattr("fvcom_source", os.path.abspath(path))
            if add_thickness:
                dst.setncattr("fvcom_thickness", THICKNESS)
    return add_thickness


def _convert_one(args):
    path, variables, out, mesh, bounds, thickness = args
    return convert_file(path, variables, out, mesh=mesh, bounds=bounds, thickness=thickness)


def _paths(x):
    if isinstance(x, str):
        x = os.path.expanduser(x)
        found = sorted(glob.glob(x))
        if len(found) == 0:
            raise FileNotFoundError(f"{x} does not exist!")
        return found
    if isinstance(x, (list, tuple)):
        paths = []
        for ff in x:
            if not isinstance(ff, str):
                raise TypeError("Please supply file paths as str")
            ff = os.path.expanduser(ff)
            if not os.path.exists(ff):
                raise FileNotFoundError(f"{ff} does not exist!")
            paths.append(ff)
        if len(paths) == 0:
            raise ValueError("Please supply at least one FVCOM file")
        return list(dict.fromkeys(paths))
    raise TypeError("Please supply a file path, a list of file paths or a wildcard")


def open_fvcom(x=None, variables=None, thickness=True):
    """
    Open FVCOM output as a Dataset.

    The variables asked for are extracted from the FVCOM files and put on a grid
    that CDO, and so nctoolkit, understands: each node or element of the mesh is
    a grid cell with its true area. The sigma layers become vertical levels,
    numbered from 1 at the surface.

    Parameters
    ---------------
    x : str or list
        An FVCOM file, a list of them or a wildcard, e.g. "output/*.nc".
    variables : str or list
        The variable or variables to extract. Defaults to None, which means every
        variable on the nodes of the mesh that is on the sigma layers or has no
        vertical axis (e.g. temp, salinity, zeta, h). A warning lists any variables
        left out, i.e. those on the elements (e.g. u, v) or the sigma levels (e.g. km).
        Supply these explicitly to open them. A Dataset has a single grid, so
        supplied variables must all be on the nodes or all be on the elements, and
        all be on the sigma layers or all on the sigma levels.
    thickness : bool
        Add the thickness of each sigma layer, (siglev[k] - siglev[k + 1]) * (h + zeta),
        as a variable? Defaults to True. Its name is in the Dataset's fvcom_thickness
        attribute, and vertical_mean, vertical_integration and vertical_interp use it.

    Returns
    ---------------
    open_fvcom : nctoolkit.DataSet

    Examples
    ------------

    >>> import nctoolkit as nc
    >>> ds = nc.open_fvcom("fvcom_0001.nc")
    >>> ds = nc.open_fvcom("fvcom_0001.nc", variables=["temp", "salinity"])
    >>> ds.vertical_mean()
    >>> ds.to_latlon(lon=[-10, -2], lat=[48, 57], res=0.05)
    """
    from nctoolkit.api import DataSet

    if variables is not None:
        if isinstance(variables, str):
            variables = [variables]
        if not isinstance(variables, (list, tuple)) or len(variables) == 0:
            raise TypeError("variables must be a str or a list of str")
        for vv in variables:
            if not isinstance(vv, str):
                raise TypeError("variables must be a str or a list of str")
        variables = list(dict.fromkeys(variables))
    if not isinstance(thickness, bool):
        raise TypeError("thickness must be True or False")

    if x is None:
        raise ValueError("Please supply FVCOM files")
    paths = _paths(x)

    with netCDF4.Dataset(paths[0]) as src:
        if variables is None:
            variables, skipped = _default_variables(src)
            if len(skipped) > 0:
                warnings.warn(
                    "No variables were given, so all those on the nodes and sigma layers of the FVCOM "
                    f"mesh were opened. These were not: {', '.join(skipped)}. "
                    "To open them, supply them with variables, e.g. variables = ['u', 'v']"
                )
        location, axis = _check_variables(src, variables)
        mesh = read_mesh(src)
    bounds = mesh.bounds(location)

    mesh_file = temp_file(".nc")
    mesh.save(mesh_file)
    # kept safe from clean up while the files are converted
    append_safe(mesh_file)

    outs = [temp_file(".nc") for ff in paths]
    jobs = [(ff, variables, out, mesh, bounds, thickness) for ff, out in zip(paths, outs)]

    try:
        cores = session_info["cores"]
        if cores > 1 and len(paths) > 1:
            import multiprocessing as mp

            with mp.get_context("fork").Pool(min(cores, len(paths))) as pool:
                added = pool.map(_convert_one, jobs)
        else:
            added = [_convert_one(job) for job in jobs]
    except Exception:
        remove_safe(mesh_file)
        for ff in outs + [mesh_file]:
            if os.path.exists(ff):
                os.remove(ff)
        raise

    for out in outs:
        append_safe(out)

    # the files stay safe while the dataset holds them, as with open_data
    if len(outs) == 1:
        ds = DataSet(outs[0])
    else:
        ds = DataSet(outs)
    ds.fvcom = True
    ds.fvcom_thickness = THICKNESS if all(added) else None
    # the dataset now keeps the mesh file safe
    ds._fvcom_mesh = mesh_file
    remove_safe(mesh_file)
    return ds


# ---------------------------------------------------------------------------
# helpers for the dataset methods
# ---------------------------------------------------------------------------


def is_fvcom(ds):
    return getattr(ds, "fvcom", False) is True


def not_for_fvcom(why="it needs a regular lon/lat grid", hint=None):
    """Decorate a dataset method that does not work with FVCOM data"""
    import functools

    def decorate(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if is_fvcom(self):
                refuse(func.__name__, why, hint)
            return func(self, *args, **kwargs)

        return wrapper

    return decorate


def refuse(method, why="it needs a regular lon/lat grid", hint=None):
    if hint is None:
        hint = "Please regrid the data first, e.g. using to_latlon"
    raise TypeError(f"{method}: This method does not work with FVCOM data, as {why}. {hint}".strip())


def drop_thickness(ds):
    """Remove the FVCOM layer thickness, for methods that work on a single variable"""
    thickness = getattr(ds, "fvcom_thickness", None)
    if thickness is not None and thickness in ds.variables and len(ds.variables) > 1:
        ds.drop(variables=thickness)
        ds.run()


def thickness_of(ds, thickness=None):
    """The thickness variable for the vertical methods of an FVCOM dataset"""
    if thickness is not None:
        return thickness
    if ds.fvcom_thickness is None:
        raise ValueError(
            "This FVCOM dataset no longer has its layer thickness, so the sigma layers cannot be weighted. "
            "The thickness is added by open_fvcom(..., thickness=True). Keep it when selecting variables, "
            "e.g. subset(variables=['temp', 'layer_thickness']), or supply thickness"
        )
    if ds.fvcom_thickness not in ds.variables:
        raise ValueError(
            f"The layer thickness, {ds.fvcom_thickness}, is no longer in the dataset, so the layers cannot be weighted. "
            "Please keep it in the dataset, or supply thickness"
        )
    return ds.fvcom_thickness


# ---------------------------------------------------------------------------
# regridding
# ---------------------------------------------------------------------------


def _find(units, standard_name, nc):
    for name, var in nc.variables.items():
        if getattr(var, "standard_name", None) == standard_name:
            return var
    for name, var in nc.variables.items():
        if getattr(var, "units", None) in units:
            return var
    return None


def target_points(target_grid):
    """
    lon and lat of the cells of a CDO grid (a grid description or a netCDF
    file), flattened in CDO's order, with the grid's SCRIP dims and type
    """
    out = temp_file(".nc")
    command = f"cdo -s -f nc -const,1,{target_grid} {out}"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not os.path.exists(out):
        raise ValueError(f"Unable to read the target grid: {result.stderr.decode('utf-8')}")
    try:
        with netCDF4.Dataset(out) as nc:
            lon = _find(["degrees_east", "degree_east"], "longitude", nc)
            lat = _find(["degrees_north", "degree_north"], "latitude", nc)
            if lon is None or lat is None:
                raise ValueError("The target grid has no longitudes and latitudes")
            if lon.ndim == 1 and lat.ndim == 1 and lon.dimensions != lat.dimensions:
                glon, glat = np.meshgrid(lon[:], lat[:])
                return glon.ravel(), glat.ravel(), [lon.size, lat.size], "lonlat"
            if lon.ndim == 2:
                ny, nx = lon.shape
                return np.asarray(lon[:]).ravel(), np.asarray(lat[:]).ravel(), [nx, ny], "curvilinear"
            return np.asarray(lon[:]).ravel(), np.asarray(lat[:]).ravel(), [lon.size], "unstructured"
    finally:
        if os.path.exists(out):
            os.remove(out)


def source_points(ff):
    """lon and lat of the cells of a file on an FVCOM grid"""
    with netCDF4.Dataset(ff) as nc:
        lon = _find(["degrees_east", "degree_east"], "longitude", nc)
        lat = _find(["degrees_north", "degree_north"], "latitude", nc)
        if lon is None or lat is None or lon.ndim != 1:
            raise ValueError("Unable to find the FVCOM mesh's longitudes and latitudes")
        return np.asarray(lon[:], dtype="float64"), np.asarray(lat[:], dtype="float64")


def _match(lon, lat, ref_lon, ref_lat):
    """For each point, its number in ref, or -1"""
    key = lambda a, b: pd.MultiIndex.from_arrays([np.round(_wrap(a), 6), np.round(b, 6)])
    ref = pd.Series(np.arange(len(ref_lon)), index=key(ref_lon, ref_lat))
    ref = ref[~ref.index.duplicated()]
    found = ref.reindex(key(lon, lat))
    return np.where(found.isna(), -1, found.fillna(-1).values).astype("int64")


def _barycentric(mesh, triangles, lon, lat):
    """
    The triangle (row of triangles) each point is in, -1 if none, and the
    weights of its three corners
    """
    from matplotlib.tri import Triangulation

    found = np.full(len(lon), -1)
    weights = np.zeros((len(lon), 3))
    if len(triangles) == 0:
        return found, weights
    try:
        finder = Triangulation(mesh.lon, mesh.lat, triangles).get_trifinder()
    except Exception as e:
        raise ValueError(f"Unable to search the FVCOM mesh: {e}")
    found = finder(lon, lat)
    ok = found >= 0
    corners = triangles[found[ok]]
    cx, cy = mesh.lon[corners], mesh.lat[corners]
    x, y = lon[ok], lat[ok]
    det = (cy[:, 1] - cy[:, 2]) * (cx[:, 0] - cx[:, 2]) + (cx[:, 2] - cx[:, 1]) * (cy[:, 0] - cy[:, 2])
    first = ((cy[:, 1] - cy[:, 2]) * (x - cx[:, 2]) + (cx[:, 2] - cx[:, 1]) * (y - cy[:, 2])) / det
    second = ((cy[:, 2] - cy[:, 0]) * (x - cx[:, 2]) + (cx[:, 0] - cx[:, 2]) * (y - cy[:, 2])) / det
    w = np.clip(np.column_stack([first, second, 1 - first - second]), 0, 1)
    weights[ok] = w / w.sum(axis=1, keepdims=True)
    return found, weights


def mesh_links(mesh, src_lon, src_lat, dst_lon, dst_lat, method):
    """
    The remapping links (dst, src, weight) from the cells of an FVCOM grid to
    the target points. method is "bil" or "nn"
    """
    # put the target on the mesh's side of the dateline
    dst_lon = np.asarray(dst_lon, dtype="float64")
    dst_lat = np.asarray(dst_lat, dtype="float64")
    if mesh.lon.max() > 180:
        dst_lon = np.where(dst_lon < 0, dst_lon + 360, dst_lon)
    else:
        dst_lon = np.where(dst_lon > 180, dst_lon - 360, dst_lon)

    on_nodes = _match(src_lon, src_lat, mesh.lon, mesh.lat)
    if (on_nodes >= 0).all():
        location, where = NODE, on_nodes
    else:
        on_elements = _match(src_lon, src_lat, mesh.lonc, mesh.latc)
        if (on_elements >= 0).all():
            location, where = NELE, on_elements
        else:
            raise ValueError("The grid of the dataset is no longer that of the FVCOM mesh, so it cannot be regridded")

    if location == NODE:
        # the cell of each node, or -1 if it is not in the dataset
        local = np.full(mesh.n_node, -1)
        local[where] = np.arange(len(where))
        keep = (local[mesh.nv] >= 0).all(axis=1)
        triangles = mesh.nv[keep]
        found, w = _barycentric(mesh, triangles, dst_lon, dst_lat)
        ok = np.where(found >= 0)[0]
        corners = local[triangles[found[ok]]]
        if method == "nn":
            scale = np.cos(np.radians(dst_lat[ok]))[:, None]
            gaps = ((mesh.lon[triangles[found[ok]]] - dst_lon[ok][:, None]) * scale) ** 2
            gaps += (mesh.lat[triangles[found[ok]]] - dst_lat[ok][:, None]) ** 2
            nearest = np.argmin(gaps, axis=1)
            return ok, corners[np.arange(len(ok)), nearest], np.ones(len(ok))
        return np.repeat(ok, 3), corners.ravel(), w[ok].ravel()

    # values on the elements
    local = np.full(mesh.n_nele, -1)
    local[where] = np.arange(len(where))
    keep = local >= 0
    elements = np.where(keep)[0]
    triangles = mesh.nv[keep]
    found, w = _barycentric(mesh, triangles, dst_lon, dst_lat)
    ok = np.where(found >= 0)[0]
    if method == "nn":
        # the element each point is in
        return ok, local[elements[found[ok]]], np.ones(len(ok))

    # bilinear: the value at each node is the area weighted mean of the
    # elements round it, which is then interpolated within the triangle
    areas = mesh.triangle_areas()[elements]
    incidence = pd.DataFrame(
        {"node": triangles.ravel(), "src": np.repeat(local[elements], 3), "area": np.repeat(areas, 3)}
    )
    incidence["share"] = incidence.area / incidence.groupby("node").area.transform("sum")
    links = pd.DataFrame(
        {"dst": np.repeat(ok, 3), "node": triangles[found[ok]].ravel(), "w": w[ok].ravel()}
    )
    links = links.merge(incidence.loc[:, ["node", "src", "share"]], on="node")
    links["weight"] = links.w * links.share
    links = links.groupby(["dst", "src"], as_index=False).weight.sum()
    return links.dst.values, links.src.values, links.weight.values


def write_weights(path, src_lon, src_lat, dst_lon, dst_lat, dst_dims, dst_type, links, method):
    """Write remapping links as a SCRIP weights file that cdo remap can use"""
    dst, src, weight = links
    # tiny weights are dropped: with FVCOM_REMAP's huge stand-in for missing
    # values, any weight left must be large enough to flag a missing value
    keep = weight > 1e-9
    dst, src, weight = dst[keep], src[keep], weight[keep]
    if len(dst) == 0:
        raise ValueError("None of the target grid is inside the FVCOM mesh")
    totals = np.bincount(dst, weights=weight, minlength=len(dst_lon))
    weight = weight / totals[dst]
    order = np.lexsort((src, dst))
    dst, src, weight = dst[order], src[order], weight[order]
    n_src, n_dst = len(src_lon), len(dst_lon)
    frac = np.zeros(n_dst)
    frac[np.unique(dst)] = 1.0
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as nc:
        nc.createDimension("src_grid_size", n_src)
        nc.createDimension("dst_grid_size", n_dst)
        nc.createDimension("src_grid_rank", 1)
        nc.createDimension("dst_grid_rank", len(dst_dims))
        nc.createDimension("num_links", len(dst))
        nc.createDimension("num_wgts", 1)
        nc.createVariable("src_grid_dims", "i4", ("src_grid_rank",))[:] = [n_src]
        nc.createVariable("dst_grid_dims", "i4", ("dst_grid_rank",))[:] = dst_dims
        for side, lon, lat, size in [("src", src_lon, src_lat, "src_grid_size"), ("dst", dst_lon, dst_lat, "dst_grid_size")]:
            for name, values in [("lat", lat), ("lon", lon)]:
                var = nc.createVariable(f"{side}_grid_center_{name}", "f8", (size,))
                var.units = "radians"
                var[:] = np.radians(values)
        for side, size in [("src", "src_grid_size"), ("dst", "dst_grid_size")]:
            var = nc.createVariable(f"{side}_grid_imask", "i4", (size,))
            var.units = "unitless"
            var[:] = 1
        var = nc.createVariable("src_grid_frac", "f8", ("src_grid_size",))
        var.units = "unitless"
        var[:] = 1.0
        var = nc.createVariable("dst_grid_frac", "f8", ("dst_grid_size",))
        var.units = "unitless"
        var[:] = frac
        nc.createVariable("src_address", "i4", ("num_links",))[:] = src + 1
        nc.createVariable("dst_address", "i4", ("num_links",))[:] = dst + 1
        nc.createVariable("remap_matrix", "f8", ("num_links", "num_wgts"))[:] = weight[:, None]
        nc.title = "nctoolkit FVCOM remapping"
        nc.normalization = "none"
        nc.map_method = "Bilinear remapping" if method == "bil" else "Nearest neighbor"
        nc.conventions = "SCRIP"
        nc.source_grid = "unstructured"
        nc.dest_grid = dst_type


def fvcom_weights(ff, target_grid, method, mesh_file):
    """A SCRIP weights file for remapping ff, on an FVCOM grid, to target_grid"""
    if mesh_file is None or not os.path.exists(mesh_file):
        raise ValueError("The FVCOM mesh of this dataset is not available. Please re-open it with open_fvcom")
    mesh = load_mesh(mesh_file)
    src_lon, src_lat = source_points(ff)
    dst_lon, dst_lat, dst_dims, dst_type = target_points(target_grid)
    links = mesh_links(mesh, src_lon, src_lat, dst_lon, dst_lat, method)
    weights_nc = temp_file(".nc")
    write_weights(weights_nc, src_lon, src_lat, dst_lon, dst_lat, dst_dims, dst_type, links, method)
    return weights_nc


# ---------------------------------------------------------------------------
# vertical interpolation
# ---------------------------------------------------------------------------


def sigma_to_z(values, depths, total, levels):
    """
    Linearly interpolate values on sigma layers to fixed depths, as oceanVal does.

    Parameters
    ----------
    values : np.ndarray
        Values on the layers, (time, layer, cell).
    depths : np.ndarray
        Depths of the layer centres below the free surface, (time, layer, cell),
        increasing with the layer.
    total : np.ndarray
        Depth of the water, (time, cell).
    levels : list
        Depths below the free surface to interpolate to. Positive down.

    Returns
    -------
    np.ndarray
        Values at the depths, (time, depth, cell). Depths above the top layer centre
        take the top layer value, depths between the bottom layer centre and the
        seabed take the bottom layer value, and depths below the seabed are NaN.
    """
    levels = np.asarray(levels, dtype="float64")
    n_time, n_layer, n_cell = values.shape
    out = np.full((n_time, len(levels), n_cell), np.nan, dtype="float64")
    for tt in range(n_time):
        layer_depths = np.asarray(depths[tt], dtype="float64")
        vals = np.asarray(values[tt], dtype="float64")
        # layers either side of each level, clamped to the top and bottom layers
        k = (layer_depths[None, :, :] < levels[:, None, None]).sum(axis=1)
        upper = np.clip(k - 1, 0, n_layer - 1)
        lower = np.clip(k, 0, n_layer - 1)
        d_upper = np.take_along_axis(layer_depths, upper, axis=0)
        d_lower = np.take_along_axis(layer_depths, lower, axis=0)
        v_upper = np.take_along_axis(vals, upper, axis=0)
        v_lower = np.take_along_axis(vals, lower, axis=0)
        gap = d_lower - d_upper
        weight = np.zeros_like(gap)
        np.divide(levels[:, None] - d_upper, gap, out=weight, where=(upper != lower) & (gap > 0))
        result = v_upper + weight * (v_lower - v_upper)
        # nothing below the seabed
        with np.errstate(invalid="ignore"):
            result[levels[:, None] > total[tt][None, :]] = np.nan
        out[tt] = result
    return out


def check_levels(levels):
    if isinstance(levels, (int, float)) and not isinstance(levels, bool):
        levels = [levels]
    if not isinstance(levels, (list, tuple)) or len(levels) == 0:
        raise ValueError("Please supply the depths to interpolate to as a list")
    for ll in levels:
        if isinstance(ll, bool) or not isinstance(ll, (int, float, np.integer, np.floating)):
            raise TypeError(f"{ll} is not a valid depth")
        if ll < 0:
            raise ValueError("Depths must be positive, in metres below the surface")
    return [float(x) for x in levels]


def interp_file(ff, thickness, levels, out):
    """
    Interpolate the layered variables of ff, a file with the layer thickness,
    to fixed depths, writing them to out
    """
    with netCDF4.Dataset(ff) as src:
        if thickness not in src.variables:
            raise ValueError(f"{thickness} is not in the dataset")
        th = src.variables[thickness]
        if "time" not in th.dimensions or th.ndim < 3:
            raise ValueError(f"{thickness} must have a time and a vertical dimension")
        t_dim = th.dimensions[0]
        z_dim = th.dimensions[1]
        h_dims = th.dimensions[2:]
        layered = [
            v for v in src.variables
            if v != thickness and src.variables[v].dimensions == th.dimensions
        ]
        if len(layered) == 0:
            raise ValueError("There are no variables on the sigma layers to interpolate")

        n_times = src.dimensions[t_dim].size
        n_cells = int(np.prod([src.dimensions[d].size for d in h_dims]))

        with netCDF4.Dataset(out, "w", format="NETCDF4") as dst:
            dst.createDimension(t_dim, None)
            dst.createDimension("depth", len(levels))
            # the grid: anything without the time or vertical dimensions
            grid_vars = [
                v for v in src.variables
                if t_dim not in src.variables[v].dimensions and z_dim not in src.variables[v].dimensions
            ]
            needed = set(h_dims)
            for v in grid_vars:
                needed.update(src.variables[v].dimensions)
            time_vars = [t_dim] if t_dim in src.variables else []
            if t_dim in src.variables and "bounds" in src.variables[t_dim].ncattrs():
                time_vars.append(src.variables[t_dim].getncattr("bounds"))
            for v in time_vars:
                needed.update(src.variables[v].dimensions)
            for d in sorted(needed):
                if d not in dst.dimensions:
                    dst.createDimension(d, None if src.dimensions[d].isunlimited() else src.dimensions[d].size)

            def copy_var(name):
                var = src.variables[name]
                fill = var.getncattr("_FillValue") if "_FillValue" in var.ncattrs() else None
                new = dst.createVariable(name, var.dtype, var.dimensions, fill_value=fill)
                new.setncatts({k: var.getncattr(k) for k in var.ncattrs() if k != "_FillValue"})
                new[:] = var[:]

            for v in grid_vars + [x for x in time_vars if x in src.variables]:
                copy_var(v)

            depth = dst.createVariable("depth", "f8", ("depth",))
            depth.setncatts(
                {"standard_name": "depth", "long_name": "depth below the sea surface",
                 "units": "m", "positive": "down", "axis": "Z"}
            )
            depth[:] = levels

            outputs = dict()
            for v in layered:
                var = src.variables[v]
                new = dst.createVariable(v, "f4", (t_dim, "depth") + h_dims, fill_value=FILL)
                new.setncatts(
                    {k: var.getncattr(k) for k in var.ncattrs() if k not in ["_FillValue", "missing_value"]}
                )
                new.setncattr("missing_value", np.float32(FILL))
                outputs[v] = new

            n_layers = src.dimensions[z_dim].size
            block = max(1, int(BLOCK_VALUES // (n_cells * n_layers)))
            for start in range(0, n_times, block):
                stop = min(n_times, start + block)
                thick = np.ma.filled(np.ma.masked_invalid(th[start:stop]).astype("float64"), np.nan)
                thick = thick.reshape(stop - start, n_layers, n_cells)
                total = thick.sum(axis=1)
                depths = np.cumsum(thick, axis=1) - thick / 2
                for v in layered:
                    values = src.variables[v][start:stop]
                    values = np.ma.filled(np.ma.masked_invalid(values).astype("float64"), np.nan)
                    values = values.reshape(stop - start, n_layers, n_cells)
                    result = sigma_to_z(values, depths, total, levels)
                    shape = (stop - start, len(levels)) + tuple(src.dimensions[d].size for d in h_dims)
                    result = np.where(np.isfinite(result), result, FILL).reshape(shape)
                    outputs[v][start:stop] = result

            for att in src.ncattrs():
                if att not in ["fvcom_thickness"]:
                    dst.setncattr(att, src.getncattr(att))
    return layered
