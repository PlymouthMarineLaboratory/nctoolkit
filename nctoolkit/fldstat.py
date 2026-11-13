import copy

from nctoolkit.cleanup import cleanup
from nctoolkit.runthis import run_cdo, tidy_command
from nctoolkit.temp_file import temp_file
from nctoolkit.session import remove_safe
from nctoolkit.utils import cdo_version_blocked
from nctoolkit.fvcom import not_for_fvcom


def boxstat(self, stat="mean", x=1, y=1):
    """Method to calculate the spatial stat from a dataset"""

    if not isinstance(x, int):
        raise ValueError("x should be int")
    if not isinstance(y, int):
        raise ValueError("y should be int")

    if x <= 0:
        raise ValueError("x should be positive")
    if y <= 0:
        raise ValueError("y should be positive")

    if len(self) == 0:
        raise ValueError("Failure due to empty dataset!")

    cdo_command = f"-gridbox{stat},{x},{y}"

    self.cdo_command(cdo_command, ensemble=False)


@not_for_fvcom("it needs a regular lon/lat grid")
def box_mean(self, x=1, y=1):
    """
    box_mean: Calculate the grid box mean for all variables.

    This is performed for each time step.

    Parameters
    -------------
    x: int
        Number of boxes in the x, e.g. east-west direction
    y: int or float
        Number of boxes in the y, e.g. north-south direction

    Examples
    ------------
    If you want to calculate the mean in each 4 by 4 box:

    >>> ds.box_mean(x=4, y=4)

    """

    boxstat(self, stat="mean", x=x, y=y)


@not_for_fvcom("it needs a regular lon/lat grid")
def box_max(self, x=1, y=1):
    """
    box_max: Calculate the grid box max for all variables.

    This is performed for each time step.

    Parameters
    -------------
    x: int
        Number of boxes in the x, e.g. east-west direction
    y: int or float
        Number of boxes in the y, e.g. north-south direction


    Examples
    ------------
    If you want to calculate the max in each 4 by 4 box:

    >>> ds.box_max(x=4, y=4)

    """

    boxstat(self, stat="max", x=x, y=y)


@not_for_fvcom("it needs a regular lon/lat grid")
def box_min(self, x=1, y=1):
    """
    box_min: Calculate the grid box min for all variables.

    This is performed for each time step.

    Parameters
    -------------
    x: int
        Number of boxes in the x, e.g. east-west direction
    y: int or float
        Number of boxes in the y, e.g. north-south direction

    Examples
    ------------
    If you want to calculate the min in each 4 by 4 box:

    >>> ds.box_min(x=4, y=4)

    """

    boxstat(self, stat="min", x=x, y=y)


@not_for_fvcom("it needs a regular lon/lat grid")
def box_sum(self, x=1, y=1):
    """
    box_sum: Calculate the grid box sum for all variables.

    This is performed for each time step.

    Parameters
    -------------
    x: int
        Number of boxes in the x, e.g. east-west direction
    y: int or float
        Number of boxes in the y, e.g. north-south direction

    Examples
    ------------

    If you want to calculate the sum in each 4 by 4 box:

    >>> ds.box_sum(x=4, y=4)

    """

    boxstat(self, stat="sum", x=x, y=y)


@not_for_fvcom("it needs a regular lon/lat grid")
def box_range(self, x=1, y=1):
    """
    box_range: Calculate the grid box range for all variables.

    This is performed for each time step.

    Parameters
    -------------
    x: int
        Number of boxes in the x, e.g. east-west direction
    y: int or float
        Number of boxes in the y, e.g. north-south direction

    Examples
    ------------
    If you want to calculate the range in each 4 by 4 box:

    >>> ds.box_range(x=4, y=4)


    """

    boxstat(self, stat="range", x=x, y=y)


def fldstat(self, stat="mean"):
    """Method to calculate the spatial stat from a dataset"""

    if len(self) == 0:
        raise ValueError("Failure due to empty dataset!")

    cdo_command = f"-fld{stat}"

    self.cdo_command(cdo_command, ensemble=False)


def spatial_mean(self):
    """
    spatial_mean: Calculate the area weighted spatial mean for all variables.

    This is performed for each time step.

    Examples
    ------------

    If you want to calculate the spatial mean for a dataset, just do the following:

    >>> ds.spatial_mean()

    Note
    ------
    This method will calculate the average using weights based on each cell's
    area. If cell areas cannot be calculated, it will take a straight average, and a warning
    will say this.

    """
    fldstat(self, stat="mean")


