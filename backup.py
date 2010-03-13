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

class Overrides(list):
    @staticmethod
    def is_db_override(val):
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

        overrides = []
        for line in fh.readlines():
            line = re.sub(r'#.*', '', line).strip()
            if not line:
                continue

            overrides += line.split()

        def is_legal(override):
            if cls.is_db_override(override):
                return True

            if re.match(r'^-?/', override):
                return True

            return False

        for override in overrides:
            if not is_legal(override):
                raise Error(`override` + " is not a legal override")

        return cls(overrides)

    def fs(self):
        for val in self:
            if not self.is_db_override(val):
                yield val
    fs = property(fs)

    def db(self):
        for val in self:
            if self.is_db_override(val):
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
        self.overrides = Overrides.fromfile(self.paths.overrides)

class ProfilePaths(Paths):
    files = [ 'dirindex', 'dirindex.conf', 'selections' ]

class BackupPaths(Paths):
    files = [ 'fsdelta', 'newpkgs', 'myfs', 'etc', 'etc/mysql' ]

def _write_new_packages(dest, base_selections):
    base_selections = DpkgSelections(base_selections)
    current_selections = DpkgSelections()

    fh = file(dest, "w")
    new_packages = list(current_selections - base_selections)
    new_packages.sort()
    for package in new_packages:
        print >> fh, package
    fh.close()

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

def _write_whatchanged(dest, dirindex, dirindex_conf, overrides=[]):
    paths = read_paths(file(dirindex_conf))
    paths += overrides

    fh = file(dest, "w")
    changes = [ str(change)
                for change in whatchanged(dirindex, paths) ]
    changes.sort()
    for change in changes:
        print >> fh, change
    fh.close()

def backup(conf):
    profile = ProfilePaths(conf.profile)
    paths = BackupPaths("/TKLBAM")

    if isdir(paths.path):
        shutil.rmtree(paths.path)
    os.mkdir(paths.path)

    etc = str(paths.etc)
    os.mkdir(etc)
    shutil.copy("/etc/passwd", etc)
    shutil.copy("/etc/group", etc)

    os.mkdir(paths.etc.mysql)
    shutil.copy("/etc/mysql/debian.cnf", paths.etc.mysql)

    _write_whatchanged(paths.fsdelta, 
                      profile.dirindex, profile.dirindex_conf, 
                      conf.overrides.fs)

    _write_new_packages(paths.newpkgs, profile.selections)
    _mysql2fs(paths.myfs, conf.overrides.db)

