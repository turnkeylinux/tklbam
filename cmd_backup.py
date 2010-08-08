#!/usr/bin/python
"""
Backup the current system

Arguments:
    <override> := -?( /path/to/add/or/remove | mysql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Options:
    --address=TARGET_URL      manual backup target URL
                              default: automatically configured via Hub

    -q --quiet                Be less verbose
    -s --simulate             Simulate operation. Don't actually backup.

Configurable options:
    --volsize MB              Size of backup volume in MBs
                              default: $CONF_VOLSIZE

    --full-backup FREQUENCY   Time frequency of full backup
                              default: $CONF_FULL_BACKUP

                              format := <int>[DWM]

                                e.g.,
                                3D - three days
                                2W - two weeks
                                1M - one month
                                
Resolution order for configurable options:

  1) comand line (highest precedence)
  2) configuration file ($CONF_PATH)
  3) built-in default (lowest precedence)

Configuration file format ($CONF_PATH):

  <option-name> <value>

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
    conf = backup.BackupConf()
    print >> sys.stderr, tpl.substitute(CONF_PATH=conf.paths.conf,
                                        CONF_OVERRIDES=conf.paths.overrides,
                                        CONF_VOLSIZE=conf.volsize,
                                        CONF_FULL_BACKUP=conf.full_backup)
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
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'qsh', 
                                       ['help',
                                        'simulate', 'quiet', 
                                        'profile=', 'secretfile=', 'address=',
                                        'volsize=', 'full-backup='])
    except getopt.GetoptError, e:
        usage(e)

    conf = backup.BackupConf()
    conf.secretfile = registry.path.secret

    opt_simulate = False

    opt_profile = None
    for opt, val in opts:
        if opt in ('-s', '--simulate'):
            opt_simulate = True

        elif opt == '--profile':
            opt_profile = val

        elif opt in ('-q', '--quiet'):
            conf.verbose = False

        elif opt == '--secretfile':
            if not exists(val):
                usage("secretfile %s does not exist" % `val`)
            conf.secretfile = val
        elif opt == '--address':
            conf.address = val

        elif opt == '--volsize':
            conf.volsize = val

        elif opt == '--full-backup':
            conf.full_backup = val

        elif opt in ('-h', '--help'):
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

    print "backup.Backup(%s)" % (`conf`)
    b = backup.Backup(conf)
    try:
        b.run(opt_simulate)
    finally:
        if not opt_simulate:
            b.cleanup()
    hb.updated_backup(conf.address)

if __name__=="__main__":
    main()

