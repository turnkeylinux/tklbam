# the registry is implemented as a virtual object with properties that are
# mapped directly to files.
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
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
from os.path import *
from paths import Paths as _Paths
import simplejson

from datetime import datetime

import shutil
from utils import AttrDict
import hub

from version import TurnKeyVersion, detect_profile_id

import conf

class UNDEFINED:
    pass

class _Registry(object):
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

    tklbam-internal create-profile --help

Also, if TKLBAM is linked to the Hub you can:

- Download a profile for another TurnKey system with --force-profile=codename (e.g., "core")
- Download the all-purpose generic profile with --force-profile=generic

Run "tklbam-init --help" for further details.
"""

    ENV_VARNAME = "TKLBAM_REGISTRY"
    DEFAULT_PATH = os.environ.get(ENV_VARNAME, '/var/lib/tklbam')

    EMPTY_PROFILE = "empty"
    CUSTOM_PROFILE = "custom"

    class Paths(_Paths):
        files = ['restore.log', 'backup.log', 'backup.pid',
                 'backup-resume', 'sub_apikey', 'secret', 'key', 'credentials', 'hbr',
                 'profile', 'profile/stamp', 'profile/profile_id']

    def __init__(self, path=None):
        if path is None:
            path = os.environ.get(self.ENV_VARNAME, self.DEFAULT_PATH)

        if not exists(path):
            os.makedirs(path)
            os.chmod(path, 0o700)

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
                os.chmod(path, 0o600)
                print(s, file=fh)
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
            d = "\n".join([ "%s=%s" % (k, v) for k, v in list(d.items()) ])

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
        retval = self._file_dict(self.path.credentials, val)
        if retval:
            return hub.Credentials.from_dict(retval)
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

    @classmethod
    def _custom_profile_id(cls, path):
        name = basename(abspath(path))
        return "%s:%s" % (cls.CUSTOM_PROFILE, name)

    def profile(self, val=UNDEFINED):
        if val is None:
            return shutil.rmtree(self.path.profile, ignore_errors=True)

        if val is UNDEFINED:
            if not exists(self.path.profile.stamp):
                return None

            timestamp = int(os.stat(self.path.profile.stamp).st_mtime)
            profile_id = self._file_str(self.path.profile.profile_id)
            if profile_id is None:
                profile_id = detect_profile_id()
            return Profile(self.path.profile, profile_id, timestamp)
        else:
            profile_archive = val

            self.profile = None
            os.makedirs(self.path.profile)

            if val == self.EMPTY_PROFILE:
                self._file_str(self.path.profile.profile_id, val)
                file(self.path.profile.stamp, "w").close()

            elif isdir(str(val)):
                self.profile = None
                shutil.copytree(val, self.path.profile)
                self._file_str(self.path.profile.profile_id, self._custom_profile_id(val))
                file(self.path.profile.stamp, "w").close()

            else:
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
                return

            try:
                return BackupSessionConf(simplejson.loads(s))
            except:
                return

        else:
            s = simplejson.dumps(val)
            self._file_str(self.path.backup_resume, s)

    backup_resume_conf = property(backup_resume_conf, backup_resume_conf)

    def _update_profile(self, profile_id=None):
        """Get a new profile if we don't have a profile in the registry or the Hub
        has a newer profile for this appliance. If we can't contact the Hub raise
        an error if we don't already have profile."""

        if not profile_id:
            if self.profile:
                profile_id = self.profile.profile_id
            else:
                profile_id = detect_profile_id()

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
            new_profile = hub_backups.get_new_profile(profile_id, profile_timestamp)
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

            raise self.CachedProfile("using cached profile because of a Hub error: " + desc)

    def update_profile(self, profile_id=None):
        if profile_id is None:
            # don't attempt to update empty or custom profiles
            if self.profile and \
               (self.profile.profile_id == registry.EMPTY_PROFILE or
                self.profile.profile_id.startswith(registry.CUSTOM_PROFILE + ":")):
                return

        try:
            # look for exact match first
            self._update_profile(profile_id)
        except self.ProfileNotFound as first_exception:
            if profile_id:
                if not re.match(r'^turnkey-', profile_id):
                    profile_id = "turnkey-" + profile_id

                if not TurnKeyVersion.from_string(profile_id).is_complete():
                    completed_profile_id = _complete_profile_id(profile_id)
                    if completed_profile_id:
                        try:
                            self._update_profile(completed_profile_id)
                            return
                        except:
                            pass

            raise first_exception

def _complete_profile_id(partial):
    partial = TurnKeyVersion.from_string(partial)
    system = TurnKeyVersion.from_system()
    if not system:
        return

    if partial.arch is None:
        partial.arch = system.arch

    if partial.release is None or system.release.startswith(partial.release):
        partial.release = system.release

    return str(partial)

class Profile(str):
    def __new__(cls, path, profile_id, timestamp):
        return str.__new__(cls, path)

    def __init__(self, path, profile_id, timestamp):
        str.__init__(self)
        self.path = path
        self.timestamp = timestamp
        self.profile_id = profile_id

class BackupSessionConf(AttrDict):
    def __init__(self, d={}):
        AttrDict.__init__(self, d)
        self.overrides = conf.Limits(self.overrides)

registry = _Registry()

class NotInitialized(hub.Backups.NotInitialized):
    def __init__(self):
        command = "tklbam-init"
        if registry.path != registry.DEFAULT_PATH:
            command = "%s=%s %s" % (registry.ENV_VARNAME, registry.path, command)

        hub.Backups.NotInitialized.__init__(self, 'Hub link required, run "%s" first' % command)

def update_profile(profile_id=None, strict=True):
    import sys
    global registry

    if profile_id == registry.EMPTY_PROFILE:
        print("""
Creating an empty profile, which means:

- We only backup files as included or excluded in the override paths specified
  on the command line or configured in /etc/tklbam/overrides

- We can't detect which files have changed since installation so we will
  indiscriminately backup all files in the included directories.
""")


    if not strict:
        try:
            registry.update_profile(profile_id)
        except:
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
                print("\n" + e.__doc__, file=sys.stderr)

            sys.exit(1)
    os.environ['TKLBAM_PROFILE_ID'] = registry.profile.profile_id

def hub_backups():
    import sys

    try:
        hb = hub.Backups(registry.sub_apikey)
    except hub.Backups.NotInitialized:
        raise NotInitialized()

    return hb
