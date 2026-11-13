import glob
import sys
import copy
import multiprocessing as mp
import os
import pandas as pd
import random
import re
import string
import subprocess
import warnings
import urllib.request

from netCDF4 import Dataset

from nctoolkit.cleanup import cleanup, temp_check
from nctoolkit.runthis import run_cdo
from nctoolkit.session import (
    nc_protected,
    nc_protected_par,
    session_info,
    nc_safe,
    session_files,
    append_safe,
    remove_safe,
    append_protected,
    remove_protected,
    append_tempdirs,
)
from nctoolkit.session import nc_safe_par, temp_dirs, temp_dirs_par
from nctoolkit.show import (
    nc_variables,
    nc_years,
    nc_months,
    nc_levels,
    nc_times,
    nc_format,
)
from nctoolkit.temp_file import temp_file


# context manager code so that thredds checks will be stopped if slow
import signal
import time
from contextlib import contextmanager
import xarray as xr


def fix_files(paths):
    """
    A simple function that switches to symlinks when a file path has a space in it

    """
    change = 0
    new_files = []
    for ff in paths:
        if " " in ff:
            change += 1

    if change == 0:
        return paths

    for ff in paths:
        if " " in ff:
            out = temp_file("nc")
            ff_full = os.path.abspath(ff)
            os.symlink(ff_full, out)
            new_files.append(out)
        else:
            new_files.append(ff)
    return new_files


class TimeoutException(Exception):
    pass


@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutException(
            "Timed out. Connecting to the thredds server is very slow!"
        )

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


# A custom format for warnings.
def custom_formatwarning(msg, *args, **kwargs):
    # ignore everything except the message
    return "Warning: " + str(msg) + "\n"


warnings.formatwarning = custom_formatwarning

# set up the session info
letters = string.ascii_lowercase
try:
    login = os.getlogin()
except:
    login = ""
session_info["stamp"] = (
    "nctoolkit_"
    + login
    + "_"
    + "".join(random.choice(letters) for i in range(8))
    + "nctoolkit"
)
session_info["temp_dir"] = "/tmp/"
session_info["user_dir"] = False
session_info["thread_safe"] = False
session_info["lazy"] = True
session_info["precision"] = None
session_info["parallel"] = False
session_info["progress"] = "on"
session_info["checks"] = True
session_info["user"] = ""

# get the cdo methods

read = subprocess.run(
   "cdo --operators", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
).stdout

cdo_methods = [x.split(" ")[0].replace("b'", "") for x in str(read).split("\\n")]

cdo_methods = [mm for mm in cdo_methods if len(mm) > 0]

cdo_methods.append("L")
cdo_methods.append("reduce_dim")
session_info["cdo_methods"] = cdo_methods


session_info["coast"] = None 


session_info["interactive"] = sys.__stdin__.isatty()


result = os.statvfs("/tmp/")
session_info["size"] = result.f_frsize * result.f_bavail


session_info["latest_size"] = 0
session_info["cores"] = 1

append_tempdirs("/tmp")
append_tempdirs("/var/tmp")


def _move_all(source, target):
    """
    Move every item from one session list to another.

    The lists can be plain lists or multiprocessing list proxies. Items are copied
    and then the source is emptied, rather than removing items while looping over
    the source, which would skip every other item.

    Slicing is used to copy, not list(): a multiprocessing list proxy has no
    __iter__, so list() runs until the manager raises IndexError, and that
    exception forms a reference cycle which keeps the calling frames, and so
    DataSets and their temp files, alive until the cyclic collector runs.
    """
    items = source[:]
    if len(items) > 0:
        target.extend(items)
        del source[:]


def update_options(kwargs):
    valid_keys = [
        "thread_safe",
        "lazy",
        "cores",
        "precision",
        "temp_dir",
        "parallel",
        "checks",
        "progress",
        "coast",
        "user",
    ]

    for key in kwargs:
        find = True
        if key not in valid_keys:
            raise AttributeError(key + " is not a valid option")

        if key == "parallel" or key == "lazy" or key == "thread_safe":
            if not isinstance(kwargs[key], bool):
                raise TypeError(f"{key} should be boolean")

        if key == "coast":
            if not isinstance(kwargs[key], bool):
                raise TypeError(f"{key} should be boolean")
            session_info["key"] = kwargs[key]

        if key == "checks":
            if not isinstance(kwargs[key], bool):
                raise TypeError(f"{key} should be boolean")
            find = False

        if not isinstance(kwargs[key], bool) and find:
            if key == "temp_dir":
                if isinstance(kwargs[key], str):
                    if os.path.exists(kwargs[key]) is False:
                        raise ValueError("The temp_dir specified does not exist!")
                    session_info[key] = os.path.abspath(kwargs[key])
                    session_info["user_dir"] = True
                find = False
            if key == "progress" and find:
                if kwargs[key] not in ["on", "off", "auto", "of"]:
                    raise ValueError("progress must be one of 'on', 'off', 'auto'")

                if kwargs[key] == "of":
                    session_info[key] = "off"
                else:
                    session_info[key] = kwargs[key]
                find = False

            if key == "cores" and find:
                if isinstance(kwargs[key], int):
                    if kwargs[key] > mp.cpu_count():
                        raise ValueError(
                            str(kwargs[key])
                            + " is greater than the number of system cores ("
                            + str(mp.cpu_count())
                            + ")"
                        )
                    session_info[key] = kwargs[key]
                    find = False
                else:
                    raise TypeError("cores must be an int")
            else:
                if find:
                    if key == "precision":
                        if kwargs[key] not in [
                            "I8",
                            "I16",
                            "I32",
                            "F32",
                            "F64",
                            "default",
                        ]:
                            raise ValueError("precision supplied is not valid!")
                        if kwargs[key] == "default":
                            session_info[key] = None
                        else:
                            session_info[key] = kwargs[key]
                        find = False
                    else:
                        if key == "user":
                            if not isinstance(kwargs[key], str):
                                raise ValueError("user supplied must be str")
                            if len(session_files()) > 0:
                                raise ValueError(
                                    "You can only define user at the start of a session"
                                )
                            session_info[key] = kwargs[key]
                            session_info["stamp"] = (
                                session_info["stamp"] + "_" + kwargs[key] + "_"
                            )

                            find = False
                        else:
                            raise ValueError(
                                kwargs[key] + " is not valid session info!"
                            )
        else:
            session_info[key] = kwargs[key]

            # update safe-lists etc. if running in parallel
            if kwargs[key] and key == "parallel" and find:
                for ff in list(temp_dirs):
                    append_tempdirs(ff)

                _move_all(nc_safe, nc_safe_par)
                _move_all(nc_protected, nc_protected_par)

            if (kwargs[key] is False) and key == "parallel" and find:
                for ff in temp_dirs_par[:]:
                    append_tempdirs(ff)

                _move_all(nc_safe_par, nc_safe)
                _move_all(nc_protected_par, nc_protected)


