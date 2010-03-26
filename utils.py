import sys
import os
from os.path import *

import tempfile
import shutil

from stdtrap import UnitedStdTrap

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
        self = str.__new__(cls, path)
        self.pid = os.getpid()

        return self

    def remove(self):
        if exists(self):
            shutil.rmtree(self)

    def __del__(self):
        if self.pid == os.getpid():
            self.remove()

def system(command, transparent=None):
    """Run a command and intercept its output 
       Returns: (status, output)

    Arguments:
    <command>       Command to pass to os.system()
    <transparent>   Allow output to reach stdout "transparently"?
                    By default: True if stdout is a tty, False otherwise
    """
    if transparent is None:
        if os.isatty(sys.stdout.fileno()):
            transparent = True
        else:
            transparent = False

    trap = UnitedStdTrap(transparent=transparent)
    try:
        status = os.system(command)
    finally:
        trap.close()
    output = trap.std.read()

    return status, output

