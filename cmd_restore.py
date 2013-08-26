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
Restore a backup

Arguments:

    <hub-backup> := backup-id || unique label pattern

Options / General:

    --download-only=path/to/backup/   Download backup to directory without doing a system restore

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

    --keyfile=KEYFILE                 Path to escrow keyfile.
                                      default: Hub provides this automatically.

    --address=TARGET_URL              manual backup target URL (needs --keyfile)
                                      default: Hub provides this automatically.

Options / System restore:

    --limits="LIMIT-1 .. LIMIT-N"     Restore filesystem or database limitations

      LIMIT := -?( /path/to/include/or/exclude | mysql:database[/table] )

    --skip-files                      Don't restore filesystem
    --skip-database                   Don't restore databases
    --skip-packages                   Don't restore new packages

    --logfile=PATH                    Path to log file
                                      default: /var/log/tklbam-restore

    --no-rollback                     Disable rollback
    --silent                          Disable feedback


    --noninteractive                  Disable interactive user prompts
    --force                           Disable sanity checking

    --debug                           Run $$SHELL after Duplicity

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

"""

import os
import sys
import getopt

from string import Template
import re

from os.path import *
from restore import Restore

from stdtrap import UnitedStdTrap
from temp import TempFile
import executil

import hub
import keypacket
import passphrase
import hooks

from registry import registry

from version import get_turnkey_version, codename
from utils import is_writeable

import backup
from conf import Conf

import traceback

PATH_LOGFILE = "/var/log/tklbam-restore"

class Error(Exception):
    pass

class ExitCode:
    OK = 0
    INCOMPATIBLE = 10
    BADPASSPHRASE = 11

def do_compatibility_check(backup_turnkey_version, interactive=True):

    backup_codename = codename(backup_turnkey_version)
    local_codename = codename(get_turnkey_version())

    if local_codename == backup_codename:
        return

    def fmt(codename):
        return codename.upper().replace("-", " ")

    backup_codename = fmt(backup_codename)
    local_codename = fmt(local_codename)

    print "WARNING: INCOMPATIBLE APPLIANCE BACKUP"
    print "======================================"
    print
    print "Restoring a %s backup to a %s appliance is not recommended." % (backup_codename, local_codename)
    print "For best results, restore to a fresh %s installation instead." % backup_codename

    if not interactive:
        sys.exit(ExitCode.INCOMPATIBLE)

    print
    print "(Use --force to suppress this check)"
    print

    while True:
        answer = raw_input("Do you want to continue? [yes/no] ")
        if answer:
            break

    if answer.lower() not in ('y', 'yes'):
        fatal("You didn't answer 'yes'. Aborting!")

def get_backup_record(arg):
    hb = hub.Backups(registry.sub_apikey)
    if re.match(r'^\d+$', arg):
        backup_id = arg

        try:
            return hb.get_backup_record(backup_id)
        except hub.InvalidBackupError, e:
            raise Error('invalid backup id (%s)' % backup_id)

    # treat our argument as a pattern
    matches = [ hbr for hbr in hb.list_backups()
                if re.search(arg, hbr.label, re.IGNORECASE) ]

    if not matches:
        raise Error("'%s' doesn't match any backup labels" % arg)

    if len(matches) > 1:
        raise Error("'%s' matches more than one backup label" % arg)

    return matches[0]

def decrypt_key(key, interactive=True):
    try:
        return keypacket.parse(key, "")
    except keypacket.Error:
        pass

    while True:
        try:
            if interactive:
                p = passphrase.get_passphrase(confirm=False)
            else:
                print "Passphrase: "
                p = sys.stdin.readline().strip()

            return keypacket.parse(key, p)

        except keypacket.Error:
            if not interactive:
                print >> sys.stderr, "Incorrect passphrase"
                sys.exit(ExitCode.BADPASSPHRASE)

            print >> sys.stderr, "Incorrect passphrase, try again"

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s [ -options ] [ <hub-backup> ]" % sys.argv[0]

    tpl = Template(__doc__.strip())
    conf = Conf()
    print >> sys.stderr, tpl.substitute(CONF_PATH=conf.paths.conf,
                                        CONF_RESTORE_CACHE_SIZE=conf.restore_cache_size,
                                        CONF_RESTORE_CACHE_DIR=conf.restore_cache_dir)

    sys.exit(1)

def main():
    download_path = None

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
    
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h',
                                       ['download-only=',
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
    except getopt.GetoptError, e:
        usage(e)

    conf = Conf()

    for opt, val in opts:
        if opt == '--download-only':
            download_path = val
            if exists(download_path):
                if not isdir(download_path):
                    fatal("--download-only=%s is not a directory" % download_path)
            else:
                os.mkdir(download_path)
            
        elif opt == '--limits':
            opt_limits += re.split(r'\s+', val)
        elif opt == '--keyfile':
            if not isfile(val):
                fatal("keyfile %s does not exist or is not a file" % `val`)

            opt_key = file(val).read()
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

        elif opt == '-h':
            usage()

        elif opt == '--restore-cache-size':
            conf.restore_cache_size = val

        elif opt == '--restore-cache-dir':
            conf.restore_cache_dir = val

        elif opt == '--debug':
            opt_debug = True

    restore_cache_size = conf.restore_cache_size
    restore_cache_dir = conf.restore_cache_dir

    hbr = None
    credentials = None

    if args:
        if len(args) != 1:
            usage("incorrect number of arguments")

        try:
            hbr = get_backup_record(args[0])
            credentials = hub.Backups(registry.sub_apikey).get_credentials()
        except Error, e:
            fatal(e)

    else:
        if not opt_address:
            usage()

    if opt_address:
        if hbr:
            fatal("a manual --address is incompatible with a <backup-id>")

        if not opt_key:
            fatal("a manual --address needs a --keyfile")

    address = hbr.address if hbr else opt_address

    if hbr:
        if not opt_force:
            do_compatibility_check(hbr.turnkey_version, interactive)

        if opt_key and \
           keypacket.fingerprint(hbr.key) != keypacket.fingerprint(opt_key):

            fatal("invalid escrow key for the selected backup")

    key = opt_key if opt_key else hbr.key
    secret = decrypt_key(key, interactive)

    if download_path:
        restore = Restore(address, secret, restore_cache_size, restore_cache_dir,
                          opt_limits, opt_time, credentials=credentials, download_path=download_path)

        return

    trap = UnitedStdTrap(usepty=True, transparent=(False if silent else True))
    log_fh = None
    try:
        try:
            hooks.restore.pre()
            restore = Restore(address, secret, restore_cache_size, restore_cache_dir,
                              opt_limits, opt_time, credentials=credentials, rollback=not no_rollback)

            hooks.restore.inspect(restore.extras.path)
            if opt_debug:
                trap.close()
                trap = None

                os.chdir(restore.backup_archive)
                executil.system(os.environ.get("SHELL", "/bin/bash"))
                os.chdir('/')

            if not skip_packages:
                restore.packages()

            if not skip_files:
                restore.files()

            if not skip_database:
                restore.database()

            print
            hooks.restore.post()

        finally:
            if trap:
                trap.close()
                log_fh = file(opt_logfile, "w")
                log_fh.write(trap.std.read())
    except:
        if sys.exc_type and log_fh:
            print >> log_fh
            traceback.print_exc(file=log_fh)

        raise

    finally:
        if log_fh:
            log_fh.close()


    print "We're done. You may want to reboot now to restart all services."

if __name__=="__main__":
    main()
