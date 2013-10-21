#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
from os.path import *

import sys

from subprocess import *
from squid import Squid

from utils import AttrDict

import resource
RLIMIT_NOFILE_MAX = 8192

def _find_duplicity_pylib(path):
    if not isdir(path):
        return None

    for fpath, dnames, fnames in os.walk(path):
        if 'duplicity' in dnames:
            return fpath

    return None

PATH_DEPS = os.environ.get('TKLBAM_DEPS', '/usr/lib/tklbam/deps')
PATH_DEPS_BIN = join(PATH_DEPS, "bin")
PATH_DEPS_PYLIB = _find_duplicity_pylib(PATH_DEPS)

class Error(Exception):
    pass

class Duplicity:
    """low-level interface to Duplicity"""

    def __init__(self, *args):
        """Duplicity command. The first member of args can be a an array of tuple arguments"""

        if isinstance(args[0], list):
            opts = args[0][:]
            args = args[1:]
        else:
            opts = []

        if not args:
            raise Error("no arguments!")

        opts += [ ('archive-dir', '/var/cache/duplicity') ]

        opts = [ "--%s=%s" % (key, val) for key, val in opts ]
        self.command = ["duplicity"] + opts + list(args)

    def run(self, passphrase, creds=None, debug=False):
        sys.stdout.flush()

        if creds:
            os.environ['AWS_ACCESS_KEY_ID'] = creds.accesskey
            os.environ['AWS_SECRET_ACCESS_KEY'] = creds.secretkey
            os.environ['X_AMZ_SECURITY_TOKEN'] = ",".join([creds.producttoken, creds.usertoken])

        if PATH_DEPS_BIN not in os.environ['PATH'].split(':'):
            os.environ['PATH'] = PATH_DEPS_BIN + ':' + os.environ['PATH']

        if PATH_DEPS_PYLIB:
            os.environ['PYTHONPATH'] = PATH_DEPS_PYLIB

        os.environ['PASSPHRASE'] = passphrase

        if debug:
            import executil
            shell = os.environ.get("SHELL", "/bin/bash")
            if shell == "/bin/bash":
                shell += " --norc"
            executil.system(shell)

        child = Popen(self.command)
        del os.environ['PASSPHRASE']

        exitcode = child.wait()
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))

    def __str__(self):
        return " ".join(self.command)


def _raise_rlimit(type, newlimit):
    soft, hard = resource.getrlimit(type)
    if soft > newlimit:
        return

    if hard > newlimit:
        return resource.setrlimit(type, (newlimit, hard))

    try:
        resource.setrlimit(type, (newlimit, newlimit))
    except ValueError:
        return

class Target(AttrDict):
    def __init__(self, address, credentials, secret):
        AttrDict.__init__(self)
        self.address = address
        self.credentials = credentials
        self.secret = secret

class Downloader(AttrDict):
    """High-level interface to Duplicity downloads"""

    CACHE_SIZE = "50%"
    CACHE_DIR = "/var/cache/tklbam/restore"

    def __init__(self, time=None, cache_size=CACHE_SIZE, cache_dir=CACHE_DIR):
        AttrDict.__init__(self)

        self.time = time
        self.cache_size = cache_size
        self.cache_dir = cache_dir

    def __call__(self, download_path, target):
        if self.time:
            opts = [("restore-time", self.time)]
        else:
            opts = []

        squid = Squid(self.cache_size, self.cache_dir)
        squid.start()

        orig_env = os.environ.get('http_proxy')
        os.environ['http_proxy'] = squid.address

        _raise_rlimit(resource.RLIMIT_NOFILE, RLIMIT_NOFILE_MAX)
        Duplicity(opts, '--s3-unencrypted-connection', target.address, download_path).run(target.secret, target.credentials)

        if orig_env:
            os.environ['http_proxy'] = orig_env
        else:
            del os.environ['http_proxy']

        sys.stdout.flush()

        squid.stop()

class Uploader(AttrDict):
    """High-level interface to Duplicity uploads"""

    VOLSIZE = 25
    FULL_IF_OLDER_THAN = "1M"
    S3_PARALLEL_UPLOADS = 1

    def __init__(self, 
                 verbose=True,
                 volsize=VOLSIZE, 
                 full_if_older_than=FULL_IF_OLDER_THAN,
                 s3_parallel_uploads=S3_PARALLEL_UPLOADS, 

                 includes=[], 
                 include_filelist=None,
                 excludes=[],
                 ):

        AttrDict.__init__(self)

        self.verbose = verbose
        self.volsize = volsize
        self.full_if_older_than = full_if_older_than
        self.s3_parallel_uploads = s3_parallel_uploads

        self.includes = includes
        self.include_filelist = include_filelist
        self.excludes = excludes

    def __call__(self, source_dir, target, force_cleanup=True, dry_run=False, debug=False, log=None):
        if log is None:
            log = lambda s: None

        opts = []
        if self.verbose:
            opts += [('verbosity', 5)]

        if force_cleanup:
            cleanup_command = Duplicity(opts, "cleanup", "--force", target.address)
            log(cleanup_command)

            if not dry_run:
                cleanup_command.run(target.secret, target.credentials)

            log("\n")

        opts += [('volsize', self.volsize),
                 ('full-if-older-than', self.full_if_older_than),
                 ('gpg-options', '--cipher-algo=aes')]

        for include in self.includes:
            opts += [ ('include', include) ]

        if self.include_filelist:
            opts += [ ('include-filelist', self.include_filelist) ]

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
