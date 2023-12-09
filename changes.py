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
import sys
import os
from os.path import lexists, isdir, islink

from dirindex import DirIndex
from pathmap import PathMap

import stat
import errno

import pwd
import grp

from typing import Optional, Generator, Self, Callable, Any

class Error(Exception):
    pass

def fmt_uid(uid: int|str) -> str:
    try:
        return pwd.getpwuid(int(uid)).pw_name
    except:
        return str(uid)

def fmt_gid(gid: int|str) -> str:
    try:
        return grp.getgrgid(int(gid)).gr_name
    except:
        return str(gid)

class Change:
    """
    Example usage::
        change = Change.parse(line)
        print change
        print change.path

        if change.OP in ('o', 's'):
            print change.uid, change.gid

        if change.OP == 's':
            print change.mode

        # or instead of using OP we can do this
        if isinstance(change, Change.Deleted):
            assert change.OP == 'd'

    """
    class Base:
        OP: Optional[str] = None
        def __init__(self, path: str):
            self.path = path
            self._stat: Optional[os.stat_result] = None

        def stat_(self) -> os.stat_result:
            if not self._stat:
                self._stat = os.lstat(self.path)

            return self._stat

        stat = property(stat_)

        def fmt(self, *args: str) -> str:
            items = []
            for item in [self.OP, self.path, *args]:
                if item != None:
                    items.append(str(item))

            return "\t".join(items)

        def __str__(self) -> str:
            return self.fmt()

        @classmethod
        def fromline(cls, line: str) -> Self:
            args = line.rstrip().split('\t')
            return cls(*args)

    class Deleted(Base):
        OP = 'd'

    class Overwrite(Base):
        OP = 'o'
        def __init__(self, path: str, uid: Optional[str] = None, gid: Optional[str] = None):
            Change.Base.__init__(self, path)

            if uid is None:
                self.uid = self.stat.st_uid
            else:
                self.uid = int(uid)

            if gid is None:
                self.gid = self.stat.st_gid
            else:
                self.gid = int(gid)

        def __str__(self) -> str:
            return self.fmt(str(self.uid), str(self.gid))

    class Stat(Overwrite):
        OP = 's'
        def __init__(self, path: str, uid: Optional[str] = None, gid: Optional[str] = None, mode: Optional[str] = None):
            Change.Overwrite.__init__(self, path, uid, gid)
            if mode is None:
                self.mode = self.stat.st_mode
            else:
                if isinstance(mode, int):
                    self.mode = mode
                else:
                    self.mode = int(mode, 8)

        def __str__(self) -> str:
            return self.fmt(str(self.uid), str(self.gid), oct(self.mode))

    @classmethod
    def parse(cls, line: str) -> Base:
        #op2class: dict[Optional[str], Self] = dict((val.OP, val) for val in list(cls.__dict__.values())
        #                if isinstance(val, type))
        op2class: dict[Optional[str], Self] = {}
        for val in list(cls.__dict__.values()):
            if isinstance(val, type):
                op2class[val.OP] = val  # type: ignore[attr-defined,assignment]
                # error: "type" has no attribute "OP"  [attr-defined]
                # Incompatible types in assignment (expression has type "type", target has type "Self")  [assignment]

        op = line[0]
        if op not in op2class:
            raise Error("illegal change line: " + line)

        return op2class[op].fromline(line[2:])  # type: ignore[attr-defined]
        # "Self" has no attribute "fromline"  [attr-defined]

def mkdir(path: str) -> None:
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

