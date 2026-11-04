import nctoolkit as nc
import numpy as np
import pandas as pd
import xarray as xr
import os, pytest
import platform
import re


ff = "data/sst.mon.mean.nc"

class TestCrop:
    def test_pub_plot(self):

        # generate a random file name
        out_file = "asdfkjbuwnjlajksdfi.png"

        ds = nc.open_data("data/sst.mon.mean.nc", checks = False)

        with pytest.raises(ValueError):
            ds.pub_plot()


        ds.subset(time = 0)
        ds.pub_plot(out = out_file, land = "grey")

        with pytest.raises(ValueError, match=r"Did you mean"):
            ds.pub_plot(grid_colourrs = "none")

        with pytest.raises(ValueError, match=r"not a valid"):
            ds.pub_plot(invalid = None)

        assert os.path.exists(out_file)
        # get file size
        # this needs to be improved so it figures if the file is similar to the one in the repo
        assert os.path.getsize(out_file) > 140000 and os.path.getsize(out_file) < 150000

        with pytest.raises(ValueError):
            ds.pub_plot(mid_point = -1000)
        with pytest.raises(ValueError):
            ds.pub_plot(mid_point = 1000)


        ds.assign(tos = lambda x: x.sst + 273.15)
        ds.pub_plot(var = "sst", out = out_file, land = "grey")

        assert os.path.exists(out_file)
        # get file size
        # this needs to be improved so it figures if the file is similar to the one in the repo
        assert os.path.getsize(out_file) > 140000 and os.path.getsize(out_file) < 150000

        # value error check

        with pytest.raises(ValueError):
            ds.pub_plot(legend_position = "blah")

        with pytest.raises(ValueError):
            ds.pub_plot(scale = "blah")

        with pytest.raises(ValueError):
            ds.pub_plot(coast = "blah")

        with pytest.raises(TypeError):
            ds.pub_plot(land = 1)

        ds1 = ds.copy()
        ds1.assign(tos = lambda x: x.sst + 273.15)

        with pytest.raises(ValueError):
            ds1.pub_plot()
        with pytest.raises(ValueError):
            ds1 = nc.open_data("data/sst.mon.mean.nc", checks = False)
            ds1.pub_plot()
        
        with pytest.raises(ValueError):
            ds1.pub_plot()


        from difflib import SequenceMatcher

        def similar(a, b):
            return SequenceMatcher(None, a, b).ratio()
        
        with pytest.raises(ValueError):
            ds.pub_plot(all_wrong = False)

        with pytest.raises(ValueError):
            ds.pub_plot(lands = "grey")

        os.remove(out_file)

    def test_pub_plot_options(self):
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        import cartopy.crs as ccrs

        out_file = "pubplot_options_test.png"

        ds = nc.open_data(ff, checks = False)
        ds.subset(time = 0)

        ds.pub_plot(out = out_file, dpi = 50)
        # auto size is 5 inches tall
        assert mpimg.imread(out_file).shape[0] == 5 * 50
        os.remove(out_file)
        plt.close("all")

        ds.pub_plot(coast = None)
        plt.close("all")

        ds_global = nc.open_data("data/sst.mon.ltm.1981-2010.nc", checks = False)
        ds_global.subset(time = 0, variables = "sst")

        ds_global.pub_plot()
        assert isinstance(plt.gcf().axes[0].projection, ccrs.Robinson)
        plt.close("all")

        ds_global.pub_plot(projection = ccrs.PlateCarree())
        assert isinstance(plt.gcf().axes[0].projection, ccrs.PlateCarree)
        plt.close("all")

        ds.pub_plot(legend = "Temp", legend_position = "bottom")
        assert plt.gcf().axes[1].get_xlabel() == "Temp"
        plt.close("all")

        from cartopy.mpl.gridliner import Gridliner

        def n_grid_labels():
            fig = plt.gcf()
            fig.canvas.draw()
            gls = [a for a in fig.axes[0].artists if isinstance(a, Gridliner)]
            return sum(a.get_visible() for gl in gls for a in gl.label_artists)

        ds.pub_plot()
        assert n_grid_labels() > 0
        plt.close("all")

        ds.pub_plot(grid_labels = False)
        assert n_grid_labels() == 0
        plt.close("all")

        # global Robinson maps also label the curved edges
        ds_global.pub_plot(grid_labels = False)
        assert n_grid_labels() == 0
        plt.close("all")

        with pytest.raises(TypeError):
            ds.pub_plot(grid_labels = "no")

    @pytest.mark.skipif(platform.system() == "Darwin", reason="panel_plot tests are not relevant on macOS")
    def test_panel_plot(self):
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg

        def month(t):
            ds = nc.open_data(ff, checks = False)
            ds.subset(time = t)
            return ds

        panels = {"Jan": month(0), "Feb": month(1), "Mar": month(2)}

        def map_axes():
            return [a for a in plt.gcf().axes if hasattr(a, "projection")]

        def grid_shape(axes):
            gs = axes[0].get_subplotspec().get_gridspec()
            return gs.nrows, gs.ncols

        nc.panel_plot(panels)
        axes = map_axes()
        assert [a.get_title() for a in axes] == ["Jan", "Feb", "Mar"]
        assert grid_shape(axes) == (2, 2)
        # one shared colour bar
        assert len(plt.gcf().axes) == 4

        # every panel shares one colour scale, set from all panels together
        clims = {a.collections[0].get_clim() for a in axes}
        assert len(clims) == 1
        pooled = np.concatenate([
            ds.to_xarray().sst.values.ravel() for ds in panels.values()
        ])
        lo, hi = np.nanmin(pooled), np.nanmax(pooled)
        # the scale spans zero, so it is symmetric around zero
        assert np.isclose(clims.pop()[1], max(abs(lo), abs(hi)))
        plt.close("all")

        nc.panel_plot(panels, nrow = 1)
        assert grid_shape(map_axes()) == (1, 3)
        plt.close("all")

        nc.panel_plot(panels, ncol = 1)
        assert grid_shape(map_axes()) == (3, 1)
        plt.close("all")

        nc.panel_plot(panels, legend_position = "bottom", legend = "SST")
        cbax = [a for a in plt.gcf().axes if not hasattr(a, "projection")][0]
        assert cbax.get_xlabel() == "SST"
        assert cbax.bbox.width > cbax.bbox.height
        plt.close("all")

        out_file = "panel_plot_test.png"
        nc.panel_plot(panels, size = [10, 6], out = out_file, dpi = 50)
        assert mpimg.imread(out_file).shape[0] == 6 * 50
        os.remove(out_file)
        plt.close("all")

        # "~" in out is expanded to the home directory
        import tempfile, shutil
        home = os.path.expanduser("~")
        tmp_dir = tempfile.mkdtemp(dir = home)
        tilde_out = "~/" + os.path.relpath(tmp_dir, home) + "/panels.png"
        nc.panel_plot(panels, out = tilde_out)
        assert os.path.exists(os.path.join(tmp_dir, "panels.png"))
        shutil.rmtree(tmp_dir)
        plt.close("all")

        # one colour bar and colour scale per panel
        unshared = {"Jan": month(0), "Jul": month(6)}
        nc.panel_plot(unshared, shared_colourbar = False)
        axes = map_axes()
        assert len(plt.gcf().axes) == 4
        clims = [a.collections[0].get_clim() for a in axes]
        assert clims[0] != clims[1]
        plt.close("all")

        with pytest.raises(TypeError):
            nc.panel_plot(panels, shared_colourbar = "no")

        # per-panel values with separate colour bars; single values still apply to all
        nc.panel_plot(
            unshared,
            shared_colourbar = False,
            limits = [[0, 10], [5, 20]],
            colours = ["viridis", "plasma"],
            land = "grey",
        )
        ims = [a.collections[0] for a in map_axes()]
        assert [im.get_clim() for im in ims] == [(0, 10), (5, 20)]
        assert [im.get_cmap().name for im in ims] == ["viridis", "plasma"]
        plt.close("all")

        # per-panel var with a shared colour bar
        tos = month(6)
        tos.rename({"sst": "tos"})
        nc.panel_plot({"sst": month(0), "tos": tos}, var = ["sst", "tos"])
        assert len({a.collections[0].get_clim() for a in map_axes()}) == 1
        plt.close("all")

        with pytest.raises(ValueError, match = "but there are 2 panels"):
            nc.panel_plot(unshared, land = ["grey"])
        with pytest.raises(ValueError, match = "single value"):
            nc.panel_plot(unshared, colours = ["viridis", "plasma"])
        with pytest.raises(ValueError, match = "but there are 2 panels"):
            nc.panel_plot(unshared, shared_colourbar = False, limits = [[0, 10]])
        plt.close("all")

        with pytest.raises(TypeError):
            nc.panel_plot([month(0)])
        with pytest.raises(ValueError):
            nc.panel_plot({})
        with pytest.raises(TypeError):
            nc.panel_plot({"a": "not a dataset"})
        with pytest.raises(ValueError, match = "cannot hold"):
            nc.panel_plot(panels, nrow = 1, ncol = 1)
        with pytest.raises(ValueError, match = "time step"):
            nc.panel_plot({"all": nc.open_data(ff, checks = False)})
        plt.close("all")


