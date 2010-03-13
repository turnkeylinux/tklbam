import re
import os
import stat
from os.path import *

from pathmap import PathMap

class Error(Exception):
    pass

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

    @classmethod
    def create(cls, path_index, paths):
        """create index from paths"""
        di = cls()
        di.walk(*paths)
        di.save(path_index)
        
        return di

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
            if not exists(path):
                continue

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

        files_new = []
        paths_stat = []

        for path in (b - a):
            if stat.S_ISDIR(other[path].mod):
                paths_stat.append(path)
            else:
                files_new.append(path)

        paths_in_both = b & a
        files_edited = []
        def attrs_equal(attrs, a, b):
            for attr in attrs:
                if getattr(a, attr) != getattr(b, attr):
                    return False

            return True

        for path in paths_in_both:
            if not attrs_equal(('size', 'mtime'), self[path], other[path]):
                if not stat.S_ISDIR(other[path].mod):
                    files_edited.append(path)
                    continue

            if not attrs_equal(('mod', 'uid', 'gid'), self[path], other[path]):
                paths_stat.append(path)
        
        return files_new, files_edited, paths_stat

create = DirIndex.create

def read_paths(fh):
    paths = []
    
    for line in fh.readlines():
        path = re.sub(r'#.*', '', line).strip()
        if not path:
            continue

        # only accept absolute paths
        if not re.match(r'^-?/', path):
            raise Error(`path` + " is not an absolute path")

        paths.append(path)

    return paths