def options(**kwargs):
    """
    Define session options.

    Parameters
    ---------------
    **kwargs
        Define options using key, value pairs.
        Set thread_safe = True if hdf5 was built to be thread safe.
        Set lazy = False if you want methods to evaluate non-lazily
        Set cores = n, if you want nctoolkit to process the individual files in multi-file datasets in parallel. Note this
        only applies to multi-file datasets and will not improve performance with single files.
        Set temp_dir = "/foo" if you want to change the temporary directory used by nctoolkit to save temporary files.
        Set  = "/foo" if you want to change the temporary directory used by nctoolkit to save temporary files.
        Set progress to "on" or "off" if you always or never want a progress bar to show when multi-file datasets are processed. This defaults to "auto", i.e.
        nctoolkit will automatically decide whether to show a progress bar based on the size of the ensemble.

    Examples
    ------------

    If you wanted to process the files in multi-file datasets in parallel with 6 cores, do the following:

    >>> import nctoolkit as nc
    >>> nc.options(cores = 6)

    If you want to set evaluation to always be lazy do the following:

    >>> nc.options(lazy = True)

    If you want nctoolkit to store temporary files in a specific directory, do this:

    >>> nc.options(temp_dir = "/foo")

    """

    update_options(kwargs)
    return None


# if nctoolkitrc exists, we need to read the possible options from there...


def find_config():
    # first look in the working directory
    for ff in [".nctoolkitrc", "nctoolkitrc"]:
        if os.path.exists(ff):
            return ff

    # now look in the home directory....
    from os.path import expanduser

    home = expanduser("~")
    for ff in [".nctoolkitrc", "nctoolkitrc"]:
        if os.path.exists(home + "/" + ff):
            return home + "/" + ff

    return None


config_file = find_config()

if config_file is not None:
    # valid_keys = ["thread_safe", "lazy", "cores", "precision", "temp_dir"]

    file1 = open(config_file, "r")
    Lines = file1.readlines()

    count = 0
    # Strips the newline character
    for line in Lines:
        text = line.replace(" ", "").strip()
        if text.count(":") != 1:
            if len(text) > 0:
                raise ValueError(f"Line in {config_file} is invalid: {line}")

    for line in Lines:
        text = line.replace(" ", "").strip()
        if len(text) > 0:
            terms = text.split(":")
            key = terms[0]
            value = None

            if (terms[1].strip() == "True") and value is None:
                value = True

            if (terms[1] == "False") and (value is None):
                value = False

            if (terms[1].isnumeric()) and (value is None):
                value = int(terms[1])

            if value is None:
                value = terms[1]
                value = value.replace("'", "").replace('"', "")
            if len(key) > 0:
                update_options({key: value})


# run temp_check to see if any files are held over from previous sessions
temp_check()


