# the registry is implemented as a virtual object with properties that are
# mapped directly to files.
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#

import os
import re
from os.path import exists, basename, abspath, isdir, join #realpath
#from paths import Paths as _Paths
import json

from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Self

import shutil
from utils import BaseAttrDict, _check_path

import hub

from version import TurnKeyVersion, detect_profile_id
#from paths import Paths
import conf

UNDEFINED_S = "TKLBAM UNDEFINED STRING"
UNDEFINED_D = {UNDEFINED_S: UNDEFINED_S}

IAMRole = hub.Credentials().IAMRole
IAMUser = hub.Credentials().IAMUser

ENV_VARNAME = "TKLBAM_REGISTRY"
DEFAULT_PATH = '/var/lib/tklbam3'
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_default_path() -> str:
    return os.environ.get(ENV_VARNAME, DEFAULT_PATH)


class BackupSessionConf(BaseAttrDict):
    def __init__(self, d: Optional[dict[str, str]] = None) -> None:
        if not d:
            d = {}
        self.overrides = conf.Limits()
        for key, value in d:
            if key == 'overrides':
                setattr(self, key, conf.Limits(value))
            else:
                setattr(self, key, value)


class BaseRegisry(dict):

    updated_dt: Optional[datetime] = None

    def __init__(self, address: Optional[str] = None,
                 backup_id: Optional[str] = None,
                 updated: Optional[str] = None
                 ) -> None:
        self.address = address or ''
        self.backup_id = int(backup_id or 0)
        self.updated = updated or datetime.now()

    @property
    def updated(self) -> Optional[str]:
        if self.updated_dt:
            return self.updated_dt.strftime(DATETIME_FORMAT)

    @updated.setter
    def updated(self, value: str | datetime) -> None:
        if isinstance(value, datetime):
            self.updated_dt = value
        elif isinstance(value, str):
            try:
                self.updated_dt = datetime.strptime(value, DATETIME_FORMAT)
            except ValueError as e:
                raise ValueError(e)


@dataclass
class RegCredPaths(BaseAttrDict):
    address: str = ''
    backup_id: str = ''


