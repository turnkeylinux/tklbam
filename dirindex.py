import os
import stat
from os.path import *

import glob
import types

class Error(Exception):
    pass

class PathMap(dict):
    @staticmethod
    def _expand(path):
        def needsglob(path):
            for c in ('*?[]'):
                if c in path:
                    return True
            return False

        path = abspath(path)
        if needsglob(path):
            return glob.glob(path)
        else:
            return [ path ]

    def __init__(self, paths):
        for path in paths:
            if path[0] == '-':
                path = path[1:]
                sign = False
            else:
                sign = True

            for expanded in self._expand(path):
                self[expanded] = sign

    def includes(self):
        for path in self:
            if self[path]:
                yield path
    includes = property(includes)

    def excludes(self):
        for path in self:
            if not self[path]:
                yield path
    excludes = property(excludes)

    def is_included(self, path):
        while path not in ('', '/'):
            if path in self:
                return self[path]
            path = dirname(path)

        return False

class DirIndex(dict):
    class Record:
        def __init__(self, path, mod, uid, gid, size, mtime):
            self.path = path
            self.mod = mod
            self.uid = uid
            self.gid = gid
            self.size = size
            self.mtime = mtime

        @classmethod
        def fromline(cls, line):
            vals = line.strip().split('\t')
            if len(vals) != 6:
                raise Error("bad index record: " + line)

            path = vals[0]
            del vals[0]

            vals = [ int(val, 16) for val in vals ]
            return cls(path, *vals)

        def fmt(self):
            vals = [ self.path ] 
            for val in ( self.mod, self.uid, self.gid, self.size, self.mtime ):
                vals.append("%x" % val)

            return "\t".join(vals)

        def __repr__(self):
            return "DirIndex.Record(%s, mod=%s, uid=%d, gid=%d, size=%d, mtime=%d)" % \
                    (`self.path`, oct(self.mod), self.uid, self.gid, self.size, self.mtime)

    def __init__(self, fromfile=None):
        if fromfile:
            for line in file(fromfile).readlines():
                rec = DirIndex.Record.fromline(line)
                self[rec.path] = rec

    def _add_path(self, path):
        st = os.lstat(path)
        self[path] = DirIndex.Record(path, 
                                     st.st_mode, 
                                     st.st_uid, st.st_gid, 
                                     st.st_size, st.st_mtime)

    def walk(self, *paths):
        """walk paths and add files to index"""
        pathmap = PathMap(paths)

        def _walk(dir):
            dentries = []

            for dentry in os.listdir(dir):
                path = join(dir, dentry)
                if path in pathmap.excludes:
                    continue
                
                dentries.append(dentry)

                if not islink(path) and isdir(path):
                    for val in _walk(path):
                        yield val

            yield dir, dentries

        for path in pathmap.includes:

            self._add_path(path)

            if islink(path) or not isdir(path):
                continue

            for dpath, dentries in _walk(path):
                for dentry in dentries:
                    path = join(dpath, dentry)

                    self._add_path(path)

    def prune(self, *paths):
        """prune index down to paths that are included AND not excluded"""

        pathmap = PathMap(paths)
        for path in self.keys():
            if not pathmap.is_included(path):
                del self[path]

    def save(self, tofile):
        fh = file(tofile, "w")
        paths = self.keys()
        paths.sort()
        for path in paths:
            print >> fh, self[path].fmt()

    def diff(self, other):
        a = set(self)
        b = set(other)

        paths_new = list(b - a)
        paths_in_both = b & a

        paths_edited = []
        paths_stat = []

        def attrs_equal(attrs, a, b):
            for attr in attrs:
                if getattr(a, attr) != getattr(b, attr):
                    return False

            return True

        for path in paths_in_both:
            if not attrs_equal(('size', 'mtime'), self[path], other[path]):
                if not stat.S_ISDIR(other[path].mod):
                    paths_edited.append(path)
                    continue

            if not attrs_equal(('mod', 'uid', 'gid'), self[path], other[path]):
                paths_stat.append(path)
        
        return paths_new, paths_edited, paths_stat

def create(path_index, paths):
    """create index from paths"""
    di = DirIndex()
    di.walk(*paths)
    di.save(path_index)

class Change:
    class Base:
        OP = None
        def __init__(self, path):
            self.path = path
            self._stat = None

        def stat(self):
            if not self._stat:
                self._stat = os.lstat(self.path)

            return self._stat
        stat = property(stat)

        def fmt(self, *args):
            return "\t".join([self.OP, self.path] + map(str, args))

        def __str__(self):
            return self.fmt()

        @classmethod
        def fromline(cls, line):
            args = line.rstrip().split('\t')
            return cls(*args)

    class Deleted(Base):
        OP = 'd'

    class Overwrite(Base):
        OP = 'o'
        def __init__(self, path, uid=None, gid=None):
            Change.Base.__init__(self, path)

            if uid is None:
                self.uid = self.stat.st_uid
            else:
                self.uid = int(uid)

            if gid is None:
                self.gid = self.stat.st_gid
            else:
                self.gid = int(gid)

        def __str__(self):
            return self.fmt(self.uid, self.gid)

    class Stat(Overwrite):
        OP = 's'
        def __init__(self, path, uid=None, gid=None, mode=None):
            Change.Overwrite.__init__(self, path, uid, gid)
            if mode is None:
                self.mode = self.stat.st_mode
            else:
                if isinstance(mode, int):
                    self.mode = mode
                else:
                    self.mode = int(mode, 8)

        def __str__(self):
            return self.fmt(self.uid, self.gid, oct(self.mode))

    @classmethod
    def parse(cls, line):
        op2class = dict((val.OP, val) for val in cls.__dict__.values() 
                        if isinstance(val, types.ClassType))
        op = line[0]
        if op not in op2class:
            raise Error("illegal change line: " + line)

        return op2class[op].fromline(line[2:])

def whatchanged(path_index, paths):
    di_saved = DirIndex(path_index)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    new, edited, stat = di_saved.diff(di_fs)
    changes = [ Change.Overwrite(path) for path in new + edited ]

    changes += [ Change.Stat(path) for path in stat ]

    di_saved.prune(*paths)
    deleted = set(di_saved) - set(di_fs)
    changes += [ Change.Deleted(path) for path in deleted ]

    return changes