def is_url(x):
    regex = re.compile(
        r"^(?:http|ftp)s?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    return re.match(regex, x) is not None


def convert_bytes(num):
    """
    A function to make file size human readable
    """
    for x in ["bytes", "KB", "MB", "GB", "TB"]:
        if num < 1000.0:
            return str(num) + " " + x
        num /= 1000.0


def file_size(file_path):
    """
    A function to return file size
    """
    if os.path.isfile(file_path):
        file_info = os.stat(file_path)
        return file_info.st_size


def from_xarray(ds):
    """
    Convert an xarray dataset to an nctoolkit dataset
    This will first save the xarray dataset as a temporary netCDF file.

    Parameters
    ---------------
    ds : xarray dataset
        xarray dataset you want to convert to nctoolkit DataSet.

    Returns
    ---------------
    from_xarray : nctoolkit.DataSet
    """
    ff = temp_file(".nc")
    ds.to_netcdf(ff)

    append_safe(ff)

    d = DataSet(ff)
    return d


def open_geotiff(x=[]):
    """
    Open a geotiff and convert to a Dataset
    This requires rioxarray to be installed.

    Parameters
    ---------------
    x : str or list
        A string or list of geotiff files or a single url.
        This requires rioxarray to be installed.

    Returns
    ---------------
    open_geotiff: nctoolkit.DataSet
    """

    if isinstance(x, str):
        x = [x]

    if not isinstance(x, list):
        raise ValueError("List of str was not supplied!")

    try:
        import rioxarray
    except:
        raise ValueError("This requires rioxarray to be installed")

    ds = open_data()
    if len(x) > 0:
        for ff in x:
            raster = rioxarray.open_rasterio(ff)
            out_file = temp_file() + "nc"
            raster.rio.to_raster(out_file)
            ds.append(out_file)
    return ds


def open_data(x=[], checks=True, **kwargs):
    """
    Read netCDF data as a Dataset object

    Parameters
    ---------------
    x : str or list
        A string or list of netCDF files or a single url. The function will check the
        files exist. If x is not a list, but an iterable it will be converted to a list.
        If a *.nc style wildcard is supplied, open_data will use all files available.
        By default an empty dataset is created, ie. using open_data() will create an empty
        dataset that can then be expanded using append.
    checks: boolean
        Do you want basic checks to ensure cdo can read files? Default to True.
        Setting to False can result in a minor speed up.
    **kwargs: kwargs
        Optional arguments for internal use by open_thredds and open_url.

    Returns
    ---------------
    open_data : nctoolkit.DataSet


    Examples
    ------------

    If you want to open a single file as a dataset, do the following:

    >>> import nctoolkit as nc
    >>> ds = nc.open_data("example.nc")

    If you want to open a list of files as a multi-file dataset, you would do something like this:

    >>> import nctoolkit as nc
    >>> ds = nc.open_data(["file1.nc", "file2.nc", "file3.nc"])

    If you wanted to open all files in a directory "data" as a multi-file dataset, you can use a wildcard:

    >>> import nctoolkit as nc
    >>> ds = nc.open_data("data/*.nc")

    """

    if session_info["checks"] is False:
        checks = False

    thredds = False

    ftp_details = None
    wait = None
    file_stop = None

    source = "file"

    for key in kwargs:
        if key == "thredds":
            thredds = kwargs[key]
        if key == "ftp_details":
            ftp_details = kwargs[key]
        if key == "wait":
            wait = kwargs[key]
        if key == "file_stop":
            file_stop = kwargs[key]
        if key == "source":
            source = kwargs[key]

    if isinstance(x, str) and thredds is False:
        x = os.path.expanduser(x)
        if is_url(x) is False:
            x = glob.glob(x)
            if len(x) == 0:
                raise FileNotFoundError("Please provide files that exist")

    # make sure data has been supplied
    if x is None:
        raise ValueError("No data was supplied!")

    # coerce an iterable to a list
    if not isinstance(x, str):
        x = [y for y in x]
        for ff in x:
            if not isinstance(ff, str):
                raise TypeError("You have not supplied an iterable made of file paths!")

    if isinstance(x, str):
        x = [x]

    if isinstance(x, list):
        x = [os.path.expanduser(y) for y in x]
        x = fix_files(x)

    if isinstance(x, list):
        if len(x) == 1:
            x = x[0]

    # check the files provided exist
    stop_time = 10000000000000000000000000000000000
    if wait is not None:
        stop_time = min(wait, stop_time)
    if file_stop is not None:
        stop_time = min(file_stop, stop_time)

    if isinstance(x, str):
        x = os.path.expanduser(x)
        if source != "file" or os.path.exists(x) is False:
            if is_url(x):
                if thredds is False:
                    new_x = temp_file(".nc")

                    if ftp_details is not None and x.startswith("ftp"):
                        user = ftp_details["user"]
                        password = ftp_details["password"]
                        x = x.replace("ftp://", f"ftp://{user}:{password}@")

                    start = time.time()

                    search = True
                    while search:
                        if os.path.exists(new_x) is False:
                            try:
                                # work out if there is a time limit for individual files
                                if stop_time != 10000000000000000000000000000000000:
                                    with time_limit(stop_time):
                                        urllib.request.urlretrieve(x, new_x)
                                else:
                                    urllib.request.urlretrieve(x, new_x)
                            except:
                                nothing = "x"
                        search += 1
                        if os.path.exists(new_x):
                            break

                        if wait is None:
                            if search == 3:
                                break
                        else:
                            end = time.time()
                            if (end - start) > wait:
                                break
                    if os.path.exists(new_x) is False:
                        raise ValueError(f"Could not download {x}")

                    x = new_x
                else:
                    if checks:
                        if wait is not None:
                            with time_limit(stop_time):
                                out = subprocess.run(
                                    "cdo sinfo " + x,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                )
                                if "Open failed" in str(out.stderr):
                                    raise ValueError(f"{x} is not compatible with CDO!")

            else:
                raise FileNotFoundError("Data set " + x + " does not exist!")

        if checks:
            out = subprocess.run(
                "cdo sinfo " + x,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if "Open failed" in out.stderr.decode("utf-8"):
                mes = (
                    out.stderr.decode("utf-8")
                    .replace("cdo    sinfo: ", "")
                    .replace("<\n", "")
                    .replace("\n", "")
                )
                mes = re.sub(" +", " ", mes)
                raise ValueError(mes)

            append_safe(x)
            append_protected(x)

        else:
            append_safe(x)
            append_protected(x)

    # it's possible there are duplicates in the data
    # Get rid of them..
    # Note: This will also ensure the original list is deep copied

    if isinstance(x, list):
        orig_size = len(x)
        x = list(dict.fromkeys(x))
        if len(x) < orig_size:
            warnings.warn(message="Duplicates in data set have been removed!")

    if isinstance(x, list):
        if source == "url":
            for ff in x:
                if is_url(ff) is False:
                    raise ValueError(f"{x} is not a url")

            new_files = []
            for ff in x:
                if is_url(ff):
                    if thredds is False:
                        new_x = temp_file(".nc")

                        if ftp_details is not None and x.startswith("ftp"):
                            user = ftp_details["user"]
                            password = ftp_details["password"]
                            ff = ff.replace("ftp://", f"ftp://{user}:{password}@")

                        start = time.time()

                        search = True
                        while search:
                            if os.path.exists(new_x) is False:
                                try:
                                    # work out if there is a time limit for individual files
                                    if stop_time != 10000000000000000000000000000000000:
                                        with time_limit(stop_time):
                                            urllib.request.urlretrieve(ff, new_x)
                                    else:
                                        urllib.request.urlretrieve(ff, new_x)
                                except:
                                    nothing = "x"
                            search += 1
                            if os.path.exists(new_x):
                                break

                            if wait is None:
                                if search == 3:
                                    break
                            else:
                                end = time.time()
                                if (end - start) > wait:
                                    break
                        if os.path.exists(new_x) is False:
                            raise ValueError(f"Could not download {x}")

                        new_files.append(new_x)
                x = new_files

    if isinstance(x, list) and source != "url":
        if thredds is False:
            for ff in x:
                if os.path.exists(ff) is False:
                    raise FileNotFoundError(f"{ff} does not exist!")
            for ff in x:
                append_safe(ff)
                append_protected(ff)

            if len(x) > 1:
                for ff in x:
                    if os.path.exists(ff) is False:
                        raise FileNotFoundError("Data set " + ff + " does not exist!")

    # if there is only one file in the list, change it to a single file
    if isinstance(x, list):
        if len(x) == 1:
            x = x[0]

    d = DataSet(x)
    d._thredds = thredds

    if (len(d) == 1) and checks and (thredds is False):
        d_contents = d.contents.reset_index(drop=True)
        try:
            d_sub = d_contents.query("fill_value == 0.0").reset_index(drop=True)
            if len(d_sub) > 0:
                file_out = ",".join(list(d_sub.variable))
                warnings.warn(
                    f"These variables have 0 as the fill value: {file_out}. Set to a different fill value if you are using sensitive methods."
                )
        except:
            # warning will be trigger, so no need to do anything
            blah = "blah"

        list1 = d_contents.data_type
        positions = [ind for ind, x in enumerate(list1) if x.startswith("I")]
        if len(positions):
            bad = list(d.contents.reset_index(drop=True).variable[positions])

        # df = d.contents.reset_index(drop=True).query("'I' in data_type")
        if len(positions) > 0:
            check = ",".join(bad)
            if "," in check:
                warnings.warn(
                    message=f"The variable(s) {check} have integer data type. Consider setting data type to float 'F64' or 'F32' using set_precision."
                )
            else:
                warnings.warn(
                    message=f"The variable {check} has integer data type. Consider setting data type to float 'F64' or 'F32' using set_precision."
                )

    return d


def open_thredds(x=None, wait=None, checks=False):
    """
    Read thredds data as a Dataset object

    Parameters
    ---------------
    x : str or list
        A string or list of thredds urls, which must end with .nc.
    checks : boolean
        Do you want to check if data is available over thredds?
    wait : int
        Time to wait for thredds server to be checked. Limitless if not supplied.

    Returns
    ---------------
    open_thredds : nctoolkit.DataSet

    Examples
    ------------

    If you want to open a file available over thredds or opendap, do the following:

    >>> import nctoolkit as nc
    >>> ds = nc.open_thredds("htttp:://foo.nc")


    """

    if not isinstance(checks, bool):
        raise TypeError("Please provide boolean for checks")

    if wait is not None:
        if not isinstance(wait, (int, float)):
            raise TypeError("Please provide an integer for wait!")
        if wait <= 0:
            raise ValueError("Please provide a positive value for wait!")

    if session_info["cores"] > 1:
        warnings.warn(
            message="Using multiple cores on thredds data is volatile. It has therefore been reset to 1."
        )
        session_info["cores"] = 1

    return open_data(x=x, thredds=True, wait=wait, checks=checks, source="thredds")


def open_url(x=None, ftp_details=None, wait=None, file_stop=None):
    """
    Read netCDF data from a url as a DataSet object

    Parameters
    ---------------
    x : str
        A string with a url. Prior to processing data will be downloaded to
        a temp folder.
    ftp_details : dict
        A dictionary giving the user name and password combination for ftp downloads: {"user":user, "password":pass}
    wait : int
        Time to wait, in seconds, for data to download. A minimum of 3 attempts will be made to download the data.
    file_stop : int
        Time limit, in minutes, for individual attempts at downloading data. This is useful to get around download freezes.

    Returns
    ---------------
    open_url : nctoolkit.DataSet

    Examples
    ------------

    If you want to open a file available over a url do the following:

    >>> import nctoolkit as nc
    >>> ds = nc.open_url("htttp:://foo.nc")

    This will download the file as a temporary folder for use in the dataset.

    """

    if wait is not None:
        if not isinstance(wait, int):
            raise TypeError("Please provide a valid wait!")

        if wait <= 0:
            raise TypeError("Please provide a valid wait!")

    if file_stop is not None:
        if not isinstance(file_stop, int):
            raise TypeError("Please provide a valid file_stop!")

        if file_stop <= 0:
            raise TypeError("Please provide a valid file_stop!")

    if ftp_details is not None:
        if len(ftp_details) != 2:
            raise ValueError("ftp_details is not a 2 element dictionary")

        user = ftp_details[list(ftp_details.keys())[0]]
        password = ftp_details[list(ftp_details.keys())[1]]
        new_dict = {"user": user, "password": password}
    else:
        new_dict = None

    return open_data(
        x=x, ftp_details=new_dict, wait=wait, file_stop=file_stop, source="url"
    )


def merge(*datasets, match=["day", "year", "month"]):
    """
    Merge datasets

    Parameters
    -------------
    datasets: kwargs
        Datasets to merge.
    match: list
        Temporal matching criteria. This is a list which must be made up of a subset of
        day, year, month. This checks that the datasets have compatible times.
        For example, if you want to ensure the datasets have the same years, then use
        match = ["year"].
    """
    # A deprecation warning:
    warnings.warn(
        "This method is deprecated. Use the append and merge approach instead.",
        DeprecationWarning,
    )

    all_files = []
    for dataset in datasets:
        if not isinstance(dataset, DataSet):
            raise TypeError("Please check everything is a DataSet object!")
        # make sure everything has been evaluated
        dataset.run()
        all_files += dataset.current
    result = open_data(all_files)
    result.merge(match=match)
    return result


def cor_time(x=None, y=None):
    """
    Calculate the temporal correlation coefficient between two datasets
    This will calculate the temporal correlation coefficient, for each time step,
    between two datasets. The datasets must either have the same variables or only
    have one variable.

    Parameters
    -------------
    x: dataset
        First dataset to use
    y: dataset
        Second dataset to use

    Returns
    -------------
    cor_time: nctoolkit Dataset
        A dataset containing the temporal correlation coefficient for each grid cell
    """

    if not isinstance(x, DataSet):
        raise TypeError("Please check x is a dataset")

    if not isinstance(y, DataSet):
        raise TypeError("Please check y is a dataset")
        # make sure everything has been evaluated

    x.run()
    y.run()

    df = (
        x.contents.loc[:, ["variable", "data_type"]]
        .rename(columns={"data_type": "type1"})
        .merge(
            y.contents.loc[:, ["variable", "data_type"]].rename(
                columns={"data_type": "type2"}
            )
        )
        .query("type1 != type2")
    )
    if len(df) > 0:
        raise ValueError(
            "Datasets have different data types. Please unify them using set_precision"
        )

    if len(x) > 1 or len(y) > 1:
        raise TypeError("cor_time only accepts single file datasets!")

    a = x.copy()
    b = y.copy()

    if x.variables != y.variables:
        if len(x.variables) > 1 or len(y.variables) > 1:
            raise ValueError(
                "This method currently only works with single variable datasets or "
                "datasets with identical variables!"
            )

    target = temp_file("nc")

    if len(x.variables) == 1:
        command = (
            "cdo -setname,cor -timcor "
            + a.current[0]
            + " "
            + b.current[0]
            + " "
            + target
        )
    else:
        command = "cdo -timcor " + a.current[0] + " " + b.current[0] + " " + target

    target = run_cdo(command, target=target, precision=x._precision)

    data = open_data(target)

    remove_safe(target)

    return data


def cor_space(x=None, y=None):
    """
    Calculate the spatial correlation coefficient between two datasets
    This will calculate the spatial correlation coefficient, for each time step,
    between two datasets. The datasets must either have the same variables or only
    have one variable.

    Returns
    -------------
    cor_space: nctoolkit Dataset
        A dataset containing the correlation coefficient for each time step.

    Parameters
    -------------
    x: dataset
        First dataset to use
    y: dataset
        Second dataset to use
    """

    if not isinstance(x, DataSet):
        raise TypeError("Please check x is a dataset")

    if not isinstance(y, DataSet):
        raise TypeError("Please check y is a dataset")
        # make sure everything has been evaluated

    x.run()
    y.run()

    df = (
        x.contents.loc[:, ["variable", "data_type"]]
        .rename(columns={"data_type": "type1"})
        .merge(
            y.contents.loc[:, ["variable", "data_type"]].rename(
                columns={"data_type": "type2"}
            )
        )
        .query("type1 != type2")
    )
    if len(df) > 0:
        raise ValueError(
            "Datasets have different data types. Please unify them using set_precision"
        )

    if len(x) > 1 or len(y) > 1:
        raise TypeError("cor_time only accepts single file datasets!")

    a = x.copy()
    b = y.copy()

    if x.variables != y.variables:
        if len(x.variables) > 1 or len(y.variables) > 1:
            raise ValueError(
                "This method currently only works with single variable datasets "
                "or datasets with identical variables!"
            )

    target = temp_file("nc")

    if len(x.variables) == 1:
        command = (
            "cdo -setname,cor -fldcor "
            + a.current[0]
            + " "
            + b.current[0]
            + " "
            + target
        )
    else:
        command = "cdo -fldcor " + a.current[0] + " " + b.current[0] + " " + target

    target = run_cdo(command, target=target, precision=x._precision)

    data = open_data(target)

    remove_safe(target)

    return data


class DataSet(object):
    """
    A modifiable ensemble of netCDF files
    """

    def __init__(self, start=""):
        """Initialize the starting file name etc"""
        # Attribuates of interest to users
        self.history = []
        self.start = start
        if isinstance(start, str):
            self._current = [start]
        else:
            self._current = start

        # attributes to the module, but not users (probably)
        if session_info["lazy"]:
            self._execute = False
        else:
            self._execute = True
        self._hold_history = []
        self._merged = False
        self._safe = []
        # some trackers to make end of the chain processing easier
        self._thredds = False
        self._zip = False
        self._format = None
        self._align = ""

        self._precision = "default"

        self._grid = None
        self._weights = None

        # FVCOM output, opened by open_fvcom
        # fvcom: is the dataset on an FVCOM mesh?
        # fvcom_thickness: the variable holding the thickness of the sigma layers
        self.fvcom = False
        self.fvcom_thickness = None
        self._mesh_file = None

        # track number of held over commands
        self._ncommands = 0

        # add a dictionary for caching attributes
        self._atts = dict()

        self._atts["variables"] = [None, -1]
        self._atts["months"] = [None, -1]
        self._atts["levels"] = [None, -1]
        self._atts["times"] = [None, -1]
        self._atts["calendar"] = [None, -1]
        self._atts["size"] = [None, -1]
        self._atts["ncformat"] = [None, -1]
        self._atts["years"] = [None, -1]
        self._atts["calendar"] = [None, -1]
        self._atts["contents"] = [None, -1]



    def __getitem__(self, index):
        return self.current[index]

    def __len__(self):
        return len(self.current)

    def __iter__(self):
        for ff in self.current:
            yield ff
        return

    def __repr__(self):
        self.run()
        if len(self) == 0:
            return "Empty dataset"
        current = str(len(self))

        output = "<nctoolkit.DataSet>:\nNumber of files: " + current
        output = output + "\n" + "File contents:"
        # repr_params = fmt.get_dataframe_repr_params()
        output += "\n"
        output += self.show_contents(min(12, len(self))).to_string()
        output += "\n"
        if len(self) > 12:
            output += "......"
        return output

    @property
    def size(self):
        """The size of an object
        This will print the number of files, total size, and smallest and largest files
        in an DataSet object.

        Returns
        -------------
        size: dict
            A dictionary containing the number of files, total size, and smallest and
        """
        self.run()
        all_sizes = []

        min_size = 1e15
        max_size = -1

        for ff in self:
            all_sizes.append(file_size(ff))

            if file_size(ff) > max_size:
                max_size = file_size(ff)

            if file_size(ff) < min_size:
                min_size = file_size(ff)

        min_size = convert_bytes(min_size)
        max_size = convert_bytes(max_size)

        sum_size = convert_bytes(sum(all_sizes))
        result = dict()

        result["Number of files in ensemble"] = len(self)
        result["Ensemble size"] = sum_size
        result["Smallest file size"] = min_size
        result["Largest file size"] = max_size
        return result

    @property
    def calendar(self):
        """
        List calendars of dataset files

        Returns
        -------
        list
            List of calendars in the dataset files

        """

        self.run()

        n_commands = self._atts["calendar"][1]

        if n_commands == len(self._hold_history):
            return self._atts["calendar"][0]

        cals = []
        for ff in self:
            with Dataset(ff) as ds:
                for x in [x for x in ds.variables.keys() if "time" in x]:
                    y = ds.variables[x]
                    try:
                        cal = y.getncattr("calendar")
                    except:
                        cal = None
                    if cal is not None:
                        break
            if cal is None:
                raise ValueError("Unable to parse the calendars")

            cals.append(pd.DataFrame({"file": ff, "calendar": [cal]}))

        cals = pd.concat(cals).reset_index(drop=True)

        if len(set(cals.calendar)) == 1:
            self._atts["calendar"][0] = cals.calendar[0]
            return cals.calendar[0]

        self._atts["calendar"][1] = len(self._hold_history)

        self._atts["calendar"][0] = cals

        return cals

    @property
    def variables(self):
        """
        List variables contained in a dataset

        Returns
        -------
        list
            List of variables

        """

        self.run()

        n_commands = self._atts["variables"][1]

        if n_commands == len(self._hold_history):
            return self._atts["variables"][0]


        all_variables = []
        for ff in self:
            all_variables += nc_variables(ff)

        all_variables = list(set(all_variables))

        all_variables.sort()

        # populate the atts dictionary

        self._atts["variables"][0] = all_variables
        self._atts["variables"][1] = len(self._hold_history)


        return all_variables

    @property
    def months(self):
        """
        List months contained in a dataset

        Returns
        -------
        list
            List of months in the dataset
        """

        self.run()

        n_commands = self._atts["months"][1]

        if n_commands == len(self._hold_history): 
            return self._atts["months"][0]

        all_months = []
        for ff in self:
            all_months += nc_months(ff)

        all_months = list(set(all_months))

        all_months.sort()

        # populate the atts dictionary

        self._atts["months"][0] = all_months
        self._atts["months"][1] = len(self._hold_history)

        return all_months

    @property
    def levels(self):
        """
        List levels contained in a dataset

        Returns
        -------
        list
            List of levels in the dataset

        """

        self.run()

        n_commands = self._atts["levels"][1]

        if n_commands == len(self._hold_history):
            return self._atts["levels"][0]

        all_levels = []
        for ff in self:
            all_levels += nc_levels(ff)

        all_levels = list(set(all_levels))

        all_levels.sort()

        # populate the atts dictionary

        self._atts["levels"][0] = all_levels
        self._atts["levels"][1] = len(self._hold_history)


        return all_levels

    @property
    def times(self):
        """
        List times contained in a dataset

        Returns
        -------
        list
            List of times in the dataset
        """

        self.run()

        n_commands = self._atts["times"][1]

        if n_commands == len(self._hold_history):
            return self._atts["times"][0]


        all_times = []
        for ff in self:
            all_times += nc_times(ff)

        all_times = list(set(all_times))

        all_times.sort()

        # populate the atts dictionary

        self._atts["times"][0] = all_times
        self._atts["times"][1] = len(self._hold_history)


        return all_times

    @property
    def ncformat(self):
        """
        List formats of files contained in a dataset

        Return
        ------
        list
            List of netCDF formats in the dataset
        """

        self.run()

        all_formats = []
        for ff in self:
            all_formats += nc_format(ff)

        all_formats = list(set(all_formats))

        all_formats.sort()

        return all_formats

    @property
    def years(self):
        """
        List years contained in a dataset

        Returns
        -------
        list
            List of years in the dataset

        """

        self.run()

        n_commands = self._atts["years"][1]

        if n_commands == len(self._hold_history):
            return self._atts["years"][0]

        all_years = []
        for ff in self:
            all_years += nc_years(ff)

        all_years = list(set(all_years))

        all_years.sort()

        # populate the atts dictionary

        self._atts["years"][0] = all_years

        self._atts["years"][1] = len(self._hold_history)


        return all_years

    def show_contents(self, n=None):
        """
        Detailed list of variables contained in a dataset.
        This will only display the variables in the first file of an ensemble.
        """

        try:
            if n is None:
                n = len(self)

            list_contents = []

            use_names = True

            for ff in self:
                if "nctoolkit" in ff:
                    use_names = False

            for ff in self[0:n]:
                with Dataset(ff) as dataset:
                    out = subprocess.run(
                        "cdo sinfon " + ff,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if "Unsupported file structure" in str(out.stderr):
                        for ff in self:
                            remove_safe(ff)
                            remove_protected(ff)
                        raise ValueError(
                            "Unsupported file structure. Check file using the check method."
                        )
                    if "expandWildCards" in out.stderr.decode("utf-8"):
                        for ff in self:
                            remove_safe(ff)
                            remove_protected(ff)
                        raise ValueError(out.stderr.decode("utf-8"))
                    out = out.stdout.decode("utf-8")
                    out = out.split("\n")
                    out_inc = ["Grid coordinates :" in ff for ff in out]
                    var_det = []
                    i = 1
                    while True:
                        if out_inc[i]:
                            break
                        i += 1
                        var_det.append(out[i - 1])

                    def split_var(x):
                        x = x.replace(":", "").split(" ")
                        x = [x for x in x if len(x) > 0]
                        new_x = []
                        include = False
                        for y in x[1:]:
                            if y.isnumeric():
                                include = True

                            if include:
                                new_x.append(y)
                        return new_x

                    def fix_head(x):
                        x = (
                            x.replace(":", "")
                            .replace("  ", " ")
                            .replace("Parameter name", "variable")
                        )
                        x = x[x.find("Level") :].replace("  ", " ")
                        return x.split(" ")

                    def fix_type(x):
                        position = [m.start() for m in re.finditer(":", x)][-1]

                        return (
                            x[: (position - 4)]
                            + x[(position - 4) : position].replace(" ", "")
                            + " "
                            + x[(position):]
                        )

                    var_det[0] = fix_head(var_det[0])
                    for ii in range(1, len(var_det)):
                        var_det[ii] = fix_type(var_det[ii])
                        var_det[ii] = split_var(var_det[ii])

                    df = pd.DataFrame.from_records(var_det[1:], columns=var_det[0])
                    df = df.loc[:, ["Levels", "Points", "variable", "Dtype"]]
                    df = df.rename(
                        columns={
                            "Levels": "nlevels",
                            "Points": "npoints",
                            "Dtype": "data_type",
                        }
                    )

                    longs = None
                    units = None
                    longs = []

                    cdo_result = list(df.variable)

                    for x in cdo_result:
                        try:
                            longs.append(dataset.variables[x].long_name)
                        except:
                            longs.append(None)
                    units = []
                    for x in cdo_result:
                        try:
                            units.append(dataset.variables[x].units)
                        except:
                            units.append(None)

                    df = pd.DataFrame({"variable": cdo_result}).merge(df)

                    if longs is not None:
                        df["long_name"] = longs
                    if units is not None:
                        df["unit"] = units

                    df = df.assign(nlevels=lambda x: x.nlevels.astype("int")).assign(
                        npoints=lambda x: x.npoints.astype("int")
                    )

                    try:
                        times = []

                        with xr.open_dataset(ff, decode_times=False) as ds:
                            time_name = [x for x in ds.variables if "time" in x]

                            # get time name

                            if len(time_name) > 0:
                                time_name = time_name[0]
                            else:
                                time_name = "time"

                            for vv in cdo_result:
                                done = False
                                try:
                                    ds_times = ds[vv][time_name].values
                                except:
                                    times.append(None)
                                    done = True

                                if done is False:
                                    try:
                                        n_times = len(ds_times)
                                    except:
                                        n_times = 1
                                    times.append(n_times)

                        df["ntimes"] = times

                        df = df.loc[
                            :,
                            [
                                "variable",
                                "ntimes",
                                "npoints",
                                "nlevels",
                                "long_name",
                                "unit",
                                "data_type",
                            ],
                        ]
                        try:
                            fills = []
                            for vv in df.variable:
                                fills.append(dataset.variables[vv]._FillValue)
                            df["fill_value"] = fills
                        except:
                            df = df

                        list_contents.append(df.assign(file=ff))
                    except:
                        warnings.warn(
                            "Potential data format issues identified. Consider running check!"
                        )
                        df = df.loc[
                            :,
                            [
                                "variable",
                                "npoints",
                                "nlevels",
                                "long_name",
                                "unit",
                                "data_type",
                            ],
                        ]
                        list_contents.append(df.assign(file=ff))

            if len(list_contents) == 1:
                return list_contents[0].drop(columns="file")

            if use_names is False:
                new_df = []
                i = 1
                for x in list_contents:
                    new_df.append(x.assign(file=f"file {i}"))
                    i += 1

                new_df = pd.concat(new_df)

                if len(set(new_df.file)) == 1:
                    return new_df.drop(columns="file")
                else:
                    new_df = new_df.set_index("file")
                    return new_df
            else:
                return pd.concat(list_contents).set_index("file")
        except:
            raise ValueError(
                "Unable to parse dataset contents. Consider running checks on dataset"
            )

    @property
    def contents(self):
        """
        Detailed list of variables contained in a dataset.
        This will only display the variables in the first file of an ensemble.

        Returns
        -------
        pandas.DataFrame
            A pandas dataframe containing the variables, number of points, number of levels, long name, units, and data type of each variable in the dataset.
        """

        self.run()

        n_commands = self._atts["contents"][1]

        if n_commands == len(self._hold_history):
            return self._atts["contents"][0]
        
        df = self.show_contents()
        self._atts["contents"][0] = df
        self._atts["contents"][1] = len(self._hold_history)

        return df

    @property
    def start(self):
        """
        The starting file or files of the DataSet object

        Returns
        -------
        list
            A list of the starting files in the DataSet object
        """
        return self._start

    @start.setter
    def start(self, value):
        if isinstance(value, str):
            self._start = [value]
        if isinstance(value, list):
            self._start = value

    @property
    def current(self):
        """
        The current file or files in the DataSet object

        Returns
        -------
        list
            A list of the current files in the DataSet object
        """
        return self._current

    @current.setter
    def current(self, value):
        for ff in self:
            remove_safe(ff)

        if isinstance(value, str):
            append_safe(value)
            self._current = [value]
        if isinstance(value, list):
            self._current = value

            for ff in value:
                append_safe(ff)

    @property
    def history(self):
        """
        The history of operations on the DataSet

        Returns
        -------
        list
            A list of the operations performed on the DataSet
        """
        return self._history

    @history.setter
    def history(self, value):
        self._history = value

    @property
    def _fvcom_mesh(self):
        """The file holding the FVCOM mesh, used when regridding"""
        return getattr(self, "_mesh_file", None)

    @_fvcom_mesh.setter
    def _fvcom_mesh(self, value):
        # the mesh file is kept while any dataset uses it
        old = getattr(self, "_mesh_file", None)
        if value is not None:
            append_safe(value)
        if old is not None:
            remove_safe(old)
        self._mesh_file = value

    def copy(self):
        """
        Make a deep copy of an DataSet object.
        Note: This will not make disk copies of the temporary files underlying datasets, so it will be disk-space efficient.

        Returns
        ---------------
        copy: nctoolkit DataSet
        """
        self.run()

        new = copy.deepcopy(self)
        for ff in new:
            append_safe(ff)
        if new._mesh_file is not None:
            append_safe(new._mesh_file)
        if self._weights is not None:
            append_safe(self._weights)
            append_safe(self._grid)
        return new

    def __del__(self):
        if self is not None:
            for ff in self:
                if ff is not None:
                    try:
                        remove_safe(ff)
                    except:
                        blah = "blah"
            for ff in self._safe:
                if ff is not None:
                    try:
                        remove_safe(ff)
                    except:
                        blah = "blah"
            if self._weights is not None:
                remove_safe(self._weights)
            if self._weights is not None:
                remove_safe(self._grid)
            if getattr(self, "_mesh_file", None) is not None:
                try:
                    remove_safe(self._mesh_file)
                except:
                    blah = "blah"

        try:
            cleanup()
        except:
            blah = "blah"

    @start.deleter
    def start(self):
        raise AttributeError("You cannot delete the start point")

    # import the methods

    from nctoolkit.add_etc import abs
    from nctoolkit.add_etc import add
    from nctoolkit.add_etc import exp
    from nctoolkit.add_etc import log
    from nctoolkit.add_etc import log10
    from nctoolkit.add_etc import subtract
    from nctoolkit.add_etc import multiply
    from nctoolkit.add_etc import divide
    from nctoolkit.add_etc import power
    from nctoolkit.add_etc import square
    from nctoolkit.add_etc import sqrt
    from nctoolkit.add_etc import day_stat
    from nctoolkit.add_etc import rmse
    from nctoolkit.add_etc import __add__
    from nctoolkit.add_etc import __truediv__
    from nctoolkit.add_etc import __sub__
    from nctoolkit.add_etc import __mul__
    from nctoolkit.add_etc import __pow__

    from nctoolkit.anomaly import annual_anomaly
    from nctoolkit.anomaly import monthly_anomaly

    from nctoolkit.append import append
    from nctoolkit.append import remove

    from nctoolkit.assign import assign

    from nctoolkit.cdo_command import cdo_command
    from nctoolkit.cellareas import cell_area

    from nctoolkit.centres import centre

    from nctoolkit.checks import check
    from nctoolkit.checks import is_corrupt

    from nctoolkit.cleanup import disk_clean

    from nctoolkit.clear import reset

    from nctoolkit.compare import compare
    from nctoolkit.compare import __eq__
    from nctoolkit.compare import __gt__
    from nctoolkit.compare import __lt__
    from nctoolkit.compare import __le__
    from nctoolkit.compare import __ge__
    from nctoolkit.compare import __ne__

    from nctoolkit.compare_data import gt
    from nctoolkit.compare_data import lt
    from nctoolkit.compare_data import le
    from nctoolkit.compare_data import ge
    from nctoolkit.compare_data import ne
    from nctoolkit.compare_data import eq

    from nctoolkit.corr import cor_space
    from nctoolkit.corr import cor_time

    from nctoolkit.crop import crop

    from nctoolkit.distgrid import distribute

    from nctoolkit.drop import drop

    from nctoolkit.ensembles import ensemble_mean
    from nctoolkit.ensembles import ensemble_max
    from nctoolkit.ensembles import ensemble_median
    from nctoolkit.ensembles import ensemble_min
    from nctoolkit.ensembles import ensemble_range
    from nctoolkit.ensembles import ensemble_stdev
    from nctoolkit.ensembles import ensemble_sum
    from nctoolkit.ensembles import ensemble_var

    from nctoolkit.ensembles import ensemble_percentile

    from nctoolkit.esoteric import assign_coords
    from nctoolkit.esoteric import fix_nemo_ersem_grid
    from nctoolkit.esoteric import fix_amm7_grid
    from nctoolkit.esoteric import set_gridtype
    from nctoolkit.esoteric import no_leaps
    from nctoolkit.esoteric import as_double
    from nctoolkit.esoteric import as_type

    from nctoolkit.fill import fill_na

    from nctoolkit.fldstat import spatial_mean
    from nctoolkit.fldstat import spatial_min
    from nctoolkit.fldstat import spatial_max
    from nctoolkit.fldstat import spatial_range
    from nctoolkit.fldstat import spatial_stdev
    from nctoolkit.fldstat import spatial_sum
    from nctoolkit.fldstat import spatial_percentile
    from nctoolkit.fldstat import spatial_var

    from nctoolkit.fldstat import box_mean
    from nctoolkit.fldstat import box_max
    from nctoolkit.fldstat import box_min
    from nctoolkit.fldstat import box_sum
    from nctoolkit.fldstat import box_range

    from nctoolkit.format import format

    from nctoolkit.inttime import time_interp
    from nctoolkit.inttime import timestep_interp

    from nctoolkit.invert import invert

    from nctoolkit.masking import mask_box

    from nctoolkit.mergers import collect
    from nctoolkit.mergers import merge

    from nctoolkit.meridonials import meridonial_mean
    from nctoolkit.meridonials import meridonial_min
    from nctoolkit.meridonials import meridonial_max
    from nctoolkit.meridonials import meridonial_range

    from nctoolkit.mp_matchers import match_points

    from nctoolkit.nco_command import nco_command

    from nctoolkit.phenology import phenology


    from nctoolkit.plot import plot
    from nctoolkit.static_plot import pub_plot
    from nctoolkit.static_plot import quiver_plot

    from nctoolkit.reduce import reduce_dims

    from nctoolkit.reduce_grid import reduce_grid

    from nctoolkit.regrid import regrid

    from nctoolkit.rename import rename

    from nctoolkit.resample import resample_grid

    from nctoolkit.rollstat import rolling_mean
    from nctoolkit.rollstat import align
    from nctoolkit.rollstat import rolling_min
    from nctoolkit.rollstat import rolling_max
    from nctoolkit.rollstat import rolling_range
    from nctoolkit.rollstat import rolling_sum
    from nctoolkit.rollstat import rolling_stdev
    from nctoolkit.rollstat import rolling_var

    from nctoolkit.run import run

    from nctoolkit.subset import subset

    from nctoolkit.set import set

    from nctoolkit.setters import set_date
    from nctoolkit.setters import set_year
    from nctoolkit.setters import set_day
    from nctoolkit.setters import as_missing
    from nctoolkit.setters import set_fill
    from nctoolkit.setters import set_units
    from nctoolkit.setters import set_longnames
    from nctoolkit.setters import set_precision
    from nctoolkit.setters import missing_as

    from nctoolkit.shift import shift

    from nctoolkit.split import split

    from nctoolkit.strip_vars import strip_variables
    from nctoolkit.sumall import sum_all

    from nctoolkit.temporal_stat import tmean
    from nctoolkit.temporal_stat import tpercentile
    from nctoolkit.temporal_stat import tmax
    from nctoolkit.temporal_stat import tmedian
    from nctoolkit.temporal_stat import tmin
    from nctoolkit.temporal_stat import trange
    from nctoolkit.temporal_stat import tvar
    from nctoolkit.temporal_stat import tstdev
    from nctoolkit.temporal_stat import tsum
    from nctoolkit.temporal_stat import tcumsum
    from nctoolkit.temporal_stat import na_count
    from nctoolkit.temporal_stat import na_frac

    from nctoolkit.thresholds import first_above
    from nctoolkit.thresholds import first_below
    from nctoolkit.thresholds import last_above
    from nctoolkit.thresholds import last_below

    from nctoolkit.to_lonlat import to_latlon

    from nctoolkit.to_nc import to_nc

    from nctoolkit.transect import to_transect

    from nctoolkit.toxarray import to_xarray
    from nctoolkit.toxarray import to_dataframe

    from nctoolkit.tozlev import to_zlevels

    from nctoolkit.verticals import vertical_mean
    from nctoolkit.verticals import vertical_min
    from nctoolkit.verticals import vertical_max
    from nctoolkit.verticals import vertical_range
    from nctoolkit.verticals import vertical_sum
    from nctoolkit.verticals import vertical_integration
    from nctoolkit.verticals import vertical_cumsum
    from nctoolkit.verticals import top
    from nctoolkit.verticals import vertical_interp
    from nctoolkit.verticals import bottom
    from nctoolkit.verticals import bottom_mask
    from nctoolkit.verticals import surface_mask
    from nctoolkit.verticals import generate_level_bounds

    from nctoolkit.zip import zip

    from nctoolkit.zonals import zonal_mean
    from nctoolkit.zonals import zonal_min
    from nctoolkit.zonals import zonal_max
    from nctoolkit.zonals import zonal_range
    from nctoolkit.zonals import zonal_sum

    # deprecated methods
    from nctoolkit.deprecated import invert_levels
