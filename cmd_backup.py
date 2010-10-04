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
Backup the current system

Arguments:
    <override> := -?( /path/to/include/or/exclude | mysql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Options:
    --address=TARGET_URL      manual backup target URL
                              default: automatically configured via Hub

    -s --simulate             Simulate operation. Don't actually backup.
                              Useful for inspecting /TKLBAM by hand.

    -q --quiet                Be less verbose
    --logfile=PATH            Path of file to log to
                              default: $LOGFILE

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

import datetime
from string import Template

import hub
import backup
import hooks
from registry import registry

from version import get_turnkey_version
from stdtrap import UnitedStdTrap

from utils import is_writeable

PATH_LOGFILE = "/var/log/tklbam-backup"

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ override ... ]" % sys.argv[0]
    tpl = Template(__doc__.strip())
    conf = backup.BackupConf()
    print >> sys.stderr, tpl.substitute(CONF_PATH=conf.paths.conf,
                                        CONF_OVERRIDES=conf.paths.overrides,
                                        CONF_VOLSIZE=conf.volsize,
                                        CONF_FULL_BACKUP=conf.full_backup,
                                        LOGFILE=PATH_LOGFILE)
    sys.exit(1)

def warn(e):
    print >> sys.stderr, "warning: " + str(e)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

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
                                        'logfile=',
                                        'simulate', 'quiet', 
                                        'checkpoint-restore',
                                        'profile=', 'secretfile=', 'address=',
                                        'volsize=', 'full-backup='])
    except getopt.GetoptError, e:
        usage(e)

    opt_logfile = PATH_LOGFILE

    conf = backup.BackupConf()
    conf.secretfile = registry.path.secret

    for opt, val in opts:
        if opt in ('-s', '--simulate'):
            conf.simulate = True

        elif opt == '--profile':
            conf.profile = val

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

        elif opt == '--checkpoint-restore':
            conf.checkpoint_restore = True

        elif opt == '--logfile':
            if not is_writeable(val):
                fatal("logfile '%s' is not writeable" % val)
            opt_logfile = val

        elif opt in ('-h', '--help'):
            usage()

    conf.overrides += args

    hb = hub.Backups(registry.sub_apikey)
    if not conf.profile:
        conf.profile = get_profile(hb)

    if not conf.address:
        try:
            registry.credentials = hb.get_credentials()
        except hb.Error, e:
            # asking for get_credentials() might fail if the hub is down. 
            # But If we already have the credentials we can survive that.
            if isinstance(e, hub.NotSubscribedError) or not registry.credentials:
                raise
            warn(e)

        conf.credentials = registry.credentials

        if registry.hbr:
            try:
                registry.hbr = hb.get_backup_record(registry.hbr.backup_id)
            except hb.Error, e:
                # if the Hub is down we can hope that the cached address 
                # is still valid and warn and try to backup anyway.
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

    b = backup.Backup(conf)
    try:
        trap = UnitedStdTrap(transparent=True)
        try:
            hooks.backup.pre()
            b.run()
            hooks.backup.post()
        finally:
            trap.close()
            fh = file(opt_logfile, "a")

            timestamp = "### %s ###" % datetime.datetime.now().ctime()
            print >> fh, "#" * len(timestamp)
            print >> fh, timestamp
            print >> fh, "#" * len(timestamp)

            fh.write(trap.std.read())
            fh.close()
            
    except:
        if not conf.checkpoint_restore:
            b.cleanup()
        raise

    b.cleanup()
    if not conf.simulate:
        hb.updated_backup(conf.address)

if __name__=="__main__":
    main()

