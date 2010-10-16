#!/usr/bin/python
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
"""
Initialization (start here)

Arguments:

    API-KEY    Cut and paste this from your Hub account's user profile.

Options:

    --force    Force re-initialization with new API-KEY.

"""

import sys
import hub
import keypacket

from registry import registry

import os
import base64
import struct
import hashlib
import getopt
import shutil

def is_valid_apikey(apikey):
    padded = "A" * (20 - len(apikey)) + apikey
    try:
        struct.unpack("!L8s", base64.b32decode(padded + "=" * 4))
    except TypeError:
        return False

    return True

def generate_secret():
    # effective is key size: 160-bits (SHA1)
    # base64 encoding to ensure cli safeness
    # urandom guarantees we won't block. Redundant randomness just in case.
    return base64.b64encode(hashlib.sha1(os.urandom(32)).digest()).rstrip("=")

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ API-KEY ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help", "force"])
    except getopt.GetoptError, e:
        usage(e)

    apikey = None
    force = False

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--force':
            force = True

    if args:
        if len(args) != 1:
            usage()

        apikey = args[0]

    if not force and registry.sub_apikey:
        fatal("already initialized")

    if not apikey:
        print "Copy paste the API-KEY from your Hub account's user profile"
        print

        while True:
            apikey = raw_input("API-KEY: ").strip()
            if apikey:
                break

    if not is_valid_apikey(apikey):
        fatal("'%s' is an invalid API-KEY" % apikey)

    try:
        sub_apikey = hub.Backups.get_sub_apikey(apikey)
    except Exception, e:
        fatal(e)

    if force:
        if os.path.exists(registry.path):
            shutil.rmtree(registry.path)
            os.mkdir(registry.path)

    registry.sub_apikey = sub_apikey
    registry.secret = generate_secret()
    registry.key = keypacket.fmt(registry.secret, "")

    try:
        credentials = hub.Backups(sub_apikey).get_credentials()
        registry.credentials = credentials

    except hub.NotSubscribedError, e:
        print >> sys.stderr, "Warning: " + str(e)
        print >> sys.stderr

    print "Linked TKLBAM to your Hub account."

if __name__=="__main__":
    main()
