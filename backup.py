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

import os
from os.path import exists, join

import shutil
import simplejson

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import Packages

import duplicity
import mysql

import executil

from utils import AttrDict

class ProfilePaths(Paths):
    files = [ 'dirindex', 'dirindex.conf', 'packages' ]

class ExtrasPaths(Paths):
    PATH = "/TKLBAM"
    def __init__(self, path=None):
        if path is None:
            path = self.PATH

        Paths.__init__(self, path)

    def __new__(cls, path=None):
        return str.__new__(cls, path)

    files = [ 'backup-conf', 'fsdelta', 'fsdelta-olist', 'newpkgs', 'myfs', 'etc', 'etc/mysql' ]

def _rmdir(path):
    if exists(path):
        shutil.rmtree(path)

def _fpaths(dpath):
    arr = []
    for dpath, dnames, fnames in os.walk(dpath):
        for fname in fnames:
            arr.append(join(dpath, fname))
    return arr

def _filter_deleted(files):
    return [ f for f in files if exists(f) ]

def print_if(conditional):
    def printer(s):
        if conditional:
            print s
    return printer

class BackupConf(AttrDict):
    def __init__(self, profile_id, overrides, skip_files, skip_packages, skip_database):
        AttrDict.__init__(self)
        self.profile_id = profile_id
        self.overrides = overrides
        self.skip_files = skip_files
        self.skip_packages = skip_packages
        self.skip_database = skip_database

    @classmethod
    def fromfile(cls, path):
        if not exists(path):
            return None

        d = simplejson.load(file(path))
        return cls(*(d[attr]
                     for attr in ('profile_id', 'overrides', 'skip_files', 'skip_packages', 'skip_database')))

    def tofile(self, path):
        simplejson.dump(dict(self), file(path, "w"))

