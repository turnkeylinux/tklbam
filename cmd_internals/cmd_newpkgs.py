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

"""Print list of new packages"""
import sys
from typing import Optional, NoReturn

from pkgman import Packages


def usage(e: Optional[str] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print(f"Syntax: {sys.argv[0]} base-packages-list [ packages-list ]",
          file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        usage()

    base_packages = Packages.fromfile(args[0])
    try:
        packages = Packages.fromfile(args[1])
    except:  # TODO don't use bare except
        packages = Packages()

    for package in (packages - base_packages):
        print(package)


if __name__ == "__main__":
    main()
