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

    -v --verbose            Turn on verbosity
    -s --simulate           Simulate operation. Don't actually backup.

"""

from os.path import *

import sys
import getopt

from string import Template

import backup

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

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
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'svh', 
                                       ['simulate', 'verbose', 
                                        'profile=', 'keyfile=', 'address='])
    except getopt.GetoptError, e:
        usage(e)

    conf = backup.BackupConf()

    opt_simulate = False
    opt_verbose = False
    for opt, val in opts:
        if opt in ('-v', '--verbose'):
            opt_verbose = True
        elif opt in ('-s', '--simulate'):
            opt_simulate = True
        elif opt == '--profile':
            conf.profile = val
        elif opt == '--keyfile':
            if not exists(val):
                usage("keyfile %s does not exist" % `val`)
            conf.keyfile = val
        elif opt == '--address':
            conf.address = val
        elif opt == '-h':
            usage()

    conf.overrides += args

    if not conf.address:
        fatal("address not configured")

    if not exists(conf.keyfile):
        print "generating new secret key"
        backup.Key.create(conf.keyfile)

    key = backup.Key.read(conf.keyfile)

    if not isdir(conf.profile):
        fatal("profile dir %s doesn't exist" % `conf.profile`)

    if opt_simulate:
        opt_verbose = True

    b = backup.Backup(conf, key)
    if opt_verbose:
        print "PASSPHRASE=$(cat %s) %s" % (conf.keyfile, b.command)

    if not opt_simulate:
        try:
            b.run()
        finally:
            b.cleanup()

if __name__=="__main__":
    main()
