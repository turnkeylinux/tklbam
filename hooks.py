import os
from os.path import exists, isdir, join
import subprocess
from typing import Optional

from registry import registry

from conf import Conf


class HookError(Exception):
    pass


def _is_signed(fpath: str, keyring: str) -> bool:
    fpath_sig = fpath + ".sig"
    if not exists(fpath_sig):
        return False

    p = subprocess.run(["gpg", f"--keyring={keyring}", "--verify", fpath_sig])
    if p.returncode == 0:
        return True
    else:
        return False


def _run_hooks(path, args, keyring: Optional[str] = None) -> None:
    if not isdir(path):
        return

    for fname in os.listdir(path):
        fpath = join(path, fname)
        if not os.access(fpath, os.X_OK):
            continue

        if fpath.endswith(".sig"):
            continue

        if keyring and not _is_signed(fpath, keyring):
            continue

        p = subprocess.run([fpath, *args])
        if p.returncode != 0:
            raise HookError(f"`{fpath} {' '.join(args)}` non-zero exitcode"
                            f" (p.returncode)")


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
    LOCAL_HOOKS = os.environ.get("TKLBAM_HOOKS", join(Conf.DEFAULT_PATH,
                                                      BASENAME))

    PROFILE_KEYRING = "/etc/apt/trusted.gpg.d/turnkey.gpg"

    def __init__(self, name: str):
        self.name = name

    def _run(self, state: str) -> None:

        _run_hooks(self.LOCAL_HOOKS, (self.name, state))
        if registry.profile:
            _run_hooks(join(registry.profile, self.BASENAME),
                       (self.name, state), keyring=self.PROFILE_KEYRING)

    def pre(self) -> None:
        self._run("pre")

    def post(self) -> None:
        self._run("post")

    def inspect(self, extras_path: str) -> None:
        orig_cwd = os.getcwd()

        os.chdir(extras_path)
        self._run("inspect")
        os.chdir(orig_cwd)


backup = Hooks("backup")
restore = Hooks("restore")
