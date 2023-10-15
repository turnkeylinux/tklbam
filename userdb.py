#
# Copyright (c) 2010-2016 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import logging

from collections import OrderedDict
from typing import Optional, Self
from functools import cmp_to_key

class Error(Exception):
    pass

logging.basicConfig(level=logging.DEBUG)

class Base(OrderedDict):
    class Ent(list):
        LEN: Optional[int] = None

        def _getter(self) -> Optional[str]:
            return self._field(0)

        def _setter(self, val: Optional[int]) -> None:
            self._field(0, val)

        def _field(self, index: int, val: Optional[int] = None) -> Optional[str]:
            if val is not None:
                self[index] = str(val)
            else:
                return self[index]
            return None

        name = property(_getter, _setter)
        id = property(_getter, _setter)

        def copy(self) -> list:
            return type(self)(self[:])

    def _fix_missing_root(self) -> Optional[str]:

        if 'root' in self:
            return None

        def get_altroot(db: Self) -> Optional[str]:
            for name in db:
                if db[name].id == 0:
                    altroot = db[name].copy()
                    break

            else:
                names = list(db.keys())
                if not names:
                    return None # empty db, nothing we can do.

                altroot = db[names.pop()].copy()
                altroot.id = 0

            altroot.name = 'root'
            return altroot

        self['root'] = get_altroot(self)
        return None

    def __init__(self, arg: Optional[str|dict[str, str]] = None):
        super().__init__()

        if not arg:
            return None

        if isinstance(arg, str):
            for line in arg.strip().split('\n'):
                vals = line.split(':')
                if self.Ent.LEN:
                    if len(vals) != self.Ent.LEN:
                        raise Error("line with incorrect field count (%d != %d) '%s'" % (len(vals), self.Ent.LEN, line))

                name = vals[0]
                self[name] = self.Ent(vals)

            self._fix_missing_root()

        elif isinstance(arg, dict):
            super().__init__(arg)

    def __str__(self) -> str:
        ents = list(self.values())
        ents.sort(key=lambda ent: ent.id)

        return "\n".join([ ':'.join(ent) for ent in ents ]) + "\n"

    def ids_setter_getter(self):
        return [ self[name].id for name in self ]
    ids = property(ids_setter_getter)

    def new_id(self, extra_ids: list[int] = [], old_id: int = 1000) -> int:
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

    def aliases(self, name: str) -> list[str]:
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
    def _merge_get_entry(name: str, db_old, db_new,
                         #db_old : Base,
                         #db_new : Base,
                         merged_ids: Optional[list[str]] = None
                         ) -> Optional[str]:
        """get merged db entry (without side effects)"""
        if not merged_ids:
            merged_ids = []

        oldent = db_old[name].copy() if name in db_old else None
        newent = db_new[name].copy() if name in db_new else None

        # entry exists in neither
        if oldent is None and newent is None:
            return None

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
    def merge(cls, db_old, db_new
              #db_old: Base,
              #db_new: Base
              ):  # -> tuple[Base, dict[str, str]]:
        logging.debug(f'\nmerge(cls,\n\t{db_old=}\n\t{db_new=}')

        db_merged = cls()
        old2newids = {}

        aliased = []
        names = set(db_old) | set(db_new)

        def merge_entry(name: str) -> None:

            ent = cls._merge_get_entry(name, db_old, db_new, db_merged.ids)
            #if name in db_old and db_old[name].id != ent.id:
            #if name in db_old and isinstance(db_old[name], str) and hasattr(ent, 'id') and db_old[name].id != ent.id:
            if name in db_old and isinstance(db_old[name], str) and ent is not None and hasattr(ent, 'id') and db_old[name].id != ent.id:
                old2newids[db_old[name].id] = ent.id

            db_merged[name] = ent

        # merge non-aliased entries first
        for name in names:

            if db_old.aliases(name):
                aliased.append(name)
                continue

            merge_entry(name)

        def aliased_sort(a: str, b: str) -> int:
            logging.debug(f'aliased_sort_key({a=}, {b=}')
            # sorting order:

            # 1) common entry with common uid first
            # 2) common entry without common uid
            # 3) uncommon entry

            a_has_common_uid = a in db_new and db_new[a].id == db_old[a].id
            b_has_common_uid = b in db_new and db_new[b].id == db_old[b].id

            comparison = (b_has_common_uid > a_has_common_uid) - (b_has_common_uid < a_has_common_uid)
            if comparison != 0:
                return comparison

            # if we're here, neither a or b has a common uid
            # check if a or b are common to both db_old and db_new

            a_is_common = a in db_old and a in db_new
            b_is_common = b in db_old and b in db_new

            #return cmp(b_is_common, a_is_common)
            return (b_is_common > a_is_common) - (b_is_common < a_is_common)

        logging.info(f'Sorting aliased:\n{aliased=}\n{aliased_sort=}')
        aliased.sort(key=cmp_to_key(aliased_sort))

        def get_merged_alias_id(name: str) -> Optional[str]:

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
                    new_ent.name = new_ent.name + '_orig'

                    db_merged[new_ent.name] = new_ent

        return db_merged, old2newids

class EtcGroup(Base):
    class Ent(Base.Ent):
        LEN = 4
        gid = Base.Ent.id

class EtcPasswd(Base):
    class Ent(Base.Ent):
        LEN = 7
        uid = Base.Ent.id

        def _getter(self) -> Optional[str]:
            return self._field(0)
        def _setter(self, val: Optional[int]) -> None:
            self._field(0, val)

        gid = property(_getter, _setter)

    def fixgids(self, gidmap: dict[str, str]) -> None:
        for name in self:
            oldgid = self[name].gid
            if oldgid in gidmap:
                self[name].gid = gidmap[oldgid]

def merge(old_passwd: str, old_group: str, new_passwd: str, new_group: str) -> tuple[Base, Base, dict[str, str], dict[str, str]]:
    logging.debug(f'\nmerge(\n\t{old_passwd=},\n\t{old_group=},\n\t{new_passwd=},\n\t{new_group=})')
    g1 = EtcGroup(old_group)
    g2 = EtcGroup(new_group)

    group, gidmap = EtcGroup.merge(g1, g2)

    p1 = EtcPasswd(old_passwd)
    p2 = EtcPasswd(new_passwd)

    p1.fixgids(gidmap)

    passwd, uidmap = EtcPasswd.merge(p1, p2)
    return passwd, group, uidmap, gidmap
