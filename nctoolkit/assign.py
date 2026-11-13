import re
import dill
import inspect
import numpy as np

from nctoolkit.session import session_info
from nctoolkit.utils import version_below


def split_equation(mystr):
    return re.split("[-+^!=*/(&|)\[\]]", mystr)


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def between_brackets(s):
    return s[s.find("(") + 1 : s.find(")")]


def find_possible(x):
    if "vert" in x:
        for y in ["mean", "max", "min", "sum"]:
            if y in x:
                return f"vertical_{y}"
    if "spa" in x:
        for y in ["mean", "max", "min", "sum"]:
            if y in x:
                return f"spatial_{y}"
    if "zon" in x:
        for y in ["mean", "max", "min", "sum"]:
            if y in x:
                return f"zonal_{y}"
    return None


def find_parens(s):
    toret = {}
    pstack = []

    for i, c in enumerate(s):
        if c == "[":
            pstack.append(i)
        elif c == "]":
            toret[pstack.pop()] = i

    return toret


def find_parens2(s):
    toret = {}
    pstack = []

    for i, c in enumerate(s):
        if c == "{":
            pstack.append(i)
        elif c == "}":
            toret[pstack.pop()] = i

    return toret


def find_parens3(s):
    toret = {}
    pstack = []

    for i, c in enumerate(s):
        if c == "(":
            pstack.append(i)
        elif c == ")":
            if len(pstack) == 0:
                raise IndexError("No matching closing parens at: " + str(i))
            toret[pstack.pop()] = i

    if len(pstack) > 0:
        raise IndexError("No matching opening parens at: " + str(pstack.pop()))

    return toret


funs = [
    "abs",
    "floor",
    "ceil",
    "sqrt",
    "exp",
    "ln",
    "sin",
    "min",
    "max",
    "cos",
    "tan",
    "int",
    "float",
    "log10",
    "thickness",
]

translation = dict()
for ff in funs:
    if ff in dir(np):
        translation[ff] = ff

translation["int"] = "int"
# translation["deltaz"] = "cdeltaz"
translation["float"] = "float"

translation["arcsin"] = "asin"
translation["arccos"] = "acos"
translation["arctan"] = "atan"

# translate the spatials
translation["spatial_mean"] = "fldmean"
translation["spatial_min"] = "fldmin"
translation["spatial_max"] = "fldmax"
translation["spatial_sum"] = "fldsum"


# translate the spatials
translation["vertical_mean"] = "vertmean"
translation["vertical_min"] = "vertmin"
translation["vertical_max"] = "vertmax"
translation["vertical_sum"] = "vertsum"


translation["zonal_mean"] = "zonmean"
translation["zonal_min"] = "zonmin"
translation["zonal_max"] = "zonmax"
translation["zonal_sum"] = "zonsum"
translation["isnan"] = "isMissval"

translation["cell_area"] = "gridarea"

translation["level"] = "clev"

translation["log"] = "ln"

translation["timestep"] = "ctimestep"

translation["year"] = "cyear"
translation["month"] = "cmonth"
translation["day"] = "cday"
translation["hour"] = "chour"
translation["second"] = "csecond"
translation["minute"] = "cminute"

translation["lon"] = "clon"
translation["lat"] = "clat"

translation["longitude"] = "clon"
translation["latitude"] = "clat"


# split using all possible mathematical operators
def split1(mystr):
    return re.split("([+-/*()<>=])", mystr)


def is_lambda(v):
    LAMBDA = lambda: 0
    return isinstance(v, type(LAMBDA)) and v.__name__ == LAMBDA.__name__


pattern = re.compile(":\w*")


