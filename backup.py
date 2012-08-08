import os
from os.path import *

import re
import shutil

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import Packages

import duplicity
import mysql

class ProfilePaths(Paths):
    files = [ 'dirindex', 'dirindex.conf', 'packages' ]

class ExtrasPaths(Paths):
    files = [ 'fsdelta', 'fsdelta-olist', 'newpkgs', 'myfs', 'etc', 'etc/mysql' ]

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
    return [ file for file in files if exists(file) ]

class Backup:
    EXTRAS_PATH = "/TKLBAM"

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

    def __init__(self, conf, force_cleanup=False):
        profile_paths = ProfilePaths(conf.profile)
        extras_paths = ExtrasPaths(self.EXTRAS_PATH)

        if not conf.checkpoint_restore or conf.simulate:
            _rmdir(extras_paths.path)

        self.force_cleanup = force_cleanup
        if not exists(extras_paths.path):
            self.force_cleanup = True
            if conf.verbose:
                print "CREATING " + extras_paths.path

            try:
                self._create_extras(extras_paths, profile_paths, conf)
            except:
                # destroy potentially incomplete extras
                _rmdir(extras_paths.path)
                raise
        else:
            if conf.verbose:
                print "RE-USING " + extras_paths.path

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

    def run(self, debug=False):
        conf = self.conf
        passphrase = file(conf.secretfile).readline().strip()

        opts = []
        if conf.verbose:
            opts += [('verbosity', 5)]

        if not conf.checkpoint_restore or self.force_cleanup:
            cleanup_command = duplicity.Command(opts, "cleanup", "--force", conf.address)
            if conf.verbose:
                print "\n# " + str(cleanup_command)

            if not conf.simulate:
                cleanup_command.run(passphrase, conf.credentials)

        opts += [('volsize', conf.volsize),
                 ('full-if-older-than', conf.full_backup),
                 ('include', self.extras_paths.path),
                 ('gpg-options', '--cipher-algo=aes')]

        if not conf.backup_skip_files:
             opts += [('include-filelist', self.extras_paths.fsdelta_olist)]

        opts += [('exclude', '**')]

        args = [ '--s3-unencrypted-connection', '--allow-source-mismatch' ] 

        if conf.simulate and conf.verbose:
            args += [ '--dry-run' ]

        if conf.s3_parallel_uploads > 1:
            s3_multipart_chunk_size = conf.volsize / conf.s3_parallel_uploads
            if s3_multipart_chunk_size < 5:
                s3_multipart_chunk_size = 5
            args += [ '--s3-use-multiprocessing', '--s3-multipart-chunk-size=%d' % s3_multipart_chunk_size ]

        args += [ '/', conf.address ]


        backup_command = duplicity.Command(opts, *args)

        if conf.verbose:
            print "\n# PASSPHRASE=$(cat %s) %s" % (conf.secretfile, 
                                                   backup_command)


        backup_command.run(passphrase, conf.credentials, debug=debug)

    def cleanup(self):
        _rmdir(self.extras_paths.path)

