import os
from os.path import *

class Error(Exception):
    pass

class DirIndex(dict):
    @staticmethod
    def _parse(line):
        vals = line.strip().split('\t')
        if len(vals) != 3:
            raise Error("bad index record: " + line)

        path = vals[0]
        mtime, size = int(vals[1]), int(vals[2])

        return path, mtime, size

    @staticmethod
    def _fmt(path, mtime, size):
        return "%s\t%d\t%d" % (path, mtime, size)

    def __init__(self, fromfile=None):
        if fromfile:
            for line in file(fromfile).readlines():
                path, mtime, size = self._parse(line)
                self[path] = (mtime, size)

    def walk(self, *paths):
        includes = []
        excludes = []

        for path in paths:
            if path[0] == '-':
                excludes.append(abspath(path[1:]))
            else:
                includes.append(abspath(path))

        def excluded(path):
            for exclude in excludes:
                if path == exclude or path.startswith(exclude + '/'):
                    return True

            return False

        for path in includes:
            for dpath, dnames, fnames in os.walk(path):
                for fname in fnames:
                    path = join(dpath, fname)
                    if excluded(path):
                        continue
                    
                    st = os.lstat(path)
                    self[path] = (int(st.st_mtime), int(st.st_size))

    def save(self, tofile):
        fh = file(tofile, "w")
        paths = self.keys()
        paths.sort()
        for path in paths:
            print >> fh, self._fmt(path, *self[path])

    def new_or_changed(self, other):
        a = set(self)
        b = set(other)

        delta = list(b - a)
        samepaths = b & a

        for path in samepaths:
            if self[path] != other[path]:
                delta.append(path)
        
        return delta

    def prune(self, *paths):
        includes = []
        excludes = []

        for path in paths:
            if path[0] == '-':
                excludes.append(abspath(path[1:]))
            else:
                includes.append(abspath(path))

        def included(path, includes):
            for include in includes:
                if path == include or path.startswith(include + '/'):
                    return True

            return False

        for path in self.keys():
            if not included(path, includes) or included(path, excludes):
                del self[path]

def create(path_index, paths):
    di = DirIndex()
    di.walk(*paths)
    di.save(path_index)

def new_or_changed(path_index, paths):
    di_saved = DirIndex(path_index)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    return di_saved.new_or_changed(di_fs)

def deleted(path_index, paths):
    di_saved = DirIndex(path_index)
    di_saved.prune(*paths)

    di_fs = DirIndex()
    di_fs.walk(*paths)

    return set(di_saved) - set(di_fs)
