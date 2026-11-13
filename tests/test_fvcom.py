"""
FVCOM support: the horizontal mesh and the vertical sigma layers.

The synthetic FVCOM files, and most of the expected values, come from
oceanVal's FVCOM tests (tests/test_fvcom.py and tests/test_fvcom_analysis.py).
"""

import warnings

import numpy as np
import pandas as pd
import pytest

import nctoolkit as nc
from nctoolkit.fvcom import sigma_to_z

from fvcom_helpers import fvcom_file, fvcom_mesh, inside_mesh, node_areas, triangle_areas

nc.options(lazy=True)


@pytest.fixture(scope="module")
def fvcom_path(tmp_path_factory):
    return fvcom_file(str(tmp_path_factory.mktemp("fvcom") / "fvcom_0001.nc"))


@pytest.fixture
def nodes(fvcom_path):
    return nc.open_fvcom(fvcom_path, ["temp", "salinity", "zeta"])


def values(ds, var):
    return ds.to_xarray()[var].values


# ---------------------------------------------------------------------------
# opening
# ---------------------------------------------------------------------------


class TestOpen:
    def test_the_mesh_is_an_unstructured_grid_with_cells(self, nodes):
        assert nodes.fvcom is True and nodes.fvcom_thickness == "layer_thickness"
        lon, lat, nv = fvcom_mesh()
        x = nodes.to_xarray()
        assert x.temp.dims == ("time", "siglay", "node") and x.sizes["node"] == len(lon)
        # the layers are numbered from the surface, and zeta is on the surface
        assert nodes.levels == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        # the values are on the nodes, in the order of the file
        assert np.allclose(x.lon.values, lon) and np.allclose(x.lat.values, lat)
        assert np.allclose(x.temp.values[0, 0], 10 + lon)

    def test_all_node_variables_are_opened_by_default(self, fvcom_path):
        with pytest.warns(UserWarning, match="u, km"):
            ds = nc.open_fvcom(fvcom_path)
        assert set(ds.variables) >= {"temp", "salinity", "zeta", "h", "layer_thickness"}
        assert "u" not in ds.variables and "km" not in ds.variables

    def test_element_variables_can_be_supplied(self, fvcom_path):
        ds = nc.open_fvcom(fvcom_path, ["u"])
        assert "u" in ds.variables

    def test_nodes_and_elements_cannot_be_mixed(self, fvcom_path):
        with pytest.raises(ValueError, match="nodes and elements"):
            nc.open_fvcom(fvcom_path, ["temp", "u"])
        with pytest.raises(ValueError, match="siglay.*siglev"):
            nc.open_fvcom(fvcom_path, ["temp", "km"])

    def test_the_thickness_changes_with_zeta(self, tmp_path):
        levels = np.array([0.0, -0.1, -0.3, -0.6, -0.8, -1.0])
        path = fvcom_file(str(tmp_path / "uneven.nc"), siglev=levels, zeta=[0.0, 1.0, 5.0])
        ds = nc.open_fvcom(path, "temp")
        lon, _, _ = fvcom_mesh()
        h = 20 + 200 * (lon + 5)
        expected = -np.diff(levels)[None, :, None] * (h[None, None, :] + np.array([0.0, 1.0, 5.0])[:, None, None])
        assert np.allclose(values(ds, "layer_thickness"), expected, rtol=1e-6)


# ---------------------------------------------------------------------------
# the horizontal mesh
# ---------------------------------------------------------------------------


