#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
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
from changes import Changes
from pathmap import PathMap
from pkgman import Installer
from rollback import Rollback

import utils

import backup
import conf
import mysql
import pgsql

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

    @staticmethod
    def _title(title, c='='):
        return title + "\n" + c * len(title) + "\n"

    def __init__(self, backup_extract_path, limits=[], rollback=True, simulate=False):
        extras_path = backup_extract_path + backup.ExtrasPaths.PATH
        if not isdir(extras_path):
            raise self.Error("illegal backup_extract_path: can't find '%s'" % extras_path)

        if simulate:
            rollback = False

        self.simulate = simulate
        self.rollback = Rollback.create() if rollback else None
        self.extras = backup.ExtrasPaths(extras_path)
        self.limits = conf.Limits(limits)
        self.backup_extract_path = backup_extract_path

    def database(self):
        if not exists(self.extras.myfs) and not exists(self.extras.pgfs):
            return

        if self.rollback:
            self.rollback.save_database()

        if exists(self.extras.myfs):

            print "\n" + self._title("Restoring MySQL databases")

            try:
                mysql.restore(self.extras.myfs, self.extras.etc.mysql,
                              limits=self.limits.mydb, callback=mysql.cb_print(), simulate=self.simulate)

            except mysql.Error, e:
                print "SKIPPING MYSQL DATABASE RESTORE: " + str(e)

        if exists(self.extras.pgfs):
        
            print "\n" + self._title("Restoring PgSQL databases")

            if self.simulate:
                print "CAN't SIMULATE PGSQL RESTORE, SKIPPING"
                return

            try:
                pgsql.restore(self.extras.pgfs, self.limits.pgdb, callback=pgsql.cb_print())

            except pgsql.Error, e:
                print "SKIPPING PGSQL DATABASE RESTORE: " + str(e)


    def packages(self):
        newpkgs_file = self.extras.newpkgs
        if not exists(newpkgs_file):
            return

        print "\n" + self._title("Restoring new packages")

        # apt-get update, otherwise installer may skip everything
        print self._title("apt-get update", '-')
        if not self.simulate:
            system("apt-get update")

        packages = file(newpkgs_file).read().strip()
        packages = [] if not packages else packages.split('\n')

        installer = Installer(packages, self.PACKAGES_BLACKLIST)

        print "\n" + self._title("apt-get install", '-')

        if installer.skipping:
            print "SKIPPING: " + " ".join(installer.skipping) + "\n"

        if not installer.command:
            print "NO NEW INSTALLABLE PACKAGES"
            return

        print installer.command
        if not self.simulate:
            exitcode = installer()
            if exitcode != 0:
                print "# WARNING: non-zero exitcode (%d)" % exitcode

        if self.rollback:
            self.rollback.save_new_packages(installer.installed)

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
            print >> tmp, fpath.lstrip('/')
        tmp.close()

        utils.apply_overlay(src, dst, tmp.path)

    def files(self):
        extras = self.extras
        if not exists(extras.fsdelta):
            return

        overlay = self.backup_extract_path
        simulate = self.simulate
        rollback = self.rollback
        limits = self.limits.fs

        print "\n" + self._title("Restoring filesystem")

        passwd, group, uidmap, gidmap = self._userdb_merge(extras.etc, "/etc")

        if uidmap or gidmap:
            print "MERGING USERS AND GROUPS\n"

            for olduid in uidmap:
                print "UID %d => %d" % (olduid, uidmap[olduid])
            for oldgid in gidmap:
                print "GID %d => %d" % (oldgid, gidmap[oldgid])

            print

        changes = Changes.fromfile(extras.fsdelta, limits)
        deleted = list(changes.deleted())

        if rollback:
            rollback.save_files(changes, overlay)

        fsdelta_olist = self._get_fsdelta_olist(extras.fsdelta_olist, limits)
        if fsdelta_olist:
            print "FILES OVERLAY:\n"
            print "\n".join(fsdelta_olist)

            if not simulate:
                self._apply_overlay(overlay, '/', fsdelta_olist)

        statfixes = list(changes.statfixes(uidmap, gidmap))

        if statfixes or deleted:
            print "\nPOST-OVERLAY FIXES:\n"

        for action in statfixes:
            print action
            if not simulate:
                action()

        for action in deleted:
            print action

            # rollback moves deleted to 'originals'
            if not simulate and not rollback:
                action()

        def w(path, s):
            file(path, "w").write(str(s))

        if not simulate:
            w("/etc/passwd", passwd)
            w("/etc/group", group)
