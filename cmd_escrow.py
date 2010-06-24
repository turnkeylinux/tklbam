#!/usr/bin/python
"""Create an independent backup escrow key. Save this somewhere safe.

Arguments:

    KEYFILE              File path to save the escrow key (- for stdout)

Options:

    -P --no-passphrase   Don't encrypt escrow key with a passphrase 
"""

import sys
import getopt

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [-options] KEYFILE" % sys.argv[0]
    print >> sys.stderr, __doc__
    sys.exit(1)

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hP", ["help", "no-passphrase"])
    except getopt.GetoptError, e:
        usage(e)

    if not args:
        usage()

    if len(args) != 1:
        usage("bad number of arguments")

    keyfile = args[0]

    opt_no_passphrase = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt in ('-P', '--no-passphrase'):
            opt_no_passphrase = True

    print `opt_no_passphrase`
    print `keyfile`

if __name__ == "__main__":
    main()
