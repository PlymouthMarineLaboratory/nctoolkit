from nctoolkit.fvcom import not_for_fvcom


@not_for_fvcom("it needs a regular lon/lat grid")
def resample_grid(self, factor=None):
    """
    resample_grid: Resample the horizontal grid of a dataset

    Parameters
    -------------
    factor : int
        The resampling factor. Must be a positive integer. No interpolation occurs.
        Example: factor of 2 will sample every other grid cell

    Examples
    ------------
    If you wanted to select every other grid cell, you could do the following:

        >>> ds.resample_grid(2)
    """
    if factor is None:
        raise ValueError("Please provide a resampling factor")

    if not isinstance(factor, int):
        raise TypeError(f"{factor} is not an integer")

    if factor < 1:
        raise ValueError(f"{factor} is not a postive integer greater than 1")

    cdo_command = f"-samplegrid,{factor}"
    self.cdo_command(cdo_command, ensemble=False)