@dataclass
class _Registry:
    class CachedProfile(Exception):
        pass

    class ProfileNotFound(Exception):
        """\
Without a profile TKLBAM can't auto-configure the backup process for your
system. Sorry about that! However even without a profile you can still:

- Restore existing backups
- Backup raw directories with the --raw-upload option

You can use the --force-profile option to fix or workaround a missing profile
in several ways:

- Use an empty profile with --force-profile=empty
- Use a custom profile with --force-profile=path/to/custom/profile/

    tklbam3-internal create-profile --help

Also, if TKLBAM is linked to the Hub you can:

- Download a profile for another TurnKey system with --force-profile=codename
  (e.g., "core")
- Download the all-purpose generic profile with --force-profile=generic

Run "tklbam3-init --help" for further details.
"""

    path: str = ''

    _secret: Optional[str] = None
    _key: Optional[str] = None
    _credentials: Optional[str] = None
    _hbr: Optional[str] = None
    _backup_resume: bool = True
    _sub_apikey: str = ''

    _check_path = staticmethod(_check_path)

    EMPTY_PROFILE = "empty"
    CUSTOM_PROFILE = "custom"
    DEFAULT_PATH = DEFAULT_PATH

    def __post_init__(self) -> None:
        if self.path == '':
            self.path = os.environ.get(ENV_VARNAME, DEFAULT_PATH)
        if not exists(self.path):
            os.makedirs(self.path)
            os.chmod(self.path, 0o700)
        if not self.path:
            return None
        self.restore_log_path = join(self.path, 'restore.log')
        self.backup_log_path = join(self.path, 'backup.log')
        self.backup_pid_path = join(self.path, 'backup.pid')
        self.backup_resume_path = join(self.path, 'backup-resume')
        self.sub_apikey_path = join(self.path, 'sub_apikey')
        self.secret_path = join(self.path, 'secret')
        self.key_path = join(self.path, 'key')
        self.credentials_path = join(self.path, 'credentials')
        self.hbr_path = join(self.path, 'hbr')
        self.profile_path = join(self.path, 'profile')
        self.profile_stamp_path = join(self.path, 'profile/stamp')
        self.profile_id_path = join(self.path, 'profile/profile_id')

    @staticmethod
    def _file_str(path: Optional[str], s: str = UNDEFINED_S) -> Optional[str]:
        if not path:
            return None
        if s == UNDEFINED_S:
            if not exists(path):
                return None
            with open(path) as fob:
                return fob.read().rstrip()
        else:
            if s is None:
                if exists(path):
                    os.remove(path)
            else:
                with open(path, "w") as fob:
                    os.chmod(path, 0o600)
                    fob.write(f'{s}\n')
        return None

    @classmethod
    def _file_tuple(cls, path: str,
                    t: str = UNDEFINED_S
                    ) -> Optional[list[str]]:
        if t and t != UNDEFINED_S:
            t = "\n".join([str(v) for v in t])

        retval = cls._file_str(path, t)
        if retval:
            return retval.split('\n')
        return None

    @classmethod
    def _file_dict(cls, path: Optional[str],
                   d: dict[str, str] | BaseRegisry = UNDEFINED_D
                   ) -> Optional[BaseRegisry]:
        if not path:
            return None
        retval = None
        retclass = BaseRegisry()
        if d and d != UNDEFINED_D:
            if isinstance(d, dict):
                d_ = "\n".join([f"{k}={v}" for k, v in list(d.items())])
                retval = cls._file_str(path, *d_)
            else:
                return d
        if retval:
            for line in retval.split("\n"):
                k, v = line.split("=", 1)
                retclass[k] = v
            return retclass
        return None

    @property
    def sub_apikey(self, val: str = UNDEFINED_S) -> Optional[str]:
        return self._file_str(self.sub_apikey_path, val)

    @property
    def secret(self, val: str = UNDEFINED_S) -> Optional[str]:
        return self._file_str(self.secret_path, val)

    @property
    def key(self, val: str = UNDEFINED_S) -> Optional[str]:
        return self._file_str(self.key_path, val)

    @property
    def credentials(self, val: dict[str, str] = UNDEFINED_D
                    ) -> Optional[IAMRole | IAMUser]:
        retval = self._file_dict(self.credentials_path, val)
        if retval:
            return hub.Credentials.from_dict(retval)
        return None

    @property
    def hbr(self, val: RegCredPaths = RegCredPaths(UNDEFINED_S)
            ) -> Optional[BaseRegisry]:
        # hbr getter setter
        if val and val != UNDEFINED_S:
            val_ = BaseRegisry(address=val.address,
                               backup_id=val.backup_id)
        else:
            val_ = BaseRegisry()

        retval = self._file_dict(self.hbr_path, val_)
        if retval:
            if retval.updated:
                retval.updated = retval.updated
            return retval
        return None

    @classmethod
    def _custom_profile_id(cls, path: str) -> str:
        name = basename(abspath(path))
        return f"{cls.CUSTOM_PROFILE}:{name}"

    @property
    def profile(self,
                val: hub.ProfileArchive = hub.ProfileArchive(UNDEFINED_S)
                ) -> Optional[Profile]:
        if val is None:
            return shutil.rmtree(self.profile_path, ignore_errors=True)

        if val == UNDEFINED_S:
            if not exists(self.profile_stamp_path):
                return None

            timestamp = str(os.stat(self.profile_stamp_path).st_mtime)
            profile_id = self._file_str(self.profile_id_path)
            if profile_id is None:
                profile_id = detect_profile_id()
            return Profile(self.profile_path, profile_id, timestamp)
        else:
            profile_archive = val

            #self.profile = None  # XXX Can't do this!
            os.makedirs(self.profile_path)

            if val == self.EMPTY_PROFILE:
                self._file_str(self.profile_id_path, str(val))
                open(self.profile_stamp_path, "w").close()

            elif isdir(str(val)):
                #self.profile = None  # XXX Can't do this!
                shutil.copytree(str(val), self.profile_path)
                self._file_str(self.profile_id_path,
                               self._custom_profile_id(str(val)))
                open(self.profile_stamp_path, "w").close()

            else:
                profile_archive.extract(self.profile_path)
                open(self.profile_stamp_path, "w").close()
                os.utime(self.profile_stamp_path,
                         (0, profile_archive.timestamp))
                self._file_str(self.profile_id_path,
                               profile_archive.profile_id)
        return None

    @property
    def backup_resume_conf(self, val: str = UNDEFINED_S
                           ) -> Optional[BackupSessionConf]:
        if val is None:
            if exists(self.backup_resume_path):
                os.remove(self.backup_resume_path)
            return None

        if val == UNDEFINED_S:
            s = self._file_str(self.backup_resume_path)
            if s is None:
                return None
            try:
                return BackupSessionConf(json.loads(s))
            except:  # TODO bare exception
                return None
        else:
            s = json.dumps(val)
            self._file_str(self.backup_resume_path, s)
            return None

    def _update_profile(self, profile_id: Optional[str] = None) -> None:
        """Get a new profile if we don't have a profile in the registry or the
        Hub has a newer profile for this appliance. If we can't contact the
        Hub raise an error if we don't already have profile."""

        if not profile_id:
            if self.profile:
                profile_id = self.profile.profile_id
            else:
                profile_id = detect_profile_id()
        assert profile_id is not None
        if profile_id == self.EMPTY_PROFILE or isdir(profile_id):
            self.profile = profile_id
            return

        hub_backups = hub.Backups(self.sub_apikey)
        if self.profile and self.profile.profile_id == profile_id:
            profile_timestamp = self.profile.timestamp
        else:
            # forced profile is not cached in the self
            profile_timestamp = None

        try:
            new_profile = hub_backups.get_new_profile(profile_id,
                                                      profile_timestamp)
            if new_profile:
                self.profile = new_profile
                print("Downloaded %s profile" % self.profile.profile_id)

        except hub.NotSubscribed:
            raise

        except hub_backups.Error as e:
            errno, errname, desc = e.args
            if errname == "BackupArchive.NotFound":
                raise self.ProfileNotFound(desc)

            if not self.profile or (self.profile.profile_id != profile_id):
                raise

            raise self.CachedProfile(
                    "using cached profile because of a Hub error: " + desc)

    def update_profile(self, profile_id: Optional[str] = None) -> None:
        if profile_id is None:
            # don't attempt to update empty or custom profiles
            if (self.profile and
                    (self.profile.profile_id == registry.EMPTY_PROFILE or
                     self.profile.profile_id.startswith(
                         registry.CUSTOM_PROFILE + ":")
                     )):
                return None

        try:
            # look for exact match first
            self._update_profile(profile_id)
        except self.ProfileNotFound as first_exception:
            if profile_id:
                if not re.match(r'^turnkey-', profile_id):
                    profile_id = "turnkey-" + profile_id
                check_profile = TurnKeyVersion.from_string(profile_id)
                if check_profile and not check_profile.is_complete():
                    completed_profile_id = _complete_profile_id(profile_id)
                    if completed_profile_id:
                        try:
                            self._update_profile(completed_profile_id)
                            return None
                        except:  # TODO fix bare except
                            pass

            raise first_exception


