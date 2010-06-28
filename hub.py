import os
from os.path import *

import re
import struct
import base64
from hashlib import sha1 as sha
from paths import Paths
import pickle
import glob
from datetime import datetime

import executil
from utils import AttrDict

class Error(Exception):
    pass

class NotSubscribedError(Error):
    pass

class InvalidBackupError(Error):
    pass

class APIKey:
    def __init__(self, apikey):
        apikey = str(apikey)
        self.encoded = apikey
        
        padded = "A" * (20 - len(apikey)) + apikey
        try:
            uid, secret = struct.unpack("!L8s", base64.b32decode(padded + "=" * 4))
        except TypeError:
            raise Error("Invalid characters in API-KEY")

        self.uid = uid
        self.secret = secret

    @classmethod
    def generate(cls, uid, secret=None):
        if secret is None:
            secret = os.urandom(8)
        else:
            secret = sha(secret).digest()[:8]

        packed = struct.pack("!L8s", uid, secret)
        encoded = base64.b32encode(packed).lstrip("A").rstrip("=")

        return cls(encoded)

    def subkey(self, namespace):
        return self.generate(self.uid, namespace + self.secret)

    def __str__(self):
        return self.encoded

    def __repr__(self):
        return "APIKey(%s)" % `str(self)`

    def __eq__(self, other):
        return self.encoded == other.encoded

    def __ne__(self, other):
        return not self.__eq__(other)

class DummyUser(AttrDict):
    def __init__(self, uid, apikey):
        self.uid = uid
        self.apikey = apikey
        self.credentials = None
        self.backups = {}
        self.backups_max = 0

    def subscribe(self):
        accesskey = base64.b64encode(sha("%d" % self.uid).digest())[:20]
        secretkey = base64.b64encode(os.urandom(30))[:40]

        self.credentials = accesskey, secretkey

    def unsubscribe(self):
        self.credentials = None

    def new_backup(self, address, key, turnkey_version, server_id=None):
        self.backups_max += 1

        id = str(self.backups_max)
        backup_record = DummyBackupRecord(id, address, key, \
                                          turnkey_version, server_id)

        self.backups[id] = backup_record

        return backup_record

class DuplicityFile(AttrDict):
    @classmethod
    def from_fname(cls, fname):
        m = re.match(r'duplicity-(.*?)\.(.*?).(?:sigtar|vol.*difftar)', fname)
        if not m:
            return None

        type, timestamp = m.groups()
        m = re.search(r'to\.(.*)', timestamp)
        if m:
            timestamp, = m.groups()

        if 'full' in type:
            type = 'full'
        else:
            type = 'inc'

        try:
            timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return

        return cls(type, timestamp)

    def __init__(self, type, timestamp):
        self.type = type
        self.timestamp = timestamp

class DummySession(AttrDict):
    def __init__(self, type, timestamp, size=0):
        self.type = type
        self.timestamp = timestamp
        self.size = size

def _parse_duplicity_sessions(path):
    sessions = {}
    for fname in os.listdir(path):
        fpath = join(path, fname)
        fsize = os.stat(fpath).st_size

        df = DuplicityFile.from_fname(fname)
        if not df:
            continue

        if not df.timestamp in sessions:
            sessions[df.timestamp] = DummySession(df.type, df.timestamp, fsize)
        else:
            sessions[df.timestamp].size += fsize

    return sessions.values()

class DummyBackupRecord(AttrDict):
    # backup_id, address
    def __init__(self, backup_id, address, key, turnkey_version, server_id):
        self.backup_id = backup_id
        self.address = address
        self.key = key
        self.turnkey_version = turnkey_version
        self.server_id = server_id

        self.created = datetime.now()
        self.updated = None

        # in MBs
        self.size = 0
        self.label = "TurnKey Backup"

        # no user interface for this in the dummy hub
        self.sessions = []

    def update(self):
        self.updated = datetime.now()

        path = self.address[len("file://"):] 

        self.sessions = _parse_duplicity_sessions(path)
        self.size = sum([ session.size for session in self.sessions ]) / (1024 * 1024)

