# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
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

def _fmt_s3_headers(product, user):
    return "x-amz-security-token=" + ",".join([product,user])

class Command:
    def __init__(self, *args):
        """Duplicity command. The first member of args can be a an array of tuple arguments"""

        if isinstance(args[0], list):
            opts = args[0]
            args = args[1:]
        else:
            opts = []

        if not args:
            raise Error("no arguments!")

        opts += [ ('archive-dir', '/var/cache/duplicity') ]

        opts = [ "--%s=%s" % (key, val) for key, val in opts ]
        self.command = ["duplicity"] + opts + list(args)

    def run(self, passphrase, creds=None):
        sys.stdout.flush()

        if creds:
            os.environ['AWS_ACCESS_KEY_ID'] = creds.accesskey
            os.environ['AWS_SECRET_ACCESS_KEY'] = creds.secretkey

            s3_headers = _fmt_s3_headers(creds.producttoken, 
                                         creds.usertoken)
            os.environ['AWS_S3_HEADERS'] = s3_headers

        if PATH_DEPS_BIN not in os.environ['PATH'].split(':'):
            os.environ['PATH'] = PATH_DEPS_BIN + ':' + os.environ['PATH']

        if PATH_DEPS_PYLIB:
            os.environ['PYTHONPATH'] = PATH_DEPS_PYLIB

        os.environ['PASSPHRASE'] = passphrase
        child = Popen(self.command)
        del os.environ['PASSPHRASE']

        exitcode = child.wait()
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))
        
    def __str__(self):
        return " ".join(self.command)
