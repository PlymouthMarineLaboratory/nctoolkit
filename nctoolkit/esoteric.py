import copy
import pandas as pd
import numpy as np
import xarray as xr

from .temp_file import temp_file
from .cleanup import cleanup
from .runthis import run_nco
from .api import open_data
import warnings
from nctoolkit.fvcom import not_for_fvcom


@not_for_fvcom("it is only for NEMO's AMM7 grid", "")
def fix_amm7_grid(self):
    """
    A quick hack to change the grid file in AMM7 North West European shelf Nemo grids.

    """

    ds = open_data(self[0])
    # check the number of grid cells
    if max(ds.contents.npoints) != 111375:
        warnings.warn("This is not a NEMO ERSEM grid")
        return None

    lon_name = [x for x in ds.to_xarray().coords if "lon" in x][0]
    lat_name = [x for x in ds.to_xarray().coords if "lat" in x][0]
    lons = ds.to_xarray()[lon_name].values.flatten()
    if (
        len(set(list(pd.DataFrame({"lon": lons}).groupby("lon").size().sort_values())))
        == 1
    ):
        raise ValueError("There appears to be nothing to fix!")
    lons = list(set(lons))

    for i in range(1, len(lons)):
        if np.round(lons[i] - lons[i - 1], 5) == np.round(lons[i + 1] - lons[i], 5):
            break
    xinc = np.round(lons[i] - lons[i - 1], 5)

    lats = ds.to_xarray()[lat_name].values.flatten()
    lats = list(set(lats))

    for i in range(1, len(lats)):
        if np.round(lats[i] - lats[i - 1], 5) == np.round(lats[i + 1] - lats[i], 5):
            break
    yinc = np.round(lats[i] - lats[i - 1], 5)
    grid_file = temp_file().replace(".", "")
    ysize = ds.to_xarray()[lon_name].shape[0]
    xsize = ds.to_xarray()[lat_name].shape[1]
    xfirst = min(lons)
    lats = ds.to_xarray()[lat_name].values.flatten()
    yfirst = min(
        pd.DataFrame({"lat": lats})
        .groupby("lat")
        .size()
        .sort_values()
        .reset_index()["lat"][0:-1]
    )
    with open(grid_file, "a") as file:
        file.write("#\n")
        file.write("# gridID 1\n")
        file.write("#\n")
        file.write("gridtype = lonlat\n")
        file.write(f"gridsize = {xsize*ysize}\n")
        file.write(f"xsize = {xsize}\n")
        file.write(f"ysize = {ysize}\n")
        file.write("xname = lon\n")
        file.write("xlongname= longitude\n")
        file.write("xunits= degrees_east\n")
        file.write("yname = lat\n")
        file.write("ylongname= latitude\n")
        file.write("yunits= degrees_north\n")
        file.write(f"xfirst= {xfirst}\n")
        file.write(f"xinc= {xinc}\n")
        file.write(f"yfirst= {yfirst}\n")
        file.write(f"yinc= {yinc}\n")
    self.cdo_command(f"-setgrid,{grid_file}")
    self.run()


