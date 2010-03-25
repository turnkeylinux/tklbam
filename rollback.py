import os
from os.path import *

import stat
import shutil

from paths import Paths

import mysql
from changes import Changes
from dirindex import DirIndex
from pkgman import Packages

from utils import remove_any

class Error(Exception):
    pass

class Rollback(Paths):
    PATH = "/var/backups/tklbam-rollback"

    files = [ 'etc', 'etc/mysql', 
              'fsdelta', 'dirindex', 'originals', 
              'newpkgs', 'myfs' ]
    Error = Error

    class Originals(str):
        @staticmethod
        def _move(source, dest):
            if not lexists(source):
                raise Error("no such file or directory " + `source`)

            if not exists(dirname(dest)):
                os.makedirs(dirname(dest))

            remove_any(dest)
            shutil.move(source, dest)

        def move_in(self, source):
            """Move source into originals"""
            dest = join(self, source.strip('/'))
            self._move(source, dest)

        def move_out(self, dest):
            """Move path from originals to dest"""
            source = join(self, dest.strip('/'))
            self._move(source, dest)

    @classmethod
    def create(cls, path=PATH):
        if exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        os.chmod(path, 0700)

        path = cls(path)

        os.mkdir(path.etc)
        os.mkdir(path.etc.mysql)
        os.mkdir(path.originals)
        os.mkdir(path.myfs)

        return path

    def __new__(cls, path=PATH):
        return Paths.__new__(cls, path)

    def __init__(self, path=PATH):
        """deletes path if it exists and creates it if it doesn't"""
        if not exists(path):
            raise Error("No such directory " + `path`)

        Paths.__init__(self, path)

        self.originals = self.Originals(self.originals)

    def _rollback_files(self):
        changes = Changes.fromfile(self.fsdelta)
        dirindex = DirIndex(self.dirindex)

        for change in changes:
            if change.path not in dirindex:
                remove_any(change.path)
                continue

            if change.OP in ('o', 'd'):
                try:
                    self.originals.move_out(change.path)
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
            shutil.copy(join(self.etc, fname), "/etc")

    def _rollback_packages(self):
        rollback_packages = Packages.fromfile(self.newpkgs)
        current_packages = Packages()

        purge_packages = current_packages & rollback_packages
        if purge_packages:
            os.system("dpkg --purge " + " ".join(purge_packages))

    def _rollback_database(self):
        mysql.fs2mysql(mysql.mysql(), self.myfs, add_drop_database=True)
        shutil.copy(join(self.etc.mysql, "debian.cnf"), "/etc/mysql")
        os.system("killall -HUP mysqld > /dev/null 2>&1")

    def rollback(self):
        self._rollback_database()
        self._rollback_files()
        self._rollback_packages()
        shutil.rmtree(self)
