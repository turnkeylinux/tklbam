#!/usr/bin/python
"""
Backup the current system

Arguments:
    <override> := -?( /path/to/add/or/remove | mysql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Resolution order for options:
1) command line (highest precedence)
2) configuration files ($CONF)

Options:
    --profile=PATH          base profile path
                            default: $DEFAULT_PROFILE

    --keyfile=PATH          secret keyfile
                            default: $CONF_KEY

    --address=TARGET_URL    duplicity target URL
                            default: read from $CONF_ADDRESS

"""

import os
import sys
import getopt

import re
from string import Template
from paths import Paths

class Error(Exception):
    pass

class Conf:
    profile = "/usr/share/tklbam/profile"

    path = "/etc/tklbam"
    class Paths(Paths):
        files = [ 'address', 'key', 'overrides' ]
    paths = Paths(path)

    @staticmethod
    def _read_address(path):
        try:
            return file(path).read().strip()
        except:
            return None

    @staticmethod
    def _read_overrides(inputfile):
        overrides = []
        
        try:
            fh = file(inputfile)
        except:
            return []

        for line in fh.readlines():
            line = re.sub(r'#.*', '', line).strip()
            if not line:
                continue

            overrides += line.split()

        def is_legal(override):
            if override[0] == '-':
                override = override[1:]

            if ':' in override:
                namespace, val = override.split(':', 1)
                if namespace in ('mysql', 'pgsql'):
                    return True

            return override[0] == '/'

        for override in overrides:
            if not is_legal(override):
                raise Error(`override` + " is not a legal override")

        return overrides

    def __init__(self):
        self.keyfile = self.paths.key
        self.address = self._read_address(self.paths.address)
        self.overrides = self._read_overrides(self.paths.overrides)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ override ... ]" % sys.argv[0]
    tpl = Template(__doc__.strip())
    print >> sys.stderr, tpl.substitute(CONF=Conf.paths.path,
                                        CONF_OVERRIDES=Conf.paths.overrides,
                                        CONF_KEY=Conf.paths.key,
                                        CONF_ADDRESS=Conf.paths.address,
                                        DEFAULT_PROFILE=Conf.profile)
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['profile=', 'keyfile=', 'address='])
    except getopt.GetoptError, e:
        usage(e)

    conf = Conf()

    for opt, val in opts:
        if opt == '--profile':
            conf.profile = val
        elif opt == '--keyfile':
            conf.keyfile = val
        elif opt == '--address':
            conf.address = val
        elif opt == '-h':
            usage()

    if not conf.address:
        usage("address not configured")

    conf.overrides += args

    print "conf.profile = " + `conf.profile`
    print "conf.keyfile = " + `conf.keyfile`
    print "conf.address = " + `conf.address`
    print "conf.overrides = " + `conf.overrides`

if __name__=="__main__":
    main()
