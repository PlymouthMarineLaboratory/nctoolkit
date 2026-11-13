import signal

from contextlib import contextmanager
from nctoolkit.session import session_info
from nctoolkit.show import nc_variables

def coast_check():
    try:
        import geoviews
        import cartopy
        from cartopy import crs
        import cartopy.crs as ccrs

        projection = ccrs.PlateCarree()
        return True
    except:
        return False



class TimeoutException(Exception):
    pass


@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutException("Timed out. Try plotting fewer variables!")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


def plot(self, vars=None, autoscale=True, out=None, coast=None, **kwargs):
    """
    plot: Automatically plot a dataset.

    Parameters
    -------------
    vars: str or list
        A string or list of the variables to plot
    autoscale: bool
        Set to True if you want the colorbar to be scaled to the min/max of the data. Default is True
    out: str
        Name of output file if you want to save as html. Defaults to None.
    coast: bool
        Set to True if you want a coastline to show up on spatial map. Default is True if a working version of cartopy is available. It is False otherwise.

    **kwargs: Optional args to be sent to hvplot

    Returns
    ----------
    If out is None, returns a hvplot object. Otherwise, saves a html file to the location specified by out.


    Examples
    ------------

    If you want to plot all data in a dataset, do the following:

    >>> ds.plot()

    If you only want to plot a single variable, do the following. Note, this is often faster if you
    have a large dataset.

    >>> ds.plot("var_of_choice")

    """
    from ncplot import view

    if session_info["coast"] is None:
        session_info["coast"] = coast_check()

    if "title" not in kwargs.keys():
        kwargs["title"] = ""

    # run any commands
    self.run()

    if not session_info["coast"]:
        if coast is None:
            coast = False
    else:
        if coast is None:
            coast = True



    if len(self) > 1:
        vars_1 = nc_variables(self[0])
        vars_2 = nc_variables(self[1])
        # check if they have the same variables
        if set(vars_1) != set(vars_2):  
            raise ValueError("Unable to plot multi-file datasets when variables differ across files.") 

    # a single file is passed as a path, as older versions of ncplot cannot handle lists
    to_plot = self.current if len(self) > 1 else self[0]

    if vars is None:
        if len(set(self.contents.nlevels)) > 1:
            raise ValueError(
                "Unable to plot datasets when variables have differing levels"
            )

    if isinstance(vars, str):
        vars = [vars]

    if not isinstance(vars, list) and vars is not None:
        raise ValueError("vars must be a list")
    if vars is None:
        vars = self.variables

    if isinstance(vars, list):
        if len(set(self.contents.query("variable in @vars").nlevels)) > 1:
            raise ValueError(
                "Unable to plot datasets when variables have differing levels"
            )
    if vars is None and len(self.variables) > 1:
        if out is None:
            with time_limit(20):
                return view(self[0], autoscale=autoscale, coast=coast, **kwargs)
        else:
            return view(self[0], autoscale=autoscale, coast=coast, **kwargs)

    if isinstance(vars, list) and len(vars) > 1:
        if out is None:
            with time_limit(20):
                return view(
                    self[0],
                    vars=vars,
                    autoscale=autoscale,
                    out=out,
                    coast=coast,
                    **kwargs
                )
        else:
            return view(
                to_plot, vars=vars, autoscale=autoscale, out=out, coast=coast, **kwargs
            )

    return view(to_plot, vars=vars, autoscale=autoscale, out=out, coast=coast, **kwargs)
