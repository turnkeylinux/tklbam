#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
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

        def copy(self):
            return type(self)(self[:])

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

    def aliases(self, name):
        if name not in self:
            return []

        name_id = self[name].id
        aliases = []
        for other in self:
            if other == name:
                continue

            if self[other].id == name_id:
                aliases.append(other)

        return aliases

    @staticmethod
    def _merge_get_entry(name, db_old, db_new, merged_ids=[]):
        """get merged db entry (without side effects)"""

        oldent = db_old[name].copy() if name in db_old else None
        newent = db_new[name].copy() if name in db_new else None

        # entry exists in neither
        if oldent is None and newent is None:
            return

        # entry exists only in new db
        if newent and oldent is None:
            return newent

        # entry exists in old db
        ent = oldent

        # entry exists in both new and old dbs
        if oldent and newent:

            if ent.id != newent.id:
                ent.id = newent.id

        # entry exists only in old db
        if oldent and newent is None:

            used_ids = db_new.ids + merged_ids
            if ent.id in used_ids:
                ent.id = db_old.new_id(used_ids)

        return ent

    @classmethod
    def merge_db(cls, db_old, db_new):

        db_merged = cls()
        idmap = {}

        aliased = []
        names = set(db_old) | set(db_new)

        def merge_entry(name):

            ent = cls._merge_get_entry(name, db_old, db_new, db_merged.ids)
            if name in db_old and db_old[name].id != ent.id:
                idmap[db_old[name].id] = ent.id

            db_merged[name] = ent

        # merge non-aliased entries first
        for name in names:

            if db_old.aliases(name):
                aliased.append(name)
                continue

            merge_entry(name)

        def aliased_sort(a, b):
            # sorting order:

            # 1) common entry with common uid first
            # 2) common entry without common uid
            # 3) uncommon entry

            a_has_common_uid = a in db_new and db_new[a].id == db_old[a].id
            b_has_common_uid = b in db_new and db_new[b].id == db_old[b].id

            comparison = cmp(b_has_common_uid, a_has_common_uid)
            if comparison != 0:
                return comparison

            # if we're here, neither a or b has a common uid
            # check if a or b are common to both db_old and db_new

            a_is_common = a in db_old and a in db_new
            b_is_common = b in db_old and b in db_new

            return cmp(b_is_common, a_is_common)

        aliased.sort(aliased_sort)

        def get_merged_alias_id(name):

            for alias in db_old.aliases(name):
                if alias not in db_merged:
                    continue

                return db_merged[alias].id

            return None

        for name in aliased:
            ent = cls.Ent(db_old[name])

            merged_id = get_merged_alias_id(name)

            if merged_id is None:
                merge_entry(name)
            else:
                # merge alias entry with the id of any previously merged alias
                ent.id = merged_id
                db_merged[name] = ent

                if name in db_new and db_new[name].id != ent.id:

                    # we can't remap ids in new, so merge new entry as *_copy of itself
                    new_ent = cls.Ent(db_new[name])
                    new_ent[0] = new_ent[0] + '_orig'

                    db_merged[new_ent[0]] = new_ent

        return db_merged, idmap

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
