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

This links TKLBAM to your Hub account and downloads a backup profile, which is
used to calculate the list of system changes we need to backup. The profile
usually describes the installation state of a TurnKey appliance and contains a
list of packages, filesystem paths to scan for changes and an index of the
contents of those paths which records timestamps, ownership and permissions. 

Arguments:

    API-KEY                        Cut and paste this from your Hub account's user profile.

Options:

    --force                        Force re-initialization with new API-KEY.

    --force-profile=PROFILE_ID     Force a specific backup profile 
                                   (e.g., "core", "turnkey-core-13.0-wheezy-amd64")

                                   Default value: String in /etc/turnkey_version

                                   Special value: "empty": creates an empty
                                   backup profile. Backup configurations will
                                   only be taken from /etc/tklbam.
   
Security warning:

    Providing your Hub account's APIKEY as a command line argument is
    potentially less secure than allowing tklbam-init to prompt you for it
    interactively:

    * The APIKEY may briefly show up in the process list
    * The shell may save the APIKEY to its history file (e.g., ~/.bash_history)

Examples:

    # initialize TKLBAM
    tklbam-init

    # initialize TKLBAM with the core profile
    tklbam-init --force-profile=core

    # initialize TKLBAM with a non-default registry path
    TKLBAM_REGISTRY=/var/lib/tklbam2 tklbam-init

"""

import sys
import hub
import keypacket

import registry
from conf import Conf

import os
import base64
import struct
import hashlib
import getopt

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

        elif opt == '--force':
            force = True

        elif opt == '--force-profile':
            force_profile = True
            conf.force_profile = val

    if args:
        if len(args) != 1:
            usage()

        apikey = args[0]

    if not registry.registry.secret:
        registry.registry.secret = generate_secret()
        registry.registry.key = keypacket.fmt(registry.registry.secret, "")
        print """\
Generated backup encryption key:

    For extra security run "tklbam-passphrase" to cryptographically protect it
    with a passphrase, which will be needed later to restore. If you use lose
    the passphrase it will be impossible to restore your backup and you may
    suffer data loss. To safeguard against this you may want to create an
    escrow key with "tklbam-escrow".
"""

    if force or not registry.registry.sub_apikey:
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

        registry.registry.sub_apikey = sub_apikey

        hb = hub.Backups(sub_apikey)
        try:
            credentials = hb.get_credentials()
            registry.registry.credentials = credentials
            print "Linked TKLBAM to your Hub account."

        except hub.NotSubscribed, e:
            print "Linked TKLBAM to your Hub account but there's a problem:"
            print

    elif not force_profile and registry.registry.profile:
        fatal("already initialized")

    if force_profile or not registry.registry.profile:
        registry.update_profile(conf.force_profile)

if __name__=="__main__":
    main()
