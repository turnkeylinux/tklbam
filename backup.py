#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#

import os
from os.path import exists, join, isdir, realpath

import stat

import shutil
import json

from typing import Optional, Self
from dataclasses import dataclass, asdict

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import Packages
from .registry import Profile
import mysql
import pgsql

from utils import fmt_title, apply_overlay


@dataclass
class ProfilePaths:
    path: str
    packages: str = ''
    dirindex: str = ''
    dirindex_conf: str = ''

    @dataclass
    class _ProfPaths:
        path: str

    def __post_init__(self):
        self.paths = self._ProfPaths(realpath(self.path))


class ExtrasPaths(Paths):
    PATH = "TKLBAM"
    backup_conf: str
    fsdelta: str
    fsdelta_olist: str
    newpkgs: str
    pgfs: str
    myfs: str
    etc: str
    etc_mysql: str

    def __init__(self, backup_root=None):
        if backup_root is None:
            backup_root = '/'

        Paths.__init__(self, join(backup_root, self.PATH))

    def __new__(cls, root_path: Optional[str] = None) -> Self:
        return str.__new__(cls, root_path)

    files = ['backup-conf', 'fsdelta', 'fsdelta-olist', 'newpkgs', 'pgfs',
             'myfs', 'etc', 'etc/mysql']


def _rmdir(path: str) -> None:
    if exists(path):
        shutil.rmtree(path)


def _fpaths(dpath: str) -> list[str]:
    arr = []
    for dpath, dnames, fnames in os.walk(dpath):
        for fname in fnames:
            arr.append(join(dpath, fname))
    return arr


def _filter_deleted(files: list[str]) -> list[str]:
    return [f for f in files if exists(f)]


@dataclass
class BackupConf:
    profile_id: str
    overrides: list[str]
    skip_files: bool
    skip_packages: bool
    skip_database: bool

    def __post_init__(self) -> None:
        self.overrides_mydb = []
        self.overrides_pgdb = []
        self.overrides_fs = []
        # XXX not sure about this processing here...
        # Should perhaps go elsewhere?
        for override in self.overrides:
            if override.startswith('mysql:') \
                    or override.startswith('-mysql:'):
                self.overrides_mydb.append(override)
            elif override.startswith('pgsql:') \
                    or override.startswith('-pgsql:'):
                self.overrides_pgdb.append(override)
            else:
                self.overrides_fs.append(override)

    @classmethod
    def fromfile(cls, path: str) -> Optional[Self]:
        if not exists(path):
            return None

        with open(path) as fob:
            d = json.load(fob)
        return cls(*(d[attr]
                     for attr in ('profile_id', 'overrides',
                                  'skip_files', 'skip_packages',
                                  'skip_database')))

    def tofile(self, path: str) -> None:
        with open(path, "w") as fob:
            fob.write(json.dumps(asdict(self)) + '\n')