@not_for_fvcom("it is only for NEMO-ERSEM grids", "")
def fix_nemo_ersem_grid(self):
    """
    A quick hack to change the grid file in North West European shelf Nemo grids.

    """

    ds = open_data(self[0])
    # check the number of grid cells
    if max(ds.contents.npoints) != 111375:
        warnings.warn("This is not a NEMO ERSEM grid")
        return None

    lon_name = [x for x in ds.to_xarray().coords if "lon" in x][0]
    lat_name = [x for x in ds.to_xarray().coords if "lat" in x][0]
    lons = ds.to_xarray()[lon_name].values.flatten()
    if (
        len(set(list(pd.DataFrame({"lon": lons}).groupby("lon").size().sort_values())))
        == 1
    ):
        raise ValueError("There appears to be nothing to fix!")
    lons = list(set(lons))

    for i in range(1, len(lons)):
        if np.round(lons[i] - lons[i - 1], 5) == np.round(lons[i + 1] - lons[i], 5):
            break
    xinc = np.round(lons[i] - lons[i - 1], 5)

    lats = ds.to_xarray()[lat_name].values.flatten()
    lats = list(set(lats))

    for i in range(1, len(lats)):
        if np.round(lats[i] - lats[i - 1], 5) == np.round(lats[i + 1] - lats[i], 5):
            break
    yinc = np.round(lats[i] - lats[i - 1], 5)
    grid_file = temp_file().replace(".", "")
    ysize = ds.to_xarray()[lon_name].shape[0]
    xsize = ds.to_xarray()[lat_name].shape[1]
    xfirst = min(lons)
    lats = ds.to_xarray()[lat_name].values.flatten()
    yfirst = min(
        pd.DataFrame({"lat": lats})
        .groupby("lat")
        .size()
        .sort_values()
        .reset_index()["lat"][0:-1]
    )
    with open(grid_file, "a") as file:
        file.write("#\n")
        file.write("# gridID 1\n")
        file.write("#\n")
        file.write("gridtype = lonlat\n")
        file.write(f"gridsize = {xsize*ysize}\n")
        file.write(f"xsize = {xsize}\n")
        file.write(f"ysize = {ysize}\n")
        file.write("xname = lon\n")
        file.write("xlongname= longitude\n")
        file.write("xunits= degrees_east\n")
        file.write("yname = lat\n")
        file.write("ylongname= latitude\n")
        file.write("yunits= degrees_north\n")
        file.write(f"xfirst= {xfirst}\n")
        file.write(f"xinc= {xinc}\n")
        file.write(f"yfirst= {yfirst}\n")
        file.write(f"yinc= {yinc}\n")
    self.cdo_command(f"-setgrid,{grid_file}")
    self.run()


def no_leaps(self):
    """
    Remove leap years.
    This uses an undocumented CDO feature to remove Feb 29 and sets the calendar to leap year free

    Examples
    ------------
    Remove leap years from a dataset:
    >>> ds.no_leaps()

    """

    cdo_command = f"-del29feb"

    self.cdo_command(cdo_command, ensemble=False)


@not_for_fvcom("the FVCOM mesh is unstructured, and its grid type cannot be changed", "")
def set_gridtype(self, grid):
    """
    Set the grid type. Only use this if, for example, the grid is "generic" when it should be lonlat.

    Parameters
    -------------
    grid : str
        Grid type. Needs to be one of "curvilinear", "unstructured", "dereference", "regular", "regularnn" or "lonlat".

    """

    # check that the values supplied are valid
    # This will convert things to ints, and if it can't be done, throw an error

    if grid not in [
        "curvilinear",
        "unstructured",
        "dereference",
        "regular",
        "regularnn",
        "lonlat",
    ]:
        raise ValueError("Grid type supplies is not supported")

    cdo_command = f"-setgridtype,{grid}"

    self.cdo_command(cdo_command, ensemble=False)


def assign_coords(self, lon_name=None, lat_name=None, time_name=None):
    """
    Assign coordinates to variables

    Parameters
    -------------
    lon_name : str
        Name of the longitude dimension
    lat_name : str
        Name of the latitude dimension
    """

    # add grid number check

    self.run()

    if len(self) > 1:
        raise TypeError("This only works for single files currently")

    if (lon_name is None) or (lat_name is None):
        TypeError("Please provide lon and lat names!")

    if not isinstance(lat_name, str):
        TypeError("Method does not yet work with ensembles")

    if not isinstance(lat_name, str):
        TypeError("Method does not yet work with ensembles")

    if not isinstance(time_name, str):
        TypeError("Method does not yet work with ensembles")

    # change the units in turn. This doesn't seem to be something you can chain?

    if lon_name is not None:
        nco_command = "ncatted "

        for vv in self.variables:
            nco_command += (
                "-a coordinates," + vv + ",c,c,'" + lon_name + " " + lat_name + "' "
            )

        target = temp_file("nc")

        nco_command += self[0] + " " + target

        target = run_nco(nco_command, target)

        self.current = target

        # clean up the directory
        cleanup()

        self.history.append(nco_command)
        self._hold_history = copy.deepcopy(self.history)

    if time_name is not None:
        nco_command = "ncatted "

        for vv in self.variables:
            nco_command += "-a coordinates," + vv + ",c,c,'" + time_name + " ' "

        target = temp_file("nc")

        nco_command += self[0] + " " + target

        target = run_nco(nco_command, target)

        self.current = target

        # clean up the directory
        cleanup()

        self.history.append(nco_command)
        self._hold_history = copy.deepcopy(self.history)


