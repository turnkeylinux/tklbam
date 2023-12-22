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
Print a list of files that have changed

Options:
    -i --input=PATH     Read a list of paths from a file (- for stdin)

    -c --create         Create index
"""
import sys
import getopt
from typing import Optional, NoReturn

import dirindex
import changes

def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Syntax: %s [-options] index path1 ... pathN" % sys.argv[0], file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:ch', 
                                       ['create', 'input='])
    except getopt.GetoptError as e:
        usage(e)

    opt_create = False
    opt_input = None

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        elif opt in ('-c', '--create'):
            opt_create = True

        elif opt in ('-i', '--input'):
            opt_input = val

    if not args or (not opt_input and len(args) < 2):
        usage()

    path_index = args[0]
    paths = args[1:]
    
    if opt_input:
        fh = open(opt_input) if opt_input != '-' else sys.stdin
        paths = dirindex.read_paths(fh) + paths

    if opt_create:
        dirindex.create(path_index, paths)
        return

    for change in changes.whatchanged(path_index, paths):
        print(change)

if __name__=="__main__":
    main()