class Changes(list):
    """
    A list of Change instances, which we can load from a file and write
    back to a file.

    The smarts is in statfixes() and deleted() methods which compare the
    list of changes to the current filesystem and yield Action() instances.

    Action()s can be printed (e.g., for simulation or verbosity) or called
    to run the operation that needs to be performed.

    """
    class Action:
        def __init__(self, func: Callable, *args: str):
            self.func: Callable = func
            self.args: list[str] = list(args)

        def __call__(self) -> str:
            return self.func(*self.args)

        def __str__(self) -> str:
            func = self.func
            args = self.args

            if func is os.lchown:
                path, uid, gid = args
                return "chown -h %s:%s %s" % (fmt_uid(uid), fmt_gid(gid), path)
            elif func is os.chmod:
                path, mode = args
                return "chmod %s %s" % (oct(int(mode)), path)
            elif func is os.remove:
                path, = args
                return "rm " + path
            elif func is mkdir:
                path, = args
                return "mkdir -p " + path
            return ''

    def __add__(self, other: list[Any]) -> list[Any]:
        cls = type(self)
        return cls(list.__add__(self, other))

    @classmethod
    def fromfile(cls, f: str, paths: Optional[list[str]] = None): # -> Changes:
        if f == '-':
            fh = sys.stdin
        else:
            fh = open(f)

        changes = [Change.parse(line) for line in fh.readlines()]
        fh.close()
        if paths:
            pathmap = PathMap(paths)
            changes_ = []
            for change in changes:
                if change.path in pathmap:
                    changes_.append(change)
            return cls(changes_)

        return cls(changes)

    def tofile(self, f: str) -> None:
        with open(f, "w") as fob:
            for change in self:
                fob.writelines(str(change) + "\n")

    def deleted(self, optimized: bool = True) -> Generator[Action, None, None]:
        for change in self:
            if change.OP != 'd':
                continue

            if optimized:
                if not lexists(change.path):
                    continue

                if not islink(change.path) and isdir(change.path):
                    continue

            yield self.Action(os.remove, change.path)

    def statfixes(self,
                  uidmap: dict[str, str] = {},
                  gidmap: dict[str, str] = {},
                  optimized: bool = True
                  ) -> Generator[Action, None, None]:
        class TransparentMap(dict):
            def __getitem__(self, key):
                if key in self:
                    return dict.__getitem__(self, key)
                return key

        uidmap = TransparentMap(uidmap)
        gidmap = TransparentMap(gidmap)

        for change in self:

            if not optimized or not lexists(change.path):
                # backwards compat: old backups only stored IMODE in fsdelta, so we assume S_ISDIR
                if change.OP == 's' and (stat.S_IMODE(change.mode) == change.mode or stat.S_ISDIR(change.mode)):
                    yield self.Action(mkdir, change.path)
                    yield self.Action(os.lchown, change.path, str(uidmap[change.uid]), gidmap[change.gid])
                    yield self.Action(os.chmod, change.path, str(stat.S_IMODE(change.mode)))

                if optimized:
                    continue

            if change.OP == 'd':
                continue

            # optimization: if not remapped we can skip 'o' changes
            if change.OP == 'o' and \
               change.uid not in uidmap and change.gid not in gidmap:
                continue

            st = os.lstat(change.path)
            if change.OP in ('s', 'o'):
                if not optimized or \
                   (st.st_uid != uidmap[change.uid] or \
                    st.st_gid != gidmap[change.gid]):

                    yield self.Action(os.lchown, change.path,
                                        uidmap[change.uid], gidmap[change.gid])

            if change.OP == 's':
                if not optimized or \
                    (not islink(change.path) and \
                     stat.S_IMODE(st.st_mode) != stat.S_IMODE(change.mode)):
                    yield self.Action(os.chmod, change.path, str(stat.S_IMODE(change.mode)))

def whatchanged(di_path: str, paths: list[str]) -> Changes:
    """Compared current filesystem with a saved dirindex from before.
       Returns a Changes() list."""

    di_saved = DirIndex(di_path)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    new, edited, statfix = di_saved.diff(di_fs)
    changes = Changes()

    changes += [ Change.Overwrite(path) for path in new + edited ]
    changes += [ Change.Stat(path) for path in statfix ]

    di_saved.prune(*paths)
    deleted = set(di_saved) - set(di_fs)
    changes += [ Change.Deleted(path) for path in deleted ]

    return changes
