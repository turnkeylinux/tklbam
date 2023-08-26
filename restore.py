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
import sys

import os
from os.path import *

import userdb
import pkgman

from changes import Changes
from pathmap import PathMap
from rollback import Rollback

from utils import AttrDict, fmt_title, apply_overlay

import backup
import conf
import mysql
import pgsql

import simplejson

from temp import TempFile

class Error(Exception):
    pass

def system(command):
    sys.stdout.flush()
    sys.stderr.flush()
    return os.system(command)

class Restore:
    Error = Error

    PACKAGES_BLACKLIST = ['linux-*', 'vmware-tools*']

    def __init__(self, backup_extract_path, limits=[], rollback=True, simulate=False):
        self.extras = backup.ExtrasPaths(backup_extract_path)
        if not isdir(self.extras.path):
            raise self.Error("illegal backup_extract_path: can't find '%s'" % self.extras.path)

        if simulate:
            rollback = False

        self.conf = AttrDict(simplejson.loads(file(self.extras.backup_conf).read())) \
                    if exists(self.extras.backup_conf) else None

        self.simulate = simulate
        self.rollback = Rollback.create() if rollback else None
        self.limits = conf.Limits(limits)
        self.backup_extract_path = backup_extract_path

    def database(self):
        if not exists(self.extras.myfs) and not exists(self.extras.pgfs):
            return

        if self.rollback:
            self.rollback.save_database()

        if exists(self.extras.myfs):

            print(fmt_title("DATABASE - unserializing MySQL databases from " + self.extras.myfs))

            try:
                mysql.restore(self.extras.myfs, self.extras.etc.mysql,
                              limits=self.limits.mydb, callback=mysql.cb_print(), simulate=self.simulate)

            except mysql.Error as e:
                print("SKIPPING MYSQL DATABASE RESTORE: " + str(e))

        if exists(self.extras.pgfs):
        
            print("\n" + fmt_title("DATABASE - Unserializing PgSQL databases from " + self.extras.pgfs))

            if self.simulate:
                print("CAN'T SIMULATE PGSQL RESTORE, SKIPPING")
                return

            try:
                pgsql.restore(self.extras.pgfs, self.limits.pgdb, callback=pgsql.cb_print())

            except pgsql.Error as e:
                print("SKIPPING PGSQL DATABASE RESTORE: " + str(e))

    def packages(self):
        newpkgs_file = self.extras.newpkgs
        if not exists(newpkgs_file):
            return

        packages = file(newpkgs_file).read().strip()
        packages = [] if not packages else packages.split('\n')

        if not packages:
            return

        print(fmt_title("PACKAGES - %d new packages listed in %s" % (len(packages), newpkgs_file), '-'))

        already_installed = set(pkgman.installed()) & set(packages)
        if len(already_installed) == len(packages):
            print("ALL NEW PACKAGES ALREADY INSTALLED\n")
            return

        if already_installed:
            print("// New packages not already installed: %d" % (len(packages) - len(already_installed)))

        # apt-get update, otherwise installer may skip everything
        print("// Update list of available packages")
        print()
        print("# apt-get update")
        system("apt-get update")

        installer = pkgman.Installer(packages, self.PACKAGES_BLACKLIST)

        print()
        print("// Installing new packages")

        if installer.skipping:
            print("// Skipping uninstallable packages: " + " ".join(installer.skipping))

        print()

        if not installer.command:
            print("NO NEW PACKAGES TO INSTALL\n")
            return

        print("# " + installer.command)

        if not self.simulate:
            exitcode = installer()
            if exitcode != 0:
                print("# WARNING: non-zero exitcode (%d)" % exitcode)

        if self.rollback:
            self.rollback.save_new_packages(installer.installed)

        print()

    @staticmethod
    def _userdb_merge(old_etc, new_etc):
        old_passwd = join(old_etc, "passwd")
        new_passwd = join(new_etc, "passwd")

        old_group = join(old_etc, "group")
        new_group = join(new_etc, "group")

        def r(path):
            return file(path).read()

        return userdb.merge(r(old_passwd), r(old_group),
                            r(new_passwd), r(new_group))

    @staticmethod
    def _get_fsdelta_olist(fsdelta_olist_path, limits=[]):
        pathmap = PathMap(limits)
        return [ fpath 
                 for fpath in file(fsdelta_olist_path).read().splitlines() 
                 if fpath in pathmap ] 

    @staticmethod
    def _apply_overlay(src, dst, olist):
        tmp = TempFile("fsdelta-olist-")
        for fpath in olist:
            print(fpath.lstrip('/'), file=tmp)
        tmp.close()

        apply_overlay(src, dst, tmp.path)

    def files(self):
        extras = self.extras
        if not exists(extras.fsdelta):
            return

        overlay = self.backup_extract_path
        simulate = self.simulate
        rollback = self.rollback
        limits = self.limits.fs

        print(fmt_title("FILES - restoring files, ownership and permissions", '-'))

        passwd, group, uidmap, gidmap = self._userdb_merge(extras.etc, "/etc")

        if uidmap or gidmap:
            print("MERGING USERS AND GROUPS:\n")

            for olduid in uidmap:
                print("  UID %d => %d" % (olduid, uidmap[olduid]))
            for oldgid in gidmap:
                print("  GID %d => %d" % (oldgid, gidmap[oldgid]))

            print()

        changes = Changes.fromfile(extras.fsdelta, limits)
        deleted = list(changes.deleted())

        if rollback:
            rollback.save_files(changes, overlay)

        fsdelta_olist = self._get_fsdelta_olist(extras.fsdelta_olist, limits)
        if fsdelta_olist:
            print("OVERLAY:\n")
            for fpath in fsdelta_olist:
                print("  " + fpath)

            if not simulate:
                self._apply_overlay(overlay, '/', fsdelta_olist)

            print()

        statfixes = list(changes.statfixes(uidmap, gidmap))

        if statfixes or deleted:
            print("POST-OVERLAY FIXES:\n")

        for action in statfixes:
            print("  " + str(action))
            if not simulate:
                action()

        for action in deleted:
            print("  " + str(action))

            # rollback moves deleted to 'originals'
            if not simulate and not rollback:
                action()

        if statfixes or deleted:
            print()

        def w(path, s):
            file(path, "w").write(str(s))

        if not simulate:
            w("/etc/passwd", passwd)
            w("/etc/group", group)
