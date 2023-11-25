#!/usr/bin/python3
#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Restore a backup

Arguments:

    <hub-backup> := backup-id || unique label pattern || path/to/backup/extract

Options / General:

    --raw-download=PATH               Use Duplicity to download raw backup extract
                                      without performing a system restore

Options / Duplicity:

    --time=TIME                       Time to restore Duplicity backup archive from

      TIME := YYYY-MM-DD | YYYY-MM-DDThh:mm:ss | <int>[mhDWMY]

              2010-08-06 - 2010, August 6th, 00:00

              2010-08-07T14:00 - 2010, August 7th 14:00 UTC

              6m - 6 minutes
              5h - 5 hours
              4D - 4 days ago
              3W - 3 weeks ago
              2M - 2 months ago
              1Y - 1 year ago

    --keyfile=KEYFILE                 Path to tklbam-escrow created keyfile
                                      default: automatically retrieved from the Hub

    --address=TARGET_URL              custom backup target URL (needs --keyfile)
                                      default: S3 storage bucket automatically provided by Hub

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

Options / System restore:

    --simulate                        Do a dry run simulation of the system restore

    --limits="LIMIT-1 .. LIMIT-N"     Restore filesystem or database limitations

      LIMIT := -?( /path/to/include/or/exclude | mysql:database[/table] | pgsql:database[/table] )

    --skip-files                      Don't restore filesystem
    --skip-database                   Don't restore databases
    --skip-packages                   Don't restore new packages

    --logfile=PATH                    Path to log file
                                      default: /var/log/tklbam-restore

    --no-rollback                     Disable rollback
    --silent                          Disable feedback


    --noninteractive                  Disable interactive user prompts
    --force                           Disable sanity checking

    --debug                           Run interactive shell before Duplicity and before system restore

Options / Configurable (see resolution order below):

    --restore-cache-size=SIZE         The maximum size of the download cache
                                      default: $CONF_RESTORE_CACHE_SIZE

    --restore-cache-dir=PATH          The path to the download cache directory
                                      default: $CONF_RESTORE_CACHE_DIR

Resolution order for configurable options:

  1) command line (highest precedence)
  2) configuration file ($CONF_PATH)
  3) built-in default (lowest precedence)

Configuration file format ($CONF_PATH):

  <option-name> <value>

Examples:

    # Restore Hub backup id 1
    tklbam-restore 1

    # Same result as above but in two steps: first download the extract, then apply it
    tklbam-restore 1 --raw-download=/tmp/mybackup
    tklbam-restore /tmp/mybackup

    # Restore backup created with tklbam-backup --raw-upload=/srv
    tklbam-restore 2 --raw-download=/srv

    # Restore from Duplicity archives at a custom backup address on the local filesystem
    tklbam-restore --address=file:///mnt/backups/mybackup --keyfile=mybackup.escrow

    # Simulate restoring Hub backup id 1 while excluding changes to the /root path,
    # mysql 'customers' DB, and the 'emails' table in the 'webapps' DB
    tklbam-restore 1 --simulate --limits="-/root -mysql:customers -mysql:webapp/emails"

    # Simulate restoring only the /root files in Hub backup id 1
    tklbam-restore 1 --simulate --skip-database --skip-packages --limits="/root"

