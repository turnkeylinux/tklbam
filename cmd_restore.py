#!/usr/bin/python
"""
Restore backup

Options:
    --skip-files                Don't restore filesystem
    --skip-database             Don't restore databases
    --skip-packages             Don't restore new packages

    --no-rollback               Disable rollback

"""

from os.path import *

import sys
import getopt

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] <address> <keyfile> [ limits ... ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
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

    # debug
    for var in ('address', 'keyfile', 'limits', 'skip_files', 'skip_database', 'skip_packages', 'no_rollback'):
        print "%s = %s" % (var, `locals()[var]`)

import os
import shutil
import userdb

def test():
    path = "/var/tmp/restore"
    os.rename(path + "/backup/TKLBAM", path + "/extras")

    extras = path + "/extras"

    old_passwd = extras + "/etc/passwd"
    old_group = extras + "/etc/group"
    new_passwd = "/etc/passwd"
    new_group = "/etc/group"

    def r(path):
        return file(path).read()

    passwd, group, uidmap, gidmap = userdb.merge(r(old_passwd), r(old_group), r(new_passwd), r(new_group))

    # we don't really need to write these files
    def w(path, s):
        file(path, "w").write(str(s) + "\n")

    w(path + "/passwd", passwd)
    w(path + "/group", group)
    
    print "uidmap = " + `uidmap`
    print "gidmap = " + `gidmap`

if __name__=="__main__":
    test()
