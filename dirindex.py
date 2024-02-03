# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

import re
import os
import stat
from os.path import lexists, islink, isdir, join

from pathmap import PathMap

from dataclasses import dataclass
from typing import Optional, Self, Generator, IO


class Error(Exception):
    pass


class DirIndex(dict):
    @dataclass
    class Record:
        path: str
        mod: int
        uid: int
        gid: int
        size: int
        mtime: float
        symlink: Optional[str] = None

        @classmethod
        def frompath(cls, path: str) -> Self:
            st = os.lstat(path)

            symlink = (os.readlink(path)
                       if stat.S_ISLNK(st.st_mode)
                       else None)

            rec = cls(path,
                      st.st_mode,
                      st.st_uid,
                      st.st_gid,
                      st.st_size,
                      st.st_mtime,
                      symlink)
            return rec

        @classmethod
        def fromline(cls, line: str) -> Self:
            line_split = line.strip().split('\t')
            if len(line_split) == 6:
                path, mod, uid, gid, size, mtime = line_split
                symlink = None
            elif len(line_split) == 7:
                path, mod, uid, gid, size, mtime, symlink = line_split
            else:
                raise Error("bad index record: " + line)

            return cls(path,
                       int(mod, 16),
                       int(uid, 16),
                       int(gid, 16),
                       int(size, 16),
                       float(mtime),
                       symlink)

        def fmt(self) -> str:
            vals = [self.path, self.mod, self.uid,
                    self.gid, self.size, self.mtime]
            if self.symlink:
                vals.append(self.symlink)
            return "\t".join(map(str, vals))

        def __repr__(self) -> str:
            return (f"DirIndex.Record({repr(self.path)}, mod={oct(self.mod)},"
                    f" uid={self.uid}, gid={self.gid}, size={self.size},"
                    f" mtime=self.mtime)")

    @classmethod
    def create(cls, path_index: str, paths: list[str]) -> Self:
        """create index from paths"""
        di = cls()
        di.walk(*paths)
        di.save(path_index)
        return di

    def __init__(self, fromfile: Optional[str] = None):
        if fromfile:
            with open(fromfile) as fob:
                for line in fob.readlines():
                    if not line.strip():
                        continue

                    rec = DirIndex.Record.fromline(line)
                    self[rec.path] = rec

    def add_path(self, path: str) -> None:
        """add a single path to the DirIndex"""
        self[path] = DirIndex.Record.frompath(path)

    def walk(self, *paths: str) -> Generator[str, None, None]:
        """walk paths and add files to index"""
        pathmap = PathMap(list(paths))

        def _walk(dir_: str) -> Generator[tuple[str, list[str]], None, None]:
            dentries: list[str] = []

            for dentry in os.listdir(dir_):
                path = join(dir_, dentry)
                if path in pathmap.excludes:
                    continue
                dentries.append(dentry)

                if not islink(path) and isdir(path):
                    for val in _walk(path):
                        yield val

            yield dir_, dentries

        for path in pathmap.includes:
            if not lexists(path):
                continue

            self.add_path(path)

            if islink(path) or not isdir(path):
                continue

            for dpath, dentries in _walk(path):
                for dentry in dentries:
                    path = join(dpath, dentry)

                    self.add_path(path)
        yield ''

    def prune(self, *paths: str) -> None:
        """prune index down to paths that are included AND not excluded"""

        pathmap = PathMap(list(paths))
        for path in list(self.keys()):
            if path not in pathmap:
                del self[path]

    def save(self, tofile: str) -> None:
        paths = list(self.keys())
        paths.sort()
        with open(tofile, "w") as fh:
            for path in paths:
                print(self[path].fmt(), file=fh)

    def diff(self, other: Self) -> tuple[list[str], list[str], list[str]]:
        a = set(self)
        b = set(other)

        files_new = []
        paths_stat = []

        for path in (b - a):
            mod = other[path].mod

            # ignore Unix sockets
            if stat.S_ISSOCK(mod):
                continue

            if stat.S_ISDIR(mod):
                paths_stat.append(path)
            else:
                files_new.append(path)

        paths_in_both = b & a
        files_edited = []

        def attrs_equal(attrs: list[str], a: str, b: str) -> bool:
            for attr in attrs:
                if getattr(a, attr) != getattr(b, attr):
                    return False

            return True

        def symlink_equal(a,  #: Self,
                          b  #: Self
                          ) -> bool:
            if a.symlink and (a.symlink == b.symlink):
                return True

            return False

        for path in paths_in_both:
            if not attrs_equal(['size', 'mtime'], self[path], other[path]):
                mod = other[path].mod
                if not (stat.S_ISDIR(mod) or stat.S_ISSOCK(mod)) \
                   and not symlink_equal(self[path], other[path]):
                    files_edited.append(path)
                    continue

            if not attrs_equal(['mod', 'uid', 'gid'], self[path], other[path]):
                paths_stat.append(path)

        return files_new, files_edited, paths_stat


create = DirIndex.create


def read_paths(fh: IO[str]) -> list[str]:
    paths = []

    for line in fh.readlines():
        path = re.sub(r'#.*', '', line).strip()
        if not path:
            continue

        # only accept absolute paths
        if not re.match(r'^-?/', path):
            raise Error(repr(path) + " is not an absolute path")

        paths.append(path)

    return paths