class Backup:
    class Error(Exception):
        pass

    def _write_new_packages(self, dest: str, base_packages: str) -> None:
        base_packages_ = Packages.fromfile(base_packages)
        current_packages = Packages()

        new_packages = [x for x in current_packages if x not in base_packages_]
        new_packages.sort()

        if new_packages:
            self._log("Save list of new packages:\n")
            self._log("  cat > %s << EOF " % dest)
            self._log("  " + " ".join(new_packages))
            self._log("  EOF\n")

        with open(dest, "w") as fob:
            fob.write('\n'.join(new_packages) + '\n')

    def _write_whatchanged(self, dest: str, dest_olist: str,
                           dirindex: str, dirindex_conf: str,
                           overrides: list[str] = []
                           ) -> None:
        with open(dirindex_conf) as fob:
            paths = read_paths(fob)
        paths += overrides

        changes = whatchanged(dirindex, paths)
        changes.sort(key=lambda a: a.path)

        changes.tofile(dest)
        olist = [change.path for change in changes if change.OP == 'o']
        with open(dest_olist, "w") as fob:
            fob.write('\n'.join(olist) + '\n')

        if self.verbose:
            if changes:
                self._log("Save list of filesystem changes to %s:\n" % dest)

            actions = list(changes.deleted(optimized=False)
                           ) + list(changes.statfixes(optimized=False))
            actions.sort(key=lambda a: a.args[0])

            umask = os.umask(0)
            os.umask(umask)

            for action in actions:
                if action.func is os.chmod:
                    path, mode = action.args
                    default_mode = (0o777 if isdir(path) else 0o666) ^ umask
                    if default_mode == stat.S_IMODE(int(mode)):
                        continue
                elif action.func is os.lchown:
                    path, uid, gid = action.args
                    if uid == 0 and gid == 0:
                        continue

                self._log("  " + str(action))

            if olist:
                self._log("\nSave list of new files to %s:\n" % dest_olist)
                for path in olist:
                    self._log("  " + path)

    def _create_extras(self, extras: ExtrasPaths,
                       profile: ProfilePaths, conf: BackupConf
                       ) -> None:
        os.mkdir(extras.path)
        os.chmod(extras.path, 0o700)

        etc = str(extras.etc)
        os.mkdir(etc)
        self._log("  mkdir " + etc)

        self._log("\n// needed to automatically detect and"
                  " fix file ownership issues\n")

        shutil.copy("/etc/passwd", etc)
        self._log("  cp /etc/passwd " + etc)

        shutil.copy("/etc/group", etc)
        self._log("  cp /etc/group " + etc)

        if not conf.skip_packages or not conf.skip_files:
            self._log("\n" + fmt_title("Comparing current system state to"
                                       " the base state in the backup profile",
                                       '-'))

        if not conf.skip_packages and exists(profile.packages):
            self._write_new_packages(extras.newpkgs, profile.packages)

        if not conf.skip_files:
            # support empty profiles
            dirindex = "/dev/null"
            dirindex_conf = "/dev/null"
            if exists(profile.dirindex):
                dirindex = profile.dirindex
            if exists(profile.dirindex_conf):
                dirindex_conf = profile.dirindex_conf

            conf_overrides_fs = []
            if conf.overrides_fs is not None:
                conf_overrides_fs = conf.overrides_fs
            self._write_whatchanged(extras.fsdelta, extras.fsdelta_olist,
                                    dirindex, dirindex_conf,
                                    conf_overrides_fs)

        if not conf.skip_database:

            try:
                if mysql.MysqlService.is_running():
                    self._log("\n" + fmt_title("Serializing MySQL database to"
                                               " " + extras.myfs, '-'))

                    mysql.backup(extras.myfs, extras.etc_mysql,
                                 limits=conf.overrides_mydb,
                                 callback=mysql.cb_print()
                                 ) if self.verbose else None

            except mysql.Error:
                pass

            try:
                if pgsql.PgsqlService.is_running():
                    self._log("\n" + fmt_title("Serializing PgSQL databases to"
                              " " + extras.pgfs, '-'))
                    pgsql.backup(extras.pgfs, conf.overrides_pgdb,
                                 callback=pgsql.cb_print()
                                 if self.verbose else None)

            except pgsql.Error:
                pass

    def _log(self, s: str = "") -> None:
        if self.verbose:
            print(s)

    def __init__(self,
                 profile: Profile,
                 overrides: list[str],
                 skip_files: bool = False,
                 skip_packages: bool = False,
                 skip_database: bool = False,
                 resume: bool = False,
                 verbose: bool = True,
                 extras_root: str = "/"
                 ) -> None:

        self.verbose = verbose

        if not profile:
            raise self.Error("can't backup without a profile")

        profile_paths = ProfilePaths(profile.path)
        extras_paths = ExtrasPaths(extras_root)

        # decide whether we can allow resume=True
        # /TKLBAM has to exist and the backup configuration has to match
        backup_conf = BackupConf(profile.profile_id,
                                 overrides,
                                 skip_files=skip_files,
                                 skip_packages=skip_packages,
                                 skip_database=skip_database)

        saved_backup_conf = BackupConf.fromfile(extras_paths.backup_conf)

        if backup_conf != saved_backup_conf:
            resume = False

        if not resume:
            _rmdir(extras_paths.path)
        else:
            self._log("ATTEMPTING TO RESUME ABORTED BACKUP SESSION")

        self.resume = resume

        # create or re-use /TKLBAM
        if not exists(extras_paths.path):

            self._log(fmt_title(f"Creating {extras_paths.path} (contains"
                                " backup metadata and database dumps)"))
            self._log("  mkdir -p " + extras_paths.path)

            try:
                self._create_extras(extras_paths, profile_paths, backup_conf)
                backup_conf.tofile(extras_paths.backup_conf)
            except:  # TODO don't use bare except
                # destroy potentially incomplete extras
                _rmdir(extras_paths.path)
                raise

        # print uncompressed footprint
        if verbose:

            # files in /TKLBAM + /TKLBAM/fsdelta-olist
            fpaths = _fpaths(extras_paths.path)

            if not skip_files:
                with open(extras_paths.fsdelta_olist) as fob:
                    fsdelta_olist = fob.read().splitlines()
                fpaths += _filter_deleted(fsdelta_olist)

            size = sum([os.lstat(fpath).st_size
                        for fpath in fpaths])

            if size > 1024 * 1024 * 1024:
                size_fmt = "%.2f GB" % (float(size) / (1024 * 1024 * 1024))
            elif size > 1024 * 1024:
                size_fmt = "%.2f MB" % (float(size) / (1024 * 1024))
            else:
                size_fmt = "%.2f KB" % (float(size) / 1024)

            self._log(f"\nUNCOMPRESSED BACKUP SIZE: {size_fmt} in"
                      f"{len(fpaths)} files")

        self.extras_paths = extras_paths

    def dump(self, path: str) -> Optional[str]:
        def r(p):  # TODO this appears to be unused?!
            print("hit hidden func 'r'!")
            return join(path, p.lstrip('/'))

        if exists(self.extras_paths.fsdelta_olist):
            apply_overlay('/', path, self.extras_paths.fsdelta_olist)
        return None
