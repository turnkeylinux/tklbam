import sys

import os
from os.path import *

import shutil
import commands

import userdb
from paths import Paths
from changes import Changes
from pathmap import PathMap
from dirindex import DirIndex
from pkgman import Installer
from rollback import Rollback
from temp import TempDir

import utils

import backup
import mysql

class Error(Exception):
    pass

def system(command):
    sys.stdout.flush()
    sys.stderr.flush()
    return os.system(command)

class Restore:
    Error = Error

    @staticmethod
    def _title(title, c='='):
        return title + "\n" + c * len(title) + "\n"

    @staticmethod
    def _duplicity_restore(address, key):
        tmpdir = TempDir(prefix="tklbam-")
        os.chmod(tmpdir, 0700)

        os.environ['PASSPHRASE'] = key
        command = "duplicity %s %s" % (commands.mkarg(address), tmpdir)
        sys.stdout.flush()
        status = system(command)
        del os.environ['PASSPHRASE']

        if status != 0:
            raise Error("Duplicity failed (%d)" % status)

        return tmpdir

    def __init__(self, address, key, limits=[], rollback=True):
        print "Restoring duplicity archive from " + address
        backup_archive = self._duplicity_restore(address, key)

        extras_path = TempDir(prefix="tklbam-extras-")
        os.rename(backup_archive + backup.Backup.EXTRAS_PATH, extras_path)

        self.extras = backup.ExtrasPaths(extras_path)
        self.rollback = Rollback.create() if rollback else None
        self.limits = backup.Limits(limits)
        self.backup_archive = backup_archive

    def database(self):
        print "\n" + self._title("Restoring databases")

        if self.rollback:
            self.rollback.save_database()

        if exists(self.extras.myfs):
            try:
                mysql.restore(self.extras.myfs, self.extras.etc.mysql, 
                              limits=self.limits.db, callback=mysql.cb_print())

            except mysql.Error:
                pass
        
    def packages(self):
        newpkgs_file = self.extras.newpkgs

        print "\n" + self._title("Restoring new packages")

        # apt-get update, otherwise installer may skip everything
        print self._title("apt-get update", '-')
        system("apt-get update")

        packages = file(newpkgs_file).read().strip().split('\n')
        installer = Installer(packages)

        if self.rollback:
            self.rollback.save_new_packages(installer.installable)

        print "\n" + self._title("apt-get install", '-')
        if installer.skipping:
            print "SKIPPING: " + " ".join(installer.skipping) + "\n"

        if installer.command:
            print installer.command
        else:
            print "NO NEW INSTALLABLE PACKAGES"

        try:
            exitcode = installer()
            if exitcode != 0:
                print "# WARNING: non-zero exitcode (%d)" % exitcode

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
                        utils.remove_any(root_fpath)

                    shutil.move(overlay_fpath, root_fpath)
                    yield root_fpath
                except Exception, e:
                    yield OverlayError(root_fpath, e)

    def files(self):
        extras = self.extras
        overlay = self.backup_archive
        rollback = self.rollback
        limits = self.limits.fs

        print "\n" + self._title("Restoring filesystem")

        print "MERGING USERS AND GROUPS\n"
        passwd, group, uidmap, gidmap = self._userdb_merge(extras.etc, "/etc")

        for olduid in uidmap:
            print "UID %d => %d" % (olduid, uidmap[olduid])
        for oldgid in gidmap:
            print "GID %d => %d" % (oldgid, gidmap[oldgid])

        changes = Changes.fromfile(extras.fsdelta, limits)
        deleted = list(changes.deleted())

        if rollback:
            rollback.save_files(changes)

        print "\nOVERLAY:\n"
        for val in self._iter_apply_overlay(overlay, "/", limits):
            print val

        print "\nPOST-OVERLAY FIXES:\n"
        for action in changes.statfixes(uidmap, gidmap):
            print action
            action()

        for action in deleted:
            print action

            # rollback moves deleted to 'originals'
            if not rollback:
                action()

        def w(path, s):
            file(path, "w").write(str(s))

        w("/etc/passwd", passwd)
        w("/etc/group", group)

