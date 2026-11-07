import os
import subprocess
from os.path import *

from pylib import executil
from registry import registry

from conf import Conf

class HookError(Exception):
    pass

def _hook_paths(path):
    if not isdir(path):
        return []
    return [join(path, name) for name in os.listdir(path)
            if not name.endswith(".sig") and isfile(join(path, name))
            and os.access(join(path, name), os.X_OK)]


def _verify_profile_hooks(paths, keyring):
    # An empty profile must not require GPG or a keyring.
    if not paths:
        return
    if not isfile(keyring) or not os.access(keyring, os.R_OK):
        raise HookError("Profile verification keyring is missing or unreadable: %s; "
                        "reinstall the tklbam package before retrying" % keyring)
    for fpath in paths:
        signature = fpath + ".sig"
        if not isfile(signature):
            raise HookError("Missing signature for profile hook %s; "
                            "restore the authentic backup profile before retrying" % fpath)
        try:
            # gpgv accepts only this packaged trust ring. Its home is also
            # explicit, so root's default keyring/configuration is irrelevant.
            process = subprocess.Popen(
                ["gpgv", "--homedir", dirname(keyring), "--keyring", keyring,
                 "--", signature, fpath],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, error = process.communicate()
        except OSError as e:
            raise HookError("Cannot verify profile hook %s: %s; "
                            "reinstall tklbam and gpgv before retrying" % (fpath, e))
        if process.returncode:
            raise HookError("Signature verification failed for profile hook %s "
                            "with %s: %s; restore the authentic profile and packaged "
                            "verification keyring before retrying" %
                            (fpath, keyring, error.decode("utf-8", "replace").strip()))


def _run_hooks(paths, args):
    for fpath in paths:
        try:
            executil.system(fpath, *args)
        except executil.ExecError as e:
            raise HookError("`%s %s` non-zero exitcode (%d)" % \
                            (fpath, " ".join(args), e.exitcode))

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
    BASENAME = "hooks.d"
    LOCAL_HOOKS = os.environ.get("TKLBAM_HOOKS", join(Conf.DEFAULT_PATH, BASENAME))

    PROFILE_KEYRING = "/usr/share/tklbam/profile-keyring.gpg"

    def __init__(self, name):
        self.name = name

    def _run(self, state):

        profile_hooks = _hook_paths(join(registry.profile, self.BASENAME)) if registry.profile else []
        # Verify every profile hook before any local or profile hook has effects.
        _verify_profile_hooks(profile_hooks, self.PROFILE_KEYRING)
        _run_hooks(_hook_paths(self.LOCAL_HOOKS), (self.name, state))
        _run_hooks(profile_hooks, (self.name, state))

    def pre(self):
        self._run("pre")

    def post(self):
        self._run("post")

    def inspect(self, extras_path):
        orig_cwd = os.getcwd()

        os.chdir(extras_path)
        try:
            self._run("inspect")
        finally:
            os.chdir(orig_cwd)

backup = Hooks("backup")
restore = Hooks("restore")
