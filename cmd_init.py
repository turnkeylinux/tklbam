#!/usr/bin/python
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
"""
Initialization (start here)

Links TKLBAM to your Hub account and downloads a backup profile.

Arguments:

    API-KEY                        Cut and paste this from your Hub account's user profile.

Options:

    --force                        Force re-initialization with new API-KEY.
    --force-profile=PROFILE_ID     Force a specific backup profile (e.g., "core")
                                   default: cat /etc/turnkey_version

"""

import sys
import hub
import keypacket

from registry import registry
from conf import Conf

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

    print >> sys.stderr, "Usage: %s [ API-KEY ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help", "force", "force-profile="])
    except getopt.GetoptError, e:
        usage(e)

    apikey = None
    force = False
    force_profile = False

    conf = Conf()

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--force':
            force = True

        elif opt == '--force-profile':
            force_profile = True
            conf.force_profile = val

    if args:
        if len(args) != 1:
            usage()

        apikey = args[0]

    if force or not registry.sub_apikey:
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

        registry.sub_apikey = sub_apikey
        registry.secret = generate_secret()
        registry.key = keypacket.fmt(registry.secret, "")

        hb = hub.Backups(sub_apikey)
        try:
            credentials = hb.get_credentials()
            registry.credentials = credentials

        except hub.NotSubscribedError, e:
            print >> sys.stderr, "Warning: " + str(e)
            print >> sys.stderr

        print "Linked TKLBAM to your Hub account."

    elif (not force_profile and registry.profile):
        fatal("already initialized")

    if force_profile or not registry.profile:
        try:
            registry.update_profile(conf.force_profile)
        except registry.ProfileNotFound, e:
            print >> sys.stderr, "TurnKey Hub Error: %s" % str(e)
            if not conf.force_profile:
                print "\n" + e.__doc__

            sys.exit(1)

if __name__=="__main__":
    main()
