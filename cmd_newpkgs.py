#!/usr/bin/python
"""Print list of new packages"""
import os
import sys
import commands

from pkgman import DpkgSelections

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s base-selections [ selections ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        usage()

    base_selections = DpkgSelections(args[0])
    try:
        selections = DpkgSelections(args[1])
    except:
        selections = DpkgSelections()

    for package in (selections - base_selections):
        print package
        
if __name__=="__main__":
    main()
