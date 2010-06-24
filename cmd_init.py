#!/usr/bin/python
"""
Initialize TKLBAM (TurnKey Linux Backups and Migration)

Arguments:

    API-KEY    Cut and paste this from your Hub account's user profile.

"""

import sys
import hub
import keypacket

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

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        usage()

    if len(args) != 1:
        usage("incorrect number of arguments")

    if registry.sub_apikey:
        print >> sys.stderr, "error: already initialized"
        sys.exit(1)

    apikey = args[0]
    sub_apikey = hub.Backups.get_sub_apikey(apikey)

    registry.sub_apikey = sub_apikey
    registry.secret = keypacket.generate()

    try:
        credentials = hub.Backups(sub_apikey).get_credentials()
        registry.credentials = credentials

    except hub.Backups.Error, e:
        print >> sys.stderr, NOT_SUBSCRIBED

if __name__=="__main__":
    main()
