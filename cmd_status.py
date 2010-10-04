#!/usr/bin/python
# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
Print a helpful status message

Options:

    --short     The short version.

"""
import sys
import getopt
from StringIO import StringIO

from registry import registry

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ]" % (sys.argv[0])
    print >> sys.stderr, __doc__

    sys.exit(1)

def status(short=False):
    fh = StringIO()

    if not registry.sub_apikey:
        print >> fh, "TKLBAM (Backup and Migration):  NOT INITIALIZED"
        if not short:
            print >> fh
            print >> fh, '  To initialize TKLBAM, run the "tklbam-init" command to link this'
            print >> fh, '  system to your TurnKey Hub account. For details see the man page or'
            print >> fh, '  go to:'
            print >> fh
            print >> fh, '      http://www.turnkeylinux.org/docs/tklbam'

    elif not registry.hbr:
        print >> fh, "TKLBAM (Backup and Migration):  NO BACKUPS"
        if not short:
            print >> fh
            print >> fh, '  To backup for the first time run the "tklbam-backup" command. For'
            print >> fh, '  details see the man page or go to:'
            print >> fh
            print >> fh, '      http://www.turnkeylinux.org/docs/tklbam'

    else:
        hbr = registry.hbr
        status = "TKLBAM:  Backup ID #%s" % hbr.backup_id
        if registry.hbr.updated:
            status += ", Updated %s" % hbr.updated.strftime("%a %Y-%m-%d %H:%M")

        print >> fh, status

    return fh.getvalue()

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", 
                                       [ "short", "help" ])
    except getopt.GetoptError, e:
        usage(e)

    opt_short = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--short':
            opt_short = True

    print status(opt_short),

if __name__ == "__main__":
    main()
