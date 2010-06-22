from os.path import *
import os
import struct
import base64
from hashlib import sha1 as sha
from paths import Paths
import pickle

class Error(Exception):
    pass

class APIKey:
    def __init__(self, apikey):
        apikey = str(apikey)
        self.encoded = apikey
        
        padded = "A" * (16 - len(apikey)) + apikey
        uid, secret = struct.unpack("!L8s", base64.b64decode(padded))

        self.uid = uid
        self.secret = secret

    @classmethod
    def generate(cls, uid, secret=None):
        if secret is None:
            secret = os.urandom(8)
        else:
            secret = sha(secret).digest()[:8]

        packed = struct.pack("!L8s", uid, secret)
        encoded = base64.b64encode(packed).lstrip("A")

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

class AttrDict(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError("no such attribute '%s'" % name)

    def __setattr__(self, name, val):
        self[name] = val

class DummyUser(AttrDict):
    def __init__(self, uid, apikey):
        self.uid = uid
        self.apikey = apikey
        self.credentials = None

    def subscribe(self):
        accesskey = base64.b64encode(sha("%d" % self.uid).digest())[:20]
        secretkey = base64.b64encode(os.urandom(30))[:40]

        self.credentials = accesskey, secretkey

    def unsubscribe(self):
        self.credentials = None

class _DummyDB:
    class Paths(Paths):
        files = ['users']

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

dummydb = _DummyDB("/tmp/db")

class Backups:
    Error = Error
    SUBKEY_NS = "tklbam"

    @classmethod
    def get_subkey(cls, apikey):
        """Check that APIKey is valid and return subkey"""
        apikey = APIKey(apikey)
        user = dummydb.get_user(apikey.uid)

        if not user or user.apikey != apikey:
            raise Error("invalid APIKey: %s" % apikey)

        return apikey.subkey(cls.SUBKEY_NS)

    def __init__(self, subkey):
        subkey = APIKey(subkey)

        user = dummydb.get_user(subkey.uid)
        if not user or subkey != user.apikey.subkey(self.SUBKEY_NS):
            raise Error("invalid authentication subkey: %s" % subkey)

        self.user = user

    def get_credentials(self):
        if not self.user.credentials:
            raise Error("user not subscribed to Backups")

        return self.user.credentials