class TestAreas:
    def test_the_cells_of_the_nodes_are_their_control_volumes(self, nodes):
        # oceanVal: the control volumes of the nodes cover the mesh, as FVCOM's art1 does
        lon, lat, nv = fvcom_mesh()
        nodes.cell_area(join=False)
        areas = values(nodes, "cell_area").ravel()
        assert np.isclose(areas.sum(), triangle_areas(lon, lat, nv).sum(), rtol=1e-4)
        assert np.allclose(areas, node_areas(lon, lat, nv), rtol=1e-3)
        # a node on the edge of the mesh has less of it than one inside
        assert areas.min() < 0.5 * areas.max()

    def test_the_cells_of_the_elements_are_their_triangles(self, fvcom_path):
        lon, lat, nv = fvcom_mesh()
        ds = nc.open_fvcom(fvcom_path, "u")
        ds.cell_area(join=False)
        assert np.allclose(values(ds, "cell_area").ravel(), triangle_areas(lon, lat, nv), rtol=1e-4)

    def test_the_spatial_mean_is_weighted_by_area(self, nodes):
        # oceanVal TestSpatialMeans: the mean of lon over the domain, and a box
        lon, lat, nv = fvcom_mesh()
        weights = node_areas(lon, lat, nv)
        nodes.subset(variables="temp", time=0)
        nodes.top()
        whole = nodes.copy()
        whole.spatial_mean()
        value = values(whole, "temp").ravel()[0] - 10
        assert np.isclose(value, (weights * lon).sum() / weights.sum(), atol=1e-3)
        # not the plain mean
        assert not np.isclose(value, lon.mean(), atol=2e-3)
        nodes.crop(lon=[-5.0, -4.65], lat=[50.0, 51.0])
        nodes.spatial_mean()
        west = lon < -4.65
        expected = (weights * lon)[west].sum() / weights[west].sum()
        assert np.isclose(values(nodes, "temp").ravel()[0] - 10, expected, atol=1e-3)


