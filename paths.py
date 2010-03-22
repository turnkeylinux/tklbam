"""
DESCRIPTION

This modules contains:
1) Paths: high-level class for representing file paths
2) make_relative: convenience function for recalculating a path relative to another base path

File paths are accessible as instance attributes
. and - are replaced for _

The files attribute is "inherited".

USAGE

class FooPaths(Paths):
	files = ["foo", "sub.dir/sub-file"]

class BarPaths(FooPaths):
	files = [ "bar" ] + subdir("sub.dir2", ["sub-file2"])

paths = BarPaths("/tmp")
print paths.foo
print paths.sub_dir
print paths.sub_dir.sub_file
print paths.sub_dir2.sub_file2

print paths.make_relative(paths.sub_dir, paths.sub_dir.sub_file)

"""
import re
import os
from os.path import *

__all__ = ['make_relative', 'Paths', 'subdir']
def make_relative(base, path):
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
    
    files = []
    def __new__(cls, path, files=[]):
        return str.__new__(cls, path)

    def __init__(self, path, files=[]):
        self.path = path
        self.files = {}

        def classfiles(cls):
            files = cls.files
            for base in cls.__bases__:
                if issubclass(base, Paths):
                    files += classfiles(base)

            return files

        for file in files + classfiles(self.__class__):
            self.register(file)

    def __getattr__(self, name):
        if self.files.has_key(name):
            return join(self.path, self.files[name])

        raise AttributeError("no such attribute: " + name)

    @staticmethod
    def _fname2attr(fname):
        return re.sub(r'[\.-]', '_', fname)
    
    def listdir(self):
        "Return a list containing the names of the entries in directory"""
        return self.files.values()

    def register(self, filename):
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
            self.files[attr] = filename

def subdir(dir, files):
    return [ os.path.join(dir, file) for file in files ]

def test():
    class FooPaths(Paths):
            files = ["foo", "sub.dir/sub-file"]

    class BarPaths(FooPaths):
            files = [ "bar" ] + subdir("sub.dir2", ["sub-file2"])

    paths = BarPaths("/tmp")
    print paths.foo
    print paths.sub_dir
    print paths.sub_dir.sub_file
    print paths.sub_dir2.sub_file2

    return paths

if __name__ == "__main__":
    test()