"""

import os
import sys
import getopt

from string import Template
import re
import shlex
from typing import NoReturn, Optional

from os.path import exists, isdir, isfile, join
import subprocess
from restore import Restore
import duplicity

import logging

from stdtrap import UnitedStdTrap
from temp import TempDir

import hub
import keypacket
import passphrase
import hooks

from registry import registry, update_profile, hub_backups

from version import TurnKeyVersion
from utils import is_writeable, fmt_timestamp, fmt_title, path_global_or_local

from conf import Conf

import backup
import traceback

logging.basicConfig(level=logging.DEBUG)

PATH_LOGFILE = path_global_or_local("/var/log/tklbam-restore", registry.path.restore_log)

class Error(Exception):
    pass

class ExitCode:
    OK = 0
    INCOMPATIBLE = 10
    BADPASSPHRASE = 11

def do_compatibility_check(backup_profile_id: str, interactive: bool = True) -> None:
    # unless both backup and restore are TurnKey skip compatibility check
    logging.info(f"do_compatibility_check({backup_profile_id=}, {interactive=})")

    try:
        bkup = TurnKeyVersion.from_string(backup_profile_id)
        assert bkup != None
        backup_codename = bkup.codename
    except TurnKeyVersion.Error:
        return None

    turnkey_version = TurnKeyVersion.from_system()
    if not turnkey_version:
        return None

    local_codename = turnkey_version.codename

    if local_codename == backup_codename:
        return None

    def fmt(s: str) -> str:
        return s.upper().replace("-", " ")

    backup_codename = fmt(backup_codename)
    local_codename = fmt(local_codename)

    print("WARNING: INCOMPATIBLE APPLIANCE BACKUP")
    print("======================================")
    print()
    print("Restoring a %s backup to a %s appliance may create complications." % (backup_codename, local_codename))
    print("For best results try restoring instead to a fresh %s installation." % backup_codename)

    if not interactive:
        sys.exit(ExitCode.INCOMPATIBLE)

    print()
    print("(Use --force to suppress this check)")
    print()

    while True:
        answer = input("Do you want to continue? [yes/no] ")
        if answer:
            break

    if answer.lower() not in ('y', 'yes'):
        fatal("You didn't answer 'yes'. Aborting!")

def get_backup_record(arg: str) -> hub.BackupRecord:
    logging.info(f"get_backup_record({arg=})")
    hb = hub_backups()
    if re.match(r'^\d+$', arg):
        backup_id = arg

        try:
            return hb.get_backup_record(backup_id)
        except hub.InvalidBackupError:
            raise Error('invalid backup id (%s)' % backup_id)

    # treat our argument as a pattern
    matches = [ hbr for hbr in hb.list_backups()
                if re.search(arg, hbr.label, re.IGNORECASE) ]

    if not matches:
        raise Error("'%s' doesn't match any backup labels" % arg)

    if len(matches) > 1:
        raise Error("'%s' matches more than one backup label" % arg)

    return matches[0]

def decrypt_key(key: str, interactive: bool = True) -> bytes:
    logging.info(f"decrypt_key({key=}, {interactive=})")
    try:
        return keypacket.parse(key.encode(), b"")
    except keypacket.Error:
        pass

    while True:
        try:
            if interactive:
                p = passphrase.get_passphrase(confirm=False)
            else:
                print("Passphrase: ")
                p = sys.stdin.readline().strip()

            return keypacket.parse(key.encode(), p.encode())

        except keypacket.Error:
            if not interactive:
                print("Incorrect passphrase", file=sys.stderr)
                sys.exit(ExitCode.BADPASSPHRASE)

            print("Incorrect passphrase, try again", file=sys.stderr)

def warn(e: str) -> None:
    print("warning: " + str(e), file=sys.stderr)

def fatal(e: str|Error) -> NoReturn:
    print("error: " + str(e), file=sys.stderr)
    sys.exit(1)

def usage(e: Optional[str|getopt.GetoptError] = None) -> NoReturn:
    from paged import stdout

    if e:
        print("error: " + str(e), file=stdout)

    print("Usage: %s [ -options ] <hub-backup>" % sys.argv[0], file=stdout)
    print("Usage: %s [ -options ] --address=<address> --keyfile=path/to/key.escrow" % sys.argv[0], file=stdout)

    tpl = Template(__doc__.strip())
    conf = Conf()
    print(tpl.substitute(CONF_PATH=conf.paths.conf,
                                    CONF_RESTORE_CACHE_SIZE=conf.restore_cache_size,
                                    CONF_RESTORE_CACHE_DIR=conf.restore_cache_dir), file=stdout)

    sys.exit(1)

def main():
    logging.info('main()')
    backup_extract_path = None
    raw_download_path = None

    opt_simulate = False
    opt_force = False
    opt_time = None
    opt_limits = []
    opt_key = None
    opt_address = None
    opt_logfile = PATH_LOGFILE

    skip_files = False
    skip_database = False
    skip_packages = False
    no_rollback = False
    silent = False
    interactive = True

    opt_debug = False
    log_fh = None

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h',
                                       ['raw-download=',
                                        'help',
                                        'simulate',
                                        'limits=', 'address=', 'keyfile=',
                                        'logfile=',
                                        'restore-cache-size=', 'restore-cache-dir=',
                                        'force',
                                        'time=',
                                        'silent',
                                        'noninteractive',
                                        'debug',
                                        'skip-files', 'skip-database', 'skip-packages',
                                        'no-rollback'])
    except getopt.GetoptError as e:
        usage(e)

    conf = Conf()

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        elif opt == '--raw-download':
            raw_download_path = val
            if exists(raw_download_path):
                if not isdir(raw_download_path):
                    fatal("%s=%s is not a directory" % (opt, val))

            else:
                os.mkdir(raw_download_path)

        elif opt == '--simulate':
            opt_simulate = True
        elif opt == '--limits':
            opt_limits += shlex.split(val)
        elif opt == '--keyfile':
            if not isfile(val):
                fatal("keyfile %s does not exist or is not a file" % repr(val))

            with open(val) as fob:
                opt_key = fob.read()
            try:
                keypacket.fingerprint(opt_key.encode())
            except keypacket.Error:
                fatal("'%s' is not a valid keyfile created with tklbam-escrow" % val)

        elif opt == '--address':
            opt_address = val
        elif opt == '--time':
            opt_time = val
        elif opt == '--skip-files':
            skip_files = True
        elif opt == '--skip-database':
            skip_database = True
        elif opt == '--skip-packages':
            skip_packages = True
        elif opt == '--no-rollback':
            no_rollback = True
        elif opt == '--silent':
            silent = True
        elif opt == '--force':
            opt_force = True
        elif opt == '--logfile':
            if not is_writeable(val):
                fatal("logfile '%s' is not writeable" % val)
            opt_logfile = val

        elif opt == '--noninteractive':
            interactive = False

        elif opt == '--restore-cache-size':
            conf.restore_cache_size = val

        elif opt == '--restore-cache-dir':
            conf.restore_cache_dir = val

        elif opt == '--debug':
            opt_debug = True
    logging.info('vars after parsing args:\n'
                 f'{backup_extract_path=}\n'
                 f'{raw_download_path=}\n'
                 f'{opt_simulate=}\n'
                 f'{opt_force=}\n'
                 f'{opt_time=}\n'
                 f'{opt_limits=}\n'
                 f'{opt_key=}\n'
                 f'{opt_address=}\n'
                 f'{opt_logfile=}\n'
                 f'{skip_files=}\n'
                 f'{skip_database=}\n'
                 f'{skip_packages=}\n'
                 f'{no_rollback=}\n'
                 f'{silent=}\n'
                 f'{interactive=}\n'
                 f'{opt_debug=}\n')

    for opt, val in opts:
        for skip_opt in ('files', 'packages', 'database'):
            if opt != '--skip-' + skip_opt:
                continue

            os.environ['TKLBAM_RESTORE_SKIP_' + skip_opt.upper()] = 'yes'

    if raw_download_path:
        if not opt_force and os.listdir(raw_download_path) != []:
            fatal("--raw-download=%s is not an empty directory, use --force if that is ok" % raw_download_path)

    restore_cache_size = conf.restore_cache_size
    restore_cache_dir = conf.restore_cache_dir

    hbr = None
    credentials = None

    if args:
        if len(args) != 1:
            usage("incorrect number of arguments")

        arg = args[0]

        if isdir(join(arg, backup.ExtrasPaths.PATH)):
            backup_extract_path = arg
        else:
            try:
                try:
                    hbr = get_backup_record(arg)
                except hub.Backups.NotInitialized as e:
                    print("error: " + str(e), file=sys.stderr)
                    print("tip: you can still use tklbam-restore with --address or a backup extract", file=sys.stderr)

                    sys.exit(1)

                credentials = hub.Backups(registry.sub_apikey).get_credentials()
            except Error as e:
                fatal(e)

    else:
        if not opt_address:
            usage()

    def get_backup_extract() -> str:
        print(fmt_title("Executing Duplicity to download %s to %s " % (address, raw_download_path)))
        downloader(raw_download_path, target, log=_print if not silent else None, debug=opt_debug, force=opt_force)
        if raw_download_path:
            return raw_download_path
        return ''

    if backup_extract_path:
        for opt, val in opts:
            if opt[2:] in ('time', 'keyfile', 'address', 'restore-cache-size', 'restore-cache-dir'):
                fatal("%s is incompatible with restoring from path %s" % (opt, backup_extract_path))

    else:
        if opt_address:
            if hbr:
                fatal("a manual --address is incompatible with a <backup-id>")

            if not opt_key:
                fatal("a manual --address needs a tklbam-escrow created --keyfile")

        address = hbr.address if hbr else opt_address

        if hbr:
            if not opt_force and not raw_download_path:
                do_compatibility_check(hbr.profile_id, interactive)

            if opt_key and \
               keypacket.fingerprint(hbr.key) != keypacket.fingerprint(opt_key.encode()):

                fatal("invalid escrow key for the selected backup")

        assert hbr != None
        key = opt_key if opt_key else hbr.key
        secret = decrypt_key(key, interactive)

        target = duplicity.Target(address, credentials, secret)
        downloader = duplicity.Downloader(opt_time, restore_cache_size, restore_cache_dir)

        def _print(s: str) -> None:
            print(s)

        if raw_download_path:
            get_backup_extract()
            return
        else:
            raw_download_path = TempDir(prefix=b"tklbam-")
            os.chmod(raw_download_path, 0o700)

    assert conf.force_profile != None
    update_profile(conf.force_profile, strict=False)

    if not (opt_simulate or opt_debug):
        with open(opt_logfile, "a") as log_fh:

            print(file=log_fh)
            print("\n" + fmt_timestamp(), file=log_fh)

            log_fh.flush()
            trap = UnitedStdTrap(usepty=True, transparent=(False if silent else True), tee=log_fh)
    else:
        trap = None

    try:
        hooks.restore.pre()

        if not backup_extract_path:
            backup_extract_path = get_backup_extract()

        extras_paths = backup.ExtrasPaths(backup_extract_path)

        if not isdir(extras_paths.path):
            fatal("missing %s directory - this doesn't look like a system backup" % extras_paths.path)

        assert backup_extract_path != None
        os.environ['TKLBAM_BACKUP_EXTRACT_PATH'] = backup_extract_path

        if not silent:
            print(fmt_title("Restoring system from backup extract at " + backup_extract_path))

        restore = Restore(backup_extract_path, limits=opt_limits, rollback=not no_rollback, simulate=opt_simulate)

        if restore.conf:
            os.environ['TKLBAM_RESTORE_PROFILE_ID'] = restore.conf.profile_id
        hooks.restore.inspect(restore.extras.path)

        if opt_debug:
            print("""\
  The --debug option has (again) dropped you into an interactive shell so that
  you can explore the state of the system just before restore. The current
  working directory contains the backup extract.

  To exit from the shell and continue the restore run "exit 0".
  To exit from the shell and abort the restore run "exit 1".
""")
            os.chdir(backup_extract_path)
            subprocess.run([os.environ.get("SHELL", "/bin/bash")])
            os.chdir('/')

        if not skip_packages:
            restore.packages()

        if not skip_files:
            restore.files()

        if not skip_database:
            restore.database()

        print()
        logging.debug(' * just restore hook to go')
        hooks.restore.post()

    except:
        if trap:
            print(file=log_fh)
            traceback.print_exc(file=log_fh)

        raise

    finally:
        assert log_fh != None
        if trap:
            sys.stdout.flush()
            sys.stderr.flush()

            trap.close()
            log_fh.close()

    if not silent:
        print("We're done. You may want to reboot now to reload all service configurations.")

if __name__=="__main__":
    main()