def _complete_profile_id(partial: str) -> Optional[str]:
    partial_ver = TurnKeyVersion.from_string(partial)
    system = TurnKeyVersion.from_system()
    if not system:
        return None
    assert partial_ver is not None
    if partial_ver.arch is None:
        partial_ver.arch = system.arch
    assert system.release is not None
    if (partial_ver.release is None
            or system.release.startswith(partial_ver.release)):
        partial_ver.release = system.release

    return str(partial_ver)


class Profile:

    packages: str
    dirindex: str
    dirindex_conf: str
    path: str

    @classmethod
    def __new__(cls, path: str, profile_id: str, timestamp: str) -> Self:
        cls.profile_id = profile_id
        cls.timestamp = timestamp
        return str.__new__(cls, path)

    def __init__(self, path: str, profile_id: str, timestamp: str):
        self.path = path
        self.timestamp = timestamp
        self.profile_id = profile_id


registry = _Registry()


class NotInitialized(hub.Backups.NotInitialized):
    def __init__(self):
        command = "tklbam3-init"
        if registry.path != registry.DEFAULT_PATH:
            command = f"{registry.ENV_VARNAME}={registry.path} {command}"

        hub.Backups.NotInitialized.__init__(
                self, f'Hub link required, run "{command}" first')


def update_profile(profile_id: Optional[str] = None,
                   strict: bool = True
                   ) -> None:
    import sys
    global registry

    if profile_id == registry.EMPTY_PROFILE:
        print("""
Creating an empty profile, which means:

- We only backup files as included or excluded in the override paths specified
  on the command line or configured in /etc/tklbam3/overrides

- We can't detect which files have changed since installation so we will
  indiscriminately backup all files in the included directories.
""")
    if not strict:
        try:
            registry.update_profile(profile_id)
        except:  # TODO fix bare exception
            return
    else:
        try:
            registry.update_profile(profile_id)
        except hub.Backups.NotInitialized:
            raise NotInitialized()

        except hub.NotSubscribed as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

        except registry.CachedProfile as e:
            print("warning: " + str(e), file=sys.stderr)
        except registry.ProfileNotFound as e:
            print("TurnKey Hub Error: %s" % str(e), file=sys.stderr)
            if not profile_id:
                # be extra nice to people who aren't using --force-profile
                print(f"\n{e.__doc__}", file=sys.stderr)

            sys.exit(1)
    if registry.profile:
        os.environ['TKLBAM_PROFILE_ID'] = registry.profile.profile_id


def hub_backups():
    try:
        hb = hub.Backups(registry.sub_apikey)
    except hub.Backups.NotInitialized:
        raise NotInitialized()

    return hb
