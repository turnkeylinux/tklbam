#!/usr/bin/python2
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Rollback last restore

Options:

    --force     Don't ask for confirmation (caution)
"""

import sys
import getopt

from rollback import Rollback

def fatal(e):
    print("error: " + str(e), file=sys.stderr)
    sys.exit(1)

def usage(e=None):
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Usage: %s" % sys.argv[0], file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h',
                                       ['force', 'help'])
    except getopt.GetoptError as e:
        usage(e)

    opt_force = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        if opt == '--force':
            opt_force = True

    if args:
        usage()

    try:
        rollback = Rollback()
    except Rollback.Error:
        fatal("nothing to rollback")

    if not opt_force:
        print("DATA LOSS WARNING: this will rollback your system to the pre-restore")
        print("snapshot from " + rollback.timestamp.ctime())
        print()

        while True:
            answer = input("Is this really what you want? [yes/no] ")
            if answer:
                break

        if answer.lower() != "yes":
            print("You didn't answer 'yes'. Aborting!")
            sys.exit(1)

    rollback.rollback()

if __name__=="__main__":
    main()

