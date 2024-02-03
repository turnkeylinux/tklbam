#!/usr/bin/python3
#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

"""
List backup records

By default uses a built-in format, unless a user-specified format is specified.

Format variables:

    %id                     Backup id
    %label                  Descriptive label
    %profile_id             Appliance version code
    %server_id              Associated server id (- if empty)
    %created                Date the backup record was created
    %updated                Date the backup record was last updated
    %size                   Aggregate size of backup, in bytes
    %address                Backup target address
    %key                    Base64 encoded encrypted keypacket
    %skpp                   Secret Key Passphrase Protection (Yes/No)

Examples:

    list
    list "backup_id=%backup_id label=%label size=%{size}MB"

"""
import sys
import getopt
import string
from typing import Optional, NoReturn

import keypacket

from registry import hub_backups


def usage(e: Optional[str | getopt.GetoptError] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print("Usage: %s [ <format> ]" % (sys.argv[0]), file=sys.stderr)
    print(__doc__, file=sys.stderr)

    sys.exit(1)


class Formatter:
    def __init__(self, format: str):
        tpl = format.replace('$', '$$')
        tpl = tpl.replace('\\n', '\n')
        tpl = tpl.replace('\\t', '\t')
        tpl = tpl.replace('%%', '__PERCENT__')
        tpl = tpl.replace('%', '$')
        tpl = tpl.replace('__PERCENT__', '%')

        self.tpl = string.Template(tpl)

    def __call__(self, hbr: hub_backups.backup) -> str:
        # backwards compat. hack
        hbr = hbr.copy()
        hbr['turnkey_version'] = hbr['profile_id']
        return self.tpl.substitute(**hbr)


def key_has_passphrase(key: str) -> bool:
    try:
        keypacket.parse(key.encode(), b"")
        return False
    except keypacket.Error:
        return True


def fmt_skpp(key: bytes) -> str:
    return "Yes" if key_has_passphrase(key.decode()) else "No"


def fmt_size(bytes_: int) -> str:
    if bytes_ < (10 * 1024):
        return "0.01"
    if bytes_ > (1024 * 1024 * 1000 * 99.99):
        return "%d" % (bytes_ / (1024 * 1024))
    else:
        return "%-.2f" % (bytes_ / (1024 * 1024.0))


def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError as e:
        usage(e)

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    if args:
        if len(args) != 1:
            usage("incorrect number of arguments")

        format = args[0]
    else:
        format = None

    hb = hub_backups()
    hbrs = hb.list_backups()

    if format:
        format = Formatter(format)
        for hbr in hbrs:
            hbr.id = hbr.backup_id
            hbr.skpp = fmt_skpp(hbr.key)
            print(format(hbr))

    elif hbrs:
        print("# ID  SKPP  Created     Updated     Size (MB)  Label")
        for hbr in hbrs:
            assert hbr.created is not None
            print("%4s  %-3s   %s  %-10s  %-8s   %s" %
                    (hbr.backup_id, fmt_skpp(hbr.key),
                     hbr.created.strftime("%Y-%m-%d"),

                     hbr.updated.strftime("%Y-%m-%d")
                     if hbr.updated else "-",

                     fmt_size(hbr.size),
                     hbr.label))


if __name__ == "__main__":
    main()
