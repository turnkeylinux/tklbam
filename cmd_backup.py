#!/usr/bin/python2
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Backup the current system

Arguments:
    <override> := -?( /path/to/include/or/exclude | mysql:database[/table] | pgsql:database[/table] )

    Default overrides read from $CONF_OVERRIDES

Options:
    --dump=path/to/extract/        Dump a raw backup extract to path
                                   Tip: tklbam-restore path/to/raw/extract/

    --raw-upload=PATH              Use Duplicity to upload raw path contents to --address

    --address=TARGET_URL           custom backup target URL
                                   default: S3 storage bucket automatically configured via Hub

      Supported storage backends and their URL formats:

          file:///some_dir
          rsync://user[:password]@other.host[:port]//absolute_path
          rsync://user[:password]@other.host[:port]/relative_path
          rsync://user[:password]@other.host[:port]::/module/some_dir
          s3://other.host/bucket_name[/prefix]
          s3+http://bucket_name[/prefix]
          ftp://user[:password]@other.host[:port]/some_dir
          ftps://user[:password]@other.host[:port]/some_dir
          hsi://user[:password]@other.host[:port]/some_dir
          imap://user[:password]@other.host[:port]/some_dir
          scp://user[:password]@other.host[:port]/some_dir
          ssh://user[:password]@other.host[:port]/some_dir
          tahoe://alias/directory
          webdav://user[:password]@other.host/some_dir
          webdavs://user[:password]@other.host/some_dir
          gdocs://user[:password]@other.host/some_dir

    --resume                       Resume aborted backup session
    --disable-resume               Disable implicit --resume when rerunning an aborted backup

    --simulate                     Do a dry run simulation of the backup.

    -q --quiet                     Be less verbose (only print summary backup statistics)
    --logfile=PATH                 Path of file to log verbosely to
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

    --force-profile=PROFILE_ID     Force backup profile (e.g., "core")
                                   default: cat /etc/turnkey_version

Resolution order for configurable options:

  1) command line (highest precedence)
  2) configuration file ($CONF_PATH)
  3) built-in default (lowest precedence)

Configuration file format ($CONF_PATH):

  <option-name> <value>

Examples:

    # Full system-level backup
    tklbam-backup

    # Same result as above but in two steps: first dump to a directory, then upload it
    tklbam-backup --dump=/tmp/mybackup
    tklbam-backup --raw-upload=/tmp/mybackup

    # Backup Duplicity archives to a custom address on the local filesystem
    tklbam-backup --address=file:///mnt/backups/mybackup
    tklbam-escrow this-keyfile-needed-to-restore-mybackup.escrow

    # Simulate a backup that excludes the mysql customers DB and the 'emails' table in the webapp DB
    # Tip: usually you'd want to configure excludes in /etc/tklbam/overrides
    tklbam-backup --simulate -- -/srv -mysql:customers -mysql:webapp/emails

    # Create separate backups with unique backup ids containing the previously excluded items
    # Tip: use tklbam-status after tklbam-backup to determine the Hub backup ID
    export TKLBAM_REGISTRY=/var/lib/tklbam.customers-and-webapp-emails
    tklbam-backup --skip-files --skip-packages -- mysql:customers mysql:webapp/emails

    export TKLBAM_REGISTRY=/var/lib/tklbam.raw-srv
    tklbam-backup --raw-upload=/srv

