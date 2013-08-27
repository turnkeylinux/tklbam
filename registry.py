# the registry is implemented as a virtual object with properties that are
# mapped directly to files.
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#

import os
from os.path import exists
from paths import Paths
import simplejson

from datetime import datetime

import shutil
from utils import AttrDict
from hub import Credentials

from version import get_turnkey_version

class UNDEFINED:
    pass

class _Registry(object):
    class CachedProfile(Exception):
        pass

    class ProfileNotFound(Exception):
        pass

    DEFAULT_PATH = "/var/lib/tklbam"

    class Paths(Paths):
        files = ['backup-resume', 'sub_apikey', 'secret', 'key', 'credentials', 'hbr', 
                 'profile', 'profile/stamp', 'profile/profile_id']

    def __init__(self, path=None):
        if path is None:
            path = os.environ.get('TKLBAM_REGISTRY', self.DEFAULT_PATH)

        if not exists(path):
            os.makedirs(path)
            os.chmod(path, 0700)

        self.path = self.Paths(path)

    @staticmethod
    def _file_str(path, s=UNDEFINED):
        if s is UNDEFINED:
            if not exists(path):
                return None

            return file(path).read().rstrip()

        else:
            if s is None:
                if exists(path):
                    os.remove(path)
            else:
                fh = file(path, "w")
                os.chmod(path, 0600)
                print >> fh, s
                fh.close()

    @classmethod
    def _file_tuple(cls, path, t=UNDEFINED):
        if t and t is not UNDEFINED:
            t = "\n".join([ str(v) for v in t ])

        retval = cls._file_str(path, t)
        if retval:
            return tuple(retval.split('\n'))

    @classmethod
    def _file_dict(cls, path, d=UNDEFINED):
        if d and d is not UNDEFINED:
            d = "\n".join([ "%s=%s" % (k, v) for k, v in d.items() ])

        retval = cls._file_str(path, d)
        if retval:
            return AttrDict([ v.split("=", 1) for v in retval.split("\n") ])

    def sub_apikey(self, val=UNDEFINED):
        return self._file_str(self.path.sub_apikey, val)
    sub_apikey = property(sub_apikey, sub_apikey)

    def secret(self, val=UNDEFINED):
        return self._file_str(self.path.secret, val)
    secret = property(secret, secret)

    def key(self, val=UNDEFINED):
        return self._file_str(self.path.key, val)
    key = property(key, key)

    def credentials(self, val=UNDEFINED):
        if val and val is not UNDEFINED:
            val = AttrDict({'accesskey': val.accesskey,
                            'secretkey': val.secretkey,
                            'usertoken': val.usertoken,
                            'producttoken': val.producttoken})

        retval = self._file_dict(self.path.credentials, val)
        if retval:
            return Credentials(retval)

    credentials = property(credentials, credentials)

    def hbr(self, val=UNDEFINED):
        format = "%Y-%m-%d %H:%M:%S"
        if val and val is not UNDEFINED:
            val = AttrDict({'address': val.address,
                            'backup_id': val.backup_id,
                            'updated': datetime.now().strftime(format)})

        retval = self._file_dict(self.path.hbr, val)
        if retval:
            if 'updated' not in retval:
                retval.updated = None
            else:
                retval.updated = datetime.strptime(retval.updated, format)
            return retval

    hbr = property(hbr, hbr)

    def profile(self, val=UNDEFINED):
        if val is None:
            return shutil.rmtree(self.path.profile, ignore_errors=True)

        if val is UNDEFINED:
            if not exists(self.path.profile.stamp):
                return None

            timestamp = os.stat(self.path.profile.stamp).st_mtime
            profile_id = self._file_str(self.path.profile.profile_id)
            if profile_id is None:
                profile_id = get_turnkey_version()
            return Profile(self.path.profile, profile_id, timestamp)
        else:
            profile_archive = val

            if not exists(self.path.profile):
                os.makedirs(self.path.profile)

            profile_archive.extract(self.path.profile)
            file(self.path.profile.stamp, "w").close()
            os.utime(self.path.profile.stamp, (0, profile_archive.timestamp))
            self._file_str(self.path.profile.profile_id, profile_archive.profile_id)
    profile = property(profile, profile)

    def backup_resume_conf(self, val=UNDEFINED):
        if val is None:
            if exists(self.path.backup_resume):
                os.remove(self.path.backup_resume)
            return

        if val is UNDEFINED:
            s = self._file_str(self.path.backup_resume)
            if s is None:
                return s

            return BackupSessionConf(simplejson.loads(s))

        else:
            s = simplejson.dumps(val)
            self._file_str(self.path.backup_resume, s)

    backup_resume_conf = property(backup_resume_conf, backup_resume_conf)

    def update_profile(self, hub_backups, profile_id=None):
        """Get a new profile if we don't have a profile in the registry or the Hub
        has a newer profile for this appliance. If we can't contact the Hub raise
        an error if we don't already have profile."""

        if not profile_id:
            if self.profile:
                profile_id = self.profile.profile_id
            else:
                profile_id = get_turnkey_version()

        if self.profile and self.profile.profile_id == profile_id:
            profile_timestamp = self.profile.timestamp
        else:
            # forced profile is not cached in the self
            profile_timestamp = None

        try:
            new_profile = hub_backups.get_new_profile(profile_id, profile_timestamp)
            if new_profile:
                self.profile = new_profile
        except hub_backups.Error, e:
            errno, errname, desc = e.args
            if errname == "BackupArchive.NotFound":
                raise self.ProfileNotFound(desc)

            if not self.profile or (self.profile.profile_id != profile_id):
                raise

            raise self.CachedProfile("using cached profile because of a Hub error: " + desc)

class Profile(str):
    def __new__(cls, path, profile_id, timestamp):
        return str.__new__(cls, path)

    def __init__(self, path, profile_id, timestamp):
        self.path = path
        self.timestamp = timestamp
        self.profile_id = profile_id

import conf

class BackupSessionConf(AttrDict):
    def __init__(self, d={}):
        AttrDict.__init__(self, d)
        self.overrides = conf.Limits(self.overrides)

registry = _Registry()
