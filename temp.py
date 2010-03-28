"""
Safely create temporary file or directory which is automatically removed
when the object is dereferenced (by the same process that created it,
not a subprocess)
"""
import os
from os.path import *

import tempfile
import shutil

class TempFile(file):
    def __init__(self, prefix='tmp', suffix=''):
        fd, path = tempfile.mkstemp(suffix, prefix)
        os.close(fd)
        self.path = path
        self.pid = os.getpid()
        file.__init__(self, path, "w")

    def __del__(self):
        # sanity check in case we use fork somewhere
        if self.pid == os.getpid():
            os.remove(self.path)

class TempDir(str):
    def __new__(cls, prefix='tmp', suffix='', dir=None):
        path = tempfile.mkdtemp(suffix, prefix, dir)
        self = str.__new__(cls, path)

        self.pid = os.getpid()
        self.path = path
        return self

    def remove(self):
        if exists(self):
            shutil.rmtree(self)

    def __del__(self):
        if self.pid == os.getpid():
            self.remove()

