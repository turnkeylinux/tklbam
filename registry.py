import sys
import os
from os.path import *
from paths import Paths

class _Registry(object):
    class Paths(Paths):
        files = ['subkey', 'secret', 'credentials']

    def __init__(self, path=None):
        if path is None:
            path = os.environ.get('TKLBAM_REGISTRY', '/var/lib/tklbam')

        if not exists(path):
            os.makedirs(path)
            os.chmod(path, 0700)

        self.path = self.Paths(path)

    @staticmethod
    def _fileval(path, val):
        if val is None:
            if not exists(path):
                return None

            return file(path).read().rstrip()

        else:
            fh = file(path, "w")
            os.chmod(path, 0600)
            print >> fh, val
            fh.close()

    def subkey(self, val=None):
        return self._fileval(self.path.subkey, val)
    subkey = property(subkey, subkey)

    def secret(self, val=None):
        return self._fileval(self.path.secret, val)
    secret = property(secret, secret)

    def credentials(self, val=None):
        if val:
            val = val[0] + "\n" + val[1]

        retval = self._fileval(self.path.credentials, val)

        if retval:
            return tuple(retval.split('\n'))

    credentials = property(credentials, credentials)
    
registry = _Registry()