class TestAntimeridian:
    def test_split_0_360(self):
        from nctoolkit.static_plot import _split_antimeridian

        lon = np.arange(0.5, 360, 1.0)
        lat = np.arange(-89.5, 90, 1.0)
        values = np.ma.masked_array(np.tile(lon, (lat.size, 1)))
        lon_edges, lat_edges, new_values = _split_antimeridian(lon, lat, values)
        assert lon_edges[0] == -180 and lon_edges[-1] == 180
        assert np.all(np.diff(lon_edges) > 0)
        assert new_values.shape == (lat.size, lon_edges.size - 1)
        assert lat_edges.size == lat.size + 1
        # the cell centred at 180 is split between the two edges of the map
        assert new_values[0, 0] == new_values[0, -1] == 180.5 or new_values[0, 0] == 180.5

    def test_split_cell_on_antimeridian(self):
        from nctoolkit.static_plot import _split_antimeridian

        lon = np.arange(0, 360, 1.0)
        lat = np.arange(-89.5, 90, 1.0)
        values = np.tile(lon, (lat.size, 1))
        lon_edges, _, new_values = _split_antimeridian(lon, lat, values)
        assert new_values.shape[1] == lon.size + 1
        assert new_values[0, 0] == new_values[0, -1] == 180

    def test_no_split_needed(self):
        from nctoolkit.static_plot import _split_antimeridian

        lat = np.arange(-89.5, 90, 1.0)
        # edges at -180 and 180, so no cell crosses the antimeridian
        lon = np.arange(-179.5, 180, 1.0)
        assert _split_antimeridian(lon, lat, np.zeros((lat.size, lon.size))) is None
        # regional grid crossing the antimeridian is left alone
        lon = np.arange(120, 290, 1.0)
        assert _split_antimeridian(lon, lat, np.zeros((lat.size, lon.size))) is None

    def test_missing_values_stay_blank(self, tmp_path):
        import matplotlib.image as mpimg

        lon = np.arange(0.5, 360, 1.0)
        lat = np.arange(-89.5, 90, 1.0)
        data = np.cos(np.radians(lat))[:, None] * np.ones(lon.size)[None, :] * 20
        lon_diff = np.abs((lon + 180) % 360 - 180)
        # a block of missing data, standing in for land, around lon 0, lat 5 to 50
        data[np.ix_((lat > 5) & (lat < 50), lon_diff < 30)] = np.nan
        in_file = str(tmp_path / "global_0_360.nc")
        xr.Dataset(
            {"sst": (("lat", "lon"), data.astype("float32"))},
            coords={"lat": lat, "lon": lon},
        ).to_netcdf(in_file, encoding={"sst": {"_FillValue": np.float32(1e20)}})

        out_file = str(tmp_path / "plot.png")
        ds = nc.open_data(in_file, checks=False)
        ds.pub_plot(out=out_file)
        img = mpimg.imread(out_file)
        h, w = img.shape[:2]
        # the missing block must be left blank rather than coloured
        assert np.allclose(img[int(h * 0.40), int(w * 0.50), :3], 1.0)
