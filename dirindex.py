#!/usr/bin/python
"""Print a list of files that have changed

Options:
    -i --input=PATH     Read a list of paths frmo a file (- for stdin)

    -c --create         Create index
"""
import re
import sys
import getopt

import os
import stat
from os.path import *

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

    @staticmethod
    def _parse_paths(paths):
        includes = []
        excludes = []

        for path in paths:
            if path[0] == '-':
                excludes.append(abspath(path[1:]))
            else:
                includes.append(abspath(path))

        return includes, excludes

    @staticmethod
    def _included(path, includes):
        for include in includes:
            if path == include or path.startswith(include + '/'):
                return True

        return False

    def __init__(self, fromfile=None):
        if fromfile:
            for line in file(fromfile).readlines():
                rec = DirIndex.Record.fromline(line)
                self[rec.path] = rec

    def walk(self, *paths):
        """walk paths and add files to index"""
        includes, excludes = self._parse_paths(paths)

        def _walk(dir):
            dentries = []

            for dentry in os.listdir(dir):
                path = join(dir, dentry)
                dentries.append(dentry)

                if not islink(path) and isdir(path):
                    for val in _walk(path):
                        yield val

            yield dir, dentries

        for path in includes:
            if islink(path) or not isdir(path):
                continue

            for dpath, dentries in _walk(path):
                for dentry in dentries:
                    path = join(dpath, dentry)

                    if self._included(path, excludes):
                        continue
                    
                    st = os.lstat(path)
                    self[path] = DirIndex.Record(path, 
                                                 st.st_mode, 
                                                 st.st_uid, st.st_gid, 
                                                 st.st_size, st.st_mtime)

    def prune(self, *paths):
        """prune index down to paths that are included AND not excluded"""

        includes, excludes = self._parse_paths(paths)

        for path in self.keys():
            if not self._included(path, includes) or self._included(path, excludes):
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
    def __init__(self, path):
        self.path = path

class ChangeDeleted(Change):
    def fmt(self):
        return "d\t" + self.path

class ChangeOverwrite(Change):
    def fmt(self):
        st = os.stat(self.path)
        return "o\t%s\t%d\t%d" % (self.path, st.st_uid, st.st_gid)

class ChangeStat(Change):
    def fmt(self):
        st = os.stat(self.path)
        return "s\t%s\t%d\t%d\t%s" % (self.path, st.st_uid, st.st_gid, oct(st.st_mode))

def whatchanged(path_index, paths):
    di_saved = DirIndex(path_index)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    new, edited, stat = di_saved.diff(di_fs)
    changes = [ ChangeOverwrite(path) for path in new + edited ]

    changes += [ ChangeStat(path) for path in stat ]

    di_saved.prune(*paths)
    deleted = set(di_saved) - set(di_fs)
    changes += [ ChangeDeleted(path) for path in deleted ]

    return changes

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s index path1 ... pathN" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(s):
    print >> sys.stderr, "error: " + str(s)
    sys.exit(1)

def parse_input(inputfile):
    paths = []
    
    if inputfile == '-':
        fh = sys.stdin
    else:
        fh = file(inputfile)

    for line in fh.readlines():
        line = re.sub(r'#.*', '', line).strip()
        if not line:
            continue

        paths.append(line)

    return paths

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:cdh', 
                                       ['deleted', 'create', 'input='])
    except getopt.GetoptError, e:
        usage(e)

    opt_create = False
    opt_input = None

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        elif opt in ('-c', '--create'):
            opt_create = True

        elif opt in ('-i', '--input'):
            opt_input = val

    if not args or (not opt_input and len(args) < 2):
        usage()

    path_index = args[0]
    paths = args[1:]
    
    if opt_input:
        paths += parse_input(opt_input)

    if opt_create:
        create(path_index, paths)
        return

    for change in whatchanged(path_index, paths):
        print change.fmt()

if __name__=="__main__":
    main()

