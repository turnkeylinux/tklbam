import os
from os.path import exists, join, realpath
import re
from dataclasses import dataclass
from typing import Self

import duplicity

DEFAULT_PATH = os.environ.get('TKLBAM_CONF', '/etc/tklbam3')


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
        limits = []

        def is_legal(limit: str) -> bool:
            if cls._is_db_limit(limit) or re.match(r'^-?/', limit):
                return True
            return False

        try:
            with open(inputfile) as fob:
                for line in fob.readlines():
                    line = re.sub(r'#.*', '', line).strip()
                    if not line:
                        continue
                    limits.append(line)

        except FileNotFoundError:
            return cls()

        for limit in limits:
            if not is_legal(limit):
                raise Error(repr(limit) + " is not a legal limit")

        return cls(limits)

    @property
    def fs(self) -> list[str]:
        return [val for val in self if not self._is_db_limit(val)]

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

    @property
    def mydb(self) -> list[str]:
        return self._db('mysql')

    @property
    def pgdb(self) -> list[str]:
        return self._db('pgsql')

    def __add__(self, b: list) -> list:
        cls = type(self)
        return cls(list.__add__(self, b))


@dataclass
class ConfDir:
    DEFAULT_PATH = DEFAULT_PATH
    path: str = DEFAULT_PATH

    def __post_init__(self):
        self.conf: str = join(self.path, 'tklbam.conf')
        self.overrides: str = join(self.path, 'overrides.conf')
        self.hooks_dir: str = join(self.path, 'hooks.d')


@dataclass
class Conf:
    Error = Error
    DEFAULT_PATH = DEFAULT_PATH

    # dfault conf vals
    path: str = DEFAULT_PATH
    full_backup: str = duplicity.Uploader.FULL_IF_OLDER_THAN
    volsize: int = duplicity.Uploader.VOLSIZE
    s3_parallel_uploads: int = duplicity.Uploader.S3_PARALLEL_UPLOADS
    restore_cache_size: str = duplicity.Downloader.CACHE_SIZE
    restore_cache_dir: str = duplicity.Downloader.CACHE_DIR
    backup_skip_files: bool = False
    backup_skip_database: bool = False
    backup_skip_packages: bool = False
    force_profile: str = ''

    # other defaults
    secretfile: str = ''
    address: str = ''

    @staticmethod
    def _validate_bool(opt: str, value: str | bool) -> str | bool:
        """Returns value if valid, otherwise raise exception"""
        if value in (True, False):
            val = value
        else:
            if re.match(r'^true|1|yes$', str(value), re.IGNORECASE):
                val = True
            elif re.match(r'^false|0|no$', str(value), re.IGNORECASE):
                val = False
            else:
                raise Error(f"bad bool value '{value}'")
        os.environ['TKLBAM_' + opt.upper()] = 'yes'
        return val

    @staticmethod
    def _validate_string(opt: str, regex: str, value: str) -> str:
        """Returns value if valid, otherwise raise exception"""
        if not re.match(regex, str(value), re.IGNORECASE):
            raise Error(f"bad {opt} value ({value})")
        return str(value).upper()

    @staticmethod
    def _validate_int(opt: str, value: str) -> int:
        """Returns value if valid, otherwise raise exception"""
        try:
            value_ = int(value)
        except ValueError:
            raise ValueError(f"{opt} not a number ({value})")
        return value_

    @staticmethod
    def _validate_path(opt: str, value: str) -> str:
        """Returns value if valid, otherwise raise exception"""
        if not exists(value):
            raise ValueError(f"{opt} path does not exist ({value})")
        return realpath(value)

    @classmethod
    def load_from_file(cls, conffile: str) -> None:
        with open(conffile) as fob:
            for line in fob.read().split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                try:
                    opt, value = re.split(r'\s+', line, 1)
                except ValueError:
                    raise ValueError(f"{conffile}: illegal line '{line}'")

                try:
                    opt = opt.replace('-', '_')
                    if opt in ('full_backup', 'restore_cache_size'):
                        if opt == 'full_backup':
                            regex = r'^now$|^\d+[mhDWMY]'
                        else:
                            regex = r'^\d+(%|mb?|gb?)?$'
                        value = cls._validate_string(opt, regex, value)
                    elif opt in ('volsize', 's3_parallel_uploads'):
                        value = cls._validate_int(opt, value)
                    elif opt in ('restore_cache_dir', 'force_profile'):
                        value = cls._validate_path(opt, value)
                    elif opt in ('backup_skip_files', 'backup_skip_packages',
                                 'backup_skip_database'):
                        value = cls._validate_bool(opt, value)
                    elif opt == 'force_profile':
                        value = str(value).lower()
                    else:
                        raise cls.Error(f"unknown conf option '{opt}'")
                except Error as e:
                    raise ValueError(e)
                setattr(cls, opt, value)

    def __post_init__(self) -> None:
        self.paths = ConfDir(self.path)
        if not exists(self.paths.overrides):
            self.overrides = Limits()
        else:
            self.overrides = Limits.fromfile(self.paths.overrides)
        if exists(self.paths.conf):
            self.load_from_file(self.paths.conf)
        # TODO warn if file not found?
