#!/usr/bin/python
"""
List backup records

By default uses a built-in format, unless a user-specified format is specified.

Format variables:
    
    %backup_id              Backup id
    %label                  Descriptive label
    %turnkey_version        Appliance version code
    %server_id              Associated server id (- if empty)
    %created                Date the backup record was created
    %updated                Date the backup record was last updated
    %size                   Aggregate size of backup, in MBs
    %address                Backup target address
    %key                    Base64 encoded encrypted keypacket

Examples:

    list
    list "backup_id=%backup_id label=%label size=%{size}MB"

"""
import sys
import getopt
import string

import hub
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
            print format(hbr)

    elif hbrs:
        print "# ID  Created     Updated     Size (GB)  Label"
        for hbr in hbrs:
            print "%4s  %s  %-10s  %-8.1f   %s" % (hbr.backup_id,
                                                  hbr.created.strftime("%Y-%m-%d"),

                                                  hbr.updated.strftime("%Y-%m-%d") 
                                                  if hbr.updated else "-",

                                                  hbr.size / 1024.0,
                                                  hbr.label)

if __name__ == "__main__":
    main()
