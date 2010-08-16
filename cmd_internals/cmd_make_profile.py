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
"""
Make profile

Options:
    
    --profiles-conf=PATH    Dir containing profile conf files
                            Environment: PROFILES_CONF

"""
import os
import sys
import getopt

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s path/to/appliance.iso path/to/output" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['profiles-conf=', 'help'])
    except getopt.GetoptError, e:
        usage(e)

    profiles_conf = os.environ.get("PROFILES_CONF")

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--profiles-conf':
            profiles_conf = val

    if not args:
        usage()

    if len(args) != 2:
        usage("incorrect number of arguments")

    if not profiles_conf:
        fatal("need a profiles conf dir")

    iso_path, output_path = args

    print `profiles_conf`
    print `iso_path, output_path`

if __name__=="__main__":
    main()
