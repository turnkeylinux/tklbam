import os
from os.path import *

import executil

class HookError(Exception):
    pass

class Hooks:
    """
    Backup hook invocation:

        pre hook
        create extras
        inspect hook
        run duplicity to create/update backup archives
        post hook

    Restore hook invocation:
        
        pre hook
        run duplicity to get extras + overlay
        inspect hook
        apply restore to system
        post hook

    """
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

    def inspect(self, extras_path):
        orig_cwd = os.getcwd()

        os.chdir(extras_path)
        self._run("inspect")
        os.chdir(orig_cwd)

backup = Hooks("backup")
restore = Hooks("restore")
