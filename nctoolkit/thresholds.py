import os
from nctoolkit.session import session_info
from nctoolkit.utils import version_below
import nctoolkit.api as api
from nctoolkit.fvcom import drop_thickness


def first_above(self, x=None):
    """
    first_above: Identify the time step when a value is first above a threshold.

    This will do the comparison with either a number, a Dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to use for the threshold(s).
        If comparing with a dataset or single file there must only be a single variable
        in it. The grids must be the same.

    Examples
    ------------

    If you wanted to calculate the first time step where the value in a grid cell goes above 10, you would do the following

    >>> ds.first_above(10)

    If you wanted to calculate the first time step where the value in a grid cell goes above that in another dataset, the
    following will work. Note that both datasets must have the same grid, and can only have single variables. The second
    dataset can, of course, only have one timestep.

    >>> ds.first_above(ds1)

    """
    version = session_info["cdo"]
    old = version_below(version, "2.1.0")

    self.run()

    if isinstance(x, str):
        if os.path.exists(x) is False:
            raise ValueError(f"{x} does not exist on disk!")

    drop_thickness(self)
    variable = self.variables[0]

    run_code = False

    # 1: int, float multiplication
    if isinstance(x, (int, float)):
        self.compare(f">{x}")
        run_code = True

    # 2: dataset or netCDF file multiplication
    # get the netCDF file(s)
    if isinstance(x, (api.DataSet, str)):
        if isinstance(x, api.DataSet):
            x.run()
        self.gt(x)
        run_code = True

    if run_code:
        self.rename({self.variables[0]: "target"})
        self.as_missing([-1, 0.1])
        if old:
            self.assign( new=lambda x: (x.target == x.target) * (timestep(x.target) + 1), drop=True,)
        else:
            self.assign( new=lambda x: (x.target == x.target) * (timestep() + 1), drop=True)
        self.as_missing([0, 0.01])
        self.tmin()
        self.assign(first=lambda x: int(x.new) - 1, drop=True)
        self.rename({"first": variable})
        self.run()
        return None

    raise TypeError("You have not supplied a valid type for x!")


def first_below(self, x=None):
    """
    first_below: Identify the time step when a value is first below a threshold
    This will do the comparison with either a number, a Dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to use for the threshold(s).
        If comparing with a dataset or single file there must only be a single variable
        in it. The grids must be the same.

    Examples
    ------------

    If you wanted to calculate the first time step where the value in a grid cell goes below 10, you would do the following

    >>> ds.first_below(10)


    If you wanted to calculate the first time step where the value in a grid cell goes above that in another dataset, the
    following will work. Note that both datasets must have the same grid, and can only have single variables. The second
    dataset can, of course, only have one timestep.

    >>> ds.first_below(ds1)


    """

    if isinstance(x, str):
        if os.path.exists(x) is False:
            raise ValueError(f"{x} does not exist on disk!")

    self.run()

    version = session_info["cdo"]
    old = version_below(version, "2.1.0")

    drop_thickness(self)
    variable = self.variables[0]

    run_code = False

    # 1: int, float multiplication
    if isinstance(x, (int, float)):
        self.compare(f"<{x}")
        run_code = True

    # 2: dataset or netCDF file multiplication
    # get the netCDF file(s)
    if isinstance(x, (api.DataSet, str)):
        if isinstance(x, api.DataSet):
            x.run()
        self.lt(x)
        run_code = True
    if run_code:
        self.rename({self.variables[0]: "target"})
        self.as_missing([-1, 0.1])
        if old:
            self.assign( new=lambda x: (x.target == x.target) * (timestep(x.target) + 1), drop=True,)
        else:
            self.assign( new=lambda x: (x.target == x.target) * (timestep() + 1), drop=True)
        self.as_missing([0, 0.01])
        self.tmin()
        self.assign(first=lambda x: int(x.new) - 1, drop=True)
        self.rename({"first": variable})
        self.run()
        return None

    raise TypeError("You have not supplied a valid type for x!")


