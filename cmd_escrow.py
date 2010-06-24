#!/usr/bin/python
"""Create an independent backup escrow key. Save this somewhere safe.

Arguments:

    KEYFILE                File path to save the escrow key (- for stdout)

Options:

    -P  --no-passphrase    Don't encrypt escrow key with a passphrase 
    --random-passphrase    Choose a secure random passphrase (and print it)
"""

import sys
import getopt

import keypacket
from registry import registry
from passphrase import *

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options] KEYFILE" % sys.argv[0]
    print >> sys.stderr, __doc__
    sys.exit(1)

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hP", ["help", "no-passphrase", "random-passphrase"])
    except getopt.GetoptError, e:
        usage(e)

    if not args:
        usage()

    if len(args) != 1:
        usage("bad number of arguments")

    keyfile = args[0]

    opt_no_passphrase = False
    opt_random_passphrase = False

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt in ('-P', '--no-passphrase'):
            opt_no_passphrase = True

        if opt == '--random-passphrase':
            opt_random_passphrase = True

    if opt_no_passphrase and opt_random_passphrase:
        print >> sys.stderr, "error: --no-passphrase and --random-passphrase are incompatible options"
        sys.exit(1)

    if not registry.secret:
        print >> sys.stderr, "error: you need to run init first"
        sys.exit(1)

    secret = keypacket.parse(registry.secret, "")

    def _passphrase():
        if opt_no_passphrase:
            return ""

        if opt_random_passphrase:
            passphrase = random_passphrase()
            print passphrase
            return passphrase

        return get_passphrase()

    passphrase = _passphrase()
    key = keypacket.fmt(secret, passphrase)

    if keyfile == '-':
        fh = sys.stdout
    else:
        fh = file(keyfile, "w")

    print >> fh, key
    
if __name__ == "__main__":
    main()
