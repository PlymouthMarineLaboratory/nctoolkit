import copy
import os
import pandas as pd
import subprocess
import warnings

from nctoolkit.api import open_data
from nctoolkit.cleanup import cleanup
from nctoolkit.fvcom import is_fvcom, fvcom_weights, FVCOM_REMAP
from nctoolkit.generate_grid import generate_grid
from nctoolkit.runthis import run_cdo, run_this
from nctoolkit.session import append_safe, remove_safe, get_safe
from nctoolkit.temp_file import temp_file
import nctoolkit.api as api


def is_iterable(x):
    try:
        iter(x)
        return True
    except:
        return False


def regrid(self, grid=None, method="bil", recycle=False, one_grid=False, **kwargs):
    """
    regrid: Regrid a dataset to a target grid

    Horizontal interpolation

    Parameters
    -------------
    grid : nctoolkit.DataSet, pandas data frame or netCDF file
        The grid to remap to

    method : str
        Remapping method. Defaults to "bil". Methods available are:
        bilinear - "bil";
        nearest neighbour - "nn" - "nearest neighbour"
        bicubic interpolation - "bic"
        Distance-weighted average - "dis"
        First order conservative remapping - "con"
        Second order conservative remapping - "con2"
        Large area fraction remapping - "laf"
    recycle : bool
        Set to True if you want to re-use the remapping weights when you are regridding another dataset.
    one_grid : bool
        Set to True if all files in multi-file dataset have the same grid, to speed things up.
        FVCOM data, from open_fvcom, can use "bil" (linear interpolation within the mesh's
        triangles), "nn", "con", "con2", "laf" and "dis". Places outside the mesh are missing,
        except with "dis".
    kwargs : optional method to generate grid
        Instead of supplying a grid using 'grid', you can supply `lon` and `lat`. These must be equally
        lengthed lists or arrays that will be used to generate the grid. If you want to regrid to a single
        location you can just supply a float to lon and lat.

    Examples
    -------------
    Regrid to a grid defined by a pandas data frame:

    >>> ds.regrid(grid=grid_df)

    Regrid to a grid defined by a netCDF file:

    >>> ds.regrid(grid="grid.nc")

    Regrid to a grid defined by a nctoolkit.DataSet:

    >>> ds.regrid(grid=grid_ds)

    Regrid to a grid defined by a pandas data frame using nearest neighbour:

    >>> ds.regrid(grid=grid_df, method="nn")


    """

    if grid is None and len(kwargs) > 0:
        if "lon" in kwargs and "lat" in kwargs:
            lon = kwargs["lon"]
            lat = kwargs["lat"]

            if is_iterable(lon) is False:
                lon = [lon]

            if is_iterable(lat) is False:
                lat = [lat]

            if len(lon) == len(lat):
                grid = pd.DataFrame({"lon": lon, "lat": lat})

    if len(self) == 0:
        raise ValueError("Failure due to empty dataset!")

    if isinstance(method, str):
        if "nearest" in method:
            method = "nn"
        if "neighbour" in method:
            method = "nn"

    valid_methods = ["bil", "nn", "bic", "dis", "con", "con2", "laf"]

    fvcom = is_fvcom(self)
    if fvcom:
        if method == "bic":
            raise ValueError("Bicubic remapping is not available for FVCOM data. Please use bil or nn")
        if method == "dis":
            warnings.warn("Distance weighted remapping fills places outside the FVCOM mesh with values")

    if isinstance(grid, api.DataSet):
        if grid._weights is not None and grid._grid is not None:
            target_grid = grid._grid
            weights_nc = grid._weights
            cdo_command = f"-remap,{target_grid},{weights_nc}"
            if fvcom:
                cdo_command = FVCOM_REMAP.format(grid=target_grid, weights=weights_nc)
            self.cdo_command(cdo_command, ensemble=False)
            # run_this(cdo_command, self, output="ensemble")
            if fvcom:
                self.fvcom = False
                self._fvcom_mesh = None

            return None

    del_grid = None
    if grid is None:
        raise ValueError("No grid was supplied")

    grid_type = None

    # find the grid type
    if isinstance(grid, pd.DataFrame):
        grid_type = "df"
        if len(grid) == 0:
            raise ValueError("You have supplied an empty data frame as a grid!")

    if isinstance(grid, str):
        if os.path.exists(grid) is False:
            raise ValueError("grid file supplied does not exist")
        grid_type = "nc"

    if isinstance(grid, api.DataSet):
        grid.run()
        if len(grid) > 1:
            warnings.warn(message="The first file in dataset used for regridding!")
        grid = grid.current[0]
        grid_type = "nc"

    if grid_type is None:
        raise ValueError("grid supplied is not valid")

    # check that the remapping method is valid
    if (method in valid_methods) is False:
        raise ValueError("remapping method is invalid. Please check")

    # check the number of grids in the dataset

    # Do do the horizontal regridding

    grid_split = dict()

    self.run()

    if len(self) > 1 and recycle:
        raise ValueError("You cannot recycle multi-file datasets")

    i = 0
    for ff in self:
        if i == 0:
            cdo_result = subprocess.run(
                f"cdo griddes {ff}",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
            cdo_result = str(cdo_result)
            if cdo_result in grid_split:
                grid_split[cdo_result].append(ff)
            else:
                grid_split[cdo_result] = [ff]
        else:
            grid_split[cdo_result].append(ff)
        if one_grid:
            i += 1

    if grid is not None:
        # first generate the grid
        if grid_type == "df":
            target_grid = generate_grid(grid)
            del_grid = copy.deepcopy(target_grid)
            append_safe(del_grid)
        else:
            target_grid = grid
    new_files = []

    if recycle:
        append_safe(target_grid)

    if len(grid_split) > 1:
        suppress = True
    else:
        suppress = False

    for key in grid_split:
        # first we need to generate the weights for remapping
        # and add this to the files created list and self.weights
        tracker = open_data(
            grid_split[key], suppress_messages=True, thredds=self._thredds, checks=False
        )

        if fvcom and method in ["bil", "nn"]:
            # CDO cannot work out these weights for an unstructured grid,
            # so they are worked out on the FVCOM mesh
            try:
                weights_nc = fvcom_weights(
                    tracker.current[0], target_grid, method, self._fvcom_mesh
                )
            except Exception as e:
                del tracker
                raise ValueError(e)
            append_safe(weights_nc)
        else:
            weights_nc = temp_file("nc")

            cdo_command = (
                f"cdo -gen{method},{target_grid} {tracker.current[0]} {weights_nc}"
            )

            try:
                weights_nc = run_cdo(
                    cdo_command, target=weights_nc, precision=self._precision
                )
            except Exception as e:
                del tracker
                remove_safe(weights_nc)
                raise ValueError(e)

        if recycle:
            self._weights = weights_nc
            self._grid = target_grid

        cdo_command = f"cdo -remap,{target_grid},{weights_nc}"
        if fvcom and method in ["bil", "nn"]:
            cdo_command = "cdo " + FVCOM_REMAP.format(grid=target_grid, weights=weights_nc)

        tracker._execute = True

        run_this(cdo_command, tracker, output="ensemble", suppress=suppress)

        if recycle is False:
            remove_safe(weights_nc)

        for ff in tracker:
            append_safe(ff)

        new_files += tracker.current

        self.history += tracker.history

        self._hold_history = copy.deepcopy(self.history)

    if del_grid is not None:
        if recycle is False:
            remove_safe(del_grid)

    self.current = new_files

    for ff in self:
        if len([x for x in get_safe() if x == ff]) > 1:
            remove_safe(ff)

    self._thredds = False
    # the data is no longer on the FVCOM mesh
    if fvcom:
        self.fvcom = False
        self._fvcom_mesh = None
    cleanup()
    self.disk_clean()
