import copy
import xarray as xr
import subprocess
import numbers

from nctoolkit.cleanup import cleanup
from nctoolkit.flatten import str_flatten
from nctoolkit.fvcom import is_fvcom
from nctoolkit.runthis import run_nco, tidy_command
from nctoolkit.temp_file import temp_file
from nctoolkit.session import remove_safe


def crop(self, lon=[-180, 180], lat=[-90, 90], nco=False, nco_vars=None):
    """
    crop: Crop to a rectangular longitude and latitude box

    Parameters
    -------------
    lon: list
        The longitude range to select. This must be two variables,
        between -180 and 180 when nco = False.
    lat: list
        The latitude range to select. This must be two variables,
        between -90 and 90 when nco = False.
    nco: boolean
        Do you want this to use NCO for cropping? Defaults to False,
        and uses CDO. Set to True if you want to call NCO.
        NCO is typically better at handling very large horizontal grids.
    nco_vars: str or list
        If using NCO, the variables you want to select

    Examples
    ------------
    If you wanted to crop a dataset to longitudes between -40 and 30 and latitudes between -10 and 40,
    you would do the following:

    >>> ds.crop(lon = [-40, 30], lat = [-10, 40])


    If you wanted to select only the northern hemisphere, the following will work:

    >>> ds.crop(lat = [0, 90])


    """

    if lon is None:
        lon = [-180, 180]
    if lat is None:
        lat = [-90, 90]

    if nco and is_fvcom(self):
        raise ValueError(
            "crop with nco = True does not work with FVCOM data. Please use nco = False"
        )

    if nco:
        self.run()

    if isinstance(nco_vars, str):
        nco_vars = [nco_vars]

    # check validity of lon/lat supplied
    if not isinstance(lon, list) or not isinstance(lat, list):
        raise TypeError("Check that lon/lat ranges are tuples")

    if len(lon) != 2:
        raise ValueError("lon is a list of more than 2 variables")

    if len(lat) != 2:
        raise ValueError("lat is a list of more than 2 variables")

    for ll in lon:
        if isinstance(ll, numbers.Number) is False:
            raise TypeError(f"{ll} from lon is not a float or int")

    for ll in lat:
        if isinstance(ll, numbers.Number) is False:
            raise TypeError(f"{ll} from lat is not a float or int")

    # now, clip to the lonlat box we need

    if nco is False:
        if lon[1] < lon[0]:
            raise ValueError("Check lon order")

    if lat[1] < lat[0]:
        raise ValueError("Check lat order")

    if nco is False:
        if (lon[0] >= -180) and (lon[1] <= 180) and (lat[0] >= -90) and (lat[1] <= 90):
            lat_box = str_flatten(lon + lat)
            cdo_command = "-sellonlatbox," + lat_box
            cdo_command = tidy_command(cdo_command)

            self.cdo_command(cdo_command, ensemble=False)
            return None
        else:
            raise ValueError("The lonlat box supplied is not valid!")

    new_files = []
    new_commands = []

    for ff in self:
        # find the names of lonlat

        if nco_vars is not None:
            var_str = f" -v {str_flatten(nco_vars)}"
        else:
            var_str = " "

        out = subprocess.run(
            f"cdo griddes {ff}",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        lon_name = [
            x for x in str(out.stdout).replace("b'", "").split("\\n") if "xname" in x
        ][0].split(" ")[-1]
        lat_name = [
            x for x in str(out.stdout).replace("b'", "").split("\\n") if "yname" in x
        ][0].split(" ")[-1]
        target = temp_file("nc")

        # figure out if the unit is degrees east

        with xr.open_dataset(ff, decode_times=False) as ds_lon:
            max_lon = ds_lon[lon_name].values.max()

        if lon != [-180, 180] and max_lon > 180:
            if lon[0] < 0:
                lon[0] = 360 + lon[0]

            if lon[1] < 0:
                lon[1] = 360 + lon[1]

        nco_command = (
            f"ncks {var_str} -d "
            + lat_name
            + ","
            + str(float(lat[0]))
            + ","
            + str(float(lat[1]))
            + " -d "
            + lon_name
            + ","
            + str(float(lon[0]))
            + ","
            + str(float(lon[1]))
            + " "
            + ff
            + " "
            + target
        )
        if lon == [-180, 180]:
            nco_command = (
                f"ncea {var_str} -d "
                + lat_name
                + ","
                + str(float(lat[0]))
                + ","
                + str(float(lat[1]))
                + " "
                + ff
                + " "
                + target
            )

        if lat == [-90, 90]:
            nco_command = (
                f"ncea {var_str}  -d "
                + lon_name
                + ","
                + str(float(lon[0]))
                + ","
                + str(float(lon[1]))
                + " "
                + ff
                + " "
                + target
            )

        target = run_nco(nco_command, target)

        new_commands.append(nco_command)

        new_files.append(target)

    self.history += new_commands
    self._hold_history = copy.deepcopy(self.history)

    self.current = new_files

    for ff in new_files:
        remove_safe(ff)

    cleanup()
    self.disk_clean()
