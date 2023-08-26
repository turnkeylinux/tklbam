#!/usr/bin/python3
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""Create a backup escrow key (Save this somewhere safe)

Arguments:

    KEYFILE                 File path to save the escrow key (- for stdout)

Options:

    -P --no-passphrase      Don't encrypt escrow key with a passphrase
    -R --random-passphrase  Choose a secure random passphrase (and print it)
"""

import sys
import getopt

import keypacket
from registry import registry
from passphrase import *

def usage(e=None):
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Usage: %s [-options] KEYFILE" % sys.argv[0], file=sys.stderr)
    print(__doc__, file=sys.stderr)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "hRP", ["help", "no-passphrase", "random-passphrase"])
    except getopt.GetoptError as e:
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

        if opt in ('-R', '--random-passphrase'):
            opt_random_passphrase = True

    if opt_no_passphrase and opt_random_passphrase:
        print("error: --no-passphrase and --random-passphrase are incompatible options", file=sys.stderr)
        sys.exit(1)

    if not registry.secret:
        print("error: you need to run init first", file=sys.stderr)
        sys.exit(1)

    def _passphrase():
        if opt_no_passphrase:
            return ""

        if opt_random_passphrase:
            passphrase = random_passphrase()
            print(passphrase)
            return passphrase

        return get_passphrase()

    passphrase = _passphrase()
    key = keypacket.fmt(registry.secret, passphrase)

    if keyfile == '-':
        fh = sys.stdout
    else:
        fh = file(keyfile, "w")
        os.chmod(keyfile, 0o600)

    print(key, file=fh)

if __name__ == "__main__":
    main()
