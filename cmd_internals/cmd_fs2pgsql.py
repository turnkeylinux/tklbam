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
Map a filesystem created by pgsql2fs back to PostgreSQL
"""
import sys
from os.path import *

import pgsql

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s path/to/pgfs [ -?database/table ... ] " % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    args = sys.argv[1:]
    if not args:
        usage()

    pgfs = args[0]
    limits = args[1:]

    if not isdir(pgfs):
        usage("not a directory '%s'" % pgfs)

    pgsql.fs2pgsql(pgfs, limits)

if __name__ == "__main__":
    main()
