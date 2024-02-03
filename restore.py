# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

import sys
import os
from os.path import isdir, exists, join
import logging

import userdb
import pkgman

from changes import Changes
from pathmap import PathMap
from rollback import Rollback

from utils import BaseAttrDict, fmt_title, apply_overlay

import backup
import conf
import mysql
import pgsql

import json

from temp import TempFile
from userdb import Base


class Error(Exception):
    pass


logging.basicConfig(level=logging.DEBUG)
logging.debug(f'*** {__file__=}')


def system(command: str) -> int:
    sys.stdout.flush()
    sys.stderr.flush()
    return os.system(command)


class Restore:
    Error = Error

    PACKAGES_BLACKLIST = ['linux-*', 'vmware-tools*']

    def __init__(self,
                 backup_extract_path: str,
                 limits: list = [],
                 rollback: bool = True,
                 simulate: bool = False):
        logging.debug(f'Restore.__init__(')
        logging.debug(f'    {backup_extract_path=},')
        logging.debug(f'    {limits=}, {rollback=}, {simulate=}')
        logging.debug(')')
        self.extras = backup.ExtrasPaths(backup_extract_path)
        if not isdir(self.extras.path):
            raise self.Error("illegal backup_extract_path: can't find"
                             f" '{self.extras.path}'")

        if simulate:
            rollback = False

        with open(self.extras.backup_conf) as fob:
            self.conf = BaseAttrDict(json.loads(fob.read())) \
                    if exists(self.extras.backup_conf) else None

        self.simulate = simulate
        logging.debug(f'creating rollback? {rollback}')
        self.rollback = Rollback.create() if rollback else None
        self.limits = conf.Limits(limits)
        self.backup_extract_path = backup_extract_path
        logging.debug(f'__init__ complete: {self.limits=},'
                      f' {self.backup_extract_path=}')

    def database(self) -> None:
        logging.debug(f'database()')
        if not exists(self.extras.myfs) and not exists(self.extras.pgfs):
            logging.debug(f'* bailing...')
            return

        if self.rollback:
            logging.debug('* saving rollback')
            self.rollback.save_database()

        if exists(self.extras.myfs):
            logging.debug('* self.extras.myfs exists')
            print(fmt_title("DATABASE - unserializing MySQL databases from "
                            + self.extras.myfs))

            try:
                mysql.restore(self.extras.myfs,
                              self.extras.etc.mysql,
                              limits=self.limits.mydb,
                              callback=mysql.cb_print(),
                              simulate=self.simulate)
                # error: "str" has no attribute "mysql"

            except mysql.Error as e:
                print("SKIPPING MYSQL DATABASE RESTORE: " + str(e))

        if exists(self.extras.pgfs):

            print("\n" + fmt_title("DATABASE - Unserializing PgSQL databases"
                                   " from " + self.extras.pgfs))

            if self.simulate:
                print("CAN'T SIMULATE PGSQL RESTORE, SKIPPING")
                return

            try:
                pgsql.restore(self.extras.pgfs, self.limits.pgdb,
                              callback=pgsql.cb_print())

            except pgsql.Error as e:
                print("SKIPPING PGSQL DATABASE RESTORE: " + str(e))
        logging.debug('* done')

    def packages(self) -> None:
        logging.debug(f'packages()')
        newpkgs_file = self.extras.newpkgs
        if not exists(newpkgs_file):
            return

        with open(newpkgs_file) as fob:
            packages_ = fob.read().strip()
        packages = [] if not packages_ else packages_.split('\n')

        if not packages:
            return

        print(fmt_title(f"PACKAGES - {len(packages)} new packages listed in"
                        f" {newpkgs_file}", '-'))

        already_installed = set(pkgman.installed()) & set(packages)
        if len(already_installed) == len(packages):
            print("ALL NEW PACKAGES ALREADY INSTALLED\n")
            return

        if already_installed:
            print("// New packages not already installed:"
                  f" {len(packages) - len(already_installed)}")

        # apt-get update, otherwise installer may skip everything
        print("// Update list of available packages")
        print()
        print("# apt-get update")
        system("apt-get update")

        installer = pkgman.Installer(packages, self.PACKAGES_BLACKLIST)

        print()
        print("// Installing new packages")

        if installer.skipping:
            print("// Skipping uninstallable packages: "
                  + " ".join(installer.skipping))

        print()

        if not installer.command:
            print("NO NEW PACKAGES TO INSTALL\n")
            return

        print(f"# {installer.command}")

        if not self.simulate:
            exitcode = installer()
            if exitcode != 0:
                print(f"# WARNING: non-zero exitcode ({exitcode})")

        if self.rollback:
            self.rollback.save_new_packages(installer.installed)

        print()

    @staticmethod
    def _userdb_merge(old_etc: str, new_etc: str
                      ) -> tuple[Base, Base, dict[str, str], dict[str, str]]:
        logging.debug(f' _userdb_merge( {old_etc=}, {new_etc=} )')
        old_passwd = join(old_etc, "passwd")
        new_passwd = join(new_etc, "passwd")

        old_group = join(old_etc, "group")
        new_group = join(new_etc, "group")

        def r(path):
            with open(path) as fob:
                return fob.read()

        return userdb.merge(r(old_passwd), r(old_group),
                            r(new_passwd), r(new_group))

    @staticmethod
    def _get_fsdelta_olist(fsdelta_olist_path: str, limits: list[str] = []
                           ) -> list[str]:
        logging.debug(f'_get_fsdelta_olist( {fsdelta_olist_path=}, {limits=}')
        pathmap = PathMap(limits)
        with open(fsdelta_olist_path) as fob:
            return [fpath
                    for fpath in fob.read().splitlines()
                    if fpath in pathmap]

    @staticmethod
    def _apply_overlay(src: str, dst: str, olist: list[str]) -> None:
        logging.debug(f'_apply_overlay( {src=}, {dst=}, {olist=}')
        tmp = TempFile("fsdelta-olist-")
        for fpath in olist:
            logging.debug(f'1 {fpath=} (type={type(fpath)}) {tmp=}'
                          f' (type={type(tmp)})')
            fpath = fpath.lstrip('/')
            tmp.write(f'{fpath}\n'.encode())
            logging.debug(f'2 {fpath=} ({type(fpath)=}) {tmp=} ({type(tmp)=})')
        tmp.close()

        apply_overlay(src, dst, tmp.path)

    def files(self) -> None:
        logging.debug(f'files()')
        extras = self.extras
        if not exists(extras.fsdelta):
            return

        overlay = self.backup_extract_path
        simulate = self.simulate
        rollback = self.rollback
        limits = self.limits.fs

        print(fmt_title("FILES - restoring files, ownership and permissions",
                        '-'))
        logging.debug(f'about to merge {extras.etc=} & /etc')
        passwd, group, uidmap, gidmap = self._userdb_merge(extras.etc, "/etc")
        if uidmap or gidmap:
            print("MERGING USERS AND GROUPS:\n")

            for olduid in uidmap:
                print(f"  UID {olduid} => {uidmap[olduid]}")
            for oldgid in gidmap:
                print(f"  GID {oldgid} => {gidmap[oldgid]}")

            print()

        logging.debug(f'{extras.fsdelta=}')
        logging.debug(f'{limits=}')
        logging.debug('about to do changes')
        changes = Changes.fromfile(extras.fsdelta, limits)
        logging.debug(f'{bool(changes)=}')
        deleted = list(changes.deleted())
        logging.debug(f'{changes=}')
        logging.debug(f'{deleted=}')
        logging.debug(f'{rollback=}')
        if rollback:
            logging.info(f'saving rollback info to {overlay=}')
            rollback.save_files(changes, overlay)
            logging.info('saved')
        logging.debug(f'{extras.fsdelta_olist=}')
        logging.debug(f'{limits=}')
        fsdelta_olist = self._get_fsdelta_olist(extras.fsdelta_olist, limits)
        logging.debug(f'{fsdelta_olist=}')
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
            with open(path, "w") as fob:
                fob.write(str(s))

        if not simulate:
            w("/etc/passwd", passwd)
            w("/etc/group", group)
