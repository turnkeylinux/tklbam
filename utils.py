import os
from os.path import *
import shutil

def remove_any(path):
    """Remove a path whether it is a file or a directory. 
       Return: True if removed, False if nothing to remove"""

    if not lexists(path):
        return False

    if not islink(path) and isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

    return True

class TempDir(str):
    def __new__(cls, prefix='tmp', suffix='', dir=None):
        path = tempfile.mkdtemp(suffix, prefix, dir)
        return str.__new__(cls, path)

    def __del__(self):
        shutil.rmtree(self)

