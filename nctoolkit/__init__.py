from nctoolkit.api import (
    open_data,
    open_geotiff,
    from_xarray,
    merge,
    cor_time,
    cor_space,
    options,
    DataSet,
    open_thredds,
    open_url,
)


from nctoolkit.unify import unify
from nctoolkit.shape import open_shape
from nctoolkit.fvcom import open_fvcom
from nctoolkit.static_plot import panel_plot

from nctoolkit.validator import validator
from nctoolkit.matchpoint import open_matchpoint


from nctoolkit.cleanup import cleanup, clean_all, deep_clean, temp_check
from nctoolkit.session import kill_active_cdo

import atexit
import os
import signal

# Forked children (multiprocessing workers, os.fork) inherit these handlers but
# share the session stamp; only the process that imported nctoolkit may clean
# up, otherwise a worker exiting would delete the parent's live temp files.
_owner_pid = os.getpid()


def _clean_all_if_owner():
    if os.getpid() == _owner_pid:
        clean_all()


def _stop_workers():
    """
    Terminate multiprocessing children (e.g. ensemble workers) so the cdo
    processes they are running die with them, before temp files are removed
    """
    from nctoolkit.session import mp

    children = mp.active_children()
    for child in children:
        try:
            child.terminate()
        except Exception:
            pass
    for child in children:
        try:
            child.join(2)
        except Exception:
            pass


atexit.register(_clean_all_if_owner)


def _install_termination_handlers():
    """
    Remove temp files when the process is terminated by SIGTERM or SIGHUP

    Python only runs atexit handlers on a normal exit, so a plain `kill` would
    otherwise leave temp files behind. The handler cleans up and then
    re-delivers the signal with its previous disposition, so the process still
    terminates as the sender intended. Handlers someone else has already
    installed are chained to rather than replaced.
    """

    def make_handler(previous):
        def handler(signum, frame):
            kill_active_cdo()
            if os.getpid() == _owner_pid:
                _stop_workers()
            _clean_all_if_owner()
            if callable(previous):
                previous(signum, frame)
                return
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        return handler

    for name in ("SIGTERM", "SIGHUP"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            previous = signal.getsignal(signum)
            if previous is None or previous == signal.SIG_IGN:
                # not set from Python, or deliberately ignored (e.g. nohup)
                continue
            signal.signal(signum, make_handler(previous))
        except ValueError:
            # signal handlers can only be set from the main thread
            pass


_install_termination_handlers()

from nctoolkit.create_ensemble import create_ensemble, glob
from nctoolkit.session import session_files
from nctoolkit.show import nc_variables, nc_years, nc_months, nc_times

from nctoolkit.utils import validate_version, cdo_version
from nctoolkit.session import session_info
from nctoolkit.mp_adders import match_points

session_info["cdo"] = cdo_version()

try:
    from importlib.metadata import version as _version
except ImportError:
    from importlib_metadata import version as _version

try:
    __version__ = _version("nctoolkit")
except Exception:
    __version__ = "999"