def last_above(self, x=None):
    """
    last_above: Identify the final time step when a value is above a threshold
    This will do the comparison with either a number, a Dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to use for the threshold(s).
        If comparing with a dataset or single file there must only be a single variable
        in it. The grids must be the same.

    Examples
    ------------

    If you wanted to calculate the last time step where the value in a grid cell is above 10, you would do the following

    >>> ds.first_above(10)


    If you wanted to calculate the last time step where the value in a grid cell goes above that in another dataset, the
    following will work. Note that both datasets must have the same grid, and can only have single variables. The second
    dataset can, of course, only have one timestep.

    >>> ds.first_above(ds1)


    """
    if isinstance(x, str):
        if os.path.exists(x) is False:
            raise ValueError(f"{x} does not exist on disk!")

    self.run()

    version = session_info["cdo"]
    old = version_below(version, "2.1.0")

    drop_thickness(self)
    variable = self.variables[0]

    # if len(self.variables) > 1:
    #    raise ValueError("This method only works with single variable datasets!")

    run_code = False

    # 1: int, float multiplication
    if isinstance(x, (int, float)):
        self.compare(f">{x}")
        run_code = True

    # 2: dataset or netCDF file multiplication
    # get the netCDF file(s)
    if isinstance(x, (api.DataSet, str)):
        if isinstance(x, api.DataSet):
            x.run()
        self.gt(x)
        run_code = True

    if run_code:
        self.rename({self.variables[0]: "target"})
        self.as_missing([-1, 0.1])
        if old:
            self.assign( new=lambda x: (x.target == x.target) * (timestep(x.target) + 1), drop=True,)
        else:
            self.assign( new=lambda x: (x.target == x.target) * (timestep() + 1), drop=True)
        self.as_missing([0, 0.01])
        self.multiply(-1)
        self.tmin()
        self.multiply(-1)
        self.assign(last=lambda x: int(x.new) - 1, drop=True)
        self.rename({"last": variable})
        self.run()
        return None

    raise TypeError("You have not supplied a valid type for x!")


def last_below(self, x=None):
    """
    last_below: Identify the last time step when a value is below a threshold
    This will do the comparison with either a number, a Dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to use for the threshold(s).
        If comparing with a dataset or single file there must only be a single variable
        in it. The grids must be the same.

    Examples
    ------------

    If you wanted to calculate the last time step where the value in a grid cell is below 10, you would do the following

    >>> ds.last_below(10)


    If you wanted to calculate the last time step where the value in a grid cell is above that in another dataset, the
    following will work. Note that both datasets must have the same grid, and can only have single variables. The second
    dataset can, of course, only have one timestep.

    >>> ds.last_below(ds1)


    """
    if isinstance(x, str):
        if os.path.exists(x) is False:
            raise ValueError(f"{x} does not exist on disk!")

    self.run()

    version = session_info["cdo"]
    old = version_below(version, "2.1.0")

    drop_thickness(self)
    variable = self.variables[0]

    # if len(self.variables) > 1:
    #    raise ValueError("This method only works with single variable datasets!")

    run_code = False

    # 1: int, float multiplication
    if isinstance(x, (int, float)):
        self.compare(f"<{x}")
        run_code = True

    # 2: dataset or netCDF file multiplication
    # get the netCDF file(s)
    if isinstance(x, (api.DataSet, str)):
        if isinstance(x, api.DataSet):
            x.run()
        self.lt(x)
        run_code = True

    if run_code:
        self.rename({self.variables[0]: "target"})
        self.as_missing([-1, 0.1])
        if old:
            self.assign( new=lambda x: (x.target == x.target) * -1 * (timestep(x.target) + 1), drop=True,)
        else:
            self.assign( new=lambda x: (x.target == x.target) * -1 * (timestep() + 1), drop=True)
        self.as_missing([0, 0.01])
        self.assign(new=lambda x: int(x.new))
        self.tmin()
        self.multiply(-1)
        self.assign(new=lambda x: int(x.new))
        self.assign(last=lambda x: int(x.new) - 1, drop=True)
        self.rename({"last": variable})
        self.run()
        return None

    raise TypeError("You have not supplied a valid type for x!")
