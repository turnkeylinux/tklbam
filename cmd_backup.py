#!/usr/bin/python
"""
Backup the current system

Arguments:
    <override> := -?( /path/to/add/or/remove | mysql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Options:
    --address=TARGET_URL    manual backup target URL
                            default: automatically configured via Hub

    -v --verbose            Turn on verbosity
    -s --simulate           Simulate operation. Don't actually backup.

"""

from os.path import *

import sys
import getopt

from string import Template

import backup

import hub
from registry import registry

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ override ... ]" % sys.argv[0]
    tpl = Template(__doc__.strip())
    Conf = backup.BackupConf
    print >> sys.stderr, tpl.substitute(CONF=Conf.paths.path,
                                        CONF_OVERRIDES=Conf.paths.overrides)
    sys.exit(1)

def warn(e):
    print >> sys.stderr, "warning: " + str(e)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def get_turnkey_version():
    return file("/etc/turnkey_version").readline().strip()

from conffile import ConfFile

class ServerConf(ConfFile):
    CONF_FILE="/var/lib/hubclient/server.conf"
    REQUIRED=['serverid']

def get_server_id():
    if not exists(ServerConf.CONF_FILE):
        return None

    return ServerConf()['serverid']

def get_profile(hb):
    """Get a new profile if we don't have a profile in the registry or the Hub
    has a newer profile for this appliance. If we can't contact the Hub raise
    an error if we don't already have profile."""

    profile_timestamp = registry.profile.timestamp \
                        if registry.profile else None

    turnkey_version = get_turnkey_version()

    try:
        new_profile = hb.get_new_profile(turnkey_version, profile_timestamp)
        if new_profile:
            registry.profile = new_profile
    except hb.Error, e:
        if not registry.profile:
            raise

        warn("using cached profile because of a Hub error: " + str(e))

    return registry.profile

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'svh', 
                                       ['simulate', 'verbose', 
                                        'profile=', 'secretfile=', 'address='])
    except getopt.GetoptError, e:
        usage(e)

    conf = backup.BackupConf()
    conf.secretfile = registry.path.secret

    opt_simulate = False
    opt_verbose = False

    opt_profile = None
    for opt, val in opts:
        if opt in ('-v', '--verbose'):
            opt_verbose = True
        elif opt in ('-s', '--simulate'):
            opt_simulate = True

        elif opt == '--profile':
            opt_profile = val

        elif opt == '--secretfile':
            if not exists(val):
                usage("secretfile %s does not exist" % `val`)
            conf.secretfile = val
        elif opt == '--address':
            conf.address = val
        elif opt == '-h':
            usage()

    conf.overrides += args

    hb = hub.Backups(registry.sub_apikey)
    conf.profile = get_profile(hb) if not opt_profile else opt_profile

    if not conf.address:
        try:
            registry.credentials = hb.get_credentials()
        except hb.Error, e:
            # in the real implementation asking for get_credentials() might fail
            # if the hub is down. If we already have the credentials we can survive
            # that.
            if isinstance(e, hub.NotSubscribedError) or not registry.credentials:
                raise
            warn(e)

        conf.credentials = registry.credentials

        if registry.hbr:
            try:
                registry.hbr = hb.get_backup_record(registry.hbr.backup_id)
            except hb.Error, e:
                # in the real implementation if the Hub is down we can hope that
                # the cached address is still valid and warn and try to backup anyway.
                #
                # But if we reach the Hub and it tells us the backup is invalid
                # we must invalidate the cached backup record and start over.

                if isinstance(e, hub.InvalidBackupError):
                    warn("old backup record deleted, creating new ... ")
                    registry.hbr = None
                else:
                    warn(e)

        if not registry.hbr:
            registry.hbr = hb.new_backup_record(registry.key, 
                                                get_turnkey_version(), 
                                                get_server_id())

        conf.address = registry.hbr.address

    if opt_simulate:
        opt_verbose = True

    print "backup.Backup(%s)" % (`conf`)

    b = backup.Backup(conf)
    if opt_verbose:
        print "PASSPHRASE=$(cat %s) %s" % (conf.secretfile, b.command)

    if not opt_simulate:
        try:
            b.run()
        finally:
            b.cleanup()
    hb.updated_backup(conf.address)

if __name__=="__main__":
    main()

