import copy
import os
import warnings
import pandas as pd


from nctoolkit.cleanup import cleanup
from nctoolkit.runthis import run_cdo, tidy_command
from nctoolkit.session import session_info, append_safe, remove_safe
from nctoolkit.show import nc_variables, nc_times
from nctoolkit.temp_file import temp_file
from nctoolkit.api import open_data
import nctoolkit.api as api


def day_stat(self, operation=None, x=None):
    """
    Do not use
    """

    if not isinstance(operation, str):
        raise ValueError("operation must be a str")

    if operation not in ["subtract", "divide"]:
        raise ValueError("only subtract")

    if operation == "subtract":
        stat = "sub"

    if operation == "divide":
        stat = "div"

    if not isinstance(x, str):
        x = x.current
        if len(x) > 1:
            raise ValueError("requires single file")
        else:
            x = x[0]

    # create the system command and run it
    cdo_command = f"cdo -yday{stat} {self[0]} {x}"
    target = temp_file(".nc")

    the_command = cdo_command + " " + target

    the_command = tidy_command(the_command)

    target = run_cdo(the_command, target, precision=self._precision)

    self.current = target
    remove_safe(target)

    self.history.append(the_command)

    self._hold_history = copy.deepcopy(self.history)
    cleanup()


def arithall(self, stat="divc", x=None):
    """
    Method to add, subtract etc. a constant from a dataset
    This is used by add etc.
    """

    if len(self) == 0:
        raise ValueError("This does not work on empty datasets!")

    if getattr(self, "fvcom_thickness", None) is not None:
        warnings.warn(
            f"This also changes the FVCOM layer thickness, {self.fvcom_thickness}. "
            "Consider dropping it, or using assign, if you need it for vertical methods"
        )

    # create the system command and run it
    cdo_command = f"-{stat},{x}"

    self.cdo_command(cdo_command)