"""

import os
from os.path import *

import sys
import getopt

import re
import time
import shutil

from string import Template

from pidlock import PidLock

import hub
import backup
import duplicity

import hooks
from registry import registry, update_profile, hub_backups
from conf import Conf

from version import detect_profile_id
from stdtrap import UnitedStdTrap

from utils import is_writeable, fmt_title, fmt_timestamp, path_global_or_local

import traceback

PATH_LOGFILE = path_global_or_local("/var/log/tklbam-backup", registry.path.backup_log)
PATH_PIDLOCK = path_global_or_local("/var/run/tklbam-backup.pid", registry.path.backup_pid)

def usage(e=None):
    from paged import stdout

    if e:
        print("error: " + str(e), file=stdout)

    print("Usage: %s [ -options ] [ override ... ]" % sys.argv[0], file=stdout)
    tpl = Template(__doc__.strip())
    conf = Conf()
    print(tpl.substitute(CONF_PATH=conf.paths.conf,
                                    CONF_OVERRIDES=conf.paths.overrides,
                                    CONF_VOLSIZE=conf.volsize,
                                    CONF_FULL_BACKUP=conf.full_backup,
                                    CONF_S3_PARALLEL_UPLOADS=conf.s3_parallel_uploads,
                                    LOGFILE=PATH_LOGFILE), file=stdout)
    sys.exit(1)

def warn(e):
    print("warning: " + str(e), file=sys.stderr)

def fatal(e):
    print("error: " + str(e), file=sys.stderr)
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
                                        'raw-upload=',
                                        'skip-files', 'skip-database', 'skip-packages',
                                        'debug',
                                        'resume', 'disable-resume',
                                        'logfile=',
                                        'simulate', 'quiet',
                                        'force-profile=', 'secretfile=', 'address=',
                                        'volsize=', 's3-parallel-uploads=', 'full-backup='])
    except getopt.GetoptError as e:
        usage(e)

    raw_upload_path = None
    dump_path = None

    opt_verbose = True
    opt_simulate = False
    opt_debug = False
    opt_resume = None
    opt_disable_resume = False
    opt_logfile = PATH_LOGFILE

    conf = Conf()
    conf.secretfile = registry.path.secret

    for opt, val in opts:
        if opt == '--dump':
            dump_path = val

            if exists(dump_path):
                if not isdir(dump_path):
                    fatal("--dump=%s is not a directory" % dump_path)

                if os.listdir(dump_path) != []:
                    fatal("--dump=%s is not an empty directory" % dump_path)

            else:
                os.mkdir(dump_path)

            opt_disable_resume = True

        elif opt == '--raw-upload':
            if not isdir(val):
                fatal("%s=%s is not a directory" % (opt, val))

            raw_upload_path = val

        elif opt == '--simulate':
            opt_simulate = True

        elif opt == '--resume':
            opt_resume = True

        elif opt == '--disable-resume':
            opt_disable_resume = True

        elif opt == '--force-profile':
            conf.force_profile = val

        elif opt in ('-q', '--quiet'):
            opt_verbose = False

        elif opt == '--secretfile':
            if not exists(val):
                usage("secretfile %s does not exist" % repr(val))
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

    if dump_path:
        for opt, val in opts:
            if opt[2:] in ('simulate', 'raw-upload', 'volsize', 's3-parallel-uploads', 'full-backup', 'address', 'resume', 'disable-resume', 'raw-upload'):
                fatal("%s incompatible with --dump=%s" % (opt, dump_path))

    conf.overrides += args

    if opt_resume:
        # explicit resume
        if opt_simulate:
            fatal("--resume and --simulate incompatible: you can only resume real backups")

        if opt_disable_resume:
            fatal("--resume and --disable-resume incompatible")

        if registry.backup_resume_conf is None:
            fatal("no previous backup session to resume from")

    if opt_simulate and registry.backup_resume_conf and not opt_disable_resume:
        fatal("--simulate will destroy your aborted backup session. To force use --disable-resume")


    lock = PidLock(PATH_PIDLOCK, nonblock=True)
    try:
        lock.lock()
    except lock.Locked:
        fatal("a previous backup is still in progress")

    if conf.s3_parallel_uploads > 1 and conf.s3_parallel_uploads > (conf.volsize / 5):
        warn("s3-parallel-uploads > volsize / 5 (minimum upload chunk is 5MB)")

    if not raw_upload_path:
        try:
            update_profile(conf.force_profile)
        except hub.Backups.NotInitialized as e:
            fatal("you need a profile to backup, run tklbam-init first")

    credentials = None
    if not conf.address and not dump_path:
        try:
            hb = hub_backups()
        except hub.Backups.NotInitialized as e:
            fatal(str(e) + "\n" +
                  "tip: you can still use tklbam-backup with --dump or --address")

        try:
            registry.credentials = hb.get_credentials()
        except hb.Error as e:
            # asking for get_credentials() might fail if the hub is down.
            # But If we already have the credentials we can survive that.

            if isinstance(e, hub.NotSubscribed) or \
                    not registry.credentials or \
                    registry.credentials.type == 'iamrole':
                fatal(e)

            warn("using cached backup credentials: " + e.description)

        credentials = registry.credentials

        if registry.hbr:
            try:
                registry.hbr = hb.get_backup_record(registry.hbr.backup_id)
            except hb.Error as e:
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
                                                detect_profile_id(),
                                                get_server_id())

        conf.address = registry.hbr.address

    if opt_resume:
        conf = registry.backup_resume_conf
    else:
        # implicit resume
        if not opt_simulate and not opt_disable_resume and registry.backup_resume_conf == conf:
            print("Implicit --resume: Detected a rerun of an aborted backup session")
            print("                   You can disable this with the --disable-resume option")
            print()
            time.sleep(5)

            opt_resume = True

    registry.backup_resume_conf = None
    if not opt_simulate:
        registry.backup_resume_conf = conf

    secret = file(conf.secretfile).readline().strip()
    target = duplicity.Target(conf.address, credentials, secret)

    if not (opt_simulate or opt_debug or dump_path):
        log_fh = file(opt_logfile, "a")

        print(file=log_fh)
        print("\n" + fmt_timestamp(), file=log_fh)

        log_fh.flush()

        trap = UnitedStdTrap(usepty=True, transparent=opt_verbose, tee=log_fh)

    else:
        trap = None

    def backup_inprogress(bool):
        is_hub_address = registry.hbr and registry.hbr.address == conf.address
        if is_hub_address and not (dump_path or opt_simulate):
            try:
                hb.set_backup_inprogress(registry.hbr.backup_id, bool)
            except hb.Error as e:
                warn("can't update Hub of backup %s: %s" % ("in progress" if bool else "completed", str(e)))

    try:
        backup_inprogress(True)

        def _print(s):
            if s == "\n":
                print()
            else:
                print("# " + str(s))

        if raw_upload_path:
            print(fmt_title("Executing Duplicity to backup %s to %s" % (raw_upload_path, target.address)))

            _print("export PASSPHRASE=$(cat %s)" % conf.secretfile)
            uploader = duplicity.Uploader(True,
                                          conf.volsize,
                                          conf.full_backup,
                                          conf.s3_parallel_uploads)
            uploader(raw_upload_path, target, force_cleanup=not opt_resume, dry_run=opt_simulate, debug=opt_debug,
                     log=_print)

        else:
            hooks.backup.pre()
            b = backup.Backup(registry.profile,
                              conf.overrides,
                              conf.backup_skip_files, conf.backup_skip_packages, conf.backup_skip_database,
                              opt_resume, True, dump_path if dump_path else "/")

            hooks.backup.inspect(b.extras_paths.path)

            if dump_path:
                b.dump(dump_path)
            else:
                print("\n" + fmt_title("Executing Duplicity to backup system changes to encrypted, incremental archives"))
                _print("export PASSPHRASE=$(cat %s)" % conf.secretfile)

                uploader = duplicity.Uploader(True,
                                              conf.volsize,
                                              conf.full_backup,
                                              conf.s3_parallel_uploads,
                                              includes=[ b.extras_paths.path ],
                                              include_filelist=b.extras_paths.fsdelta_olist
                                                               if exists(b.extras_paths.fsdelta_olist)
                                                               else None,
                                              excludes=[ '**' ])

                uploader('/', target, force_cleanup=not b.resume, dry_run=opt_simulate, debug=opt_debug,
                         log=_print)

            hooks.backup.post()

            if opt_simulate:
                print("Completed --simulate: Leaving %s intact so you can manually inspect it" % b.extras_paths.path)
            else:
                if not dump_path:
                    shutil.rmtree(b.extras_paths.path)

    except:
        if trap:
            print(file=log_fh)
            traceback.print_exc(file=log_fh)

        raise

    finally:
        backup_inprogress(False)
        if trap:
            sys.stdout.flush()
            sys.stderr.flush()

            trap.close()
            log_fh.close()

    if not opt_verbose and trap:
        # print only the summary
        output = trap.std.read()
        m = re.search(r'(^---+\[ Backup Statistics \]---+.*)', output, re.M | re.S)
        if m:
            stats = m.group(1)
            print(stats.strip())

    registry.backup_resume_conf = None

    if not (opt_simulate or dump_path):
        try:
            hb.updated_backup(conf.address)
        except:
            pass

    if not opt_simulate:
        print("\nTIP: test your backups with a trial restore BEFORE something bad happens.")

if __name__=="__main__":
    main()
