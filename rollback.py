# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
import os
from os.path import *

import stat
import shutil

from datetime import datetime
from paths import Paths

import mysql
from changes import Changes
from dirindex import DirIndex
from pkgman import Packages

from utils import remove_any

class Error(Exception):
    pass

class Rollback:
    Error = Error

    PATH = "/var/backups/tklbam-rollback"
    class Paths(Paths):
        files = [ 'etc', 'etc/mysql', 
                  'fsdelta', 'dirindex', 'originals', 
                  'newpkgs', 'myfs' ]

    @classmethod
    def create(cls, path=PATH):
        if exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        os.chmod(path, 0700)

        self = cls(path)

        os.mkdir(self.paths.etc)
        os.mkdir(self.paths.originals)
        return self

    def __init__(self, path=PATH):
        """deletes path if it exists and creates it if it doesn't"""

        if not exists(path):
            raise Error("No such directory " + `path`)

        self.paths = self.Paths(path)
        self.timestamp = datetime.fromtimestamp(os.stat(path).st_ctime)

    @staticmethod
    def _move(source, dest):
        if not lexists(source):
            raise Error("no such file or directory " + `source`)

        if not exists(dirname(dest)):
            os.makedirs(dirname(dest))

        remove_any(dest)
        shutil.move(source, dest)

    def _move_to_originals(self, source):
        """Move source into originals"""
        dest = join(self.paths.originals, source.strip('/'))
        self._move(source, dest)

    def _move_from_originals(self, dest):
        """Move path from originals to dest"""
        source = join(self.paths.originals, dest.strip('/'))
        self._move(source, dest)

    def rollback_files(self):
        changes = Changes.fromfile(self.paths.fsdelta)
        dirindex = DirIndex(self.paths.dirindex)

        for change in changes:
            if change.path not in dirindex:
                remove_any(change.path)
                continue

            if change.OP in ('o', 'd'):
                try:
                    self._move_from_originals(change.path)
                except self.Error:
                    continue

            dirindex_rec = dirindex[change.path]
            local_rec = DirIndex.Record.frompath(change.path)

            if dirindex_rec.uid != local_rec.uid or \
               dirindex_rec.gid != local_rec.gid:
                os.lchown(change.path, dirindex_rec.uid, dirindex_rec.gid)

            if dirindex_rec.mod != local_rec.mod:
                mod = stat.S_IMODE(dirindex_rec.mod)
                os.chmod(change.path, mod)

        for fname in ('passwd', 'group'):
            shutil.copy(join(self.paths.etc, fname), "/etc")

    def rollback_new_packages(self):
        if not exists(self.paths.newpkgs):
            return

        rollback_packages = Packages.fromfile(self.paths.newpkgs)
        current_packages = Packages()

        purge_packages = current_packages & rollback_packages
        if purge_packages:
            os.system("dpkg --purge " + " ".join(purge_packages))

    def rollback_database(self):
        if exists(self.paths.myfs):
            mysql.restore(self.paths.myfs, self.paths.etc.mysql, 
                          add_drop_database=True)

    def rollback(self):
        self.rollback_database()
        self.rollback_files()
        self.rollback_new_packages()

        shutil.rmtree(self.paths)

    def save_files(self, changes):
        for fname in ("passwd", "group"):
            shutil.copy(join("/etc", fname), self.paths.etc)

        changes.tofile(self.paths.fsdelta)
        di = DirIndex()
        for change in changes:
            if lexists(change.path):
                di.add_path(change.path)
                if change.OP in ('o', 'd'):
                    self._move_to_originals(change.path)
        di.save(self.paths.dirindex)

    def save_new_packages(self, installable):
        fh = file(self.paths.newpkgs, "w")
        for package in installable:
            print >> fh, package
        fh.close()

    def save_database(self):
        try:
            mysql.backup(self.paths.myfs, self.paths.etc.mysql)
        except mysql.Error:
            pass