def assign(self, drop=False, **kwargs):
    """
    assign: Create new variables using mathematical operations on existing variables.

    Existing columns that are re-assigned will be overwritten.
    This method operators in a similar fashion to the pandas assign method.

    Parameters
    ----------
    drop : bool
        Set to True if you want existing variables to be removed once the new ones have been created.
        Defaults to False.
    **kwargs : dict of {str: callable}
        New variable names are keywords. All terms in the equation given by the lambda function
        should evaluate to a numeric. New variables are calculated for each grid cell and time step.
    Notes
    -----
    Operations are carried out in the order give. So if a new variable is created in the first argument,
    it can then be used in following arguments.

    Examples
    --------

    Temperature could be converted from Celsius to Kelvin by:

    >>> ds.assign(temperature_K=lambda x: x.temperature + 273.15)

    Temperatures higher than the spatial average temperature could be found by:

    >>> ds.assign(hot=lambda x: x.temperature > spatial_mean(x.temperature)))







    """
    frame = inspect.currentframe()

    if not isinstance(drop, bool):
        raise ValueError("drop is not boolean!")

    if len(kwargs) == 0:
        raise ValueError("Please provide assignments!")

    for k, v in kwargs.items():
        if is_lambda(v) is False:
            raise ValueError("Please check everything is a lambda function!")
        lambdas = v

    for k, v in kwargs.items():
        if is_lambda(v) is True:
            break
    lambdas = v

    # now, we need to parse things.

    interactive = False
    if session_info["interactive"]:
        import readline

        if readline.get_current_history_length() > 0:
            interactive = True
    try:
        start = lambdas
        try:
            all_str = list(inspect.getsourcelines(start))[0]
            all_str = "".join(all_str)
            start = all_str.replace("'", "").replace("\\n", "")[1:-1].replace("  ", " ")
            start = start.replace("\n", "")
        except:
            start = dill.source.getsource(start).replace("\n", "").strip()
    except:
        if interactive:
            import readline

            start = [
                str(readline.get_history_item(i + 1))
                for i in range(readline.get_current_history_length())
            ]
            i = 0
            for ss in start:
                if ".assign(" in ss or ".match_points(" in ss:
                    ind = i
                i += 1

            all_str = start[ind : len(start)]
            all_str = "".join(all_str)
            start = all_str.replace("'", "").replace("\\n", "").replace("  ", " ")
        else:
            start = lambdas
            try:
                all_str = list(inspect.getsourcelines(start))[0]
                all_str = "".join(all_str)
                start = (
                    all_str.replace("'", "").replace("\\n", "")[1:-1].replace("  ", " ")
                )

            except:
                start = dill.source.getsource(start).replace("\n", "").strip()

    # we now need to figure out if what we have is one line

    if ";" in start:
        raise ValueError("You cannot split assign calls using ;")

    if ".assign(" not in start and ".match_points(" not in start:
        raise ValueError("Please write assign methods as single line!")

    try:
        find_parens3(start)
    except:
        raise ValueError("Please write assign methods as single line!")

    start = start.strip()
    start = start[start.find("(") + 1 : -1]
    start = re.sub("\s\s+", " ", start)

    pattern1 = re.compile("drop\s*=\s*(True|False)")
    y = pattern1.search(start)
    if y is not None:
        y = y.group()
        start = start.replace(y, "").strip()

    start = start.strip()
    start = start.replace(" or ", " | ")
    start = start.replace(" and ", " & ")

    if "%" in start:
        raise ValueError("assign does not yet accept %")

    if "//" in start:
        raise ValueError("assign does not yet accept //")

    if start.endswith(","):
        start = start[:-1]

    pattern1 = re.compile("\s*:")

    for tt in pattern1.findall(start):
        start = start.replace(tt, ": ")

    if start.startswith(","):
        start = start[1:]
    start = start.strip()

    pattern1 = re.compile(",\s,")
    y = pattern1.search(start)
    if y is not None:
        y = y.group()
        start = start.replace(y, " , ").strip()

    start = start.replace("  ", " ")
    pattern1 = re.compile(",\s*\w+\s*=\s*lambda")

    for x in pattern1.finditer(start):
        index = x.span()[0]
        start = start[:index] + ";" + start[index + 1 :]

    command = list()
    starts = start

    pattern_missing = re.compile("lambda\s*:")
    if pattern_missing.search(start) is not None:
        raise ValueError("Ensure lambda functions of the form 'lambda x:'")

    if starts.endswith(","):
        starts = starts[:-1]

    if ".match_points(" in starts:
        starts = starts.replace(".match_points(", ".assign(")

    starts = starts.split(";")
    starts = [x for x in starts if ("lambda" in x) or ("drop" in x)]
    starts = ("; ").join(starts)

    for start in starts.split(";"):
        patternl = re.compile("lambda \w*:")
        lambda_value = patternl.findall(start)[0][-2]

        start = (
            " ".join(split1(start))
            .replace("  ", " ")
            .replace(" ( ", "(")
            .replace(" . ", ".")
        )

        # run equations first.
        # key here is that equation can only pure pure python or pure cdo

        check_them = True
        while check_them:
            check_start = start
            pars = find_parens(start)
            for key in pars:
                old_start = start
                start = (
                    start[:key]
                    + start[key : (pars[key] + 1)].replace(" ", "")
                    + start[pars[key] + 1 :]
                )
                if start != old_start:
                    break
            if check_start == start:
                check_them = False

        while True:
            check_start = start
            pars = find_parens2(start)
            for key in pars:
                old_start = start
                start = (
                    start[:key]
                    + start[key : (pars[key] + 1)].replace(" ", "")
                    + start[pars[key] + 1 :]
                )
                if start != old_start:
                    break
            if check_start == start:
                break

        start = start.replace(";", " ; ").replace("  ", " ")

        # tidy functions

        start = start.replace(" [", "[").replace("(", "( ").replace(" . ", ".")

        # pattern to identify functions
        fun_pattern = re.compile("[a-zA-Z\_][a-zA-Z\_z.0-9]*\(")

        for x in fun_pattern.findall(start):
            check = True
            while check:
                x_terms = re.finditer(x.replace("(", "\\(").replace("[", "\\["), start)

                terminate = len(
                    re.findall(x.replace("(", "\\(").replace("[", "\\["), start)
                )

                if terminate == 0:
                    check = False

                tracker = 0
                for y in x_terms:
                    if x in start:
                        old_start = start
                        start_parens = find_parens3(start)
                        x_term = (
                            x + start[y.span()[1] : start_parens[y.span()[1] - 1] + 1]
                        )
                        try:
                            new_x = eval(x_term, globals(), frame.f_back.f_locals)
                            if not isinstance(new_x, str):
                                if is_number(str(new_x)):
                                    start = start.replace(
                                        x_term, str(new_x).replace(" ", "")
                                    )
                            if start != old_start:
                                break
                        except:
                            odllan = "nothing"
                    tracker += 1
                    if tracker == terminate:
                        check = False

        terms = list(
            set(
                [
                    x
                    for x in start.replace(" . ", ".").split(" ")
                    if x.endswith("(") and len(x) > 1
                ]
            )
        )

        for x in terms:
            if ("[" in x and f"{lambda_value}." in x) is False:
                if fun_pattern.search(x) is not None:
                    fix = True
                    n = 0
                    n_limit = start.count("x")
                    while fix:
                        for y in re.finditer(
                            x.replace("(", "\\(").replace("[", "\\["), start
                        ):
                            if len(y.group()) > 0:
                                old_start = start
                                start_parens = find_parens3(start)
                                x_term = (
                                    x
                                    + start[
                                        y.span()[1] : start_parens[y.span()[1] - 1] + 1
                                    ]
                                )
                                start = start.replace(x_term, x_term.replace(" ", ""))
                                if old_start != start:
                                    break
                        n += 1

                        if n > n_limit:
                            fix = False

        error_message = None

        if "is False" in start:
            start = start.replace(" is False", " < 1")

        if "is True" in start:
            start = start.replace(" is True", " > 0")

        if " = = True" in start:
            start = start.replace(" = = True", " > 0")

        if " = = False" in start:
            start = start.replace(" = = False", " < 1")

        version = session_info["cdo"]
        if version_below(version, "2.1.0"):
            translation["thickness"] = "cdeltaz"
        else:
            translation["thickness"] = "cthickness"

        for x in start.split(" "):
            if "(" in x:
                x_fun = x.split("(")[0]
                pattern1 = re.compile("[A-Za-z0-9\\.\\_]*")
                if fun_pattern.match(x) is not None:
                    try:
                        # need to tweak this so that it captures the output and returns an appropriate error
                        new_x = eval(x, globals(), frame.f_back.f_locals)
                        if isinstance(new_x, str):
                            raise ValueError(f"{x} evaluates to a string")
                        if is_number(str(new_x)) is False:
                            raise ValueError(f"{x} does not evaluate to numeric!")

                        new_start = ""
                        for y in start.split(" "):
                            if y != x:
                                new_start += " " + y
                            else:
                                new_start += " " + str(new_x)
                        start = new_start
                        error_message = None

                    except:
                        if x_fun in translation.keys():
                            x_term = between_brackets(x)
                            if (f"{lambda_value}." in x_term) is False:
                                if x_fun not in ["timestep"]:
                                    raise ValueError(
                                        f"Error for {x}: nctoolkit functions must take dataset variables as args!"
                                    )
                            if x_fun == "timestep":
                                start = start.replace(x, "(" + x + "-1)")
                            if x_fun in ["cell_area", "longitude", "latitude"]:
                                if len(split_equation(x_term)) > 1:
                                    raise ValueError(
                                        f"{x_fun} can only take a single dataset variable as an argument!"
                                    )

                        else:
                            x_term = between_brackets(x)
                            if f"{lambda_value}." in x_term:
                                possible = find_possible(x_fun)
                                if possible is not None:
                                    raise ValueError(
                                        f"{x_fun} is not an assignment function. Did you mean {possible}?"
                                    )

                            if f"{lambda_value}." in x_term:
                                raise ValueError(
                                    f"{x_fun} is not an assignment function"
                                )
                            else:
                                raise ValueError(f"{x} cannot be evaluated!")

        start = (
            " ".join(split1(start))
            .replace("  ", " ")
            .replace(" ( ", "(")
            .replace(" . ", ".")
        )

        start = start.replace(";", " ; ").replace("  ", " ").replace(") ", ")")

        # put spaces round lambda x: etc.
        pattern1 = re.compile("lambda [a-zA-Z\_][a-zA-Z\_z0-9]*\:")
        for x in pattern1.findall(start):
            start = start.replace(x, x + " ")
        start = start.replace("  ", " ")

        terms = (
            start.replace(" . ", ".")
            .replace(") ", ")")
            .replace(") ", ")")
            .replace("  ", " ")
            .split(" ")
        )

        for x in terms:
            if "[" in x:
                if f"{lambda_value}." in x:
                    raise ValueError(f"{x} is not valid syntax")
                try:
                    new_term = eval(x, globals(), frame.f_back.f_locals)
                except:
                    raise ValueError(f"{x} is not available!")
                if not isinstance(new_term, (int, float)):
                    raise ValueError(f"{x} does not evaluate to numeric!")

                new_start = ""
                for y in start.split(" "):
                    if y != x:
                        new_start += " " + y
                    else:
                        new_start += " " + str(new_term)
                start = new_start

        terms = start.split(" ")

        for x in terms:
            if "{" in x:
                if f"{lambda_value}." in x:
                    raise ValueError(f"{x} is not valid syntax")
                try:
                    new_term = eval(x, globals(), frame.f_back.f_locals)
                except:
                    raise ValueError(f"{x} is not available!")
                if not isinstance(new_term, (int, float)):
                    raise ValueError(f"{x} does not evaluate to numeric!")

                new_start = ""
                for y in start.split(" "):
                    if y != x:
                        new_start += " " + y
                    else:
                        new_start += " " + str(new_term)
                start = new_start

        # fix powers

        if "^" in start:
            raise ValueError("^ is not valid syntax. Please use **")

        start = start.replace("* ", "*").replace("**", "^")

        start = re.sub(" +", " ", " ".join(split1(start)).replace(" . ", "."))

        start = start.replace("|", "||")
        start = start.replace("&", "&&")

        # we need to be able to identify lambdas and get rid of them
        # start = start.replace("=", "= ")
        start = re.sub(" +", " ", " ".join(split1(start)).replace(" . ", "."))

        # We now need to tidy up each element

        start = " ".join(split1(start))
        start = start.replace("  ", " ")
        start = start.replace(" (", "(").replace(" . ", ".")
        terms = start.split(" ")

        error_message = None

        for i in range(2, len(terms)):
            if (
                terms[i].isidentifier()
                and terms[i] != "lambda"
                and terms[min(i + 1, len(terms) - 1)] != lambda_value
            ):
                term = terms[i]

                if term in frame.f_back.f_locals:
                    try:
                        new_term = eval(term, globals(), frame.f_back.f_locals)
                        if isinstance(new_term, str):
                            error_message = f"{term} does not evaluate to a numeric!"
                            raise ValueError(f"{term} does not evaluate to a numeric!")

                        if is_number(str(new_term)) is False:
                            if isinstance(new_term, bool):
                                new_term = float(new_term)
                            else:
                                error_message = (
                                    f"{term} does not evaluate to a numeric!"
                                )
                                raise ValueError(
                                    f"{term} does not evaluate to a numeric!"
                                )

                        new_start = ""
                        for y in start.split(" "):
                            if y != term:
                                new_start += " " + y
                            else:
                                new_start += " " + str(new_term)
                        start = new_start
                    except:
                        raise ValueError(f"{term} is not available!")
                else:
                    raise ValueError(f"{term} is not available!")

        start = " ".join(split1(start))

        new_start = []

        def new_split(mystr):
            return re.split("([+-/*()&|<>=!^])", mystr)

        for tt in start.split(";"):
            tt_frag = []
            l_pattern = re.compile("lambda (\w*):")
            l_string = l_pattern.findall(tt)[0]
            tt1 = tt.replace(f"lambda {l_string}:", " ")
            tt1 = re.sub(" ", "", tt1)
            tt1 = " ".join(new_split(tt1)).replace(" . ", ".")
            tt1 = re.sub(" +", " ", tt1)

            for ss in tt1.split(" "):
                if ss.startswith(f"{l_string}."):
                    tt_frag.append(ss.replace(f"{l_string}.", ""))
                else:
                    tt_frag.append(ss)

            tt_frag = " ".join(tt_frag)
            new_start.append(tt_frag)

        start = ";".join(new_start)
        start = " ".join(split1(start))

        start = start.replace(" lambda ", " ").replace(" ", "")

        # We need to fix pow functions potentially. Though, it might be better to stick with ^

        # translate numpy style functions to cdo functions
        for key in translation:
            start = start.replace(f"{key}(", f"{translation[key]}(")

        start = " ".join(split1(start))

        def new_split(mystr):
            return re.split("([+-/*()&|<>=!^])", mystr)

        y = " ".join(new_split(start))
        z = y.split(" = ")[1]
        total = 0
        for w in (z.replace(" (", "(")).split(" "):
            if w.strip().isidentifier():
                total += 1
        if total == 0:
            raise ValueError("Formula does not use any dataset variables!")

        command.append(start)

    command = ";".join(command).replace(" ", "")

    def split_this(mystr):
        return re.split("([+-/*()<>|&=])", mystr)

    command = " ".join(split_this(command)).replace(" . ", ".").replace(";", " ; ")

    for term in command.split(" "):
        if "." in term:
            pattern1 = re.compile(r"[a-zA-Z]")
            if len(pattern1.findall(term)) > 0 and "^" not in term:
                if term.split(".")[0] in frame.f_back.f_locals:
                    try:
                        new_term = eval(term, globals(), frame.f_back.f_locals)
                        if isinstance(new_term, str):
                            raise ValueError(f"{new_term} is not numeric!")
                        if is_number(str(new_term)) is False:
                            raise ValueError(f"{new_term} is not numeric!")
                        new_start = ""
                        for y in command.split(" "):
                            if y != term:
                                new_start += " " + y
                            else:
                                new_start += " " + str(new_term)
                        command = new_start
                    except:
                        raise ValueError(f"{term} is not available!")
                else:
                    raise ValueError(f"{term} is not available!")

    command = command.replace(" ", "")

    del frame

    # create the cdo call and run it
    if drop is False:
        cdo_command = f"-aexpr,'{command}'"
    else:
        cdo_command = f"-expr,'{command}'"
        # only the new variables are kept, so the FVCOM layer thickness may be gone
        if getattr(self, "fvcom_thickness", None) not in kwargs:
            self.fvcom_thickness = None

    self.cdo_command(cdo_command, ensemble=False)
