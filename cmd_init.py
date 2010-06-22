#!/usr/bin/python
"""
Initialize TKLBAM (TurnKey Linux Backups and Migration)

Arguments:

    API-KEY    Cut and paste this from your Hub account's user profile.

"""

import os
import sys
import hub
import sha
from registry import registry

NOT_SUBSCRIBED = """\
Warning: backups are not yet enabled for your TurnKey Hub account. Log
into the Hub and go to the "Backups" section for instructions."""

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s API-KEY" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def generate_secret():
    return sha.sha(os.urandom(32)).hexdigest()

def main():
    args = sys.argv[1:]
    if not args:
        usage()

    if len(args) != 1:
        usage("incorrect number of arguments")

    if registry.subkey:
        print >> sys.stderr, "error: already initialized"
        sys.exit(1)

    apikey = args[0]
    subkey = hub.Backups.get_subkey(apikey)

    registry.subkey = subkey
    registry.secret = generate_secret()

    try:
        credentials = hub.Backups(subkey).get_credentials()
    except hub.Backups.Error, e:
        print >> sys.stderr, NOT_SUBSCRIBED

    registry.credentials = credentials

if __name__=="__main__":
    main()
