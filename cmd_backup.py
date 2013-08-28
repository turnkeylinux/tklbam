#!/usr/bin/python
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
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
    --dump=path/to/extract/        Dump a raw backup extract to path
                                   Tip: tklbam-restore path/to/raw/extract/

    --address=TARGET_URL           manual backup target URL
                                   default: S3 storage bucket automatically configured via Hub

    --resume                       Resume aborted backup session
    --disable-resume               Disable implicit --resume when rerunning an aborted backup

    --simulate                     Do a dry run simulation of the backup.

    -q --quiet                     Be less verbose
    --logfile=PATH                 Path of file to log to
                                   default: $LOGFILE

    --debug                        Run $$SHELL before Duplicity

Configurable options:

    --volsize MB                   Size of backup volume in MBs
                                   default: $CONF_VOLSIZE

    --s3-parallel-uploads=N        Number of parallel volume chunk uploads
                                   default: $CONF_S3_PARALLEL_UPLOADS

    --full-backup FREQUENCY        Time frequency of full backup
                                   default: $CONF_FULL_BACKUP

                                   format := now | <int>[mhDWM]

                                     e.g.,
                                     now - always do a full backup

                                     60m - 60 minutes
                                     12h - 12 hours
                                     3D - three days
                                     2W - two weeks
                                     1M - one month

    --skip-files                   Don't backup filesystem
    --skip-database                Don't backup databases
    --skip-packages                Don't backup new packages

    --force-profile=PROFILE_ID     Force a specific backup profile

Resolution order for configurable options:

  1) command line (highest precedence)
  2) configuration file ($CONF_PATH)
  3) built-in default (lowest precedence)

Configuration file format ($CONF_PATH):

  <option-name> <value>

"""

import os
from os.path import *

import sys
import getopt

import time
import datetime
from string import Template

from pidlock import PidLock

import hub
import backup
import duplicity

import hooks
from registry import registry
from conf import Conf

from version import get_turnkey_version
from stdtrap import UnitedStdTrap

from utils import is_writeable
import traceback

PATH_LOGFILE = "/var/log/tklbam-backup"

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ override ... ]" % sys.argv[0]
    tpl = Template(__doc__.strip())
    conf = Conf()
    print >> sys.stderr, tpl.substitute(CONF_PATH=conf.paths.conf,
                                        CONF_OVERRIDES=conf.paths.overrides,
                                        CONF_VOLSIZE=conf.volsize,
                                        CONF_FULL_BACKUP=conf.full_backup,
                                        CONF_S3_PARALLEL_UPLOADS=conf.s3_parallel_uploads,
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

def get_server_id():
    try:
        return ServerConf()['serverid']
    except KeyError:
        return None

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'qh',
                                       ['help',
                                        'dump=',
                                        'skip-files', 'skip-database', 'skip-packages',
                                        'debug',
                                        'resume', 'disable-resume',
                                        'logfile=',
                                        'simulate', 'quiet',
                                        'force-profile=', 'secretfile=', 'address=',
                                        'volsize=', 's3-parallel-uploads=', 'full-backup='])
    except getopt.GetoptError, e:
        usage(e)

    opt_dump_path = None

    opt_debug = False
    opt_resume = None
    opt_disable_resume = False
    opt_logfile = PATH_LOGFILE

    conf = Conf()
    conf.secretfile = registry.path.secret

    for opt, val in opts:
        if opt == '--dump':
            opt_dump_path = val

            if exists(opt_dump_path):
                if not isdir(opt_dump_path):
                    fatal("--dump=%s is not a directory" % opt_dump_path)

                if os.listdir(opt_dump_path) != []:
                    fatal("--dump=%s is not an empty directory" % opt_dump_path)
                
            else:
                os.mkdir(opt_dump_path)

            opt_disable_resume = True
            conf.verbose = False

        elif opt == '--simulate':
            conf.simulate = True

        elif opt == '--resume':
            opt_resume = True

        elif opt == '--disable-resume':
            opt_disable_resume = True

        elif opt == '--force-profile':
            conf.force_profile = val

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

        elif opt == '--s3-parallel-uploads':
            conf.s3_parallel_uploads = val

        elif opt == '--full-backup':
            conf.full_backup = val

        elif opt == '--logfile':
            if not is_writeable(val):
                fatal("logfile '%s' is not writeable" % val)
            opt_logfile = val

        elif opt == '--debug':
            opt_debug = True

        elif opt == '--skip-files':
            conf.backup_skip_files = True

        elif opt == '--skip-database':
            conf.backup_skip_database = True

        elif opt == '--skip-packages':
            conf.backup_skip_packages = True

        elif opt in ('-h', '--help'):
            usage()

    conf.overrides += args

    if opt_resume:
        # explicit resume
        if conf.simulate:
            fatal("--resume and --simulate incompatible: you can only resume real backups")

        if opt_disable_resume:
            fatal("--resume and --disable-resume incompatible")

        if registry.backup_resume_conf is None:
            fatal("no previous backup session to resume from")

    if conf.simulate and registry.backup_resume_conf and not opt_disable_resume:
        fatal("--simulate will destroy your aborted backup session. To force use --disable-resume")

    if conf.simulate and opt_dump_path:
        fatal("--simulate and --dump incompatible")

    lock = PidLock("/var/run/tklbam-backup.pid", nonblock=True)
    try:
        lock.lock()
    except lock.Locked:
        fatal("a previous backup is still in progress")

    if conf.s3_parallel_uploads > 1 and conf.s3_parallel_uploads > (conf.volsize / 5):
        warn("s3-parallel-uploads > volsize / 5 (minimum upload chunk is 5MB)")

    hb = hub.Backups(registry.sub_apikey)
    try:
        registry.update_profile(hb, conf.force_profile)
    except registry.CachedProfile, e:
        warn(e)
    except registry.ProfileNotFound, e:
        print >> sys.stderr, "TurnKey Hub Error: %s" % str(e)
        if not conf.force_profile:
            # be extra nice to people who aren't using --force-profile
            print """
