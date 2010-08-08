import os
from os.path import *

import re
import md5
import shutil

from paths import Paths

from dirindex import read_paths
from changes import whatchanged
from pkgman import Packages

import duplicity
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

from utils import AttrDict

class BackupConf(AttrDict):
    class Error(Exception):
        pass

    path = "/etc/tklbam"
    class Paths(Paths):
        files = [ 'overrides', 'conf' ]
    paths = Paths(path)

    def _error(self, s):
        return self.Error("%s: %s" % (self.paths.conf, s))

    def __setitem__(self, name, val):
        if name == 'full_backup':
            if not re.match(r'^\d+[HDWMY]', val):
                raise self.Error("bad full-backup value (%s)" % val)

        if name == 'volsize':
            try:
                val = int(val)
            except ValueError:
                raise self.Error("volsize not a number (%s)" % val)

        AttrDict.__setitem__(self, name, val)

    def _full_backup(self, val=None):
        print "full_backup"
        if val is None:
            return getattr(self, '_full_backup', None)

        setattr(self, '_full_backup', val)

    def _volsize(self, val=None):
        if val is None:
            return getattr(self, '_volsize', None)

        try:
            setattr(self, '_volsize', int(val))
        except ValueError:
            raise self._error("bad volsize value (%s)" % val)

    def __init__(self):
        self.secretfile = None
        self.address = None
        self.credentials = None
        self.profile = None
        self.overrides = Limits.fromfile(self.paths.overrides)
        self.verbose = True

        self.volsize = 50
        self.full_backup = "1M"

        if not exists(self.paths.conf):
            return

        for line in file(self.paths.conf).read().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                opt, val = re.split(r'\s+', line, 1)
            except ValueError:
                raise self._error("illegal line '%s'" % (line))

            try:
                if opt == 'full-backup':
                    self.full_backup = val

                elif opt == 'volsize':
                    self.volsize = val

                else:
                    raise self.Error("unknown conf option '%s'" % opt)

            except self.Error, e:
                raise self._error(e)

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

    def __init__(self, conf):
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

        self.paths = paths
        self.conf = conf

    def run(self, simulate=False):
        conf = self.conf
        passphrase = file(conf.secretfile).readline().strip()

        opts = []
        if conf.verbose:
            opts += [('verbosity', 5)]

        cleanup_command = duplicity.Command(opts, "cleanup", "--force", conf.address)
        if conf.verbose:
            print "\n# " + str(cleanup_command)

        if not simulate:
            cleanup_command.run(passphrase)

        opts += [('volsize', conf.volsize),
                 ('full-if-older-than', conf.full_backup),
                 ('include', self.paths.path),
                 ('include-filelist', self.paths.fsdelta_olist),
                 ('exclude', '**')]

        backup_command = duplicity.Command(opts, '/', conf.address)
        if conf.verbose:
            print "\n# PASSPHRASE=$(cat %s) %s" % (conf.secretfile, 
                                                 backup_command)

        if not simulate:
            backup_command.run(passphrase)

    def cleanup(self):
        shutil.rmtree(self.paths.path)

