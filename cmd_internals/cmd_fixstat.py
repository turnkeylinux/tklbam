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
Fix ownership and permissions of files according to delta specification

Options:
    -u --uid-map=<mapspec>     Old to new UID map
    -g --gid-map=<mapspec>     Old to new GID map

    -v --verbose               Print list of fixes
    -s --simulate              Print list of fixes, don't apply them

    <mapspec> := <key>,<val>[:<key>,<val> ...]
"""

import sys
import getopt
from typing import Optional, NoReturn

from changes import Changes


def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print(f"Syntax: {sys.argv[0]} [-options] delta|- [path ...]",
          file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)


def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'u:g:svh',
                                       ['uid-map=', 'gid-map=',
                                        'simulate', 'verbose'])
    except getopt.GetoptError as e:
        usage(e)

    verbose = False
    simulate = False

    uidmap: dict[int, int] = {}
    gidmap: dict[int, int] = {}

    def parse_idmap(line: str) -> dict[int, int]:
        d: dict[int, int] = {}
        for val in line.split(':'):
            k, v = val.split(',', 1)
            d[int(k)] = int(v)
        return d

    for opt, val in opts:
        if opt in ('-u', '--uid-map'):
            uidmap = parse_idmap(val)
        elif opt in ('-g', '--gid-map'):
            gidmap = parse_idmap(val)
        elif opt in ('-s', '--simulate'):
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

    for action in changes.statfixes(uidmap, gidmap):
        if verbose:
            print(action)

        if not simulate:
            action()


if __name__ == "__main__":
    main()