def operation(self, method="mul", ff=None, var=None):
    """
    Method to add, subtract etc. a netCDF file from another one
    This is used by add etc.
    """

    # throw error if there is a problem with var
    if var is not None:
        if not isinstance(var, str):
            raise TypeError("var supplied is not a string")
        if var not in nc_variables(ff):
            raise ValueError("var supplied is not available in the dataset")

    new = False
    # throw error if the file to operate with does not exist
    if ff is not None:
        if os.path.exists(ff) is False:
            raise ValueError(f"{ff} does not exist!")

    # check compatibility

    n_min = self.contents.nlevels.min()

    ds = open_data(ff, checks=False)
    contents = ds.contents

    n_max = contents.nlevels.max()

    if n_max > n_min:
        raise ValueError(
            f"Problem raised by incompatible number of vertical levels. {n_max} versus {n_min}. Please check dataset contents."
        )

    new = True

    if var is None:
        for x in self:
            n_vars = len(nc_variables(ff))
            x_vars = len(nc_variables(x))

            # if n_vars > x_vars:
            # raise ValueError("Incompatible number of variables in datasets!")

            if n_vars != x_vars:
                if n_vars > 1:
                    raise ValueError("Incompatible number of variables in datasets!")

    # grab the method string
    if new:
        if method == "mul":
            nc_str = "Multiplying by a"
        if method == "sub":
            nc_str = "Subtracting a"
        if method == "add":
            nc_str = "Adding a"
        if method == "div":
            nc_str = "Dividing by a"

    if new:
        ff_times = nc_times(ff)
        if len(ff_times) <= 1:
            new = False
            method = method
        else:
            if isinstance(ff_times[0], str):
                years = [int(x.split("T")[0].split("-")[0]) for x in ff_times]
                months = [int(x.split("T")[0].split("-")[1]) for x in ff_times]
                days = [int(x.split("T")[0].split("-")[2]) for x in ff_times]
                ff_times_df = pd.DataFrame(
                    {"year": years, "month": months, "day": months}
                )
            else:
                ff_times_df = (
                    pd.DataFrame({"time": ff_times})
                )
                ff_times_df["year"] = [x.year for x in ff_times]
                ff_times_df["month"] = [x.month for x in ff_times]
                ff_times_df["day"] = [x.day for x in ff_times]
                    # .assign(
                    #     year=lambda x: x.time.dt.year,
                    #     month=lambda x: x.time.dt.month,
                    #     day=lambda x: x.time.dt.day,
                    # )
                ff_times_df = (
                    ff_times_df
                    .drop(columns="time")
                )

            ff_times_df = ff_times_df.astype("int")

    if new:
        self1 = self.copy()

        if len(self1) == 0:
            raise ValueError("This does not work on empty datasets!")

        # If the dataset has to be merged,
        # then this operation will not work without running it first
        self1.run()

        self_times = []
        for x in self1:
            x_times = nc_times(x)
            if x_times != []:
                if isinstance(x_times[0], str):
                    years = [int(x.split("T")[0].split("-")[0]) for x in x_times]
                    months = [int(x.split("T")[0].split("-")[1]) for x in x_times]
                    days = [int(x.split("T")[0].split("-")[2]) for x in x_times]
                    df = pd.DataFrame(
                        {"year": years, "month": months, "day": months}
                    ).astype("int")
                    self_times.append(df)

                else:
                    years = [x.year for x in x_times]
                    months = [x.month for x in x_times]
                    days = [x.day for x in x_times]
                    hours = [x.hour for x in x_times]
                    df = pd.DataFrame(
                        {"year": years, "month": months, "day": days, "hour": hours}
                    ).astype("int")
                    df["path"] = x
                    self_times.append(df)
            else:
                self_times.append(None)

        possible_switch = True
        for x in self_times:
            if x is None:
                possible_switch = False

    # figure out if a yearly will do
    possible_switch = True
    if new:
        if ff_times_df.groupby("year").size().max() == 1:
            for ss in self_times:
                if set(ss.year) != set([x for x in list(ff_times_df.year)]):
                    possible_switch = False

            if possible_switch:
                method = f"year{method}"
                new = False
                warnings.warn(f"{nc_str} yearly time series")

    # now if all of the files have the same number of time steps
    possible_switch = True
    if new:
        for ss in self_times:
            if len(ff_times_df) != len(ss):
                possible_switch = False

            if possible_switch:
                method = method
                new = False
                warnings.warn(
                    f"{nc_str} time series with the same number of time steps"
                )

    # figure out if a single year monthly will do
    possible_switch = True
    if new:
        if ff_times_df.groupby("month").size().max() == 1:
            for ss in self_times:
                if set(ss.month) != set([x for x in list(ff_times_df.month)]):
                    possible_switch = False

            if possible_switch:
                method = f"ymon{method}"
                new = False
                warnings.warn(f"{nc_str} monthly time series")

    # figure out if a single year monthly will do
    possible_switch = True
    if new:
        if ff_times_df.groupby(["month", "year"]).size().max() == 1:
            for ss in self_times:
                if (
                    ss.loc[:, ["month", "year"]]
                    .drop_duplicates()
                    .reset_index(drop=True)
                    .equals(
                        ff_times_df.loc[:, ["month", "year"]]
                        .drop_duplicates()
                        .reset_index(drop=True)
                    )
                    is False
                ):
                    possible_switch = False

            if possible_switch:
                method = f"mon{method}"
                new = False
                warnings.warn(f"{nc_str} multi-year monthly time series")

    # figure out if this is a multi-year daily ts
    possible_switch = True
    if new:
        if ff_times_df.groupby(["month", "year", "day"]).size().max() == 1:
            for ss in self_times:
                if (
                    ss.loc[:, ["month", "year", "day"]]
                    .drop_duplicates()
                    .reset_index(drop=True)
                    .equals(
                        ff_times_df.loc[:, ["month", "year", "day"]]
                        .drop_duplicates()
                        .reset_index(drop=True)
                    )
                    is False
                ):
                    possible_switch = False

            if possible_switch:
                method = f"yday{method}"
                new = False
                warnings.warn(f"{nc_str} multi-year daily time series")

    if new:
        raise ValueError("Unable to carry out operation given times in datasets!")

    if new is False:
        # make sure the ff file is not removed from safe list in subsequent
        # actions prior to running
        if (ff is not None) and (session_info["lazy"]):
            append_safe(ff)
            self._safe.append(ff)

        if len(self.history) == len(self._hold_history):
            for x in self:
                # check that the datasets can actually be worked with
                if var is None:
                    if (len(nc_variables(ff)) != len(nc_variables(x))) and (
                        len(nc_variables(ff)) != 1
                    ):
                        raise ValueError(
                            "Datasets have incompatible variable numbers for the operation!"
                        )

            prior_command = ""

        else:
            prior_command = self.history[-1].replace("cdo ", " ").replace("  ", " ")

        # we need to make sure you can chain multiple adds etc.#
        # the approach below will work, but can probably be improved on

        if var is None:
            if "infile09178" in prior_command:
                cdo_command = f"cdo -{method} {prior_command} {ff}"
            else:
                cdo_command = f"cdo -{method} {prior_command} infile09178 {ff}"
        else:
            if "infile09178" in prior_command:
                cdo_command = f"cdo -{method} {prior_command} -selname,{var} {ff}"
            else:
                cdo_command = (
                    f"cdo -{method} {prior_command} infile09178 -selname,{var} {ff}"
                )

        # run the command if not lazy

        if session_info["lazy"] is False:
            new_files = []
            new_commands = []

            for FF in self:
                target = temp_file(".nc")
                the_command = cdo_command.replace("infile09178", FF) + " " + target
                the_command = tidy_command(the_command)
                target = run_cdo(the_command, target, precision=self._precision)
                new_files.append(target)
                new_commands.append(the_command)

            for cc in new_commands:
                self.history.append(cc.replace("  ", " "))

            self.current = new_files

            for ff1 in new_files:
                remove_safe(ff1)
            self._hold_history = copy.deepcopy(self.history)
            cleanup()

        # update history if lazy
        else:
            if len(self.history) > len(self._hold_history):
                self.history[-1] = cdo_command
            else:
                self.history.append(cdo_command)

        # remove anything from self._safe if it was ever set up

        cleanup()


