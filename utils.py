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
from os.path import lexists, islink, isdir
import subprocess

import shutil
import stat
import datetime

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

class AttrDict(dict):
    def __getattr__(self, name: str) -> str:
        if name in self:
            return self[name]
        raise AttributeError("no such attribute '%s'" % name)

    def __setattr__(self, name: str, val: str) -> None:
        self[name] = val

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

def apply_overlay(src: str, dst: str, olist_path: str) -> None:
    # rewrite using rsync - should be doing the same...
    subprocess.run(['rsync', '-avz', '--min-size=1', f'--files-from={olist_path}', src, dst])
    # old code:
    # cd src
    # executil.getoutput("tar --create --files-from=%s | tar --extract --directory %s" %
    #                   (olist_path, executil.mkarg(dst)))

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
