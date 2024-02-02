#!/usr/bin/python3
#
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
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
Dump PostgreSQL databases to a filesystem path.
"""

from typing import Optional, NoReturn
import sys

import pgsql


def fatal(e: Optional[str] = None) -> NoReturn:
    print("fatal: " + str(e), file=sys.stderr)
    sys.exit(1)


def usage(e: Optional[str] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print(f"Syntax: {sys.argv[0]} path/to/output [ -?database/table ... ] ",
          file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        usage()

    outdir = args[0]
    limits = args[1:]

    pgsql.backup(outdir, limits)


if __name__ == "__main__":
    main()
