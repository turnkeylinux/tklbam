#!/usr/bin/python
"""
Rollback last restore
"""

import sys
import getopt

from rollback import Rollback

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['help'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    if args:
        usage()

    try:
        rollback = Rollback()
    except Rollback.Error:
        fatal("nothing to rollback")

    rollback.rollback()

if __name__=="__main__":
    main()

