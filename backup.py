import os
from os.path import *

import re
import md5
import shutil

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import DpkgSelections

import mysql

class Error(Exception):
    pass

class Key:
    @staticmethod
    def create(keyfile):
        def mcookie():
            return md5.md5(file("/dev/random").read(16)).hexdigest()

        fh = file(keyfile, "w")
        os.chmod(keyfile, 0600)
        print >> fh, mcookie()
        fh.close()

    @staticmethod
    def read(keyfile):
        return file(keyfile).read().strip()

class Limits(list):
    @staticmethod
    def _is_db_limit(val):
        if re.match(r'^-?mysql:', val):
            return True
        else:
            return False

    @classmethod
    def fromfile(cls, inputfile):
        try:
            fh = file(inputfile)
        except:
            return cls()

        limits = []
        for line in fh.readlines():
            line = re.sub(r'#.*', '', line).strip()
            if not line:
                continue

            limits += line.split()

        def is_legal(limit):
            if cls._is_db_limit(limit):
                return True

            if re.match(r'^-?/', limit):
                return True

            return False

        for limit in limits:
            if not is_legal(limit):
                raise Error(`limit` + " is not a legal limit")

        return cls(limits)

    def fs(self):
        for val in self:
            if not self._is_db_limit(val):
                yield val
    fs = property(fs)

    def db(self):
        for val in self:
            if self._is_db_limit(val):
                yield val
    db = property(db)

    def __add__(self, b):
        cls = type(self)
        return cls(list.__add__(self, b))

class BackupConf:
    profile = "/usr/share/tklbam/profile"

    path = "/etc/tklbam"
    class Paths(Paths):
        files = [ 'address', 'key', 'overrides' ]
    paths = Paths(path)

    @staticmethod
    def _read_address(path):
        try:
            return file(path).read().strip()
        except:
            return None

    def __init__(self):
        self.keyfile = self.paths.key
        self.address = self._read_address(self.paths.address)
        self.overrides = Limits.fromfile(self.paths.overrides)

class ProfilePaths(Paths):
    files = [ 'dirindex', 'dirindex.conf', 'selections' ]

class ExtrasPaths(Paths):
    files = [ 'fsdelta', 'fsdelta-olist', 'newpkgs', 'myfs', 'etc', 'etc/mysql' ]

class Backup:
    EXTRAS_PATH = "/TKLBAM"

    @staticmethod
    def _write_new_packages(dest, base_selections):
        base_selections = DpkgSelections(base_selections)
        current_selections = DpkgSelections()

        fh = file(dest, "w")
        new_packages = list(current_selections - base_selections)
        new_packages.sort()
        for package in new_packages:
            print >> fh, package
        fh.close()

    @staticmethod
    def _mysql2fs(outdir, overrides=[], callback=None):
        limits = [ re.sub(r'^(-?)mysql:', '\\1', limit) 
                   for limit in overrides 
                   if re.match(r'^-?mysql:', limit) ]

        def any_positives(limits):
            for limit in limits:
                if limit[0] != '-':
                    return True
            return False

        if any_positives(limits):
            limits.append('mysql')

        os.mkdir(outdir)
        mysql.mysql2fs(mysql.mysqldump(), outdir, limits, callback)

    @staticmethod
    def _write_whatchanged(dest, dest_olist, dirindex, dirindex_conf, 
                           overrides=[]):
        paths = read_paths(file(dirindex_conf))
        paths += overrides

        changes = whatchanged(dirindex, paths)
        changes.sort(lambda a,b: cmp(a.path, b.path))
        olist = [ change.path for change in changes if change.OP == 'o' ]

        def write(dest, vals):
            fh = file(dest, "w")
            for val in vals:
                print >> fh, val
            fh.close()

        write(dest, changes)
        write(dest_olist, olist)

    def __init__(self, conf, key):
        profile = ProfilePaths(conf.profile)
        paths = ExtrasPaths(self.EXTRAS_PATH)

        if isdir(paths.path):
            shutil.rmtree(paths.path)
        os.mkdir(paths.path)

        etc = str(paths.etc)
        os.mkdir(etc)
        shutil.copy("/etc/passwd", etc)
        shutil.copy("/etc/group", etc)

        os.mkdir(paths.etc.mysql)
        shutil.copy("/etc/mysql/debian.cnf", paths.etc.mysql)

        self._write_whatchanged(paths.fsdelta, paths.fsdelta_olist,
                                profile.dirindex, profile.dirindex_conf, 
                                conf.overrides.fs)

        self._write_new_packages(paths.newpkgs, profile.selections)
        self._mysql2fs(paths.myfs, conf.overrides.db)

        args = ['--volsize 50',
                '--include ' + paths.path,
                '--include-filelist ' + paths.fsdelta_olist,
                "--exclude '**'",
                '/',
                conf.address]

        self.command = "duplicity " + " ".join(args)
        self.paths = paths
        self.conf = conf
        self.key = key

    def run(self):
        os.environ['PASSPHRASE'] = self.key
        exitcode = os.system(self.command)
        del os.environ['PASSPHRASE']

        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, self.command))

    def cleanup(self):
        shutil.rmtree(self.paths.path)

