#!/usr/bin/python
# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""Print list of new packages"""
import os
import sys
import commands

from pkgman import Packages

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s base-packages-list [ packages-list ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        usage()

    base_packages = Packages.fromfile(args[0])
    try:
        packages = Packages.fromfile(args[1])
    except:
        packages = Packages()

    for package in (packages - base_packages):
        print package
        
if __name__=="__main__":
    main()
