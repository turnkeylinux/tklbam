import sys
import os
from os.path import *
from paths import Paths

class Registry(object):
    class Paths(Paths):
        files = ['key', 'sub_apikey', 'secret', 'credentials']

    def __init__(self, path=None):
        if path is None:
            path = os.environ.get('TKLBAM_REGISTRY', '/var/lib/tklbam')

        if not exists(path):
            os.makedirs(path)
            os.chmod(path, 0700)

        self.path = self.Paths(path)

    @staticmethod
    def _file_str(path, s):
        if s is None:
            if not exists(path):
                return None

            return file(path).read().rstrip()

        else:
            fh = file(path, "w")
            os.chmod(path, 0600)
            print >> fh, s
            fh.close()

    @classmethod
    def _file_tuple(cls, path, t):
        t = "\n".join([ str(v) for v in t ]) if t else None
        retval = cls._file_str(path, t)
        if retval:
            return tuple(retval.split('\n'))

    def sub_apikey(self, val=None):
        return self._file_str(self.path.sub_apikey, val)
    sub_apikey = property(sub_apikey, sub_apikey)

    def secret(self, val=None):
        return self._file_str(self.path.secret, val)
    secret = property(secret, secret)

    def key(self, val=None):
        return self._(self.path.key, val)
    key = property(key, key)

    def credentials(self, val=None):
        return self._file_tuple(self.path.credentials, val)
    credentials = property(credentials, credentials)
    
registry = Registry()
