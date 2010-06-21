import os
from os.path import *

import re
import md5
import shutil

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import Packages

import mysql

class Error(Exception):
    pass

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
        return [ val for val in self if not self._is_db_limit(val) ]
    fs = property(fs)

    def db(self):
        db_limits = []
        for limit in self:
            m = re.match(r'^-?mysql:(.*)', limit)
            if not m:
                continue

            db_limit = '-' if limit[0] == '-' else ''
            db_limit += m.group(1)

            db_limits.append(db_limit)

        def any_positives(limits):
            for limit in limits:
                if limit[0] != '-':
                    return True
            return False

        if any_positives(db_limits):
            db_limits.append('mysql')

        return db_limits
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
    files = [ 'dirindex', 'dirindex.conf', 'packages' ]

class ExtrasPaths(Paths):
    files = [ 'fsdelta', 'fsdelta-olist', 'newpkgs', 'myfs', 'etc', 'etc/mysql' ]

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

        self._write_whatchanged(paths.fsdelta, paths.fsdelta_olist,
                                profile.dirindex, profile.dirindex_conf, 
                                conf.overrides.fs)

        self._write_new_packages(paths.newpkgs, profile.packages)

        try:
            mysql.backup(paths.myfs, paths.etc.mysql, 
                         limits=conf.overrides.db)
        except mysql.Error:
            pass

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

