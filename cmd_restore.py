#!/usr/bin/python
"""
Restore a backup

Arguments:

    <hub-backup> := backup-id || unique label pattern

Options:
    --limits="<limit1> .. <limitN>"   Restore filesystem or database limitations

      <limit> := -?( /path/to/add/or/remove | mysql:database[/table] )

    --keyfile=KEYFILE                 Path to escrow keyfile.
                                      default: Hub provides this automatically.

    --address=TARGET_URL              manual backup target URL (needs --keyfile)
                                      default: Hub provides this automatically.

    --skip-files                      Don't restore filesystem
    --skip-database                   Don't restore databases
    --skip-packages                   Don't restore new packages

    --no-rollback                     Disable rollback
    --silent                          Disable feedback

"""

import sys
import getopt

import re

from os.path import *
from restore import Restore
from redirect import RedirectOutput
from temp import TempFile

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ <hub-backup> ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    opt_limits = []
    opt_keyfile = None
    opt_address = None

    skip_files = False
    skip_database = False
    skip_packages = False
    no_rollback = False
    silent = False

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['limits=', 'address=', 'keyfile=', 
                                        'silent',
                                        'skip-files', 'skip-database', 'skip-packages',
                                        'no-rollback'])
                                        
    except getopt.GetoptError, e:
        usage(e)

    for opt, val in opts:
        if opt == '--limits':
            opt_limits += re.split(r'\s+', val)
        elif opt == '--keyfile':
            if not isfile(val):
                fatal("keyfile %s does not exist or is not a file" % `val`)

            opt_keyfile = val
        elif opt == '--address':
            opt_address = val
        elif opt == '--skip-files':
            skip_files = True
        elif opt == '--skip-database':
            skip_database = True
        elif opt == '--skip-packages':
            skip_packages = True
        elif opt == '--no-rollback':
            no_rollback = True
        elif opt == '--silent':
            silent = True
        elif opt == '-h':
            usage()

    backup_id = None

    if args:
        if len(args) != 1:
            usage("incorrect number of arguments")

        backup_id = args[0]

    else:
        if not opt_address:
            usage()

    if opt_address:
        if backup_id:
            fatal("a manual --address is incompatible with a <backup-id>")

        if not opt_keyfile:
            fatal("a manual --address needs a --keyfile")

    print "backup_id: " + `backup_id`
    print "opt_limits: " + `opt_limits`
    print "opt_address=%s, opt_keyfile=%s" % (opt_address, opt_keyfile)

    #if silent:
    #    log = TempFile()
    #else:
    #    log = sys.stdout

    #redir = RedirectOutput(log)
    #try:
    #    restore = Restore(address, key, limits, 
    #                      rollback=not no_rollback)

    #    if not skip_packages:
    #        restore.packages()

    #    if not skip_files:
    #        restore.files()

    #    if not skip_database:
    #        restore.database()
    #finally:
    #    redir.close()

if __name__=="__main__":
    main()
