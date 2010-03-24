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

import backup
import mysql

class Error(Exception):
    pass

def remove_any(path):
    """Remove a path whether it is a file or a directory. 
       Return: True if removed, False if nothing to remove"""

    if not exists(path):
        return False

    if not islink(path) and isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

    return True

class Rollback(Paths):
    PATH = "/var/backups/tklbam-rollback"

    files = [ 'etc', 'etc/mysql', 
              'fsdelta', 'dirindex', 'originals', 
              'newpkgs', 'myfs' ]

    class Originals(str):
        def move(self, source):
            if not exists(source):
                raise Error("no such file or directory: " + source)

            dest = join(self, source.strip('/'))
            if not exists(dirname(dest)):
                os.makedirs(dirname(dest))

            remove_any(dest)
            shutil.move(source, dest)

    def __new__(cls, path=PATH):
        return Paths.__new__(cls, path)

    def __init__(self, path=PATH):
        """deletes path if it exists and creates it if it doesn't"""
        if exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        os.chmod(path, 0700)

        Paths.__init__(self, path)

        os.mkdir(self.etc)
        os.mkdir(self.etc.mysql)
        os.mkdir(self.originals)
        os.mkdir(self.myfs)

        self.originals = self.Originals(self.originals)

class TempDir(str):
    def __new__(cls, prefix='tmp', suffix='', dir=None):
        path = tempfile.mkdtemp(suffix, prefix, dir)
        return str.__new__(cls, path)

    def __del__(self):
        shutil.rmtree(self)

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
        self.rollback = Rollback() if rollback else None
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
            if exists(root_dpath) and not isdir(root_dpath):
                os.remove(root_dpath)

            for fname in fnames:
                overlay_fpath = join(overlay_dpath, fname)
                root_fpath = join(root_dpath, fname)

                if root_fpath not in pathmap:
                    continue

                try:
                    if exists(root_fpath):
                        remove_any(root_fpath)

                    root_fpath_parent = dirname(root_fpath)
                    if not exists(root_fpath_parent):
                        os.makedirs(root_fpath_parent)

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
            shutil.copy("/etc/passwd", rollback.etc)
            shutil.copy("/etc/group", rollback.etc)

            changes.tofile(rollback.fsdelta)

            di = DirIndex()
            for change in changes:
                if exists(change.path):
                    di.add_path(change.path)
                    if change.OP == 'o':
                        rollback.originals.move(change.path)
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
                rollback.originals.move(path)
            else:
                action()

        def w(path, s):
            file(path, "w").write(str(s))

        w("/etc/passwd", passwd)
        w("/etc/group", group)

