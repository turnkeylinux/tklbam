# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
class Error(Exception):
    pass

class Base(dict):
    class Ent(list):
        LEN = None

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
                if self.Ent.LEN:
                    if len(vals) != self.Ent.LEN:
                        raise Error("line with incorrect field count (%d != %d) '%s'" % (len(vals), self.Ent.LEN, line))

                name = vals[0]
                self[name] = self.Ent(vals)

        elif isinstance(arg, dict):
            dict.__init__(self, arg)

    def __str__(self):
        arr = [ self[name] for name in self ]
        # order by id ascending
        arr.sort(lambda x,y: cmp(x.id, y.id))
        return "\n".join([ ':'.join(ent) for ent in arr ]) + "\n"

    def ids(self):
        return [ self[name].id for name in self ]
    ids = property(ids)

    def new_id(self, extra_ids=[], old_id=1000):
        """find first new id in the same number range as old id"""
        ids = set(self.ids + extra_ids)

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
                    merged[name].id = new.new_id(old.ids)
                    idmap[old[name].id] = merged[name].id

        return merged, idmap

class EtcGroup(Base):
    class Ent(Base.Ent):
        LEN = 4
        gid = Base.Ent.id

class EtcPasswd(Base):
    class Ent(Base.Ent):
        LEN = 7
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

def merge(old_passwd, old_group, new_passwd, new_group):
    g1 = EtcGroup(old_group)
    g2 = EtcGroup(new_group)

    group, gidmap = EtcGroup.merge(g1, g2)

    p1 = EtcPasswd(old_passwd)
    p2 = EtcPasswd(new_passwd)

    p1.fixgids(gidmap)

    passwd, uidmap = EtcPasswd.merge(p1, p2)
    return passwd, group, uidmap, gidmap
