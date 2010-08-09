#!/usr/bin/python
"""
Rollback last restore

Options:

    --force     Don't ask for confirmation (caution)
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
                                       ['force', 'help'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    opt_force = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        if opt == '--force':
            opt_force = True

    if args:
        usage()

    try:
        rollback = Rollback()
    except Rollback.Error:
        fatal("nothing to rollback")

    if not opt_force:
        print "DATA LOSS WARNING: this will rollback your system to the pre-restore"
        print "snapshot from " + rollback.timestamp.ctime()
        print

        while True:
            answer = raw_input("Is really this what you want? [yes/no] ")
            if answer:
                break

        if answer.lower() != "yes":
            print "You didn't answer 'yes'. Aborting!"
            sys.exit(1)
        
    rollback.rollback()

if __name__=="__main__":
    main()

