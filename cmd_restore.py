#!/usr/bin/python
"""
Restore backup

Arguments:
    <limit> := -?( /path/to/add/or/remove | mysql:database[/table] )

Options:
    --skip-files                Don't restore filesystem
    --skip-database             Don't restore databases
    --skip-packages             Don't restore new packages

    --no-rollback               Disable rollback

"""

import sys
import getopt

from os.path import *
from restore import Restore

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] <address> <keyfile> [ limit ... ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'vh', 
                                       ['skip-files', 'skip-database', 'skip-packages',
                                        'no-rollback'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    skip_files = False
    skip_database = False
    skip_packages = False
    no_rollback = False
    for opt, val in opts:
        if opt == '--skip-files':
            skip_files = True
        elif opt == '--skip-database':
            skip_database = True
        elif opt == '--skip-packages':
            skip_packages = True
        elif opt == '--no-rollback':
            no_rollback = True
        elif opt == '-h':
            usage()

    if len(args) < 2:
        usage()

    address, keyfile = args[:2]
    limits = args[2:]

    if not exists(keyfile):
        fatal("keyfile %s does not exist" % `keyfile`)

    key = file(keyfile).read().strip()

    restore = Restore(address, key, limits, 
                      log=sys.stdout, 
                      rollback=not no_rollback)

    if not skip_packages:
        restore.packages()

    if not skip_files:
        restore.files()

    if not skip_database:
        restore.database()

if __name__=="__main__":
    main()
