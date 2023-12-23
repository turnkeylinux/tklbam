#
# Copyright (c) 2010-2015 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
from os.path import isdir, join

import sys
from subprocess import Popen
from typing import Optional, Callable
from dataclasses import dataclass

from squid import Squid

from utils import iamroot

import resource
RLIMIT_NOFILE_MAX = 8192

def _find_duplicity_pylib(path: str) -> Optional[str]:
    if not isdir(path):
        return None

    for fpath, dnames, fnames in os.walk(path):
        if 'duplicity' in dnames:
            return fpath

    return None

PATH_DEPS = os.environ.get('TKLBAM_DEPS', '/usr/lib/tklbam3/deps')
PATH_DEPS_BIN = join(PATH_DEPS, "bin")
PATH_DEPS_PYLIB = _find_duplicity_pylib(PATH_DEPS)

from cmd_internal import fmt_internal_command

class Error(Exception):
    pass

@dataclass
class Creds:
    c_type: str
    accesskey: Optional[str] = None
    secretkey: Optional[str] = None
    producttoken: Optional[str] = None
    usertoken: Optional[str] = None
    sessiontoken: Optional[str] = None

class Duplicity:
    """low-level interface to Duplicity"""

    def __init__(self, opts: list[tuple[str, str]]|str, *args: str):
        """Duplicity command. The first member of args can be a an array of tuple arguments"""

        command: list[str] = []
        if isinstance(opts, str):
            if ' ' in opts:
                raise Error(f"space in opts: '{opts}'")
            command.append(opts)
        else:
            for opt in opts:
                k, v = opt
                command.append(f'--{k}={v}')

        if iamroot():
            command.append('--archive-dir=/var/cache/duplicity')

        if not args:
            raise Error("no arguments!")

        self.command: list[str] = ["duplicity"] + command + list(args)

    def run(self, passphrase: str, creds: Optional[Creds] = None, debug: bool = False) -> None:
        sys.stdout.flush()

        if creds:
            if creds.c_type in ('devpay', 'iamuser'):
                os.environ['AWS_ACCESS_KEY_ID'] = str(creds.accesskey)
                os.environ['AWS_SECRET_ACCESS_KEY'] = str(creds.secretkey)
                os.environ['X_AMZ_SECURITY_TOKEN'] = str(",".join([str(creds.producttoken),
                                                                   str(creds.usertoken)])
                                                         if creds.c_type == 'devpay'
                                                         else str(creds.sessiontoken))

            elif creds.c_type == 'iamrole':
                os.environ['AWS_STSAGENT'] = ' '.join(fmt_internal_command('stsagent'))

        if PATH_DEPS_BIN not in os.environ['PATH'].split(':'):
            os.environ['PATH'] = PATH_DEPS_BIN + ':' + os.environ['PATH']

        if PATH_DEPS_PYLIB:
            pythonpath = os.environ.get('PYTHONPATH')
            pythonpath = ((PATH_DEPS_PYLIB + ':' + pythonpath)
                          if pythonpath else PATH_DEPS_PYLIB)
            os.environ['PYTHONPATH'] = pythonpath

        os.environ['PASSPHRASE'] = passphrase

        if debug:
            print("""
  The --debug option has dropped you into an interactive shell in which you can
  explore the state of the system just before the above duplicity command is
  run, and/or execute it manually.

  For Duplicity usage info, options and storage backends, run "duplicity --help".
  To exit from the shell and continue running duplicity "exit 0".
  To exit from the shell and abort this session "exit 1".
""")

            import subprocess
            shell = [os.environ.get("SHELL", "/bin/bash")]
            if shell == ["/bin/bash"]:
                shell.append("--norc")

            subprocess.run(shell)

        child = Popen(self.command)
        del os.environ['PASSPHRASE']

        exitcode = child.wait()
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))

    def __str__(self) -> str:
        return " ".join(self.command)


def _raise_rlimit(type_: int, newlimit: int) -> None:
    soft, hard = resource.getrlimit(type_)
    if soft > newlimit:
        return None

    if hard > newlimit:
        resource.setrlimit(type_, (newlimit, hard))
        return None

    try:
        resource.setrlimit(type_, (newlimit, newlimit))
    except ValueError:
        pass
    return None

