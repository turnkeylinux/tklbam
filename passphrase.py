# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
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

def get_passphrase(confirm=True):
    if not os.isatty(sys.stdin.fileno()):
        return sys.stdin.readline().rstrip()

    while True:
        passphrase = getpass.getpass("Passphrase: ")
        if not confirm:
            return passphrase

        confirm_passphrase = getpass.getpass("Confirm passphrase: ")
        if passphrase == confirm_passphrase:
            break
        print >> sys.stderr, "Sorry, passphrases do not match"

    return passphrase

