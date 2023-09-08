#
# Copyright (c) 2007-2010 Liraz Siri <liraz@turnkeylinux.org>
#               2019 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# turnkey-paths is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
DESCRIPTION

This modules contains:
1) Paths: high-level class for representing file paths
2) make_relative: convenience function for recalculating a path relative to
   another base path

File paths are accessible as instance attributes
. and - are replaced for _

The files attribute is "inherited".

USAGE

class FooPaths(Paths):
        files = ["foo", "sub.dir/sub-file"]

class BarPaths(FooPaths):
        files = [ "bar" ] + subdir("sub.dir2", ["sub-file2"])

class DefaultPath(Paths):
    @classmethod
    def create(cls, path=None):
        if path is None:
            path = os.environ.get('DEFAULT_PATH', os.getcwd())

        return cls(path)

paths = BarPaths("/tmp")
print paths.foo
print paths.sub_dir
print paths.sub_dir.sub_file
print paths.sub_dir2.sub_file2

print paths.make_relative(paths.sub_dir, paths.sub_dir.sub_file)

"""
import re
import os
from os.path import join, realpath, dirname
from typing import Self

__all__ = ['make_relative', 'Paths', 'subdir']


def make_relative(base: str, path: str) -> str:
    """Return <path> relative to <base>.

    For example:
        make_relative("../../", "file") == "path/to/file"
        make_relative("/base", "/tmp") == "../tmp"
        make_relative("/base", "/base/backups/file") == "backups/file"

    """

    up_count = 0

    base = realpath(str(base)).rstrip('/')
    path = realpath(str(path)).rstrip('/')

    while True:
        if path == base or path.startswith(base.rstrip("/") + "/"):
            return ("../" * up_count) + path[len(base) + 1:]

        base = dirname(base).rstrip('/')
        up_count += 1


class Paths(str):
    make_relative = staticmethod(make_relative)

    files: list[str] = []

    def __new__(cls, path: str, files: list[str] = []) -> Self:
        return str.__new__(cls, path)

    def __init__(self, path: str, files: list[str] = []):
        self.path = path
        self.filesd: dict[str, str] = {}

        def classfiles(cls) -> list[str]:
            files = cls.files
            for base in cls.__bases__:
                if issubclass(base, Paths):
                    files += classfiles(base)

            return files

        for file in files + classfiles(self.__class__):
            self.register(file)

    def __getattr__(self, name: str) -> str:
        if name in self.filesd.keys():
            return join(self.path, self.filesd[name])

        raise AttributeError("no such attribute: " + name)

    @staticmethod
    def _fname2attr(fname: str) -> str:
        return re.sub(r'[\.-]', '_', fname)

    def listdir(self) -> list[str]:
        "Return a list containing the names of the entries in directory"""
        return list(self.files)

    def register(self, filename: str) -> None:
        if '/' in filename:
            subdir, filename = filename.split('/', 1)
            attr = self._fname2attr(subdir)
            subpaths = getattr(self, attr, None)
            if not subpaths or not isinstance(subpaths, Paths):
                subpaths = Paths(join(self.path, subdir))
                setattr(self, attr, subpaths)

            subpaths.register(filename)
        else:
            attr = self._fname2attr(filename)
            self.filesd[attr] = filename


def subdir(dir: str, files: list[str]) -> list[str]:
    return [os.path.join(dir, file) for file in files]


def test():
    class FooPaths(Paths):
            files = ["foo", "sub.dir/sub-file"]

    class BarPaths(FooPaths):
            files = ["bar"] + subdir("sub.dir2", ["sub-file2"])

    paths = BarPaths("/tmp")
    print(paths.foo)
    print(paths.sub_dir)
    print(paths.sub_dir.sub_file)
    print(paths.sub_dir2.sub_file2)

    return paths


if __name__ == "__main__":
    test()
