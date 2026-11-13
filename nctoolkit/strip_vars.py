import copy

from nctoolkit.flatten import str_flatten
from nctoolkit.runthis import run_nco
from nctoolkit.temp_file import temp_file
from nctoolkit.session import get_safe
from nctoolkit.session import remove_safe
from nctoolkit.fvcom import not_for_fvcom


@not_for_fvcom("it removes the mesh's coordinates and cell bounds", "")
def strip_variables(self, vars=None):
    """
    strip_variables: Remove any variables, such as bnds etc., from variables.

    This should probably only be done at the end of a processing chain before converting to a dataframe etc., as it is stripping away critical info for netCDF operations.

    Parameters
    -------------
    vars : str or list
        individual or list of variables to select and strip. All variables will be stripped if this is not defined.

    """

    self.run()

    if vars is not None:
        if isinstance(vars, str):
            vars = [vars]

        for vv in vars:
            if vv not in self.variables:
                raise ValueError(f"{vv} is not a valid variable!")

        command = f"ncks -C -v {str_flatten(vars)}"

    else:
        command = f"ncks -C -v {str_flatten(self.variables)}"

    new_files = []
    new_commands = []

    delete_these = []

    for ff in self:
        target = temp_file(".nc")

        the_command = f"{command} {ff} {target}"

        target = run_nco(the_command, target=target)

        if target in get_safe():
            delete_these.append(target)

        new_files.append(target)
        new_commands.append(the_command)

    self.current = new_files

    self.history.append(command)
    self._hold_history = copy.deepcopy(self.history)

    for ff in delete_these:
        remove_safe(ff)

    self.disk_clean()