def multiply(self, x=None, var=None):
    """
    multiply: Multiply a dataset.

    This will multiply a dataset by a constant, another dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to multiply the dataset by.
        If multiplying by a dataset or single file there must only be a single variable
        in it, unless var is supplied. The grids must be the same.
    var: str
        A variable in the x to multiply the dataset by

    Examples
    ------------

    If you wanted to multiply variables in a dataset by 10, you would do the following:

    >>> ds.multiply(10)

    Or, you could use standard python multiplication syntax:

    >>> ds * 10

    To multiply the values in a dataset by the values of variables in dataset ds2, you would do the following:

    >>> ds1.multiply(ds2)

    Or, you could use standard python multiplication syntax:

    >>> ds1 * ds2

    Grids in the datasets must match. Multiplication will occur in matching timesteps in ds1 and ds2. If there is only 1 timestep in ds2, then
    the data from that timestep in ds2 will multiply the data in all timesteps in ds1.

    Multiplying a dataset by the data from another netCDF file will work in the same way:

    >>> ds.multiply("example.nc")
    """

    # 1: int, float multiplication
    if isinstance(x, (int, float)):
        arithall(self, stat="mulc", x=x)
        return None

    # 2: dataset or netCDF file multiplication
    # get the netCDF file(s)
    if isinstance(x, api.DataSet):
        x.run()
        if len(x) == 1:
            ff = x.current[0]
        else:
            raise ValueError("This can only work with single file datasets")
    else:
        ff = x

    if not isinstance(ff, str):
        raise TypeError("You have not provided an int, float, dataset or file path!")

    operation(self=self, method="mul", ff=ff, var=var)


__mul__ = multiply


