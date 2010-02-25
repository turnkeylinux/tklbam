#!/usr/bin/python
"""Merge group and passwd files and print uid and gid maps"""
import sys
import os

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s old-group old-passwd new-group new-passwd merged-group merged-passwd" % sys.argv[0]
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

class EtcGroup(dict):
    class Ent(list):
        def gid(self, val=None):
            if val:
                self[2] = str(val)
            else:
                return int(self[2])
        gid = property(gid, gid)

    def __init__(self, buf=None):
        if not buf:
            return

        for line in buf.strip().split('\n'):
            vals = line.split(':')
            if len(vals) != 4:
                raise Error("bad line in group '%s'" % line)

            name = vals[0]
            self[name] = EtcGroup.Ent(vals)

    def __str__(self):
        arr = [ self[name] for name in self ]
        # order by gid ascending
        arr.sort(lambda x,y: cmp(x.gid, y.gid))
        return "\n".join([ ':'.join(ent) for ent in arr ])

    def gids(self):
        return [ self[name].gid for name in self ]
    gids = property(gids)

    def new_gid(self, old_gid=1000):
        """find first new gid in the same number range as old gid"""
        gids = set(self.gids)

        _range = None
        if old_gid < 100:
            _range = (1, 100)
        elif old_gid < 1000:
            _range = (100, 1000)

        if _range:
            for gid in range(*_range):
                if gid not in gids:
                    return gid

        for gid in range(1000, 65534):
            if gid not in gids:
                return gid

        raise Error("can't find slot for new gid")

    @classmethod
    def merge(cls, old, new):

        merged = EtcGroup()
        gidmap = {}

        names = set(old) | set(new)
        for name in names:

            if name in old and name in new:
                merged[name] = EtcGroup.Ent(old[name])
                merged[name].gid = new[name].gid

                if old[name].gid != new[name].gid:
                    gidmap[old[name].gid] = new[name].gid

            elif name in new:
                merged[name] = EtcGroup.Ent(new[name])

            elif name in old:
                merged[name] = EtcGroup.Ent(old[name])
                if old[name].gid in new.gids:
                    merged[name].gid = new.new_gid()
                    gidmap[old[name].gid] = merged[name].gid

        return merged, gidmap

def parse_group(path):
    groups = {}
    return groups

def main():
    args = sys.argv[1:]
    if len(args) != 6:
        usage()

    old_group, old_passwd = args[:2]
    new_group, new_passwd = args[2:4]
    merged_group, merged_passwd = args[4:6]

    g1 = EtcGroup(file(old_group).read())
    g2 = EtcGroup(file(new_group).read())

    g3, gidmap = EtcGroup.merge(g1, g2)

    #p1 = EtcPasswd(file(old_passwd).read())
    #p2 = EtcPasswd(file(new_passwd).read())

    #p3, uidmap = EtcPasswd.merge(p1, p2, gidmap)

    print g3

if __name__=="__main__":
    main()

