from nctoolkit.utils import is_curvilinear
from nctoolkit.fvcom import not_for_fvcom


def zonstat(self, stat="mean"):
    """Method to calculate the meridonial statistic from a netCDF file"""
    for ff in self:
        if is_curvilinear(ff):
            raise TypeError(f"meridonial_{stat} cannot be calculated for this grid type. Please consider using to_latlon to convert to a regular grid.")
    cdo_command = f"-mer{stat}"

    self.cdo_command(cdo_command, ensemble=False)


@not_for_fvcom("it needs a regular lon/lat grid")
def meridonial_mean(self):
    """
    meridonial_mean: Calculate the meridonial mean for each year/month combination in files.

    This applies to each file in an ensemble.

    Examples
    ------------
    If you want to calculate the meridonial mean for a dataset, do the following:

    >>> ds.meridonial_mean()
    """
    zonstat(self, stat="mean")


@not_for_fvcom("it needs a regular lon/lat grid")
def meridonial_min(self):
    """
    meridonial_min: Calculate the meridonial minimum for each year/month combination in files.

    This applies to each file in an ensemble.

    Examples
    ------------
    If you want to calculate the meridonial minimum for a dataset, do the following:

    >>> ds.meridonial_min()
    """
    zonstat(self, stat="min")


@not_for_fvcom("it needs a regular lon/lat grid")
def meridonial_max(self):
    """
    meridonial_max: Calculate the meridonial maximum for each year/month combination in files.

    This applies to each file in an ensemble.

    Examples
    ------------
    If you want to calculate the meridonial maximum for a dataset, do the following:

    >>> ds.meridonial_max()

    """
    zonstat(self, stat="max")


@not_for_fvcom("it needs a regular lon/lat grid")
def meridonial_range(self):
    """
    meridonial_range: Calculate the meridonial range for each year/month combination in files.

    This applies to each file in an ensemble.

    Examples
    ------------
    If you want to calculate the meridonial range for a dataset, do the following:

    >>> ds.meridonial_max()
    """
    zonstat(self, stat="range")