def rmse(self, x=None):
    """
    rmse: Calculate the root-mean-square-error of two datasets

    Parameters
    ------------
    x:  DataSet or netCDF file
        This must have an identifical structure to your dataset

    ------------
    """

    if isinstance(x, api.DataSet):
        x.run()
        if len(x) == 1:
            ff = x.current[0]
        else:
            raise ValueError("This can only work with single file datasets")
    else:
        ff = x

    ds2 = open_data(ff)

    if len(self) > 1:
        raise ValueError("This can only work with single file datasets")

    self.run()
    n_times = len(self.times)

    ds1 = self.copy()
    # subtract the data in one dataset from the other
    ds1.subtract(ds2)
    # square the differences
    ds1.power(2)
    # sum up over all time steps
    ds1.tsum()
    # divide by the number of time steps
    ds1.divide(n_times)
    # square the results
    ds1.sqrt()
    ds1.run()

    self.current = ds1.current
    self.history = ds1.history
    self._hold_history = ds1._hold_history


def subtract(self, x=None, var=None):
    """
    subtract: Subtract from a dataset.

    This will subtract a constant, another dataset or a netCDF file from the dataset.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to subtract from the dataset.
        If a dataset or netCDF is supplied this must only have one variable,
        unless var is provided. The grids must be the same.
    var: str
        A variable in the x to use for the operation

    Examples
    ------------

    If you wanted to subtract 10 from all variables in a dataset, you would do the following:

    >>> ds.subtract(10)

    Or, you could use standard python subtraction syntax:

    >>> ds - 10

    To substract the values in a dataset ds2 from those in a dataset ds1, you would do the following:

    >>> ds1.subtract(ds2)

    Or, you could use standard python subtraction syntax:

    >>> ds1 - ds2

    Grids in the datasets must match. Division will occur in matching timesteps in ds1 and ds2 if there are matching timesteps. If there is only 1 timestep in ds2, then
    the data from that timestep in ds2 will be subtracted from the data in all timesteps in ds1.

    """

    # 1: int, float subtraction
    if isinstance(x, (int, float)):
        arithall(self, stat="subc", x=x)
        return None

    # 2: dataset or netCDF file subtraction
    # get the netCDF file(s)
    if isinstance(x, api.DataSet):
        x.run()
        if len(x) == 1:
            ff = x.current[0]
        else:
            raise ValueError("This can only work with single file datasets")
    else:
        ff = x

    if not isinstance(ff, str):
        raise TypeError("You have not provided an int, float, dataset or file path!")

    operation(self=self, method="sub", ff=ff, var=var)


__sub__ = subtract


def add(self, x=None, var=None):
    """
    add: Add to a dataset

    This will add a constant, another dataset or a netCDF file to the dataset.
    nctoolkit will automatically determine the appropriate comparison required.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to add to the dataset.
        If a dataset or netCDF file is supplied, this must have only one variable,
        unless var is provided. The grids must be the same.
    var: str
        A variable in the x to use for the operation

    Examples
    ------------

    If you wanted to add 10 to all variables in a dataset, you would do the following:

    >>> ds.add(10)

    Or, you could use standard python addition syntax:

    >>> ds + 10

    To add the values in a dataset ds2 from a dataset ds1, you would do the following:

    >>> ds1.add(ds2)

    Or, you could use standard python addition syntax:

    >>> ds1 + ds2

    Grids in the datasets must match. Addition will occur in matching timesteps in ds1 and ds2. If there is only 1 timestep in ds2, then
    the data from that timestep will be added to the data in all ds1 time steps.

    Adding the data from another netCDF file will work in the same way:

    >>> ds1.add("example.nc")

    """

    # 1: int, float addition
    if isinstance(x, (int, float)):
        arithall(self, stat="addc", x=x)
        return None

    # 2: dataset or netCDF file addition
    # get the netCDF file(s)
    if isinstance(x, api.DataSet):
        x.run()
        if len(x) == 1:
            ff = x.current[0]
        else:
            raise ValueError("This can only work with single variable datasets")
    else:
        ff = x

    if not isinstance(ff, str):
        raise TypeError("You have not provided an int, float, dataset or file path!")

    operation(self=self, method="add", ff=ff, var=var)


