#!/usr/bin/python
"""
Restore backup

Arguments:
    <limit> := -?( /path/to/add/or/remove | mysql:database[/table] )

Options:
    --skip-files                Don't restore filesystem
    --skip-database             Don't restore databases
    --skip-packages             Don't restore new packages

    --no-rollback               Disable rollback

"""

import os
from os.path import *

import sys
import getopt

import shutil
import tempfile

import userdb
from paths import Paths
from changes import Changes
from pathmap import PathMap
from dirindex import DirIndex

import backup

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] <address> <keyfile> [ limit ... ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def test():
    tmpdir = "/var/tmp/restore/backup"
    log = sys.stdout
    restore(tmpdir, log=log)

def restore(backup_path, limits=[], log=None):
    limits = backup.Limits(limits)

    tmpdir = tempfile.mkdtemp(prefix="tklbam-extras-")
    os.rename(backup_path + backup.Backup.EXTRAS_PATH, tmpdir)
    extras = backup.ExtrasPaths(tmpdir)

    try:
        restore_files(backup_path, extras, limits.fs, log)
    finally:
        shutil.rmtree(tmpdir)

class DontWriteIfNone:
    def __init__(self, fh=None):
        self.fh = fh

    def write(self, s):
        if self.fh:
            self.fh.write(str(s))

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

class Error(Exception):
    pass

class RollbackDirectory:
    def __init__(self, path):
        """deletes path if it exists and creates it if it doesn't"""
        if exists(path):
            shutil.rmtree(path)
        os.makedirs(path)
        self.path = path

    def _mkdir(self, source, subdir=None):
        dir = [ self.path, source.strip('/') ]
        if subdir:
            dir.insert(1, subdir.lstrip('/'))
        dir = join(*dir)

        if not exists(dirname(dir)):
            os.makedirs(dirname(dir))

        return dir

    def copy(self, source, subdir=None):
        """copies path while preserving its parent directory structure"""
        if not exists(source):
            raise Error("no such file or directory: " + source)

        dest = self._mkdir(source, subdir)
        if islink(source) or not isdir(source):
            shutil.copy(source, dest)
            shutil.copystat(source, dest)
        else:
            dest = abspath(dest)
            remove_any(dest)
            shutil.copytree(source, dest)

    def move(self, source, subdir=None):
        if not exists(source):
            raise Error("no such file or directory: " + source)

        dest = self._mkdir(source, subdir)
        remove_any(dest)
        shutil.move(source, dest)

def restore_files(backup_path, extras, limits=[], log=None, rollback=True):
    log = DontWriteIfNone(log)

    def userdb_merge(old_etc, new_etc):
        old_passwd = join(old_etc, "passwd")
        new_passwd = join(new_etc, "passwd")
        
        old_group = join(old_etc, "group")
        new_group = join(new_etc, "group")

        def r(path):
            return file(path).read()

        return userdb.merge(r(old_passwd), r(old_group), 
                            r(new_passwd), r(new_group))

    passwd, group, uidmap, gidmap = userdb_merge(extras.etc.path, "/etc")

    changes = Changes.fromfile(extras.fsdelta, limits)

    if rollback:
        rbdir = RollbackDirectory("/var/backups/tklbam-rollback")
        shutil.copy(extras.fsdelta, rbdir.path)

        rbdir.copy("/etc/passwd")
        rbdir.copy("/etc/group")

        di = DirIndex()
        for change in changes:
            if exists(change.path):
                di.add_path(change.path)
                if change.OP == 'o':
                    rbdir.move(change.path, subdir="overlay")
        di.save(join(rbdir.path, "dirindex"))

    else:
        rbdir = None

    def iter_apply_overlay(overlay, root, limits=[]):
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

    for val in iter_apply_overlay(backup_path, "/", limits):
        print >> log, val

    for action in changes.statfixes(uidmap, gidmap):
        print >> log, action
        action()

    for action in changes.deleted():
        print >> log, action

        path, = action.args
        if rbdir:
            rbdir.move(path, subdir="overlay")
        else:
            action()

    def w(path, s):
        file(path, "w").write(str(s))

    w("/etc/passwd", passwd)
    w("/etc/group", group)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['skip-files', 'skip-database', 'skip-packages',
                                        'no-rollback'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    skip_files = False
    skip_database = False
    skip_packages = False
    no_rollback = False
    for opt, val in opts:
        if opt == '--skip-files':
            skip_files = True
        elif opt == '--skip-database':
            skip_database = True
        elif opt == '--skip-packages':
            skip_packages = True
        elif opt == '--no-rollback':
            no_rollback = True
        elif opt == '-h':
            usage()

    if len(args) < 2:
        usage()


    address, keyfile = args[:2]
    limits = args[2:]

    # debug
    for var in ('address', 'keyfile', 'limits', 'skip_files', 'skip_database', 'skip_packages', 'no_rollback'):
        print "%s = %s" % (var, `locals()[var]`)

if __name__=="__main__":
    args = sys.argv[1:]
    funcname = args[0]
    locals()[funcname]()
