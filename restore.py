import os
from os.path import *

import shutil
import tempfile
import commands

import userdb
from paths import Paths
from changes import Changes
from pathmap import PathMap
from dirindex import DirIndex
from pkgman import Installer
from rollback import Rollback
from utils import TempDir, remove_any

import backup
import mysql

class Error(Exception):
    pass

class Restore:
    Error = Error

    @staticmethod
    def _section_title(title):
        return title + "\n" + "=" * len(title) + "\n"

    @staticmethod
    def _duplicity_restore(address, key):
        tmpdir = TempDir(prefix="tklbam-")
        os.chmod(tmpdir, 0700)

        os.environ['PASSPHRASE'] = key
        command = "duplicity %s %s" % (commands.mkarg(address), tmpdir)
        status, output = commands.getstatusoutput(command)
        del os.environ['PASSPHRASE']

        if status != 0:
            if "No backup chains found" in output:
                raise Error("Valid backup not found at " + `address`)
            else:
                raise Error("Error restoring backup (bad key?):\n" + output)

        return tmpdir

    def __init__(self, address, key, limits=[], rollback=True, log=None):
        class DontWriteIfNone:
            def __init__(self, fh=None):
                self.fh = fh

            def write(self, s):
                if self.fh:
                    self.fh.write(str(s))

        log = DontWriteIfNone(log)
        print >> log, "Restoring duplicity archive from " + address
        backup_archive = self._duplicity_restore(address, key)

        extras_path = TempDir(prefix="tklbam-extras-")
        os.rename(backup_archive + backup.Backup.EXTRAS_PATH, extras_path)

        self.extras = backup.ExtrasPaths(extras_path)
        self.rollback = Rollback.create() if rollback else None
        self.limits = backup.Limits(limits)
        self.backup_archive = backup_archive
        self.log = log

    def database(self):
        print >> self.log, "\n" + self._section_title("Restoring databases")

        if self.rollback:
            mysql.mysql2fs(mysql.mysqldump(), self.rollback.myfs)
            shutil.copy("/etc/mysql/debian.cnf", self.rollback.etc.mysql)

        mysql.fs2mysql(mysql.mysql(), self.extras.myfs, self.limits.db, mysql.cb_print(self.log))

        shutil.copy(join(self.extras.etc.mysql, "debian.cnf"), "/etc/mysql/debian.cnf")
        os.system("killall -HUP mysqld > /dev/null 2>&1")
        
    def packages(self):
        newpkgs_file = self.extras.newpkgs
        rollback_file = (self.rollback.newpkgs if self.rollback 
                         else None)
        log = self.log

        print >> log, "\n" + self._section_title("Restoring new packages")

        # apt-get update, otherwise installer may skip everything
        print >> log, "apt-get update"
        output = commands.getoutput("apt-get update")

        def indent_lines(s, indent):
            return "\n".join([ " " * indent + line 
                               for line in str(s).splitlines() ])

        print >> log, "\n" + indent_lines(output, 4) + "\n"

        packages = file(newpkgs_file).read().strip().split('\n')
        installer = Installer(packages)

        if rollback_file:
            fh = file(rollback_file, "w")
            for package in installer.installable:
                print >> fh, package
            fh.close()

        if installer.skipping:
            print >> log, "SKIPPING: " + " ".join(installer.skipping) + "\n"

        if installer.command:
            print >> log, installer.command
        else:
            print >> log, "NO NEW INSTALLABLE PACKAGES"

        try:
            exitcode, output = installer()
            print >> log, "\n" + indent_lines(output, 4)
            if exitcode != 0:
                print >> log, "# WARNING: non-zero exitcode (%d)" % exitcode

        except installer.Error:
            pass

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
    def _iter_apply_overlay(overlay, root, limits=[]):
        def walk(dir):
            fnames = []
            subdirs = []

            for dentry in os.listdir(dir):
                path = join(dir, dentry)

                if not islink(path) and isdir(path):
                    subdirs.append(path)
                else:
                    fnames.append(dentry)

            yield dir, fnames

            for subdir in subdirs:
                for val in walk(subdir):
                    yield val

        class OverlayError:
            def __init__(self, path, exc):
                self.path = path
                self.exc = exc

            def __str__(self):
                return "OVERLAY ERROR @ %s: %s" % (self.path, self.exc)

        pathmap = PathMap(limits)
        overlay = overlay.rstrip('/')
        for overlay_dpath, fnames in walk(overlay):
            root_dpath = root + overlay_dpath[len(overlay) + 1:]

            for fname in fnames:
                overlay_fpath = join(overlay_dpath, fname)
                root_fpath = join(root_dpath, fname)

                if root_fpath not in pathmap:
                    continue

                try:
                    if not isdir(root_dpath):
                        if exists(root_dpath):
                            os.remove(root_dpath)
                        os.makedirs(root_dpath)

                    if lexists(root_fpath):
                        remove_any(root_fpath)

                    shutil.move(overlay_fpath, root_fpath)
                    yield root_fpath
                except Exception, e:
                    yield OverlayError(root_fpath, e)

    def files(self):
        extras = self.extras
        overlay = self.backup_archive
        rollback = self.rollback
        limits = self.limits.fs
        log = self.log

        print >> log, "\n" + self._section_title("Restoring filesystem")

        print >> log, "MERGING USERS AND GROUPS\n"
        passwd, group, uidmap, gidmap = self._userdb_merge(extras.etc, "/etc")

        for olduid in uidmap:
            print >> log, "UID %d => %d" % (olduid, uidmap[olduid])
        for oldgid in gidmap:
            print >> log, "GID %d => %d" % (oldgid, gidmap[oldgid])

        changes = Changes.fromfile(extras.fsdelta, limits)

        if rollback:
            for fname in ("passwd", "group"):
                shutil.copy(join("/etc", fname), rollback.etc)

            changes.tofile(rollback.fsdelta)

            di = DirIndex()
            for change in changes:
                if lexists(change.path):
                    di.add_path(change.path)
                    if change.OP == 'o':
                        rollback.originals.move_in(change.path)
            di.save(rollback.dirindex)

        print >> log, "\nOVERLAY:\n"

        for val in self._iter_apply_overlay(overlay, "/", limits):
            print >> log, val

        print >> log, "\nPOST-OVERLAY FIXES:\n"
        for action in changes.statfixes(uidmap, gidmap):
            print >> log, action
            action()

        for action in changes.deleted():
            print >> log, action

            path, = action.args
            if rollback:
                rollback.originals.move_in(path)
            else:
                action()

        def w(path, s):
            file(path, "w").write(str(s))

        w("/etc/passwd", passwd)
        w("/etc/group", group)

