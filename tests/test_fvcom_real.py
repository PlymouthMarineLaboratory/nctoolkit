"""
FVCOM support on a real mesh: clockwise triangles, sigma layers that vary
between nodes, and FVCOM's own control volume areas (art1). Skipped unless the
FVCOM output is available.
"""

import os

import netCDF4
import numpy as np
import pytest

import nctoolkit as nc

nc.options(lazy=True)

FVCOM = (
    "/data/thaumus2/scratch/maz/Models/FVCOM/run/aqua_v16_trawl/output/aqua_v16_trawl/"
    "tide_wind_nest_ersem/2012_2014_val/aqua_v16_trawl_avg_0001_2012_01.nc"
)

pytestmark = pytest.mark.skipif(not os.path.exists(FVCOM), reason="FVCOM output is not available")


@pytest.fixture(scope="module")
def raw():
    with netCDF4.Dataset(FVCOM) as src:
        siglev = src["siglev"][:].astype("f8")
        h = src["h"][:].astype("f8")
        zeta = src["zeta"][0].astype("f8")
        return {
            "temp": src["temp"][0].astype("f8"),
            "art1": src["art1"][:].astype("f8"),
            "thickness": (siglev[:-1] - siglev[1:]) * (h + zeta)[None, :],
        }


@pytest.fixture(scope="module")
def first_day():
    ds = nc.open_fvcom(FVCOM, "temp")
    ds.subset(time=0)
    ds.run()
    return ds


def test_the_water_column(first_day, raw):
    ds = first_day.copy()
    ds.vertical_mean()
    expected = (raw["temp"] * raw["thickness"]).sum(axis=0) / raw["thickness"].sum(axis=0)
    assert np.allclose(ds.to_xarray().temp.values.squeeze(), expected, atol=1e-4)


def test_the_areas_are_fvcom_s_control_volumes(first_day, raw):
    ds = first_day.copy()
    ds.cell_area(join=False)
    # art1 is in projected (UTM) metres, so is slightly larger than on the sphere
    ratio = ds.to_xarray().cell_area.values.ravel() / raw["art1"]
    assert 0.99 < ratio.min() and ratio.max() < 1.0
    ds = first_day.copy()
    ds.top()
    ds.spatial_mean()
    surface = raw["temp"][0]
    expected = (surface * raw["art1"]).sum() / raw["art1"].sum()
    assert np.isclose(ds.to_xarray().temp.values.squeeze(), expected, atol=5e-3)


def test_regridding(first_day, raw):
    ds = first_day.copy()
    ds.top()
    ds.to_latlon(lon=[-9.8, -2.6], lat=[47.8, 56.9], res=0.05)
    field = ds.to_xarray().temp.values.squeeze()
    found = field[np.isfinite(field)]
    # some of the grid is land, and nothing is outside the range on the mesh
    assert 0.3 * field.size < found.size < 0.7 * field.size
    assert raw["temp"][0].min() - 1e-4 <= found.min() and found.max() <= raw["temp"][0].max() + 1e-4
