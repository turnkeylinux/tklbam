#!/usr/bin/python
# Copyright (c) 2018 TurnKey GNU/Linux - https://www.turnkeylinux.org
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Set Fallback

This is used to setup fallback credentials used when access to the Hub is limited
or not possible.

Arguments:

    FALLBACK-ACCESS-KEY                 Your IAMUser access key

    FALLBACK-SECRET-KEY                 Your IAMUser secret access key

Security warning:

    Providing your AWS IAMUser credentials as a commandline argument is
    potentially less secure than allowing tklbam-set-fallback to prompt
    you for it interactively:

    * The shell may save the APIKEY to its history file (e.g., ~/.bash_history)
    * The FALLBACK-ACCESS-KEY and FALLBACK-SECRET-KEY may briefly show up in the
      process list.

    AWS IAMUser credentials must exist on your system in plaintext as they are
    intended to work even when you can only access your AWS bucket and should
    work automatically without interaction.

"""

import sys
import registry
import getopt

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Usage: %s [ -options ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()

    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError, e:
        usage(e)

    fallback_access_key = None
    fallback_secret_key = None

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    if args:
        if len(args) > 2:
            usage()
        elif len(args) == 1:
            fallback_access_key = args[0]
        elif len(args) == 2:
            fallback_access_key = args[0]
            fallback_secret_key = args[1]
    else:
        usage()

    if not fallback_access_key:
        print "Copy paste the AWS access key"

        while True:
            fallback_access_key = raw_input("ACCESS-KEY: ").strip()
            if fallback_access_key:
                break
    if not fallback_secret_key:
        print "Copy paste the AWS secret access key"

        while True:
            fallback_secret_key = raw_input("SECRET-KEY: ").strip()
            if fallback_secret_key:
                break

    registry.registry.fallback_access_key = fallback_access_key
    registry.registry.fallback_secret_key = fallback_secret_key

if __name__ == '__main__':
    main()
