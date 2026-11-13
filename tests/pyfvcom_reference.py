"""
Reference calculations from PyFVCOM, used to check nctoolkit's FVCOM support.

PyFVCOM is used for everything it provides: reading the file (FileReader), the
depths of the sigma layers and levels (unstructured_grid_depths), element areas
(calculate_areas), FVCOM's own control volume areas (grid.art1) and node to
element averaging (nodes2elems). Where PyFVCOM has no function for what nctoolkit does
(thickness weighting, interpolation to fixed depths, regridding to lon/lat), the
reference is plain numpy/matplotlib applied to PyFVCOM's grid and depths.

PyFVCOM 2.2.0 does not import on current scipy/matplotlib, so the two removed names
it needs are put back before importing it.
"""

import os
import sys
import warnings

import numpy as np

FVCOM = (
    "/data/thaumus2/scratch/maz/Models/FVCOM/run/aqua_v16_trawl/output/aqua_v16_trawl/"
    "tide_wind_nest_ersem/2012_2014_val/aqua_v16_trawl_avg_0001_2012_01.nc"
)
NTIME = 3  # number of days compared; keeps everything quick


def _compat():
    import matplotlib.tri as mtri
    import scipy

    sys.modules.setdefault("matplotlib.tri.triangulation", mtri)
    sys.modules.setdefault("matplotlib.tri.tricontour", mtri)
    for name in ("polyfit", "polyval"):
        if not hasattr(scipy, name):
            setattr(scipy, name, getattr(np, name))


def import_pyfvcom():
    """Import PyFVCOM, raising ImportError if it is not installed"""
    _compat()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import PyFVCOM
        from PyFVCOM import grid, read

    return PyFVCOM, grid, read


class Reference:
    """PyFVCOM's view of the first NTIME days of the file, on the nodes or the elements"""

    def __init__(self, variable, location="node", path=FVCOM, ntime=NTIME):
        _, grid, read = import_pyfvcom()
        self.location = location
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.reader = read.FileReader(
                path, variables=[variable, "zeta"], dims={"time": slice(0, ntime)}
            )
        g = self.grid = self.reader.grid
        self.values = np.asarray(getattr(self.reader.data, variable), dtype="f8")
        zeta = np.asarray(self.reader.data.zeta, dtype="f8")
        if location == "node":
            self.lon, self.lat = g.lon.astype("f8"), g.lat.astype("f8")
            self.h, self.siglev = g.h.astype("f8"), g.siglev.astype("f8")
            self.siglay = g.siglay.astype("f8")
            self.zeta = zeta
            # FVCOM's own control volume areas
            self.area = g.art1.astype("f8")
        else:
            self.lon, self.lat = g.lonc.astype("f8"), g.latc.astype("f8")
            self.h, self.siglev = g.h_center.astype("f8"), g.siglev_center.astype("f8")
            self.siglay = g.siglay_center.astype("f8")
            self.zeta = grid.nodes2elems(zeta, g.triangles)
            self.reader.calculate_areas()
            self.area = self.reader.grid.areas.astype("f8")
        # depth of each level below the surface, and the thickness of each layer
        levels = grid.unstructured_grid_depths(self.h, self.zeta.copy(), self.siglev)
        self.level_depth = self.zeta[:, None, :] - levels
        self.thickness = np.abs(np.diff(levels, axis=1))
        # depth of the layer centres below the surface
        self.centre_depth = (self.level_depth[:, :-1] + self.level_depth[:, 1:]) / 2
        self.total = self.h + self.zeta

    # vertical -------------------------------------------------------------

    def vertical_mean(self, lo=None, hi=None):
        w = self.overlap(lo, hi)
        with np.errstate(invalid="ignore", divide="ignore"):
            return (self.values * w).sum(1) / np.where(w.sum(1) > 0, w.sum(1), np.nan)

    def vertical_integration(self, lo=None, hi=None):
        return (self.values * self.overlap(lo, hi)).sum(1)

    def overlap(self, lo=None, hi=None):
        """Thickness of each layer that is between depths lo and hi below the surface"""
        if lo is None:
            return self.thickness
        top, bottom = self.level_depth[:, :-1], self.level_depth[:, 1:]
        return np.clip(np.minimum(bottom, hi) - np.maximum(top, lo), 0, None)

    def at_depths(self, depths):
        """Linear interpolation between layer centres. Above the top centre and below the
        bottom centre the nearest layer's value is used, and below the seabed it is missing"""
        out = np.full((self.values.shape[0], len(depths), self.values.shape[2]), np.nan)
        for t in range(self.values.shape[0]):
            for j in range(self.values.shape[2]):
                for k, depth in enumerate(depths):
                    if depth <= self.total[t, j]:
                        out[t, k, j] = np.interp(
                            depth, self.centre_depth[t, :, j], self.values[t, :, j]
                        )
        return out

    # horizontal -----------------------------------------------------------

    def triangulation(self):
        import matplotlib.tri as mtri

        return mtri.Triangulation(self.lon, self.lat, self.grid.triangles)

    def bilinear(self, field, lon, lat):
        """Linear interpolation of a node field within the mesh's triangles"""
        import matplotlib.tri as mtri

        return mtri.LinearTriInterpolator(self.triangulation(), field)(lon, lat).filled(np.nan)

    def nearest(self, field, lon, lat):
        """The value at the nearest node (great circle distance) of a field"""
        from scipy.spatial import cKDTree

        def xyz(lo, la):
            lo, la = np.radians(np.ravel(lo)), np.radians(np.ravel(la))
            return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]

        dist, idx = cKDTree(xyz(self.lon, self.lat)).query(xyz(lon, lat), k=2)
        return field[idx[:, 0]].reshape(np.shape(lon)), (dist[:, 0] / dist[:, 1]).reshape(np.shape(lon))


def compare(got, expected):
    """(max absolute difference, max relative difference, number of cells where only one is missing)"""
    got = np.asarray(got, dtype="f8")
    expected = np.asarray(expected, dtype="f8").reshape(np.shape(expected))
    got = got.reshape(expected.shape)
    both = np.isfinite(got) & np.isfinite(expected)
    only_one = int((np.isfinite(got) != np.isfinite(expected)).sum())
    if not both.any():
        return np.nan, np.nan, only_one
    diff = np.abs(got - expected)[both]
    scale = np.abs(expected[both]).max() or 1.0
    return float(diff.max()), float(diff.max() / scale), only_one


def available():
    return os.path.exists(FVCOM)
