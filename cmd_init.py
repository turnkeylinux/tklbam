#!/usr/bin/python
import os
import sys
import hub
import sha
from registry import registry

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s HUB-APIKEY" % sys.argv[0]
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

if __name__=="__main__":
    main()
