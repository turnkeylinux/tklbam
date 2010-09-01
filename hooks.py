import os
from os.path import *

import executil

class HookError(Exception):
    pass

class Hooks:
    path = os.environ.get("TKLBAM_HOOKS", "/etc/tklbam/hooks.d")

    def __init__(self, name):
        self.name = name

    def _run(self, state):
        if not isdir(self.path):
            return

        for fname in os.listdir(self.path):
            fpath = join(self.path, fname)
            if not os.access(fpath, os.X_OK):
                continue

            try:
                executil.system(fpath, self.name, state)
            except executil.ExecError, e:
                raise HookError("`%s %s %s` non-zero exitcode (%d)" % \
                                (fpath, self.name, state, e.exitcode))

    def pre(self):
        self._run("pre")

    def post(self):
        self._run("post")

backup = Hooks("backup")
restore = Hooks("restore")
