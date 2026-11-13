import glob
import copy
import os

from nctoolkit.cleanup import cleanup
from nctoolkit.temp_file import temp_file
from nctoolkit.session import session_info, get_tempdirs, append_safe, remove_safe
from nctoolkit.fvcom import not_for_fvcom


def dist_cdo(self, i=None, j=None):
    """
    Method to split files by period
    """
    # this cannot me chained. So release
    self.run()

    new_files = []

    commands = []

    bases = []

    for ff in self:
        # We need to split the file by name
        # But, first we need to check if there is space in the output folder
        # If there isn't, we need to switch to the /var/tmp

        if session_info["temp_dir"] == "/tmp/":
            result = os.statvfs("/tmp/")
            result = result.f_frsize * result.f_bavail
            session_info["size"] = result

            if os.path.getsize(ff) * 2 > session_info["size"]:
                session_info["temp_dir"] = "/var/tmp/"

        split_base = temp_file()
        bases.append(split_base)

        # add split base to the save list in case splitting fails. This means they can be cleared up later

        append_safe(split_base)

        cdo_command = f"cdo -s -distgrid,{i},{j} {ff} {split_base}"

        os.system(cdo_command)

        commands.append(cdo_command)

        # now, pull out the files generated

        counter = 0
        for directory in get_tempdirs():
            mylist = [f for f in glob.glob(f"{directory}/*.nc*")]
            mylist = [f for f in mylist if session_info["stamp"] in f]
            for ff in mylist:
                if split_base in ff:
                    new_files.append(ff)
                    counter += 1

        if counter == 0:
            raise ValueError("Splitting the file did not work!")

    self.history += commands
    self._hold_history = copy.deepcopy(self.history)

    self._merged = False
    self.current = new_files

    # remove the bases from the split list. This is for parallel processing

    for ff in bases:
        remove_safe(ff)

    cleanup()
    self.disk_clean()


@not_for_fvcom("it splits regular lon/lat grids into boxes")
def distribute(self, m=1, n=1):
    """
    distribute: Split the dataset into multiple evenly sized horizontal and vertical new files

    Parameters
    --------------------
    m : int
        Number of rows
    n : int
        Number of columns

    Examples
    --------------------
    If you want to split the dataset into 2 by 2 with 4 new files:
    >>> ds.distribute(m=2, n=2)


    """

    if not isinstance(m, int) or not isinstance(n, int):
        raise ValueError("Please provide integers")

    if m < 1:
        raise ValueError("Please provide integers")

    if n < 1:
        raise ValueError("Please provide integers")

    dist_cdo(self, i=n, j=m)
