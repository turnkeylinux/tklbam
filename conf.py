import os
from os.path import *

import re

from paths import Paths

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

class Conf(AttrDict):
    DEFAULT_PATH = os.environ.get('TKLBAM_CONF', '/etc/tklbam')
    class Error(Exception):
        pass

    class Paths(Paths):
        files = [ 'overrides', 'conf' ]

    def _error(self, s):
        return self.Error("%s: %s" % (self.paths.conf, s))

    def __setitem__(self, name, val):
        # sanity checking / parsing values reach us whenver someone
        # (including a method in this instance) sets an instance member

        if name == 'full_backup':
            if not re.match(r'^\d+[HDWMY]', val):
                raise self.Error("bad full-backup value (%s)" % val)

        if name == 'volsize':
            try:
                val = int(val)
            except ValueError:
                raise self.Error("volsize not a number (%s)" % val)

        if name == 's3_parallel_uploads':
            try:
                val = int(val)
            except ValueError:
                raise self.Error("s3-parallel-uploads not a number (%s)" % val)

        if name == 'restore_cache_size':
            if not re.match(r'^\d+(%|mb?|gb?)?$', val, re.IGNORECASE):
                raise self.Error("bad restore-cache value (%s)" % val)

        backup_skip_options = [ 'backup_skip_' + opt
                                for opt in ('files', 'database', 'packages') ]
        if name in backup_skip_options:
            if val not in (True, False):
                if re.match(r'^true|1|yes$', val, re.IGNORECASE):
                    val = True
                elif re.match(r'^false|0|no$', val, re.IGNORECASE):
                    val = False
                else:
                    raise self.Error("bad bool value '%s'" % val)

        AttrDict.__setitem__(self, name, val)

    def __init__(self, path=None):
        if path is None:
            path = self.DEFAULT_PATH

        self.path = path
        self.paths = self.Paths(path)

        self.secretfile = None
        self.address = None
        self.force_profile = None
        self.overrides = Limits.fromfile(self.paths.overrides)
        self.verbose = True
        self.simulate = False

        self.checkpoint_restore = True

        self.volsize = 50
        self.s3_parallel_uploads = 1
        self.full_backup = "1M"
        self.restore_cache_size = "50%"
        self.restore_cache_dir = "/var/cache/tklbam/restore"

        self.backup_skip_files = False
        self.backup_skip_database = False
        self.backup_skip_packages = False

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
                if opt in ('full-backup', 'volsize', 's3-parallel-uploads',
                           'restore-cache-size', 'restore-cache-dir',
                           'backup-skip-files', 'backup-skip-packages', 'backup-skip-database', 'force-profile'):

                    attrname = opt.replace('-', '_')
                    setattr(self, attrname, val)

                else:
                    raise self.Error("unknown conf option '%s'" % opt)

            except self.Error, e:
                raise self._error(e)

