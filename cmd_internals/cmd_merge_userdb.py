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
"""Merge passwd and group files and print uid and gid maps"""
import sys
import userdb

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s old-passwd old-group new-passwd new-group merged-passwd merged-group" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def main():
    args = sys.argv[1:]
    if len(args) != 6:
        usage()

    old_passwd, old_group = args[:2]
    new_passwd, new_group = args[2:4]
    merged_passwd, merged_group = args[4:6]

    def r(path):
        return file(path).read()

    passwd, group, uidmap, gidmap = userdb.merge(r(old_passwd), r(old_group),
                                                 r(new_passwd), r(new_group))

    print >> file(merged_passwd, "w"), passwd
    print >> file(merged_group, "w"), group

    def fmt_map(m):
         return ":".join([ "%d,%d" % (key, val) for key,val in m.items() ])

    print fmt_map(uidmap)
    print fmt_map(gidmap)

if __name__=="__main__":
    main()
