#!/usr/bin/python
"""Change passphrase of backup encryption key

Options:

    --random    Choose a secure random password (and print it)

"""

import sys
import getopt

import hub
import keypacket
from registry import registry
from passphrase import *

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help", "random"])
    except getopt.GetoptError, e:
        usage(e)

    opt_random = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--random':
            opt_random = True

    if not registry.secret:
        print >> sys.stderr, "error: you need to run init first"
        sys.exit(1)
    secret = keypacket.parse(registry.secret, "")

    if opt_random:
        passphrase = random_passphrase()
        print passphrase
    else:
        passphrase = get_passphrase()

    mykey = keypacket.fmt(secret, passphrase)
    hbr = registry.hbr
    
    # after we setup a backup record 
    # only save key to registry if update_key works
    if hbr:
        try:
            hub.Backups(registry.sub_apikey).update_key(hbr.backup_id, mykey)
            registry.key = mykey
        except hub.Error:
            raise
    else:
        registry.key = mykey

if __name__=="__main__":
    main()