def spatial_min(self):
    """
    spatial_min: Calculate the spatial minimum for all variables.

    This is performed for each time step.

    Examples
    ------------

    If you want to calculate the spatial minimum for a dataset, just do the following:

    >>> ds.spatial_min()

    """
    fldstat(self, stat="min")


def spatial_max(self):
    """
    spatial_max: Calculate the spatial maximum for all variables.

    This is performed for each time step.

    Examples
    ------------
    If you want to calculate the spatial maximum for a dataset, just do the following:

    >>> ds.spatial_max()

    """
    fldstat(self, stat="max")


def spatial_stdev(self):
    """
    spatial_stdev: Calculate the spatial standard deviation for all variables.

    This is performed for each time step.

    Examples
    ------------
    If you want to calculate the spatial standard deviation for a dataset, just do the following:

    >>> ds.spatial_stdev()
    """
    fldstat(self, stat="std")


def spatial_var(self):
    """
    spatial_var: Calculate the spatial variance for all variables.

    This is performed for each time step.

    Examples
    ------------
    If you want to calculate the spatial variance for a dataset, just do the following:

    >>> ds.spatial_var()


    """
    fldstat(self, stat="var")


def spatial_range(self):
    """
    spatial_range: Calculate the spatial range for all variables.

    This is performed for each time step.

    Examples
    ------------
    If you want to calculate the range of each variable across space for a dataset, just do the following:

    >>> ds.spatial_max()
    """
    fldstat(self, stat="range")


def spatial_sum(self, by_area=False):
    """
    spatial_sum: Calculate the spatial sum for all variables.

    This is performed for each time step.

    Parameters
    --------------
    by_area : boolean
        Set to True if you want to multiply the values by the grid cell area
        before summing over space. Default is False.

    Examples
    ------------
    If you want to calculate the spatial sum each variable across space for a dataset, just do the following:

    >>> ds.spatial_sum()

    By default, this method simply sums up each grid cell value. In some cases this is not suitable. For example,
    the values in each cell may concentrations or values per square metre etc. In this case multiplying each cell
    value by the cell area is more suitable. Do the following:

    >>> ds.spatial_sum(by_area = True)

    Each cell's value will be multiplied by the area of the cell (in square metres) prior to calculating the
    spatial sum.


    """

    if len(self) == 0:
        raise ValueError("Failure due to empty dataset!")

    if isinstance(by_area, bool) is False:
        raise TypeError("by_area is not boolean")

    if len(self) == 1 or (by_area is False):
        if by_area:
            self.run()

            cdo_command = f"-fldsum -mul {self.current[0]} -gridarea "
        else:
            cdo_command = "-fldsum"

        self.cdo_command(cdo_command, ensemble=False)

        # run_this(cdo_command, self, output="ensemble")

        return None
    
    self.run()

    new_files = []
    new_commands = []
    for ff in self:
        target = temp_file("nc")

        cdo_command = f"cdo -fldsum -mul {ff} -gridarea {ff} {target}"
        cdo_command = tidy_command(cdo_command)
        target = run_cdo(cdo_command, target=target, precision=self._precision)
        new_files.append(target)
        new_commands.append(cdo_command)

    self.history += new_commands
    self._hold_history = copy.deepcopy(self.history)

    self.current = new_files

    for ff in new_files:
        remove_safe(ff)

    cleanup()
    self.disk_clean()


def spatial_percentile(self, p=None):
    """
    spatial_percentile: Calculate the spatial percentile for all variables

    This is performed for each time step.

    Parameters
    -------------
    p: int or float
        Percentile to calculate. 0<=p<=100.

    Examples
    ------------
    If you want to calculate the median of each variable across space for a dataset, just do the following:

    >>> ds.spatial_percentile(50)
    """

    if len(self) == 0:
        raise ValueError("Failure due to empty dataset!")

    if p is None:
        raise ValueError("Please supply a percentile")

    if not isinstance(p, (int, float)):
        raise ValueError(f"{str(p)} is not a valid percentile")
    if (p < 0) or (p > 100):
        raise ValueError(f"p: {str(p)} is not between 0 and 100!")

    # fldpctl gives incorrect results in CDO 2.6.1
    cdo_version_blocked("spatial_percentile", "2.6.1")

    cdo_command = f"-fldpctl,{str(p)}"

    self.cdo_command(cdo_command, ensemble=False)
