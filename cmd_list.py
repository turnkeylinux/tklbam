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
List backup records

By default uses a built-in format, unless a user-specified format is specified.

Format variables:
    
    %id                     Backup id
    %label                  Descriptive label
    %turnkey_version        Appliance version code
    %server_id              Associated server id (- if empty)
    %created                Date the backup record was created
    %updated                Date the backup record was last updated
    %size                   Aggregate size of backup, in MBs
    %address                Backup target address
    %key                    Base64 encoded encrypted keypacket
    %kp                     Key passphrase boolean (Y for Yes, N for No)

Examples:

    list
    list "backup_id=%backup_id label=%label size=%{size}MB"

"""
import sys
import getopt
import string

import hub
import keypacket

from registry import registry

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ <format> ]" % (sys.argv[0])
    print >> sys.stderr, __doc__

    sys.exit(1)

class Formatter:
    def __init__(self, format):
        tpl = format.replace('$', '$$')
        tpl = tpl.replace('\\n', '\n')
        tpl = tpl.replace('\\t', '\t')
        tpl = tpl.replace('%%', '__PERCENT__')
        tpl = tpl.replace('%', '$')
        tpl = tpl.replace('__PERCENT__', '%')

        self.tpl = string.Template(tpl)

    def __call__(self, hbr):
        return self.tpl.substitute(**hbr)

def key_has_passphrase(key):
    try:
        keypacket.parse(key, "")
        return False
    except keypacket.Error:
        return True

def fmt_kp(key):
    return "Y" if key_has_passphrase(key) else "N"

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError, e:
        usage(e)

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

    if args:
        if len(args) != 1:
            usage("incorrect number of arguments")

        format = args[0]
    else:
        format = None

    hb = hub.Backups(registry.sub_apikey)
    hbrs = hb.list_backups()

    if format:
        format = Formatter(format)
        for hbr in hbrs:
            hbr.id = hbr.backup_id
            hbr.kp = fmt_kp(hbr.key)
            print format(hbr)

    elif hbrs:
        print "# ID  KP  Created     Updated     Size (GB)  Label"
        for hbr in hbrs:
            print "%4s  %s   %s  %-10s  %-8.2f   %s" % \
                    (hbr.backup_id, fmt_kp(hbr.key),
                     hbr.created.strftime("%Y-%m-%d"),

                     hbr.updated.strftime("%Y-%m-%d") 
                     if hbr.updated else "-",

                     hbr.size / (1024.0 * 1024 * 1024),
                     hbr.label)

if __name__ == "__main__":
    main()
