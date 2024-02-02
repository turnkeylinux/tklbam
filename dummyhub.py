import os
from os.path import exists, join

import re
import struct
import base64
from hashlib import sha1 as sha
from paths import Paths
import pickle
import glob
from datetime import datetime
from typing import Optional, Self, Any
from dataclasses import dataclass

from hub import Credentials, ProfileArchive
from hub import Error, NotSubscribed, InvalidBackupError


@dataclass
class APIKey(dict):
    apikey: str
    credentials: Optional[Credentials] = None

    def __post_init__(self) -> None:
        apikey = str(self.apikey)
        self.encoded = apikey

        padded = "A" * (20 - len(apikey)) + apikey
        try:
            uid, secret = struct.unpack("!L8s",
                                        base64.b32decode(padded + "=" * 4))
        except TypeError:
            raise Error("Invalid characters in API-KEY")

        self.uid = uid
        self.secret = secret

    @classmethod
    def generate(cls, uid: str, secret: Optional[bytes] = None) -> Self:
        if secret is None:
            secret = os.urandom(8)
        else:
            secret = sha(secret).digest()[:8]

        packed = struct.pack("!L8s", uid, secret)
        encoded = base64.b32encode(packed).lstrip(b"A").rstrip(b"=")

        return cls(encoded.decode())

    def subkey(self, namespace: str) -> Self:
        return self.generate(self.uid, namespace + self.secret)

    def __str__(self) -> str:
        return self.encoded

    def __repr__(self) -> str:
        return "APIKey(%s)" % repr(str(self))

    def __eq__(self, other: object | Self) -> bool:
        # a bit of typing hackery - to avoid 'supertype defines the argument
        # type as "object"'
        if hasattr(other, 'encoded'):
            assert isinstance(other, type(self))
            return self.encoded == other.encoded
        return False

    def __ne__(self, other: object | Self) -> bool:
        return not self.__eq__(other)


@dataclass
class DummyBackupRecord(dict):
    # backup_id, address
    backup_id: str
    address: str
    key: str
    profile_id: str
    server_id: Optional[str]

    # backup_id, address
    def __post_init__(self) -> None:

        self.created = datetime.now()
        self.updated: Optional[datetime] = None

        # in MBs
        self.size = 0
        self.label = "TurnKey Backup"

        # no user interface for this in the dummy hub
        self.sessions: list[Self] = []

    def update(self, **kwargs: Any) -> None:
        # kwargs not actually used - more type hacking - to avoid "update"
        # incompatible with supertype
        self.updated = datetime.now()

        path = self.address[len("file://"):]

        self.sessions = _parse_duplicity_sessions(path)
        self.size = sum([session.size for session in self.sessions])


@dataclass
class DummyUser:
    uid: str
    apikey: APIKey

    def __post_init__(self):
        self.credentials = None
        self.backups = DummyBackupRecord('', '', '', '', '')
        self.backups_max = 0

    def subscribe(self) -> None:
        accesskey = base64.b64encode(sha(b"%d" % self.uid).digest())[:20]
        secretkey = base64.b64encode(os.urandom(30))[:40]
        producttoken = (b"{ProductToken}"
                        + base64.b64encode(b"\x00"
                                           + os.urandom(2)
                                           + b"AppTkn"
                                           + os.urandom(224)))
        usertoken = (b"{UserToken}" + base64.b64encode(b"\x00"
                                                       + os.urandom(2)
                                                       + b"UserTkn"
                                                       + os.urandom(288)))

        self.credentials = Credentials({'accesskey': accesskey,
                                        'secretkey': secretkey,
                                        'producttoken': producttoken,
                                        'usertoken': usertoken})

    def unsubscribe(self) -> None:
        self.credentials = None

    def new_backup(self, address: str, key: str, profile_id: str,
                   server_id: Optional[str] = None
                   ) -> DummyBackupRecord:
        self.backups_max += 1

        id = str(self.backups_max)
        backup_record = DummyBackupRecord(id, address, key,
                                          profile_id, server_id)

        self.backups[id] = backup_record

        return backup_record


class DuplicityFile:
    @classmethod
    def from_fname(cls, fname: str) -> Optional[Self]:
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
            timestamp = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return None

        return cls(type, timestamp)

    def __init__(self, type_: str, timestamp: datetime) -> None:
        self.type = type_
        self.timestamp = timestamp


class DummySession:
    def __init__(self, type_: str, timestamp: datetime, size: int = 0):
        self.type = type_
        self.timestamp = timestamp
        self.size = size


def _parse_duplicity_sessions(path: str) -> list[DummyBackupRecord]:
    sessions = {}
    for fname in os.listdir(path):
        fpath = join(path, fname)
        fsize = os.stat(fpath).st_size

        df = DuplicityFile.from_fname(fname)
        if not df:
            continue

        if df.timestamp not in sessions:
            sessions[df.timestamp] = DummySession(df.type, df.timestamp, fsize)
        else:
            sessions[df.timestamp].size += fsize

    return list(sessions.values())


