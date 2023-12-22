#!/usr/bin/python3
# 
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
Delete files according to delta

Options:
    -v --verbose               Print list of fixes
    -s --simulate              Print list of fixes, don't apply them
"""

import sys
import getopt
from typing import Optional, NoReturn

from changes import Changes

def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Syntax: %s [-options] delta|- [path ...]" % sys.argv[0], file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'svh', 
                                       ['simulate', 'verbose'])
    except getopt.GetoptError as e:
        usage(e)

    simulate = False
    verbose = False
    for opt, val in opts:
        if opt in ('-s', '--simulate'):
            simulate = True
        elif opt in ('-v', '--verbose'):
            verbose = True
        else:
            usage()

    if len(args) < 1:
        usage()

    delta = args[0]
    paths = args[1:]

    changes = Changes.fromfile(delta, paths)
    if simulate:
        verbose = True

    for action in changes.deleted():
        if verbose:
            print(action)

        if not simulate:
            action()

if __name__=="__main__":
    main()
