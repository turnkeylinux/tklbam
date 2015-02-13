#!/usr/bin/python
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Initialization (start here)

By default, this links TKLBAM to your Hub account and downloads an appropriate
backup profile, which is used to calculate the list of system changes we need
to backup. On a TurnKey system the profile describes the installation state of
the appliance and contains a list of packages, filesystem paths to scan for
changes and an index of the contents of those paths which records timestamps,
ownership and permissions. On a non-TurnKey system the default backup profile
will not describe installation state, only a list of directories to backup.

Arguments:

    API-KEY                        Cut and paste this from your Hub account's user profile.

Options:

    --force                        Force re-initialization with new API-KEY.

    --force-profile=PROFILE_ID     Force a specific backup profile 
                                   (e.g., "core", "turnkey-core-13.0-wheezy-amd64")

                                   Without --force-profile the profile_id is 
                                   automatically detected.

    --force-profile=empty          "empty" is a special profile_id value that creates an empty
                                   backup profile. Backup configurations will only be taken 
                                   from /etc/tklbam.

    --force-profile=PATH           Path to a custom backup profile
                                   Details: tklbam-internal create-profile --help

    --solo                         Solo mode: disables link to Hub.
                                   You'll need to --force-profile=empty or use a custom profile

                                   tklbam-backup will only work with --address or --dump options
                                   tklbam-restore will only work with --address or a backup extract
   
Security warning:

    Providing your Hub account's APIKEY as a command line argument is
    potentially less secure than allowing tklbam-init to prompt you for it
    interactively:

    * The shell may save the APIKEY to its history file (e.g., ~/.bash_history)
    * The APIKEY may briefly show up in the process list

Examples:

    # initialize TKLBAM
    tklbam-init

    # initialize TKLBAM with the core profile
    tklbam-init --force-profile=core

    # initialize TKLBAM with a non-default registry path
    TKLBAM_REGISTRY=/var/lib/tklbam2 tklbam-init

    # initialize TKLBAM in solo mode with an empty profile
    tklbam-init --solo --force-profile=empty

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
    from paged import stdout

    if e:
        print >> stdout, "error: " + str(e)

    print >> stdout, "Usage: %s [ API-KEY ]" % sys.argv[0]
    print >> stdout, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help", "solo", "force", "force-profile="])
    except getopt.GetoptError, e:
        usage(e)

    apikey = None
    force = False
    force_profile = False
    solo = False

    conf = Conf()

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        elif opt == '--force':
            force = True

        elif opt == '--force-profile':
            force_profile = True
            conf.force_profile = val

        elif opt == "--solo":
            solo = True

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

    if solo:
        if registry.registry.sub_apikey:
            print "Broken TKLBAM link to your Hub account (--solo mode)"
            registry.registry.sub_apikey = None
            registry.registry.credentials = None
    else:
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
        try:
            registry.update_profile(conf.force_profile)
        except hub.Backups.NotInitialized:
            fatal("--solo requires --force-profile=empty or --force-profile=path/to/custom/profile ")

if __name__=="__main__":
    main()