@dataclass
class Target:
    address: str
    credentials: Creds
    secret: str


@dataclass
class Downloader:
    """High-level interface to Duplicity downloads"""

    CACHE_SIZE: str = "50%"
    CACHE_DIR: str = "/var/cache/tklbam3/restore"

    time: Optional[str] = None
    cache_size: str = CACHE_SIZE
    cache_dir: str = CACHE_DIR

    def __call__(self, download_path: str, target: Target, debug: bool = False, log: Optional[Callable] = None, force: bool = False) -> None:
        orig_env = None
        squid = None
        if log is None:
            log = lambda s: None
            assert log is not None

        if self.time:
            opts: list[tuple[str, str]] = [("restore-time", self.time)]
        else:
            opts = []
        if iamroot():
            log(f"// started squid: caching downloaded backup archives to {self.cache_dir}\n")

            squid = Squid(self.cache_size, self.cache_dir)
            squid.start()

            orig_env = os.environ.get('http_proxy')
            if squid.address:
                os.environ['http_proxy'] = squid.address

        _raise_rlimit(resource.RLIMIT_NOFILE, RLIMIT_NOFILE_MAX)
        assert isinstance(target.address, str)
        args = ['--s3-unencrypted-connection', target.address, download_path]
        if force:
            args = ['--force'] + args

        command = Duplicity(opts, *args)

        log(f"# {command}")

        command.run(target.secret, target.credentials, debug=debug)
        assert squid is not None
        if iamroot():
            if orig_env:
                os.environ['http_proxy'] = orig_env
            else:
                del os.environ['http_proxy']

            log("\n// stopping squid: download complete so caching no longer required\n")
            squid.stop()

        sys.stdout.flush()

class Uploader:
    """High-level interface to Duplicity uploads"""

    VOLSIZE: int = 25
    FULL_IF_OLDER_THAN: str = "1M"
    S3_PARALLEL_UPLOADS: int = 1

    verbose: bool = True
    volsize: int = VOLSIZE
    full_if_older_than: str = FULL_IF_OLDER_THAN
    s3_parallel_uploads: int = S3_PARALLEL_UPLOADS
    includes: Optional[list[str]] = None
    include_filelist: Optional[str] = None
    excludes: Optional[list[str]] = None

    def __post_init__(self) -> None:
        if self.includes is None:
            self.includes = []
        if self.excludes is None:
            self.excludes = []

    def __call__(self, source_dir: str, target: Target, force_cleanup: bool = True, dry_run: bool = False, debug: bool = False, log: Optional[Callable] = None):
        if log is None:
            log = lambda s: None
            assert log is not None

        opts: list[tuple[str, str]] = []
        if self.verbose:
            opts.append(('verbosity', '5'))

        if force_cleanup:
            cleanup_command = Duplicity(opts, "cleanup", "--force", target.address)
            log(cleanup_command)

            if not dry_run:
                cleanup_command.run(target.secret, target.credentials)

            log("\n")

        opts += [('volsize', str(self.volsize)),
                 ('full-if-older-than', self.full_if_older_than),
                 ('gpg-options', '--cipher-algo=aes')]

        if self.includes:
            for include in self.includes:
                opts += [ ('include', include) ]

        if self.include_filelist:
            opts += [ ('include-filelist', self.include_filelist) ]

        if self.excludes:
            for exclude in self.excludes:
                opts += [ ('exclude', exclude) ]

        args = [ '--s3-unencrypted-connection', '--allow-source-mismatch' ]

        if dry_run:
            args += [ '--dry-run' ]

        if self.s3_parallel_uploads > 1:
            s3_multipart_chunk_size = self.volsize / self.s3_parallel_uploads
            if s3_multipart_chunk_size < 5:
                s3_multipart_chunk_size = 5
            args += [ '--s3-use-multiprocessing', '--s3-multipart-chunk-size=%d' % s3_multipart_chunk_size ]

        args += [ source_dir, target.address ]

        backup_command = Duplicity(opts, *args)

        log(str(backup_command))
        backup_command.run(target.secret, target.credentials, debug=debug)
        log("\n")
