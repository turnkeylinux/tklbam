# Copyright (c) 2007-2010 Liraz Siri <liraz@turnkeylinux.org>
#               2019 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# turnkey-paths is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

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
print(paths.foo)
print(paths.sub_dir)
print(paths.sub_dir.sub_file)
print(paths.sub_dir2.sub_file2)

print(paths.make_relative(paths.sub_dir, paths.sub_dir.sub_file))

"""
import re
from os.path import join, realpath, dirname, exists
from dataclasses import dataclass
from typing import Self, Optional

from utils import BaseAttrDict

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


class PathsError(Exception):
    pass


class PathsBase(BaseAttrDict):

    path: str
    paths: Optional[list[str]] = None
    paths_cls: Optional[list[Self]] = None


@dataclass
class Paths(PathsBase):
    path: str
    files: Optional[list[Self] | list[str]] = None

    make_relative = staticmethod(make_relative)

    @staticmethod
    def _check_path(path: str) -> str:
        if exists(path):
            if path.startswith('/'):
                return make_relative(path)
            else:
                return path
        return ''

    def __post_init__(self):
        self.path = self._check_path(self.path)

        if not self.path:
            return None

        if not self.files:
            self.files = []

        for file in self.files:
            if isinstance(file, self):
                file = str()
            if '/' in file:
                file_split = file.split('/')
                path_len = len(file_split)
                if path_len == 2:
                    dir_, file = file_split
                if path_len > 4:
                    raise PathsError(
                            f"Max recursion reached while processing {file}")
                else:
                    dir_, file = file_split
                    self.dirs.append(Paths(file_split[0], files=))
                _dir, more_path = file.split('/', 1)

                if len(more_path.split('/')) == 1:
                    self.dirs.append(Paths(_dir))

            if '.' in file or '/' in file or '-' in file:
                setattr(self, file, file)
            if '.' in file or '/' in file or '-' in file:
                new_attr = file.replace('.', '_'
                                        ).replace('/', '_').replace('-', '_')
                setattr(self, new_attr, file)

    def __getattr__(self, name: str) -> str:
        if self.filesd and name in self.filesd.keys():
            return join(self.path, self.filesd[name])

        raise AttributeError("no such attribute: " + name)

    def __str__(self) -> str:
        return self.path

    @staticmethod
    def _fname2attr(fname: str) -> str:
        return re.sub(r'[\.-]', '_', fname)

    def listdir(self) -> list[str]:
        "Return a list containing the names of the entries in directory"""
        if self.files:
            return list(self.files)
        return []

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