class _DummyDB:
    class Paths(Paths):
        files = ['users', 'profiles']

    @staticmethod
    def _save(path, obj):
        pickle.dump(obj, file(path, "w"))

    @staticmethod
    def _load(path, default=None):
        if not exists(path):
            return default

        return pickle.load(file(path))

    def save(self):
        self._save(self.path.users, self.users)

    def load(self):
        self.users = self._load(self.path.users, {})

    def __init__(self, path):
        if not exists(path):
            os.makedirs(path)

        self.path = self.Paths(path)
        self.load()

    def get_user(self, uid):
        if uid not in self.users:
            return None

        return self.users[uid]

    def add_user(self):
        if self.users:
            uid = max(self.users.keys()) + 1
        else:
            uid = 1

        apikey = APIKey.generate(uid)

        user = DummyUser(uid, apikey)
        self.users[uid] = user

        return user


    def get_profile(self, turnkey_version):
        matches = glob.glob("%s/%s.tar.*" % (self.path.profiles, turnkey_version))
        if not matches:
            return None

        return matches[0]

dummydb = _DummyDB("/var/tmp/tklbam/db")

class Backups:
    # For simplicity's sake this implements a dummy version of both
    # client-side and server-side operations.
    # 
    # When translating to a real implementation the interface should remain
    # but the implementation will change completely as only client-side
    # operations remain.

    Error = Error
    SUBKEY_NS = "tklbam"

    @classmethod
    def get_sub_apikey(cls, apikey):
        """Check that APIKey is valid and return subkey"""
        apikey = APIKey(apikey)
        user = dummydb.get_user(apikey.uid)

        if not user or user.apikey != apikey:
            raise Error("invalid APIKey: %s" % apikey)

        return apikey.subkey(cls.SUBKEY_NS)

    def __init__(self, subkey):
        if subkey is None:
            raise Error("no APIKEY - tklbam not initialized")

        subkey = APIKey(subkey)

        # the non-dummy implementation should only check the subkey when an
        # action is performed. (I.e., NOT on initialization). In a REST API
        # the subkey should probably be passed as an authentication header.

        user = dummydb.get_user(subkey.uid)
        if not user or subkey != user.apikey.subkey(self.SUBKEY_NS):
            raise Error("invalid authentication subkey: %s" % subkey)

        self.user = user

    def get_credentials(self):
        if not self.user.credentials:
            raise NotSubscribedError("user not subscribed to Backups")

        return self.user.credentials

    def update_key(self, backup_id, key):
        self.get_backup_record(backup_id).key = key
        dummydb.save()

    def get_new_profile(self, turnkey_version, profile_timestamp):
        """
        Gets a profile for <turnkey_version> that is newer than <profile_timestamp>.

        If there's a new profile, returns a ProfileArchive instance.
        Otherwise returns None.

        Raises an exception if no profile exists for turnkey_version.
        """

        archive = dummydb.get_profile(turnkey_version)
        if not archive:
            raise Error("no profile exists for turnkey_version '%s'" % turnkey_version)

        archive_timestamp = os.stat(archive).st_mtime
        if profile_timestamp and profile_timestamp >= archive_timestamp:
            return None

        return ProfileArchive(archive, archive_timestamp)

    def new_backup_record(self, key, turnkey_version, server_id=None):
        # in the real implementation the hub would create a bucket not a dir...
        # the real implementation would have to make sure this is unique
        path = "/var/tmp/duplicity/" + base64.b32encode(os.urandom(10))
        os.makedirs(path)
        address = "file://" + path

        backup_record = self.user.new_backup(address, key, 
                                             turnkey_version, server_id)

        dummydb.save()

        return backup_record

    def get_backup_record(self, backup_id):
        if backup_id not in self.user.backups:
            raise InvalidBackupError("no such backup (%s)" % backup_id)

        return self.user.backups[backup_id]

    def list_backups(self):
        return self.user.backups.values()

    def updated_backup(self, address):
        # In the real implementation this should add a task which queries S3
        # with the user's credentials and updates the Hub database (e.g., size,
        # data on backup sessions, etc.)

        for backup in self.user.backups.values():
            if address == backup.address:
                backup.update()
                dummydb.save()
                return

class ProfileArchive:
    def __init__(self, archive, timestamp):
        self.path_archive = archive
        self.timestamp = timestamp

    def extract(self, path):
        executil.system("tar -xf %s -C %s" % (self.path_archive, path))
