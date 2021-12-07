#!/usr/bin/python2
#
# Copyright (c) 2015 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""Ask Hub to use IAM role to get temporary credentials to your TKLBAM S3 storage"""

import sys
from registry import hub_backups
import hub
from retry import retry

@retry(5, backoff=2)
def get_credentials(hb):
    return hb.get_credentials()

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def format(creds):
    values = [ creds[k] for k in ('accesskey', 'secretkey', 'sessiontoken', 'expiration') ]
    return " ".join(values)


def main():
    args = sys.argv[1:]
    if args:
        usage()

    try:
        hb = hub_backups()
    except hub.Backups.NotInitialized, e:
        print >> sys.stderr, "error: " + str(e)

    creds = get_credentials(hb)
    if creds.type != 'iamrole':
        fatal("STS agent incompatible with '%s' type credentials" % creds.type)

    print format(creds)

if __name__ == "__main__":
    main()