class _DummyDB:
    users: APIKey

    class Paths(Paths):
        files = ['users', 'profiles']

    @staticmethod
    def _save(path: str, obj: Optional[APIKey]) -> None:
        if isinstance(obj, str):
            with open(path, "wb") as fob:
                pickle.dump(obj, fob)

    @staticmethod
    def _load(path: str, default: Optional[APIKey] = None) -> APIKey:
        if default is None:
            default = APIKey('')
        if not exists(path):
            return default

        try:
            with open(path, 'rb') as fob:
                return pickle.load(fob)
        except:  # TODO don't use bare except
            return default

    def save(self) -> None:
        self._save(self.path.users, self.users)

    def load(self) -> None:
        self.users = self._load(self.path.users, APIKey(''))

    def __init__(self, path: str) -> None:
        if not exists(path):
            os.makedirs(path)

        self.path = self.Paths(path)
        self.load()

    def get_user(self, uid: str) -> Optional[APIKey]:
        if self.users:
            if uid not in self.users.keys():
                return None
        else:
            return None
        return self.users[uid]

    def add_user(self):
        if self.users:
            uid = int(max(self.users.keys())) + 1
        else:
            uid = 1

        apikey = APIKey.generate(str(uid))

        user = DummyUser(str(uid), apikey)
        self.users[uid] = user

        return user

    def get_profile(self, profile_id):
        matches = glob.glob(f"{self.path.profiles}/{profile_id}.tar.*")
        if not matches:
            return None

        return matches[0]


try:
    dummydb: _DummyDB
except NameError:
    dummydb = _DummyDB("/var/tmp/tklbam3/dummyhub")


class DummyProfileArchive(ProfileArchive):
    def __del__(self):
        pass


class Backups:
    # For simplicity's sake this implements a dummy version of both
    # client-side and server-side operations.
    #
    # When translating to a real implementation the interface should remain
    # but the implementation will change completely as only client-side
    # operations remain.

    Error = Error

    class NotInitialized(Error):
        pass

    SUBKEY_NS = "tklbam"

    @classmethod
    def get_sub_apikey(cls, apikey: str) -> APIKey:
        """Check that APIKey is valid and return subkey"""
        apikey_ = APIKey(apikey)
        user = dummydb.get_user(apikey_.uid)

        if not user or user.apikey != apikey_:
            raise Error(f"invalid APIKey: {apikey}")

        return apikey_.subkey(cls.SUBKEY_NS)

    def __init__(self, subkey):
        if subkey is None:
            raise self.NotInitialized("no APIKEY - tklbam not linked to the"
                                      " Hub")

        subkey_ = APIKey(subkey)

        # the non-dummy implementation should only check the subkey when an
        # action is performed. (I.e., NOT on initialization). In a REST API
        # the subkey should probably be passed as an authentication header.

        user = dummydb.get_user(subkey_.uid)
        if (not user
            or (not isinstance(user.apikey, str)
                and subkey_ != user.apikey.subkey(self.SUBKEY_NS)
                )):
            raise Error("invalid authentication subkey: %s" % subkey)

        self.user = user

    def get_credentials(self):
        if not self.user.credentials:
            raise NotSubscribed()

        return self.user.credentials

    def update_key(self, backup_id, key):
        self.get_backup_record(backup_id).key = key
        dummydb.save()

    def get_new_profile(self, profile_id, profile_timestamp):
        """
        Gets a profile for <profile_id> that is newer than <profile_timestamp>.

        If there's a new profile, returns a DummyProfileArchive instance.
        Otherwise returns None.

        Raises an exception if no profile exists for profile_id.
        """

        if not self.user.credentials:
            raise NotSubscribed()

        archive = dummydb.get_profile(profile_id)
        if not archive:
            raise Error(404, 'BackupArchive.NotFound',
                        'Backup profile archive not found: ' + profile_id)

        archive_timestamp = int(os.stat(archive).st_mtime)
        if profile_timestamp and profile_timestamp >= archive_timestamp:
            return None

        return DummyProfileArchive(profile_id, archive, archive_timestamp)

    def new_backup_record(self, key: str, profile_id: str,
                          server_id: Optional[str] = None
                          ) -> str:
        # in the real implementation the hub would create a bucket not a dir...
        # the real implementation would have to make sure this is unique
        path = b"/var/tmp/duplicity/" + base64.b32encode(os.urandom(10))
        os.makedirs(path.decode())
        address = "file://" + path.decode()

        backup_record = self.user.new_backup(address, key,
                                             profile_id, server_id)

        dummydb.save()

        return backup_record

    def get_backup_record(self, backup_id):
        if backup_id not in self.user.backups:
            raise InvalidBackupError("no such backup (%s)" % backup_id)

        return self.user.backups[backup_id]

    def list_backups(self):
        backups = list(self.user.backups.values())
        # XXX below needs fixing!!!
        return sorted(list(self.user.backups.values()),
                      lambda a,b: cmp(int(a.backup_id), int(b.backup_id)))

    def updated_backup(self, address):
        # In the real implementation this should add a task which queries S3
        # with the user's credentials and updates the Hub database (e.g., size,
        # data on backup sessions, etc.)

        for backup in list(self.user.backups.values()):
            if address == backup.address:
                backup.update()
                dummydb.save()
                return

    def set_backup_inprogress(self, backup_id, bool):
        pass
