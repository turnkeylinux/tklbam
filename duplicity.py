# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
import os
import sys

from subprocess import *

class Error(Exception):
    pass

def fmt_s3_headers(product, user):
    product = "{ProductToken}" + product
    user = "{UserToken}" + user
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

            s3_headers = fmt_s3_headers(creds.producttoken, 
                                        creds.usertoken)
            os.environ['AWS_S3_HEADERS'] = s3_headers

        os.environ['PASSPHRASE'] = passphrase
        child = Popen(self.command)
        del os.environ['PASSPHRASE']

        exitcode = child.wait()
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))
        
    def __str__(self):
        return " ".join(self.command)
