"""
nctoolkit's FVCOM grid methods against PyFVCOM, on real FVCOM output (the first
three days of the file). Skipped unless the output and PyFVCOM are available.
Tolerances are for float32 data: 1e-6 relative for operations that are the same
sum, looser where the two legitimately differ (see the comments).
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

import nctoolkit as nc
from pyfvcom_reference import FVCOM, NTIME, Reference, available, compare, import_pyfvcom

nc.options(lazy=True)

pytestmark = pytest.mark.skipif(not available(), reason="FVCOM output is not available")

try:
    import_pyfvcom()
except ImportError:  # pragma: no cover
    pytestmark = pytest.mark.skip(reason="PyFVCOM is not installed")

EXACT = 1e-6
BOX = dict(lon=[-6, -4], lat=[50, 51])
GRID = dict(lon=[-9.8, -2.6], lat=[47.8, 56.9], res=0.05)


@pytest.fixture(scope="module")
def node_ds():
    ds = nc.open_fvcom(FVCOM, ["temp", "zeta"])
    ds.subset(time=range(NTIME))
    ds.run()
    return ds


@pytest.fixture(scope="module")
def elem_ds():
    ds = nc.open_fvcom(FVCOM, "u")
    ds.subset(time=range(NTIME))
    ds.run()
    return ds


@pytest.fixture(scope="module")
def ref():
    return Reference("temp")


@pytest.fixture(scope="module")
def eref():
    return Reference("u", "element")


def values(ds, var):
    ds = ds.copy()
    ds.run()
    return ds.to_xarray()[var].values


def assert_close(got, expected, rel=EXACT):
    abs_diff, rel_diff, only_one = compare(got, expected)
    assert only_one == 0, f"{only_one} cells are missing in only one of them"
    assert rel_diff <= rel, f"max abs difference {abs_diff:.3g}, relative {rel_diff:.3g}"


# the vertical grid -------------------------------------------------------------


def test_layer_thickness(node_ds, ref):
    assert_close(values(node_ds, "layer_thickness"), ref.thickness)


def test_layer_thickness_on_elements(elem_ds, eref):
    assert_close(values(elem_ds, "layer_thickness"), eref.thickness)


def test_vertical_mean(node_ds, ref):
    ds = node_ds.copy()
    ds.vertical_mean()
    assert_close(values(ds, "temp"), ref.vertical_mean())


def test_vertical_mean_on_elements(elem_ds, eref):
    ds = elem_ds.copy()
    ds.vertical_mean()
    assert_close(values(ds, "u"), eref.vertical_mean())


def test_vertical_integration(node_ds, ref):
    ds = node_ds.copy()
    ds.vertical_integration()
    assert_close(values(ds, "temp"), ref.vertical_integration())


def test_depth_range_weights_partial_layers(node_ds, ref):
    ds = node_ds.copy()
    ds.vertical_mean(depth_range=[0, 20])
    assert_close(values(ds, "temp"), ref.vertical_mean(0, 20))
    ds = node_ds.copy()
    ds.vertical_integration(depth_range=[0, 20])
    assert_close(values(ds, "temp"), ref.vertical_integration(0, 20))


def test_top_and_bottom(node_ds, ref):
    ds = node_ds.copy()
    ds.top()
    assert_close(values(ds, "temp"), ref.values[:, 0])
    ds = node_ds.copy()
    ds.bottom()
    assert_close(values(ds, "temp"), ref.values[:, -1])


@pytest.mark.parametrize(
    "method, func",
    [
        ("vertical_min", lambda x: x.min(1)),
        ("vertical_max", lambda x: x.max(1)),
        ("vertical_range", lambda x: np.ptp(x, axis=1)),
        ("vertical_sum", lambda x: x.sum(1)),
        ("vertical_cumsum", lambda x: np.cumsum(x, axis=1)),
    ],
)
def test_unweighted_vertical_statistics(node_ds, ref, method, func):
    # these are across layers, with no thickness weighting
    ds = node_ds.copy()
    getattr(ds, method)()
    assert_close(values(ds, "temp"), func(ref.values))


def test_vertical_interp(node_ds, ref):
    levels = [5, 10, 50]
    ds = node_ds.copy()
    ds.vertical_interp(levels)
    assert_close(values(ds, "temp"), ref.at_depths(levels))


def test_to_zlevels_is_vertical_interp(node_ds):
    a = node_ds.copy()
    a.to_zlevels(levels=[5, 10])
    b = node_ds.copy()
    b.vertical_interp([5, 10])
    assert_close(values(a, "temp"), values(b, "temp"), rel=0)


def test_surface_and_bottom_masks(node_ds):
    for method, layer in [("surface_mask", 0), ("bottom_mask", -1)]:
        ds = node_ds.copy()
        ds.subset(variables="temp", time=0)
        getattr(ds, method)()
        mask = ds.to_xarray().bottom.values.reshape(24, -1)
        assert np.isfinite(mask[layer]).all()
        assert np.isfinite(np.delete(mask, layer, axis=0)).sum() == 0


# the horizontal grid -----------------------------------------------------------


def test_node_areas_are_the_control_volumes(node_ds, ref):
    ds = node_ds.copy()
    ds.cell_area(join=False)
    areas = ds.to_xarray().cell_area.values.ravel()
    # art1 is in projected metres, so is up to 1% larger than on the sphere
    assert 0.99 < (areas / ref.area).min() and (areas / ref.area).max() < 1.0


def test_element_areas_are_the_triangles(elem_ds, eref):
    ds = elem_ds.copy()
    ds.cell_area(join=False)
    ratio = ds.to_xarray().cell_area.values.ravel() / eref.area
    assert 0.99 < ratio.min() and ratio.max() < 1.01


def test_spatial_mean_is_area_weighted(node_ds, ref):
    ds = node_ds.copy()
    ds.top()
    ds.spatial_mean()
    expected = (ref.values[:, 0] * ref.area).sum(-1) / ref.area.sum()
    # areas on the sphere versus projected areas
    assert_close(values(ds, "temp"), expected, rel=2e-4)


def test_spatial_mean_on_elements(elem_ds, eref):
    ds = elem_ds.copy()
    ds.top()
    ds.spatial_mean()
    expected = (eref.values[:, 0] * eref.area).sum(-1) / eref.area.sum()
    assert_close(values(ds, "u"), expected, rel=5e-4)


@pytest.mark.parametrize(
    "method, func",
    [
        ("spatial_max", lambda x, a: x.max(-1)),
        ("spatial_min", lambda x, a: x.min(-1)),
        ("spatial_sum", lambda x, a: x.sum(-1)),
        ("spatial_range", lambda x, a: np.ptp(x, axis=-1)),
    ],
)
def test_spatial_statistics(node_ds, ref, method, func):
    ds = node_ds.copy()
    ds.top()
    getattr(ds, method)()
    assert_close(values(ds, "temp"), func(ref.values[:, 0], ref.area))


def test_spatial_stdev_and_percentile(node_ds, ref):
    x = ref.values[:, 0]
    w = ref.area / ref.area.sum()
    ds = node_ds.copy()
    ds.top()
    ds.spatial_stdev()
    mean = (x * w).sum(-1)
    assert_close(values(ds, "temp"), np.sqrt(((x - mean[:, None]) ** 2 * w).sum(-1)), rel=1e-3)
    ds = node_ds.copy()
    ds.top()
    ds.spatial_percentile(p=50)
    # the median is not area weighted
    assert_close(values(ds, "temp"), np.median(x, axis=-1), rel=1e-4)


def test_centre(node_ds, ref):
    x = ref.values[:, 0]
    ds = node_ds.copy()
    ds.top()
    ds.subset(variables="temp")
    ds.centre("latitude")
    assert_close(values(ds, "temp"), (ref.lat * x).sum(-1) / x.sum(-1), rel=1e-6)
    ds = node_ds.copy()
    ds.top()
    ds.subset(variables="temp")
    ds.centre("longitude", by_area=True)
    w = x * ref.area
    assert_close(values(ds, "temp"), (ref.lon * w).sum(-1) / w.sum(-1), rel=1e-3)


def test_crop_selects_the_nodes_in_the_box(node_ds, ref):
    ds = node_ds.copy()
    ds.top()
    ds.crop(**BOX)
    inside = (ref.lon >= -6) & (ref.lon <= -4) & (ref.lat >= 50) & (ref.lat <= 51)
    got = values(ds, "temp")[0].ravel()
    assert got.size == inside.sum()
    assert_close(np.sort(got), np.sort(ref.values[0, 0][inside]), rel=0)


def test_mask_box_keeps_the_nodes_in_the_box(node_ds, ref):
    ds = node_ds.copy()
    ds.top()
    ds.mask_box(**BOX)
    inside = (ref.lon >= -6) & (ref.lon <= -4) & (ref.lat >= 50) & (ref.lat <= 51)
    got = values(ds, "temp")[0].ravel()
    assert np.array_equal(np.isfinite(got), inside)
    assert_close(got[inside], ref.values[0, 0][inside], rel=0)


# regridding --------------------------------------------------------------------


def regridded(ds, **kwargs):
    ds = ds.copy()
    ds.top()
    ds.subset(variables="temp")
    ds.to_latlon(**GRID, **kwargs)
    x = ds.to_xarray()
    return x.lon.values, x.lat.values, x.temp.values[:, 0] if x.temp.ndim == 4 else x.temp.values


def test_bilinear_regridding_is_linear_in_the_triangles(node_ds, ref):
    lon, lat, got = regridded(node_ds)
    lons, lats = np.meshgrid(lon, lat)
    expected = np.array([ref.bilinear(ref.values[t, 0], lons, lats) for t in range(NTIME)])
    assert_close(got, expected)
    assert np.isfinite(got).sum() > 0.3 * got.size


def test_nearest_neighbour_regridding_takes_the_nearest_node(node_ds, ref):
    lon, lat, got = regridded(node_ds, method="nn")
    lons, lats = np.meshgrid(lon, lat)
    nearest, ratio = ref.nearest(ref.values[0, 0], lons, lats)
    nearest, ratio = nearest.reshape(lons.shape), ratio.reshape(lons.shape)
    found = np.isfinite(got[0])
    # the same domain as bilinear
    assert np.array_equal(found, np.isfinite(ref.bilinear(ref.values[0, 0], lons, lats)))
    differ = found & ~np.isclose(got[0], nearest, atol=1e-6)
    # CDO measures distance slightly differently, so only near ties may differ
    assert differ.sum() <= 0.001 * found.sum()
    assert (ratio[differ] > 0.9).all()


def test_transect(node_ds, ref):
    ds = node_ds.copy()
    ds.top()
    ds.subset(variables="temp")
    ds.to_transect(start=[-6, 50], end=[-4, 51], nsteps=20)
    expected = np.array(
        [
            ref.bilinear(ref.values[t, 0], np.linspace(-6, -4, 20), np.linspace(50, 51, 20))
            for t in range(NTIME)
        ]
    )
    assert_close(ds.to_xarray().temp.values.reshape(NTIME, -1), expected)


def test_match_points(node_ds, ref):
    # points at the centres of triangles in deep water
    triangles = ref.grid.triangles
    deep = np.where(ref.h > 60)[0][::5000][:3]
    which = [np.where((triangles == n).any(1))[0][0] for n in deep]
    lon = ref.lon[triangles[which]].mean(1)
    lat = ref.lat[triangles[which]].mean(1)
    df = pd.DataFrame({"lon": lon, "lat": lat, "year": 2012, "month": 1, "day": [2, 3, 4]})
    got = node_ds.copy().match_points(df.copy(), variables="temp", top=True, quiet=True)
    got = got.sort_values("day")
    expected = [ref.bilinear(ref.values[i, 0], lon[i], lat[i]).item() for i in range(3)]
    assert_close(got.temp.values, expected)

    # with depths, the layer centres are interpolated between
    df["depth"] = [5.0, 20.0, 40.0]
    got = node_ds.copy().match_points(df.copy(), variables="temp", quiet=True).sort_values("day")
    expected = []
    for i in range(3):
        column = [ref.bilinear(ref.values[i, k], lon[i], lat[i]).item() for k in range(24)]
        sigma = [ref.bilinear(ref.siglay[k], lon[i], lat[i]).item() for k in range(24)]
        total = ref.bilinear(ref.h, lon[i], lat[i]).item() + ref.bilinear(ref.zeta[i], lon[i], lat[i]).item()
        expected.append(np.interp(df.depth[i], -np.array(sigma) * total, column))
    # nctoolkit regrids the layer thickness rather than sigma, so these are close not equal
    assert_close(got.temp.values, expected, rel=1e-4)


# what is refused ---------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.zonal_mean(),
        lambda d: d.zonal_max(),
        lambda d: d.meridonial_mean(),
        lambda d: d.box_mean(),
        lambda d: d.resample_grid(1),
        lambda d: d.distribute(2, 2),
        lambda d: d.invert("latitudes"),
        lambda d: d.strip_variables(),
        lambda d: d.set_gridtype("lonlat"),
        lambda d: d.generate_level_bounds(),
        lambda d: d.fix_amm7_grid(),
        lambda d: d.fix_nemo_ersem_grid(),
        lambda d: d.crop(**BOX, nco=True),
        lambda d: d.vertical_interp([5], fixed=True),
    ],
)
def test_methods_that_need_a_regular_grid_are_refused(node_ds, call):
    with pytest.raises((TypeError, ValueError), match="FVCOM|sigma"):
        call(node_ds.copy())