class Backup:
    class Error(Exception):
        pass

    @staticmethod
    def _write_new_packages(dest, base_packages):
        base_packages = Packages.fromfile(base_packages)
        current_packages = Packages()

        fh = file(dest, "w")
        new_packages = list(current_packages - base_packages)
        new_packages.sort()
        for package in new_packages:
            print >> fh, package
        fh.close()

    @staticmethod
    def _write_whatchanged(dest, dest_olist, dirindex, dirindex_conf,
                           overrides=[]):
        paths = read_paths(file(dirindex_conf))
        paths += overrides

        changes = whatchanged(dirindex, paths)
        changes.sort(lambda a,b: cmp(a.path, b.path))
        olist = [ change.path for change in changes if change.OP == 'o' ]

        changes.tofile(dest)
        file(dest_olist, "w").writelines((path + "\n" for path in olist))

    @classmethod
    def _create_extras(cls, extras, profile, conf):
        os.mkdir(extras.path)

        etc = str(extras.etc)
        os.mkdir(etc)
        shutil.copy("/etc/passwd", etc)
        shutil.copy("/etc/group", etc)

        if not conf.backup_skip_files:
            cls._write_whatchanged(extras.fsdelta, extras.fsdelta_olist,
                                   profile.dirindex, profile.dirindex_conf,
                                   conf.overrides.fs)

        if not conf.backup_skip_packages:
            cls._write_new_packages(extras.newpkgs, profile.packages)

        if not conf.backup_skip_database:
            try:
                mysql.backup(extras.myfs, extras.etc.mysql,
                             limits=conf.overrides.db)
            except mysql.Error:
                pass

    def __init__(self, conf, profile, resume=False):
        verbose = print_if(conf.verbose)

        if not profile:
            raise self.Error("can't backup without a profile")

        profile_paths = ProfilePaths(profile.path)
        extras_paths = ExtrasPaths()

        # decide whether we can allow resume=True
        # /TKLBAM has to exist and the backup configuration has to match
        backup_conf = BackupConf(profile.profile_id,
                                 conf.overrides,
                                 conf.backup_skip_files,
                                 conf.backup_skip_packages,
                                 conf.backup_skip_database)

        saved_backup_conf = BackupConf.fromfile(extras_paths.backup_conf)

        if backup_conf != saved_backup_conf or not conf.checkpoint_restore:
            resume = False

        self.force_cleanup = False
        if not resume:
            _rmdir(extras_paths.path)
            self.force_cleanup = True
        else:
            verbose("ATTEMPTING TO RESUME ABORTED BACKUP SESSION")

        # create or re-use /TKLBAM
        if not exists(extras_paths.path):
            verbose("CREATING " + extras_paths.path)

            try:
                self._create_extras(extras_paths, profile_paths, conf)
                backup_conf.tofile(extras_paths.backup_conf)
            except:
                # destroy potentially incomplete extras
                _rmdir(extras_paths.path)
                raise

        # print uncompressed footprint
        if conf.verbose:

            # files in /TKLBAM + /TKLBAM/fsdelta-olist
            fpaths= _fpaths(extras_paths.path)

            if not conf.backup_skip_files:
                fsdelta_olist = file(extras_paths.fsdelta_olist).read().splitlines()
                fpaths += _filter_deleted(fsdelta_olist)

            size = sum([ os.lstat(fpath).st_size
                         for fpath in fpaths ])

            if size > 1024 * 1024 * 1024:
                size_fmt = "%.2f GB" % (float(size) / (1024 * 1024 * 1024))
            elif size > 1024 * 1024:
                size_fmt = "%.2f MB" % (float(size) / (1024 * 1024))
            else:
                size_fmt = "%.2f KB" % (float(size) / 1024)

            print "FULL UNCOMPRESSED FOOTPRINT: %s in %d files" % (size_fmt,
                                                                   len(fpaths))

        self.conf = conf
        self.extras_paths = extras_paths

    def upload(self, credentials, debug=False):
        verbose = print_if(self.conf.verbose)

        conf = self.conf
        passphrase = file(conf.secretfile).readline().strip()
        opts = []
        if conf.verbose:
            opts += [('verbosity', 5)]

        if not conf.checkpoint_restore or self.force_cleanup:
            cleanup_command = duplicity.Command(opts, "cleanup", "--force", conf.address)
            verbose("\n# " + str(cleanup_command))

            if not conf.simulate:
                cleanup_command.run(passphrase, credentials)

        opts += [('volsize', conf.volsize),
                 ('full-if-older-than', conf.full_backup),
                 ('include', self.extras_paths.path),
                 ('gpg-options', '--cipher-algo=aes')]

        if not conf.backup_skip_files:
            opts += [('include-filelist', self.extras_paths.fsdelta_olist)]

        opts += [('exclude', '**')]

        args = [ '--s3-unencrypted-connection', '--allow-source-mismatch' ]

        if conf.simulate: 
            args += [ '--dry-run' ]

        if conf.s3_parallel_uploads > 1:
            s3_multipart_chunk_size = conf.volsize / conf.s3_parallel_uploads
            if s3_multipart_chunk_size < 5:
                s3_multipart_chunk_size = 5
            args += [ '--s3-use-multiprocessing', '--s3-multipart-chunk-size=%d' % s3_multipart_chunk_size ]

        args += [ '/', conf.address ]


        backup_command = duplicity.Command(opts, *args)

        verbose("\n# PASSPHRASE=$(cat %s) %s" % (conf.secretfile, backup_command))

        backup_command.run(passphrase, credentials, debug=debug)

    def dump(self, path):

        def r(p):
            return join(path, p.lstrip('/'))

        shutil.copytree(self.extras_paths.path, r(self.extras_paths.path))
        executil.getoutput("tar --create --files-from=%s | tar --extract --directory %s" % 
                           (self.extras_paths.fsdelta_olist, executil.mkarg(path)))

    def cleanup(self):
        _rmdir(self.extras_paths.path)

