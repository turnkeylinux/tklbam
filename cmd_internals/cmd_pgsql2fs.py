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
Dump PostgreSQL databases to a filesystem path.
"""
import os
from os.path import *

import sys
import shutil

import pgsql

def fatal(e):
    print >> sys.stderr, "fatal: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s path/to/output [ -?database/table ... ] " % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
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

