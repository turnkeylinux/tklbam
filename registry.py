import sys
import os
from os.path import *
from paths import Paths

from utils import AttrDict

class _Registry(object):
    class Paths(Paths):
        files = ['sub_apikey', 'secret', 'key', 'credentials', 'hbr']

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
        t = "\n".join([ str(v) for v in t ]) \
            if t else None

        retval = cls._file_str(path, t)
        if retval:
            return tuple(retval.split('\n'))

    @classmethod
    def _file_dict(cls, path, d):
        d = "\n".join([ "%s\t%s" % (k, v) for k, v in d.items() ]) \
            if d else None

        retval = cls._file_str(path, d)
        if retval:
            return AttrDict([ v.split("\t", 1) for v in retval.split("\n") ])

    def sub_apikey(self, val=None):
        return self._file_str(self.path.sub_apikey, val)
    sub_apikey = property(sub_apikey, sub_apikey)

    def secret(self, val=None):
        return self._file_str(self.path.secret, val)
    secret = property(secret, secret)

    def key(self, val=None):
        return self._file_str(self.path.key, val)
    key = property(key, key)

    def credentials(self, val=None):
        return self._file_tuple(self.path.credentials, val)
    credentials = property(credentials, credentials)
    
    def hbr(self, val=None):
        return self._file_dict(self.path.hbr, val)
    hbr = property(hbr, hbr)

registry = _Registry("/tmp/registry")
