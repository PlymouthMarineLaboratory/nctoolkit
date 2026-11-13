from nctoolkit.flatten import str_flatten


def fix_ind(x):
    if x < 0:
        return x
    else:
        return x + 1


def drop(self, **kwargs):
    """
    drop: Remove variables, days, months, years or time steps from a dataset

    This will remove stated variables from files in the dataset.

    Parameters
    -------------
    *kwargs
        Possible arguments: var, year, month, day

        Note: this uses partial matches. So years, month, variable etc. will also work


    Each kwarg works as follows:

    var: str or list
        A variable or list of variables to select. This method will accept wild cards.
        So using 'var*' would select all variables beginning with 'var'.
    day : list, range or int
        Day(s) to drop.
    month : list, range or int
        Month(s) to drop.
    year : list, range or int
        Year(s) to drop.
    time : list, range or int
         Time steps to to drop. This can include negative indices.

    Examples
    ------------

    If you wanted to remove a single variable 'var1'  from a dataset data, you would do the following:

    >>> ds.drop(variable = 'var')

    If you wanted to remove a list of variables, you would do the following:

    >>> ds.drop(variable = ['var1', 'var2', 'var2'])

    If you wanted to remove the 29th Feburary you would do the following:

    >>> ds.drop(month = 2, day = 29)


    """

    if len(kwargs) == 0:
        raise ValueError("Please provide terms to drop")

    valids = ["var", "mon", "day", "year", "time"]

    for key in kwargs:
        key_check = 0
        for vv in valids:
            if vv in key:
                key_check += 1
        if key_check > 1 or key_check == 0:
            raise ValueError("Drop term is invalid or ambiguous")

    temporal_command = "-delete"

    for key in kwargs:
        if "time" in key:
            vars = kwargs[key]

            if not isinstance(vars, list):
                vars = [vars]

            for vv in vars:
                if not isinstance(vv, int):
                    raise TypeError(f"{vv} is not an int")

            vars = [fix_ind(x) for x in vars]
            vars = str_flatten(vars, ",")

            # create the cdo command and run it
            cdo_command = f"-delete,timestep={vars}"
            self.cdo_command(cdo_command, ensemble=False)

        if "var" in key:
            vars = kwargs[key]

            if not isinstance(vars, list):
                vars = [vars]

            for vv in vars:
                if not isinstance(vv, str):
                    raise TypeError(f"{vv} is not a str")

            # the FVCOM layer thickness is gone
            thickness = getattr(self, "fvcom_thickness", None)
            if thickness is not None:
                import fnmatch

                if any(fnmatch.fnmatch(thickness, vv) for vv in vars):
                    self.fvcom_thickness = None

            vars = str_flatten(vars, ",")

            # create the cdo command and run it
            cdo_command = f"-delete,name={vars}"
            self.cdo_command(cdo_command, ensemble=False)

        if ("mon" in key) or ("day" in key) or ("year" in key):
            vars = kwargs[key]

            if isinstance(vars, range):
                vars = list(vars)

            if not isinstance(vars, list):
                vars = [vars]

            for vv in vars:
                if not isinstance(vv, int):
                    raise TypeError(f"{vv} is not a int")

            vars = str_flatten(vars, ",")

            # create the cdo command and run it
            if "day" in key:
                temporal_command = temporal_command + f",day={vars}"
            if "mon" in key:
                temporal_command = temporal_command + f",month={vars}"
            if "year" in key:
                temporal_command = temporal_command + f",year={vars}"

    if len(temporal_command) > len("-delete"):
        self.cdo_command(temporal_command, ensemble=False)
