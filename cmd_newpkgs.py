#!/usr/bin/python
"""Print list of new packages"""
import sys
import commands

def usage(e=None):
    if e:
        print >> sys.stderr, e

    print >> sys.stderr, "Syntax: %s base-selections [ old-selections ]" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

class Error(Exception):
    pass

def get_selections():
    cmd = "dpkg --get-selections"
    errno, output = commands.getstatusoutput(cmd)
    if errno:
        raise Error("command failed (%d): %s" % (errno, cmd))

    return output

def main():
    args = sys.argv[1:]
    if len(args) not in (1, 2):
        usage()

    base_selections = args[0]
    try:
        old_selections = args[1]
    except:
        old_selections = None

    print `base_selections, old_selections`

        
if __name__=="__main__":
    main()