class TestRegrid:
    def test_bilinear_is_linear_within_the_triangles(self, nodes):
        # oceanVal TestWeights: a linear field is interpolated exactly, and
        # nothing outside the mesh (oceanVal test_mesh_mask)
        nodes.subset(variables=["temp", "layer_thickness"], time=0)
        nodes.top()
        nodes.to_latlon(lon=[-5.2, -3.8], lat=[49.8, 51.2], res=0.05)
        # no longer on the mesh, but the layer thickness is still known
        assert nodes.fvcom is False and nodes.fvcom_thickness == "layer_thickness"
        x = nodes.to_xarray()
        field = x.temp.values.squeeze()
        glon, glat = np.meshgrid(x.lon.values, x.lat.values)
        inside = inside_mesh(glon, glat)
        assert np.isfinite(field[inside]).all() and np.isnan(field[~inside]).all()
        assert np.allclose(field[inside], 10 + glon[inside], atol=1e-5)

    def test_nearest_neighbour(self, nodes):
        nodes.subset(variables="temp", time=0)
        nodes.top()
        nodes.regrid(pd.DataFrame({"lon": [-4.93, -4.5, -4.2], "lat": [50.07, 50.3, 50.8]}), method="nn")
        x = nodes.to_dataframe().reset_index().sort_values("lon")
        assert np.allclose(x.temp.values[:2], 10 + np.array([-4.9, -4.5]), atol=1e-5)
        # the cut-out corner
        assert np.isnan(x.temp.values[2])

    def test_values_on_the_elements_fill_their_triangles(self, fvcom_path):
        # oceanVal TestWeights: u is each element's number
        lon, lat, nv = fvcom_mesh()
        points = pd.DataFrame({"lon": [-4.93, -4.47, -3.5], "lat": [50.02, 50.31, 50.5]})
        ds = nc.open_fvcom(fvcom_path, "u")
        ds.subset(time=0)
        ds.top()
        ds.regrid(points, method="nn")
        found = ds.to_dataframe().reset_index().set_index("lon").loc[points.lon].u.values
        from matplotlib.tri import Triangulation

        expected = Triangulation(lon, lat, nv.T - 1).get_trifinder()(points.lon.values, points.lat.values)
        assert found[:2].tolist() == expected[:2].tolist() and np.isnan(found[2])
        # bilinear gives values within the elements round each point
        ds = nc.open_fvcom(fvcom_path, "u")
        ds.subset(time=0)
        ds.top()
        ds.regrid(points, method="bil")
        found = ds.to_dataframe().reset_index().set_index("lon").loc[points.lon].u.values
        assert np.isfinite(found[:2]).all() and np.isnan(found[2])

    def test_a_missing_corner_leaves_out_its_triangles(self, tmp_path):
        # oceanVal TestWeights: CDO would otherwise work out its own weights
        def gap(temp):
            lon, lat, _ = fvcom_mesh()
            temp[:, :, np.isclose(lon, -4.5) & np.isclose(lat, 50.3)] = np.ma.masked
            return temp

        ds = nc.open_fvcom(fvcom_file(str(tmp_path / "gap.nc"), missing=gap), "temp")
        ds.subset(variables="temp", time=0)
        ds.top()
        ds.regrid(pd.DataFrame({"lon": [-4.48, -4.75], "lat": [50.31, 50.25]}))
        x = ds.to_dataframe().reset_index().sort_values("lon")
        assert np.isclose(x.temp.values[0], 10 - 4.75, atol=1e-5)
        assert np.isnan(x.temp.values[1])

    def test_a_cropped_mesh_can_be_regridded(self, nodes):
        nodes.subset(variables="temp", time=0)
        nodes.top()
        nodes.crop(lon=[-5.0, -4.5], lat=[50.0, 50.5])
        nodes.to_latlon(lon=[-5.0, -4.5], lat=[50.0, 50.5], res=0.05)
        x = nodes.to_xarray()
        glon = np.meshgrid(x.lon.values, x.lat.values)[0]
        assert np.allclose(x.temp.values.squeeze(), 10 + glon, atol=1e-5)

    def test_a_transect(self, nodes):
        # oceanVal TestTransects: an east-west line that runs off the mesh
        nodes.subset(variables="temp", time=0)
        nodes.top()
        nodes.to_transect(start=[-5.2, 50.75], end=[-3.8, 50.75], nsteps=15)
        x = nodes.to_dataframe().reset_index().sort_values("lon")
        inside = inside_mesh(x.lon.values, x.lat.values)
        assert np.allclose(x.temp.values[inside], 10 + x.lon.values[inside], atol=1e-5)
        assert np.isnan(x.temp.values[~inside]).all()

    def test_matching_points(self, nodes):
        # the top layer centre is 10% of the water column down, and temp is linear
        # between the layer centres
        df = pd.DataFrame(
            {"lon": [-4.95, -4.5, -4.2], "lat": [50.05, 50.5, 50.8], "year": 2012, "month": 1,
             "day": 2, "depth": [5.0, 10.0, 50.0]}
        )
        nodes.subset(variables=["temp", "layer_thickness"])
        out = nodes.match_points(df, variables="temp", quiet=True).sort_values("lon")
        h = 20 + 200 * (-4.95 + 5) + 0.5
        centres = (np.arange(5) + 0.5) / 5 * h
        expected = np.interp(5.0, centres, 10 - 4.95 + 1 + np.arange(5))
        assert np.isclose(out.temp.values[0], expected, atol=1e-4)
        assert np.isclose(out.temp.values[1], 10 - 4.5 + 1, atol=1e-4)
        assert np.isnan(out.temp.values[2])

    @pytest.mark.parametrize(
        "method",
        ["zonal_mean", "meridonial_mean", "box_mean", "resample_grid", "distribute", "strip_variables"],
    )
    def test_what_needs_a_regular_grid_is_refused(self, nodes, method):
        args = {"resample_grid": [2], "distribute": [2, 2]}.get(method, [])
        with pytest.raises(TypeError, match="does not work with FVCOM data"):
            getattr(nodes, method)(*args)


# ---------------------------------------------------------------------------
# the vertical sigma layers
# ---------------------------------------------------------------------------


