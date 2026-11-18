#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
import errno
import sys
import subprocess
from os.path import *

import stat
import shutil

from datetime import datetime
from pylib.paths import Paths as _Paths

import mysql
import pgsql

from changes import Changes
from dirindex import DirIndex
from pkgman import Packages

import utils
import traceback

class Error(Exception):
    pass

class Rollback:
    Error = Error

    PATH = "/var/backups/tklbam-rollback"
    class Paths(_Paths):
        files = [ 'etc', 'etc/mysql',
                  'fsdelta', 'dirindex', 'originals',
                  'pending_files', 'moved_files',
                  'newpkgs', 'myfs', 'pgfs' ]

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

        utils.remove_any(dest)
        try:
            os.rename(source, dest)
        except OSError, e:
            if e.errno != errno.EXDEV:
                raise
            mode = stat.S_IMODE(os.lstat(source).st_mode)
            utils.move(source, dest)
            # The copy fallback restores ownership with chown, which can
            # clear the setuid and setgid bits.
            if mode & (stat.S_ISUID | stat.S_ISGID):
                os.chmod(dest, mode)

    def _move_to_originals(self, source):
        """Move source into originals"""
        self._move(source, self._original_path(source))

    def _move_from_originals(self, dest):
        """Move path from originals to dest"""
        self._move(self._original_path(dest), dest)

    @staticmethod
    def _normalize_path(path):
        return normpath('/' + path.lstrip('/'))

    def _original_path(self, path):
        return join(self.paths.originals, self._normalize_path(path).strip('/'))

    @staticmethod
    def _restore_metadata(path, saved):
        current = DirIndex.Record.frompath(path)
        ownership_changed = saved.uid != current.uid or saved.gid != current.gid
        if ownership_changed:
            os.lchown(path, saved.uid, saved.gid)
        mode = stat.S_IMODE(saved.mod)
        if saved.mod != current.mod or (ownership_changed and mode & (stat.S_ISUID | stat.S_ISGID)):
            os.chmod(path, mode)

    def rollback_files(self):
        pending = exists(self.paths.pending_files)
        moved = None
        if pending:
            # The restore overlay never ran. Only unwind the saved originals.
            changes = Changes.fromfile(self.paths.pending_files)
        elif exists(self.paths.fsdelta):
            changes = Changes.fromfile(self.paths.fsdelta)
            if exists(self.paths.moved_files):
                moved = set(change.path for change in Changes.fromfile(self.paths.moved_files))
                changes.sort(key=lambda change: self._normalize_path(change.path))
        else:
            return
        dirindex = DirIndex(self.paths.dirindex)

        exceptions = 0
        for change in changes:
            try:
                if pending:
                    original = self._original_path(change.path)
                    if lexists(change.path):
                        if lexists(original):
                            raise self.Error("both live and saved copies exist: " + change.path)
                        continue
                    # Keep the saved file available for retry if fixing its
                    # metadata fails.
                    self._restore_metadata(original, dirindex[change.path])
                    self._move_from_originals(change.path)
                    continue

                if change.path not in dirindex:
                    utils.remove_any(change.path)
                    continue

                if change.OP in ('o', 'd'):
                    if moved is None or change.path in moved:
                        if lexists(self._original_path(change.path)):
                            self._move_from_originals(change.path)
                        elif moved is None and not lexists(change.path):
                            # Legacy archives can omit children saved with a parent.
                            continue

                self._restore_metadata(change.path, dirindex[change.path])
            except:
                exceptions += 1
                # fault-tolerance: warn and continue, don't die
                traceback.print_exc(file=sys.stderr)

        if not pending:
            for fname in ('passwd', 'group'):
                shutil.copy(join(self.paths.etc, fname), "/etc")

        if exceptions:
            raise Error("caught %d exceptions during rollback_files" % exceptions)

    def rollback_new_packages(self):
        if not exists(self.paths.newpkgs):
            return

        rollback_packages = Packages.fromfile(self.paths.newpkgs)
        current_packages = Packages()

        purge_packages = current_packages & rollback_packages
        if purge_packages:
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            subprocess.check_call(["dpkg", "--purge"] + list(purge_packages), env=env)

    def rollback_database(self):
        if exists(self.paths.myfs):
            mysql.restore(self.paths.myfs, self.paths.etc.mysql,
                          add_drop_database=True)

        if exists(self.paths.pgfs):
            pgsql.restore(self.paths.pgfs)

    def rollback(self):
        exceptions = 0
        for method in (self.rollback_database, self.rollback_files, self.rollback_new_packages):
            try:
                method()
            except:
                exceptions += 1
                print >> sys.stderr, "error: %s raised an exception:" % method.__name__
                traceback.print_exc(file=sys.stderr)

        if exceptions:
            raise Error("caught %d exceptions during rollback; retained %s" %
                        (exceptions, self.paths))
        shutil.rmtree(self.paths)

    def save_files(self, changes, overlay_path):
        for fname in ("passwd", "group"):
            shutil.copy(join("/etc", fname), self.paths.etc)

        di = DirIndex()
        moves = Changes()
        move_paths = set()
        for change in sorted(changes, key=lambda change: self._normalize_path(change.path)):
            if not lexists(change.path):
                continue
            di.add_path(change.path)
            if change.OP == 's' or (change.OP == 'o' and
                                    not lexists(overlay_path + change.path)):
                continue
            # Moving an ancestor already saves its descendants.
            path = ancestor = self._normalize_path(change.path)
            while ancestor != '/' and ancestor not in move_paths:
                ancestor = dirname(ancestor)
            if ancestor not in move_paths:
                moves.append(change)
                move_paths.add(path)

        # Publish the pending move list before the full delta. Its presence
        # tells rollback that restore has yet to apply the overlay.
        di.save(self.paths.dirindex)
        pending_tmp = str(self.paths.pending_files) + '.tmp'
        moves.tofile(pending_tmp)
        os.rename(pending_tmp, self.paths.pending_files)
        changes.tofile(self.paths.fsdelta)
        for change in moves:
            self._move_to_originals(change.path)
        os.rename(self.paths.pending_files, self.paths.moved_files)

    def save_new_packages(self, packages):
        packages = list(packages)
        packages.sort()

        with open(self.paths.newpkgs, "w") as fob:
            for package in packages:
                fob.write(package + "\n")

    def save_database(self):
        try:
            mysql.backup(self.paths.myfs, self.paths.etc.mysql)
        except mysql.Error:
            pass

        try:
            pgsql.backup(self.paths.pgfs)
        except pgsql.Error:
            pass

