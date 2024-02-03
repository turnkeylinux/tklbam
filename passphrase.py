# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023, 2024 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.

import os
import sys
import base64
import getpass


def random_passphrase():
    random = base64.b32encode(os.urandom(10))
    parts = []
    for i in range(4):
        parts.append(random[i * 4:(i+1) * 4])

    return "-".join(parts)


class Error(Exception):
    pass


def get_passphrase(confirm=True):
    if not os.isatty(sys.stdin.fileno()):
        input = sys.stdin.readline()
        if not input:
            raise Error("can't get passphrase - broken input")

        return input.rstrip()

    while True:
        passphrase = getpass.getpass("Passphrase: ")
        if not confirm:
            return passphrase

        confirm_passphrase = getpass.getpass("Confirm passphrase: ")
        if passphrase == confirm_passphrase:
            break
        print("Sorry, passphrases do not match", file=sys.stderr)

    return passphrase
