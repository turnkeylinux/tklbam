#!/usr/bin/python
# 
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
Determine your system's default backup profile_id
"""
import sys
import getopt

from version import detect_profile_id

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)
    print >> sys.stderr, "Syntax: %s [ path/to/root ]" % sys.argv[0]
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', ['help'])
    except getopt.GetoptError, e:
        usage(e)

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    root = args[0] if args else '/'

    print detect_profile_id(root)

if __name__ == "__main__":
    main()
