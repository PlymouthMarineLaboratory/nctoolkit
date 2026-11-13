"""
Synthetic FVCOM output for the tests, copied from oceanVal's tests
(tests/viewer_simulations.py and tests/test_fvcom.py).

The mesh is 0.1 degree squares over 5-4W, 50-51N, each split into two
triangles, with the north-east corner (east of 4.45W, north of 50.55N) cut out.
"""

import datetime

import netCDF4
import numpy as np

# 2012-01-01 in FVCOM's modified julian days
MJD_2012 = 55927


def fvcom_mesh():
    """The nodes' lon, lat and nv (three, nele), 1-based, as FVCOM writes it"""
    lons = np.round(np.arange(-5.0, -3.95, 0.1), 6)
    lats = np.round(np.arange(50.0, 51.05, 0.1), 6)
    glon, glat = np.meshgrid(lons, lats)
    keep = ~((glon > -4.45) & (glat > 50.55))
    index = np.full(glon.shape, -1)
    index[keep] = np.arange(keep.sum())
    triangles = []
    for j in range(len(lats) - 1):
        for i in range(len(lons) - 1):
            a, b = index[j, i], index[j, i + 1]
            c, d = index[j + 1, i], index[j + 1, i + 1]
            if min(a, b, c, d) >= 0:
                triangles += [[a, b, d], [a, d, c]]
    return glon[keep], glat[keep], np.array(triangles).T + 1


def inside_mesh(lon, lat):
    """Is each point inside the mesh? Points on its edges count as inside"""
    lon, lat = np.asarray(lon), np.asarray(lat)
    box = (lon >= -5 - 1e-9) & (lon <= -4 + 1e-9) & (lat >= 50 - 1e-9) & (lat <= 51 + 1e-9)
    corner = (lon > -4.5 + 1e-9) & (lat > 50.5 + 1e-9)
    return box & ~corner


def triangle_areas(lon, lat, nv):
    """
    Areas of the triangles in m^2, on a sphere of radius 6371 km, as oceanVal's
    mesh_means.triangle_areas works them out
    """
    def unit(x, y):
        x, y = np.radians(x), np.radians(y)
        return np.stack([np.cos(y) * np.cos(x), np.cos(y) * np.sin(x), np.sin(y)], axis=-1)

    a, b, c = (unit(lon[nv[k] - 1], lat[nv[k] - 1]) for k in range(3))
    triple = np.abs(np.einsum("ij,ij->i", a, np.cross(b, c)))
    below = 1 + np.einsum("ij,ij->i", a, b) + np.einsum("ij,ij->i", b, c) + np.einsum("ij,ij->i", c, a)
    return 2 * np.arctan2(triple, below) * 6_371_000.0**2


def node_areas(lon, lat, nv):
    """Each node's control volume: a third of each triangle it is a corner of"""
    areas = triangle_areas(lon, lat, nv)
    out = np.zeros(len(lon))
    for k in range(3):
        np.add.at(out, nv[k] - 1, areas / 3)
    return out


def fvcom_file(path, first_day=0, n_times=3, siglev=None, zeta=0.5, missing=None):
    """
    An FVCOM file of the mesh above, written as FVCOM writes them (with
    netCDF4, as xarray will not write a 2-D variable named after one of its
    dimensions):

    * temp on the nodes (5 sigma layers) equal to 10 + lon + the layer + the day
    * salinity on the nodes equal to 30 + 0.02 * depth of the layer centre + 0.1 * the day
    * zeta on the nodes, a float or one value per time
    * u on the elements equal to the element's number
    * h = 20 + 200 * (lon + 5), siglev (6, node), siglay, times as FVCOM writes them

    siglev: the 6 sigma levels, 0 at the surface to -1 at the seabed. Even by default.
    missing: a function given temp (time, siglay, node) that masks some of it
    """
    lon, lat, nv = fvcom_mesh()
    n_node, n_nele = len(lon), nv.shape[1]
    days = first_day + np.arange(n_times)
    if siglev is None:
        siglev = -np.arange(6) / 5
    siglev = np.asarray(siglev, dtype="float64")
    siglay = 0.5 * (siglev[:-1] + siglev[1:])
    siglev = np.repeat(siglev[:, None], n_node, axis=1)
    siglay = np.repeat(siglay[:, None], n_node, axis=1)
    h = 20 + 200 * (lon + 5)
    zeta = np.broadcast_to(np.asarray(zeta, dtype="float64").reshape(-1, 1), (n_times, n_node))
    temp = 10 + lon[None, None, :] + np.arange(5)[None, :, None] + days[:, None, None]
    temp = np.ma.masked_array(temp)
    if missing is not None:
        temp = missing(temp)
    depth = -siglay[None, :, :] * (h[None, None, :] + zeta[:, None, :])
    salinity = 30 + 0.02 * depth + 0.1 * days[:, None, None]
    lonc, latc = lon[nv - 1].mean(axis=0), lat[nv - 1].mean(axis=0)
    with netCDF4.Dataset(path, "w") as ds:
        for name, size in (("node", n_node), ("nele", n_nele), ("three", 3), ("siglay", 5), ("siglev", 6), ("time", None)):
            ds.createDimension(name, size)

        def add(name, dims, values, dtype="f4", **attrs):
            fill = attrs.pop("_FillValue", None)
            variable = ds.createVariable(name, dtype, dims, fill_value=fill)
            variable[:] = values
            variable.setncatts(attrs)

        add("x", ("node",), (lon + 5) * 70000, units="meters", long_name="nodal x-coordinate")
        add("y", ("node",), (lat - 50) * 111000, units="meters", long_name="nodal y-coordinate")
        add("lon", ("node",), lon, units="degrees_east", long_name="nodal longitude")
        add("lat", ("node",), lat, units="degrees_north", long_name="nodal latitude")
        add("lonc", ("nele",), lonc, units="degrees_east", long_name="zonal longitude")
        add("latc", ("nele",), latc, units="degrees_north", long_name="zonal latitude")
        add("nv", ("three", "nele"), nv, dtype="i4", long_name="nodes surrounding element")
        add("siglay", ("siglay", "node"), siglay, long_name="Sigma Layers", positive="up")
        add("siglev", ("siglev", "node"), siglev, long_name="Sigma Levels", positive="up")
        add("h", ("node",), h, units="m", long_name="Bathymetry")
        add("time", ("time",), MJD_2012 + days, units="days since 1858-11-17 00:00:00", format="modified julian day (MJD)")
        add("Itime", ("time",), MJD_2012 + days, dtype="i4", units="days since 1858-11-17 00:00:00")
        # FVCOM's integer time has units xarray cannot decode
        add("Itime2", ("time",), np.zeros(n_times), dtype="i4", units="msec since 00:00:00")
        add("zeta", ("time", "node"), zeta, units="meters", long_name="Water Surface Elevation")
        add("temp", ("time", "siglay", "node"), temp, units="degrees_C", long_name="temperature",
            coordinates="time siglay lat lon", _FillValue=-2e20)
        add("salinity", ("time", "siglay", "node"), salinity, units="1e-3", long_name="salinity")
        add("u", ("time", "siglay", "nele"), np.broadcast_to(np.arange(n_nele, dtype="f4"), (n_times, 5, n_nele)),
            units="meters s-1", long_name="Eastward Water Velocity")
        add("km", ("time", "siglev", "node"), np.ones((n_times, 6, n_node)), units="m 2 s-1",
            long_name="Turbulent Eddy Viscosity For Momentum")
    return path
