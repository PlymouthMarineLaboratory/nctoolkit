import os
import uuid

from nctoolkit.session import session_info
from nctoolkit.session import append_tempdirs


def temp_file(ext=""):
    """
    Function to create a temporary file.
    This accounts for OS

    Parameters
    --------------------
    ext : str
        File extension
    """

    # check space left in temp dir and switch it if there isn't much
    if session_info["temp_dir"] == "/tmp/":
        result = os.statvfs("/tmp/")
        result = result.f_frsize * result.f_bavail

        if result < 0.5 * 1e9:
            if session_info["temp_dir"] == "/tmp/":
                session_info["temp_dir"] = "/var/tmp/"

    actual_temp = session_info["temp_dir"]
    actual_temp = actual_temp + "/"
    actual_temp = actual_temp.replace("//", "/")

    # The stamp goes on the file name itself, rather than being swapped into
    # the directory path: tempfile's directory isn't /tmp/ on macOS, so a
    # path-based replace would silently skip the stamp there.
    # The random part is generated directly: creating a NamedTemporaryFile
    # just to read its name leaves an unclosed file object that Python 3.14
    # reports with a ResourceWarning when it is garbage collected.
    target = actual_temp + session_info["stamp"] + "tmp" + uuid.uuid4().hex[:12]
    if not isinstance(ext, str):
        raise TypeError("Extension supplied is not a str")
    if ext.startswith("."):
        target = target + ext
    else:
        target = f"{target}.{ext}"

    append_tempdirs(os.path.dirname(target))

    return target

