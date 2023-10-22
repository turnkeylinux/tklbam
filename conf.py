import os
from os.path import exists

import re

from paths import Paths as _Paths
import duplicity

from typing import Self, Optional

class Error(Exception):
    pass

class Limits(list):
    @staticmethod
    def _is_db_limit(val: str) -> bool:
        if re.match(r'^-?(mysql|pgsql):', val):
            return True
        else:
            return False

    @classmethod
    def fromfile(cls, inputfile: str) -> Self:
        try:
            fh = open(inputfile)
        except:  # FIXME no bare exceptions!
            return cls()

        limits = []
        for line in fh.readlines():
            line = re.sub(r'#.*', '', line).strip()
            if not line:
                continue

            limits.append(line)
        fh.close()

        def is_legal(limit: str) -> bool:
            if cls._is_db_limit(limit):
                return True

            if re.match(r'^-?/', limit):
                return True

            return False

        for limit in limits:
            if not is_legal(limit):
                raise Error(repr(limit) + " is not a legal limit")

        return cls(limits)

    def fs_(self) -> list[str]:
        return [ val for val in self if not self._is_db_limit(val) ]
    fs = property(fs_)

    def _db(self, namespace: str) -> list[str]:
        db_limits = []
        for limit in self:
            m = re.match(r'^-?' + namespace + ':(.*)', limit)
            if not m:
                continue

            db_limit = '-' if limit[0] == '-' else ''
            db_limit += m.group(1)

            db_limits.append(db_limit)

        def any_positives(limits: list[str]) -> bool:
            for limit in limits:
                if limit[0] != '-':
                    return True
            return False

        if namespace == 'mysql' and any_positives(db_limits):
            db_limits.append('mysql')

        return db_limits

    def mydb_(self):
        return self._db('mysql')
    mydb = property(mydb_)

    def pgdb_(self):
        return self._db('pgsql')
    pgdb = property(pgdb_)

    def __add__(self, b: list[str]) -> Self:  # type: ignore[override]
    # error: Signature of "__add__" incompatible with supertype "list"  [override]
        cls = type(self)
        return cls(list.__add__(self, b))

from utils import AttrDict

class Conf(AttrDict):
    DEFAULT_PATH = os.environ.get('TKLBAM_CONF', '/etc/tklbam')
    class Error(Exception):
        pass

    class Paths(_Paths):
        files = [ 'overrides', 'conf' ]

    def _error(self, s: str|Error) -> Error:
        return self.Error("%s: %s" % (self.paths.conf, s))

    def __setitem__(self, name: str, val: int|str|bool) -> None:
        # sanity checking / parsing values reach us whenver someone
        # (including a method in this instance) sets an instance member

        if name == 'full_backup':
            if not re.match(r'^now$|^\d+[mhDWMY]', str(val)):
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
            if not re.match(r'^\d+(%|mb?|gb?)?$', str(val), re.IGNORECASE):
                raise self.Error("bad restore-cache value (%s)" % val)

        backup_skip_options = [ 'backup_skip_' + opt
                                for opt in ('files', 'database', 'packages') ]
        if name in backup_skip_options:
            if val not in (True, False):
                if re.match(r'^true|1|yes$', str(val), re.IGNORECASE):
                    val = True
                elif re.match(r'^false|0|no$', str(val), re.IGNORECASE):
                    val = False
                else:
                    raise self.Error("bad bool value '%s'" % val)

            if val:
                os.environ['TKLBAM_' + name.upper()] = 'yes'

        AttrDict.__setitem__(self, name, val)  # type: ignore[assignment]
        # Incompatible types in assignment (expression has type "str", target has type "_KT")  [assignment]
        # Incompatible types in assignment (expression has type "Union[int, str, bool]", target has type "_VT")  [assignment]

    def __init__(self, path: Optional[str] = None):
        AttrDict.__init__(self)
        if path is None:
            path = self.DEFAULT_PATH

        self.path = path
        self.paths = self.Paths(path)

        self.secretfile: Optional[str] = None
        self.address: Optional[str] = None
        self.force_profile: Optional[str] = None
        self.overrides = Limits.fromfile(self.paths.overrides)

        self.volsize = duplicity.Uploader.VOLSIZE
        self.s3_parallel_uploads = duplicity.Uploader.S3_PARALLEL_UPLOADS
        self.full_backup = duplicity.Uploader.FULL_IF_OLDER_THAN

        self.restore_cache_size = duplicity.Downloader.CACHE_SIZE
        self.restore_cache_dir = duplicity.Downloader.CACHE_DIR

        self.backup_skip_files = False
        self.backup_skip_database = False
        self.backup_skip_packages = False

        if not exists(self.paths.conf):
            return

        with open(self.paths.conf) as fob:
            for line in fob.read().split("\n"):
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

                except self.Error as e:
                    raise self._error(e)