class TestWaterColumn:
    """temp is 10 + lon + the layer + the day, on five even layers, h is
    20 + 200 (lon + 5) and zeta 0.5 (oceanVal TestBottomAndWaterColumn)"""

    def test_top_bottom_mean_and_integral(self, nodes):
        lon, _, _ = fvcom_mesh()
        h = 20 + 200 * (lon + 5)
        surface = 10 + lon[None, :] + np.arange(3)[:, None]
        for method, expected in [
            ("top", surface),
            ("bottom", surface + 4),
            ("vertical_mean", surface + 2),
            ("vertical_integration", (surface + 2) * (h + 0.5)),
        ]:
            ds = nodes.copy()
            getattr(ds, method)()
            assert np.allclose(values(ds, "temp").reshape(3, -1), expected, rtol=1e-5), method
        # thickness and fixed are not needed, and the thickness is used up
        nodes.vertical_mean()
        assert nodes.variables == ["salinity", "temp"] and nodes.fvcom_thickness is None

    def test_each_layer_is_weighted_by_its_thickness_at_each_time(self, tmp_path):
        levels = np.array([0.0, -0.1, -0.3, -0.6, -0.8, -1.0])
        zeta = np.array([0.0, 1.0, 5.0])
        path = fvcom_file(str(tmp_path / "uneven.nc"), siglev=levels, zeta=zeta)
        lon, _, _ = fvcom_mesh()
        h = 20 + 200 * (lon + 5)
        temp = 10 + lon[None, None, :] + np.arange(5)[None, :, None] + np.arange(3)[:, None, None]
        shares = -np.diff(levels)
        thickness = shares[None, :, None] * (h[None, None, :] + zeta[:, None, None])
        ds = nc.open_fvcom(path, "temp")
        ds.vertical_mean()
        assert np.allclose(values(ds, "temp").squeeze(), (temp * shares[None, :, None]).sum(axis=1), rtol=1e-6)
        # not the even split
        assert not np.allclose(values(ds, "temp").squeeze(), temp.mean(axis=1))
        ds = nc.open_fvcom(path, "temp")
        ds.vertical_integration()
        assert np.allclose(values(ds, "temp").squeeze(), (temp * thickness).sum(axis=1), rtol=1e-5)

    def test_what_is_missing_is_left_out(self, tmp_path):
        def gaps(temp):
            temp[:, 0, 0] = np.ma.masked  # the top layer of node 0
            temp[:, :, 1] = np.ma.masked  # every layer of node 1
            return temp

        ds = nc.open_fvcom(fvcom_file(str(tmp_path / "gaps.nc"), missing=gaps), "temp")
        ds.subset(time=0)
        lon, _, _ = fvcom_mesh()
        h = 20 + 200 * (lon + 5)
        mean = ds.copy()
        mean.vertical_mean()
        integral = ds.copy()
        integral.vertical_integration()
        mean, integral = values(mean, "temp").ravel(), values(integral, "temp").ravel()
        # node 0: the four layers below the top, each a fifth of the depth
        assert np.isclose(mean[0], 10 + lon[0] + 2.5, rtol=1e-5)
        assert np.isclose(integral[0], (10 + lon[0] + 2.5) * 0.8 * (h[0] + 0.5), rtol=1e-5)
        assert np.isnan(mean[1]) and np.isnan(integral[1])
        assert np.isclose(mean[2], 10 + lon[2] + 2, rtol=1e-5)

    def test_values_on_the_elements(self, fvcom_path):
        ds = nc.open_fvcom(fvcom_path, "u")
        ds.vertical_mean()
        assert np.allclose(values(ds, "u")[0].ravel(), np.arange(len(fvcom_mesh()[2][0])))

    def test_each_file_has_its_own_thickness(self, tmp_path):
        paths = [
            fvcom_file(str(tmp_path / "a.nc"), zeta=0.0),
            fvcom_file(str(tmp_path / "b.nc"), first_day=3, zeta=10.0),
        ]
        ds = nc.open_fvcom(paths, "temp")
        assert len(ds) == 2
        ds.vertical_integration()
        lon, _, _ = fvcom_mesh()
        h = 20 + 200 * (lon + 5)
        x = ds.to_xarray().temp.values
        assert np.allclose(x[0], (10 + lon + 2) * h, rtol=1e-5)
        assert np.allclose(x[3], (10 + lon + 5) * (h + 10), rtol=1e-5)

    def test_after_regridding(self, nodes):
        nodes.subset(time=0)
        nodes.to_latlon(lon=[-5, -4.6], lat=[50, 50.4], res=0.1)
        nodes.vertical_mean()
        x = nodes.to_xarray()
        glon = np.meshgrid(x.lon.values, x.lat.values)[0]
        assert np.allclose(x.temp.values.squeeze(), 10 + glon + 2, atol=1e-4)


