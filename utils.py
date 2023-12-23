#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
from os.path import lexists, islink, isdir, exists, realpath
import subprocess
from subprocess import Popen, PIPE

import shutil
import stat
import datetime
from typing import Any
from dataclasses import dataclass

from io import StringIO

def remove_any(path: str) -> bool:
    """Remove a path whether it is a file or a directory.
       Return: True if removed, False if nothing to remove"""

    if not lexists(path):
        return False

    if not islink(path) and isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

    return True

@dataclass
class BaseAttrDict:
    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise ValueError(
                f"{self.__class__.__name__}() has no attr '{key}'")

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __repr__(self) -> str:
        attrs = ''
        for attr in sorted(dir(self)):
            if not attr.startswith('_'):
                value = getattr(self, attr)
                if attrs:
                    attrs = attrs + ','
                attrs = attrs + f"\n\t{attr}={value}"
        return f'{self.__class__.__name__}({attrs}\n\t)'


def _check_path(path: str) -> str:
    if exists(path):
        return realpath(path)
    else:
        raise FileNotFoundError(f"Path not found: '{path}'")


def is_writeable(fpath: str) -> bool:
    try:
        with open(fpath, "w+"):
            return True
    except IOError:
        return False

# workaround for shutil.move across-filesystem bugs
def move(src: str, dst: str) -> None:
    st = os.lstat(src)

    is_symlink = stat.S_ISLNK(st.st_mode)

    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(os.path.abspath(src)))

    if is_symlink:
        linkto = os.readlink(src)
        os.symlink(linkto, dst)
        os.unlink(src)
    else:
        shutil.move(src, dst)
        os.lchown(dst, st.st_uid, st.st_gid)

class OverlayError(Exception):
    pass

def apply_overlay(src: str, dst: str, olist_path: str) -> None:
    # refactor to use subprocess
    p1 = Popen(['tar', '--create', f'--files-from={olist_path}'], cwd=src, stdout=PIPE)
    p2 = subprocess.run(['tar', '--extract', '--directory', dst], stdin=p1.stdout)
    if p2.returncode != 0 or p1.wait() != 0:
        raise OverlayError(f"Applying overlay failed: {p2.stderr.decode()}")

def fmt_title(title: str, c: str = '=') -> str:
    return title + "\n" + c * len(title) + "\n"

def fmt_timestamp() -> str:

    fh = StringIO()

    s = "### %s ###" % datetime.datetime.now().ctime()
    print("#" * len(s), file=fh)
    print(s, file=fh)
    print("#" * len(s), file=fh)

    return fh.getvalue()

def path_global_or_local(path_global: str, path_local: str) -> str:
    """Return global path if writeable, otherwise return local path"""
    if os.access(os.path.dirname(path_global), os.W_OK):
        return path_global

    return path_local

def iamroot() -> bool:
    return os.getuid() == 0
