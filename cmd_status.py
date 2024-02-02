#!/usr/bin/python3
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Print a helpful status message

Options:

    --short     The short version.

Exitcode:

    0           OK
    10          NO BACKUP
    11          NO APIKEY

"""
import sys
import getopt
from typing import Optional, NoReturn

from registry import registry


class Status:
    OK = 0
    NO_BACKUP = 10
    NO_APIKEY = 11

    @classmethod
    def get(cls):

        if not registry.sub_apikey:
            return cls.NO_APIKEY

        elif not registry.hbr:
            return cls.NO_BACKUP

        else:
            return cls.OK


def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Usage: %s [ -options ]" % (sys.argv[0]), file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)

    sys.exit(1)


def main():
    opts = None
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ["short", "help"])
    except getopt.GetoptError as e:
        usage(e)

    assert opts is not None
    opt_short = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--short':
            opt_short = True

    status = Status.get()

    if status == Status.NO_APIKEY:
        print("TKLBAM (Backup and Migration):  NOT INITIALIZED")
        if not opt_short:
            print()
            print('  To initialize TKLBAM, run the "tklbam-init" command to'
                  ' link this')
            print('  system to your TurnKey Hub account. For details see the'
                  ' man page or')
            print('  go to:')
            print()
            print('      https://www.turnkeylinux.org/tklbam')

    elif status == Status.NO_BACKUP:
        print("TKLBAM (Backup and Migration):  NO BACKUPS")
        if not opt_short:
            print()
            print('  To backup for the first time run the "tklbam-backup"'
                  ' command. For')
            print('  details see the man page or go to:')
            print()
            print('      https://www.turnkeylinux.org/tklbam')

    elif status == Status.OK:
        hbr = registry.hbr
        s = "TKLBAM:  Backup ID #%s" % hbr.backup_id
        if registry.hbr.updated:
            s += ", Updated %s" % hbr.updated.strftime("%a %Y-%m-%d %H:%M")

        print(s)

    sys.exit(status)


if __name__ == "__main__":
    main()
