#!/usr/bin/python
"""Merge passwd and group files and print uid and gid maps"""
import sys
import os

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s old-passwd old-group new-passwd new-group merged-passwd merged-group" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(s):
    print >> sys.stderr, "error: " + str(s)
    sys.exit(1)

def parse_passwd(path):
    users = {}
    for line in file(path).readlines():
        vals = line.strip().split(':')
        username = vals[0]
        users[username] = vals[1:]

class Error(Exception):
    pass

class Base(dict):
    class Ent(list):
        def id(self, val=None):
            if val:
                self[2] = str(val)
            else:
                return int(self[2])
        id = property(id, id)

    def __init__(self, arg=None):
        if not arg:
            return

        if isinstance(arg, str):
            for line in arg.strip().split('\n'):
                vals = line.split(':')
                name = vals[0]
                self[name] = self.Ent(vals)

        elif isinstance(arg, dict):
            dict.__init__(self, arg)

    def __str__(self):
        arr = [ self[name] for name in self ]
        # order by id ascending
        arr.sort(lambda x,y: cmp(x.id, y.id))
        return "\n".join([ ':'.join(ent) for ent in arr ])

    def ids(self):
        return [ self[name].id for name in self ]
    ids = property(ids)

    def new_id(self, old_id=1000):
        """find first new id in the same number range as old id"""
        ids = set(self.ids)

        _range = None
        if old_id < 100:
            _range = (1, 100)
        elif old_id < 1000:
            _range = (100, 1000)

        if _range:
            for id in range(*_range):
                if id not in ids:
                    return id

        for id in range(1000, 65534):
            if id not in ids:
                return id

        raise Error("can't find slot for new id")

    @classmethod
    def merge(cls, old, new):

        merged = cls()
        idmap = {}

        names = set(old) | set(new)
        for name in names:

            if name in old and name in new:
                merged[name] = cls.Ent(old[name])
                merged[name].id = new[name].id

                if old[name].id != new[name].id:
                    idmap[old[name].id] = new[name].id

            elif name in new:
                merged[name] = cls.Ent(new[name])

            elif name in old:
                merged[name] = cls.Ent(old[name])
                if old[name].id in new.ids:
                    merged[name].id = new.new_id()
                    idmap[old[name].id] = merged[name].id

        return merged, idmap

class EtcGroup(Base):
    class Ent(Base.Ent):
        gid = Base.Ent.id

class EtcPasswd(Base):
    class Ent(Base.Ent):
        uid = Base.Ent.id
        def gid(self, val=None):
            if val:
                self[3] = str(val)
            else:
                return int(self[3])
        gid = property(gid, gid)

    def fixgids(self, gidmap):
        for name in self:
            oldgid = self[name].gid
            if oldgid in gidmap:
                self[name].gid = gidmap[oldgid]

def main():
    args = sys.argv[1:]
    if len(args) != 6:
        usage()

    old_passwd, old_group = args[:2]
    new_passwd, new_group = args[2:4]
    merged_passwd, merged_group = args[4:6]

    g1 = EtcGroup(file(old_group).read())
    g2 = EtcGroup(file(new_group).read())

    g3, gidmap = EtcGroup.merge(g1, g2)

    p1 = EtcPasswd(file(old_passwd).read())
    p2 = EtcPasswd(file(new_passwd).read())

    p3, uidmap = EtcPasswd.merge(p1, p2)
    p3.fixgids(gidmap)

    print >> file(merged_group, "w"), g3
    print >> file(merged_passwd, "w"), p3

    def strmap(m):
         return ":".join([ "%d,%d" % (key, val) for key,val in m.items() ])

    print strmap(uidmap)
    print strmap(gidmap)

if __name__=="__main__":
    main()

