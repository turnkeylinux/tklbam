#!/usr/bin/python
"""
Rollback last restore
"""

import sys
import getopt

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

import os
import stat
from changes import Changes
from restore import Rollback, remove_any
from dirindex import DirIndex
from pkgman import DpkgSelections

def rollback_files(rollback):
    changes = Changes.fromfile(rollback.fsdelta)
    dirindex = DirIndex(rollback.dirindex)

    for change in changes:
        if change.path not in dirindex:
            remove_any(change.path)
            continue

        if change.OP in ('o', 'd'):
            try:
                rollback.originals.move_out(change.path)
            except rollback.Error:
                continue

        dirindex_rec = dirindex[change.path]
        local_rec = DirIndex.Record.frompath(change.path)

        if dirindex_rec.uid != local_rec.uid or \
           dirindex_rec.gid != local_rec.gid:
            os.lchown(change.path, dirindex_rec.uid, dirindex_rec.gid)

        if dirindex_rec.mod != local_rec.mod:
            mod = stat.S_IMODE(dirindex_rec.mod)
            os.chmod(change.path, mod)

    for fname in ('passwd', 'group'):
        shutil.copy(join(rollback.etc, fname), "/etc")

def rollback_packages(rollback):
    rollback_packages = file(rollback.newpkgs).read().strip().split('\n')
    current_packages = DpkgSelections()

    purge_packages = current_packages & set(rollback_packages)
    if purge_packages:
        os.system("dpkg --purge " + " ".join(purge_packages))

def test():
    rollback = Rollback()
    rollback_files(rollback)
    rollback_packages(rollback)

if __name__=="__main__":
    test()

