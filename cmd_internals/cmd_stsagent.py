#!/usr/bin/python3
#
# Copyright (c) 2015 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""Ask Hub to use IAM role to get temporary credentials to your TKLBAM S3
storage"""

import sys
from typing import Optional, NoReturn

from registry import hub_backups
import hub
import retries


@retries.retry(5, backoff=2)
def get_credentials(hb: hub.Backups):
    return hb.get_credentials()


def usage(e: Optional[str] = None) -> NoReturn:
    if e:
        print("error: " + str(e), file=sys.stderr)

    print(f"Syntax: {sys.argv[0]}", file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    sys.exit(1)


def fatal(e: str) -> NoReturn:
    print("error: " + str(e), file=sys.stderr)
    sys.exit(1)


def format(creds: Optional[hub.Credentials.IAMRole | hub.Credentials.IAMUser]
           ) -> str:
    if not creds:
        return ''
    values = [creds[k] for k in ('accesskey', 'secretkey',
                                 'sessiontoken', 'expiration')]
    return " ".join(values)


def main():
    args = sys.argv[1:]
    if args:
        usage()

    hb = None
    try:
        hb = hub_backups()
    except hub.Backups.NotInitialized as e:
        print("error: " + str(e), file=sys.stderr)
    if not hb:
        fatal('Unexpected error - this code should never run')
    creds = get_credentials(hb)
    if creds.kind != 'iamrole':
        fatal(f"STS agent incompatible with '{creds.type}' type credentials")

    print(format(creds))


if __name__ == "__main__":
    main()
