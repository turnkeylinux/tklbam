#!/usr/bin/python
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