class TestDepths:
    """oceanVal's tests of _sigma_to_z"""

    @staticmethod
    def interpolate(values, siglay, h, zeta, levels):
        total = h[None, :] + zeta
        depths = -siglay[None, :, :] * total[:, None, :]
        return sigma_to_z(values, depths, total, levels)

    @staticmethod
    def uniform_siglay(n_layer, n_node):
        centres = -(np.arange(n_layer) + 0.5) / n_layer
        return np.repeat(centres[:, None], n_node, axis=1)

    def test_linear_profile_is_reproduced(self):
        siglay = self.uniform_siglay(10, 3)
        h = np.array([20.0, 50.0, 100.0])
        values = (-siglay * h)[None, :, :]
        levels = [5, 10, 17.5]
        out = self.interpolate(values, siglay, h, np.zeros((1, 3)), levels)
        assert np.allclose(out[0], np.repeat(np.array(levels)[:, None], 3, axis=1), rtol=1e-6)

    def test_top_bottom_and_below_seabed(self):
        # layer centres are at 5, 15, 25, 35 m
        values = np.array([[[1.0], [2.0], [3.0], [4.0]]])
        out = self.interpolate(values, self.uniform_siglay(4, 1), np.array([40.0]), np.zeros((1, 1)), [0, 2, 38, 40, 45])
        assert np.allclose(out[0, :4, 0], [1.0, 1.0, 4.0, 4.0]) and np.isnan(out[0, 4, 0])
        out = self.interpolate(values, self.uniform_siglay(4, 1), np.array([40.0]), np.zeros((1, 1)), [5, 15, 20, 35])
        assert np.allclose(out[0, :, 0], [1.0, 2.0, 2.5, 4.0])

    def test_non_uniform_sigma_and_free_surface(self):
        siglay = np.array([[-0.1, -0.25], [-0.5, -0.5], [-0.9, -0.75]])
        h = np.array([10.0, 20.0])
        zeta = np.array([[0.0, 0.0], [2.0, -4.0]])
        values = np.array([[[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]], [[4.0, 40.0], [5.0, 50.0], [6.0, 60.0]]])
        levels = [3, 11, 17]
        out = self.interpolate(values, siglay, h, zeta, levels)
        for tt in range(2):
            total = h + zeta[tt]
            for nn in range(2):
                expected = np.interp(levels, -siglay[:, nn] * total[nn], values[tt, :, nn])
                expected[np.array(levels) > total[nn]] = np.nan
                np.testing.assert_allclose(out[tt, :, nn], expected, rtol=1e-6)
        # node 0 is 10 m deep at t=0 and 12 m deep at t=1, so 11 m is only wet at t=1
        assert np.isnan(out[0, 1, 0]) and np.isfinite(out[1, 1, 0])

    def test_nan_values_propagate(self):
        values = np.array([[[1.0], [np.nan], [3.0]]])
        out = self.interpolate(values, self.uniform_siglay(3, 1), np.array([30.0]), np.zeros((1, 1)), [0, 12, 28])
        assert out[0, 0, 0] == 1.0 and np.isnan(out[0, 1, 0]) and out[0, 2, 0] == 3.0

    def test_vertical_interp(self, nodes):
        # salinity is 30 + 0.02 * depth + 0.1 * day, with depths limited to the layer centres
        lon, _, _ = fvcom_mesh()
        total = 20 + 200 * (lon + 5) + 0.5
        levels = [0, 5, 50, 500]
        nodes.vertical_interp(levels)
        x = nodes.to_xarray()
        assert x.salinity.dims == ("time", "depth", "node") and list(x.depth.values) == levels
        depth = np.clip(np.array(levels, dtype=float)[:, None], 0.1 * total, 0.9 * total)
        expected = 30 + 0.02 * depth[None] + 0.1 * np.arange(3)[:, None, None]
        expected[:, np.array(levels)[:, None].repeat(len(lon), axis=1) > total[None, :]] = np.nan
        assert np.allclose(x.salinity.values, expected, atol=1e-4, equal_nan=True)
        with pytest.raises(ValueError, match="positive"):
            nodes.copy().vertical_interp([-5])