__add__ = add


def divide(self, x=None, var=None):
    """
    divide: Divide the data.

    This will divide the dataset by a constant, another dataset or a netCDF file.

    Parameters
    ------------
    x: int, float, DataSet or netCDF file
        An int, float, single file dataset or netCDF file to divide the dataset by.
        If a dataset or netCDF file is supplied, this must have only one variable,
        unless var is provided. The grids must be the same.
    var: str
        A variable in the x to use for the operation

    Examples
    ------------

    If you wanted to divide all variables in a dataset by 20, you would do the following:

    >>> ds.divide(10)

    Or, you could use standard python division syntax:

    >>> ds / 10

    To divide values in a dataset by those in the dataset ds2 from a dataset ds1, you would do the following:

    >>> ds1.divide(ds2)

    Or, you could use standard python division syntax:

    >>> ds1 / ds2

    Grids in the datasets must match. Division will occur in matching timesteps in ds1 and ds2. If there is only 1 timestep in ds2, then
    the data from that timestep in ds2 will divided the data in all ds1 time steps.

    """

    # 1: int, float division
    if isinstance(x, (int, float)):
        arithall(self, stat="divc", x=x)
        return None

    # 2: dataset or netCDF file division
    # get the netCDF file(s)
    if isinstance(x, api.DataSet):
        x.run()
        if len(x) == 1:
            ff = x.current[0]
        else:
            raise ValueError("This can only work with single file datasets")
    else:
        ff = x

    if not isinstance(ff, str):
        raise TypeError("You have not provided an int, float, dataset or file path!")

    operation(self=self, method="div", ff=ff, var=var)


__truediv__ = divide


def abs(self):
    """
    abs: Method to get the absolute value of variables

    Examples
    ------------

    If you wanted to get the absolute value of each variable, you just need do this:

    >>> ds.abs()

    """
    cdo_command = "-abs"

    self.cdo_command(cdo_command, ensemble=False)


def power(self, x=None):
    """
    power: Powers of variables in dataset

    Parameters
    ------------
    x: int, float
        An int or float to take the variables to the power of

    Examples
    ------------

    If you wanted to take each variable to the power of 0.5 you would do this:

    >>> ds.power(0.5)

    """

    if not isinstance(x, (int, float)):
        raise TypeError("x is not a float or int")

    cdo_command = f"-pow,{x}"

    self.cdo_command(cdo_command)


__pow__ = power


def exp(self):
    """
    exp: Method to get the exponential of variables

    Examples
    ------------

    If you wanted to calculate the exponential of a variable, you just need to do this:

    >>> ds.exp(0.5)

    """
    cdo_command = "-exp"

    self.cdo_command(cdo_command)


def log(self):
    """
    log: Method to get the natural log, ln, of variables

    Examples
    ------------

    If you wanted to calculate the natural log of each variable, you just need to do this:

    >>> ds.log()

    """
    cdo_command = "-ln"

    self.cdo_command(cdo_command)


def log10(self):
    """
    log10: Method to get the base 10 log, log10, of variables

    Examples
    ------------

    If you wanted to calculate the base 10 log of each variable, you just need to do this:

    >>> ds.log10()

    """
    cdo_command = "-log10"

    self.cdo_command(cdo_command)


def square(self):
    """
    square: Method to get the square of variables

    Examples
    ------------

    If you wanted to calculate the square of each variable, you just need to do this:

    >>> ds.square()

    """
    cdo_command = "-sqr"

    self.cdo_command(cdo_command)


def sqrt(self):
    """
    sqrt: Method to get the square root of variables

    Examples
    ------------

    If you wanted to calculate the square root of each variable, you just need to do this:

    >>> ds.sqrt()

    """
    cdo_command = "-sqrt"

    self.cdo_command(cdo_command)