This probably means that TKLBAM doesn't yet fully support your system.
If you're feeling adventurous you can force another profile with the
--force-profile option. Sorry about that."""

        sys.exit(1)

    credentials = None
    if not conf.address and not opt_dump_path:
        try:
            registry.credentials = hb.get_credentials()
        except hb.Error, e:
            # asking for get_credentials() might fail if the hub is down.
            # But If we already have the credentials we can survive that.

            if isinstance(e, hub.NotSubscribedError):
                fatal(e)

            if not registry.credentials:
                pass

            warn("using cached backup credentials: " + e.description)

        credentials = registry.credentials

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
                    warn("using cached backup record: " + str(e))

        if not registry.hbr:
            registry.hbr = hb.new_backup_record(registry.key,
                                                get_turnkey_version(),
                                                get_server_id())

        conf.address = registry.hbr.address

    if opt_resume:
        conf = registry.backup_resume_conf
    else:
        # implicit resume
        if not conf.simulate and not opt_disable_resume and registry.backup_resume_conf == conf:
            print "Implicit --resume: Detected a rerun of an aborted backup session"
            print "                   You can disable this with the --disable-resume option"
            print
            time.sleep(5)

            opt_resume = True

    registry.backup_resume_conf = None
    if not conf.simulate:
        registry.backup_resume_conf = conf

    is_hub_address = not conf.simulate and registry.hbr and registry.hbr.address == conf.address
    backup_id = registry.hbr.backup_id

    trap = UnitedStdTrap(transparent=True)
    try:
        hooks.backup.pre()
        b = backup.Backup(registry.profile, 
                          conf.overrides, 
                          conf.backup_skip_packages, conf.backup_skip_packages, conf.backup_skip_database, 
                          opt_resume, conf.verbose)
        try:
            if is_hub_address:
                try:
                    hb.set_backup_inprogress(backup_id, True)
                except hb.Error, e:
                    warn("can't update Hub of backup in progress: " + str(e))

            hooks.backup.inspect(b.extras_paths.path)

            if opt_debug or opt_dump_path:
                trap.close()
                trap = None

            if opt_dump_path:
                b.dump(opt_dump_path)
            else:
                def _print(s):
                    print "\n# " + str(s)

                if conf.verbose:
                    _print("export PASSPHRASE=$(cat %s)" % conf.secretfile)

                secret = file(conf.secretfile).readline().strip()
                target = duplicity.Target(conf.address, credentials, secret)

                uploader = duplicity.Uploader(conf.verbose, 
                                              conf.volsize, 
                                              conf.full_backup, 
                                              conf.s3_parallel_uploads,
                                              includes=[ b.extras_paths.path ],
                                              include_filelist=b.extras_paths.fsdelta_olist,
                                              excludes=[ '**' ])

                force_cleanup = not b.resume

                uploader('/', target, force_cleanup, dry_run=conf.simulate, debug=opt_debug, 
                         log=(_print if conf.verbose else None))

            hooks.backup.post()
        except:
            if not conf.checkpoint_restore:
                b.cleanup()

            # not cleaning up
            raise

    finally:
        if is_hub_address:
            try:
                hb.set_backup_inprogress(backup_id, False)
            except hb.Error, e:
                warn("can't update Hub backup completed: " + str(e))

        if trap:
            sys.stdout.flush()
            sys.stderr.flush()

            trap.close()
            if not conf.simulate:
                fh = file(opt_logfile, "a")

                timestamp = "### %s ###" % datetime.datetime.now().ctime()
                print >> fh
                print >> fh, "#" * len(timestamp)
                print >> fh, timestamp
                print >> fh, "#" * len(timestamp)
                print >> fh

                fh.write(trap.std.read())
                if sys.exc_type:
                    print >> fh
                    traceback.print_exc(file=fh)
                fh.close()

    if conf.simulate:
        print "Completed --simulate: Leaving /TKLBAM intact so you can manually inspect it"
    else:
        b.cleanup()

    registry.backup_resume_conf = None

    if not (conf.simulate or opt_dump_path):
        try:
            hb.updated_backup(conf.address)
        except:
            pass

if __name__=="__main__":
    main()
