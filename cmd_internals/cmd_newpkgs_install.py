#!/usr/bin/python3
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

"""
Install list of new packages that are available in apt-cache.

Options:
    -i --input=PATH         Read a list of packages from a file (- for stdin)
    -v --verbose            Turn on verbosity
    -s --simulate           Don't execute apt-get
"""

import re
import sys
import getopt
from typing import Optional, NoReturn

from pkgman import Installer


def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print(f"Syntax: {sys.argv[0]} [ -options ] [ package-name ... ]",
          file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)


def parse_input(inputfile: str) -> list[str]:
    packages = []

    if inputfile == '-':
        fh = sys.stdin
    else:
        fh = open(inputfile)

    for line in fh.readlines():
        line = re.sub(r'#.*', '', line).strip()
        if not line:
            continue

        packages.append(line)
    fh.close()

    return packages


def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:svh',
                                       ['input=', 'simulate', 'verbose'])
    except getopt.GetoptError as e:
        usage(e)

    opt_input = None
    opt_simulate = False
    opt_verbose = False

    for opt, val in opts:
        if opt in ('-i', '--input'):
            opt_input = val

        elif opt in ('-s', '--simulate'):
            opt_simulate = True

        elif opt in ('-v', '--verbose'):
            opt_verbose = True
        else:
            usage()

    if opt_simulate:
        opt_verbose = True

    if not args and not opt_input:
        usage()

    packages = args
    if opt_input:
        packages += parse_input(opt_input)

    installer = Installer(packages)

    if opt_verbose:
        if installer.skipping:
            print("# SKIPPING: " + " ".join(installer.skipping))

        if installer.command:
            print(installer.command)

    if not opt_simulate:
        errno, output = installer(interactive=False)
        if opt_verbose:
            print(output)
        sys.exit(errno)


if __name__ == "__main__":
    main()