def set_attributes(self, att_dict):
    """
    Set Global attributes

    Parameters
    -------------
    att_dict : dict
        Dictionary with key, value pairs representing the attribute names and their long names

    """

    self.run()

    if not isinstance(self.current, str):
        TypeError("Method does not yet work with ensembles")

    if not isinstance(att_dict, dict):
        TypeError("A dictionary has not been supplied!")

    # change the units in turn. This doesn't seem to be something you can chain?

    nco_command = "ncatted -O -h "
    for i in att_dict:
        nco_command += "-a " + i + ",global,o,c,'" + att_dict[i] + "' "

    target = ""
    if isinstance(self.start, list):
        target = ""
    else:
        if self.start == self.current:
            target = temp_file("nc")

    nco_command += self.current + " " + target

    target = run_nco(nco_command, target)

    if target != "":
        self.current = target

    # clean up the directory
    cleanup(keep=self.current)

    self.history.append(nco_command)
    self._hold_history = copy.deepcopy(self.history)


def delete_attributes(self, atts):
    """
    Set Global attributes
    Parameters
    -------------
    atts : list or str
        list or str of global attributes to remove.
    """

    self.run()

    if not isinstance(self.current, str):
        TypeError("Method does not yet work with ensembles")

    if not isinstance(atts, [str, list]):
        TypeError("A dictionary has not been supplied!")

    # change the units in turn. This doesn't seem to be something you can chain?

    nco_command = "ncatted "

    if isinstance(atts, str):
        atts = [atts]

    for i in atts:
        nco_command += "-a " + i + ",global,d,, "

    target = ""
    if isinstance(self.start, list):
        target = ""
    else:
        if self.start == self.current:
            target = temp_file("nc")

    nco_command += self.current + " " + target

    target = run_nco(nco_command, target)

    if target != "":
        self.current = target

    # clean up the directory
    cleanup(keep=self.current)

    self.history.append(nco_command)


def as_type(self, x):
    """
    Set a variable/dimension to double
    This is mostly useful for cases when time is stored as an int, but you need a double

    Parameters
    -------------
    x : dict
        A dictionary mapping variables to type. Values in dict must be one of 'int', 'float32' and 'float64'.

    Examples
    -------------
    Change time to float64:
    >>> ds.as_type({'time': 'float64'})

    """

    self.run()

    if not isinstance(x, dict):
        raise ValueError("Please provide a dictionary")

    with xr.open_dataset(self[0]) as ds:
        the_vars = list(ds.variables)

    for xx in x.keys():
        if xx not in the_vars:
            raise ValueError(f"{xx} is not a variable in the dataset")

    for xx in x.values():
        if xx not in ["int", "float32", "float64"]:
            raise ValueError(f"{xx} is not one of int, float32, float64")

    for xx in x.keys():
        if x[xx] == "float32":
            x[xx] = "float"
        if x[xx] == "float64":
            x[xx] = "double"

    the_command = ""
    for xx in x:
        the_command += f" -s '{xx}={x[xx]}({xx})'"

    self.nco_command(f"ncap2 {the_command}")


def as_double(self, x):
    """
    Set a variable/dimension to double
    This is mostly useful for cases when time is stored as an int, but you need a double

    Parameters
    -------------
    x : list
        A list of variable/dimensions you want to convert to floats

    Examples
    -------------
    Change time to double:
    >>> ds.as_double('time])

    """

    self.run()

    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        raise ValueError("Please provide a list to as_double")

    for xx in x:
        if not isinstance(xx, str):
            raise ValueError("Please provide a list of strings to as_double")

    for xx in x:
        self.nco_command(f"ncap2 -s '{xx}=double({xx})'")
