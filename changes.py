import os
from os.path import *

import types

from dirindex import DirIndex
from pathmap import PathMap

import stat

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

            self.mode = stat.S_IMODE(self.mode)

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

class Changes(list):
    def __add__(self, other):
        cls = type(self)
        return cls(list.__add__(self, other))

    @classmethod
    def fromfile(cls, f, paths=None):
        if f == '-':
            fh = sys.stdin
        else:
            fh = file(f)

        changes = [ Change.parse(line) for line in fh.readlines() ]
        if paths:
            pathmap = PathMap(paths)
            changes = [ change for change in changes
                        if pathmap.is_included(change.path) ]

        return cls(changes)

    def deleted(self):
        for change in self:
            if change.OP != 'd':
                continue

            if not exists(change.path):
                continue

            if not islink(change.path) and isdir(change.path):
                continue

            yield change.path
    
    def statfixes(self, uidmap={}, gidmap={}):
        class TransparentMap(dict):
            def __getitem__(self, key):
                if key in self:
                    return dict.__getitem__(self, key)
                return key

        uidmap = TransparentMap(uidmap)
        gidmap = TransparentMap(gidmap)

        for change in self:
            if not exists(change.path):
                continue

            if change.OP == 'd':
                continue
            
            # optimization: if not remapped we can skip 'o' changes
            if change.OP == 'o' and \
               change.uid not in uidmap and change.gid not in gidmap:
                continue

            st = os.lstat(change.path)
            if change.OP in ('s', 'o'):
                if st.st_uid != uidmap[change.uid] or \
                   st.st_gid != gidmap[change.gid]:
                    yield os.chown, (change.path, 
                                     uidmap[change.uid], gidmap[change.gid])

            if change.OP == 's':
                if stat.S_IMODE(st.st_mode) != change.mode:
                    yield os.chmod, (change.path, change.mode)

def whatchanged(di_path, paths):
    di_saved = DirIndex(di_path)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    new, edited, stat = di_saved.diff(di_fs)
    changes = Changes()

    changes += [ Change.Overwrite(path) for path in new + edited ]
    changes += [ Change.Stat(path) for path in stat ]

    di_saved.prune(*paths)
    deleted = set(di_saved) - set(di_fs)
    changes += [ Change.Deleted(path) for path in deleted ]

    return changes
