#!/usr/lib/tklbam-pypy2/bin/pypy
#
# Copyright (c) 2015 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""Ask Hub to use IAM role to get temporary credentials to your TKLBAM S3 storage

Options:

    --json      Emit boto3 credential_process JSON instead of the legacy
                space-separated form. This is what tklbam points boto3 at, so
                that duplicity can re-fetch credentials when the STS token
                expires part way through a long transfer.
"""
import _init_sys_path

import hashlib
import json
import os
import re
import sys
import time

from registry import hub_backups, registry
import hub
from pylib.retry import retry

@retry(5, backoff=2)
def get_credentials(hb):
    return hb.get_credentials()

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

def format(creds):
    values = [ creds[k] for k in ('accesskey', 'secretkey', 'sessiontoken', 'expiration') ]
    return " ".join(values)

def iso8601(expiry):
    """Normalise the Hub's expiry to the ISO8601 form boto3 expects.

    Returns None if it can't be interpreted, in which case the caller should
    omit Expiration entirely rather than emit something boto3 will choke on.
    """
    if not expiry:
        return None

    expiry = str(expiry).strip()

    # already ISO8601
    if "T" in expiry and (expiry.endswith("Z") or "+" in expiry):
        return expiry

    # unix timestamp
    if re.match(r'^\d+$', expiry):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(expiry)))

    # "YYYY-MM-DD HH:MM:SS" - the form the Hub uses for backup record dates
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ",
                             time.strptime(expiry, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None

def format_json(creds):
    """Emit the JSON document boto3's credential_process expects.

    Version must be the integer 1; SessionToken and Expiration are optional.
    Without Expiration boto3 treats the credentials as static and will not
    refresh them - which is no worse than the behaviour this replaces - so an
    unparseable expiry warns rather than failing the transfer outright.
    """
    d = {"Version": 1,
         "AccessKeyId": creds['accesskey'],
         "SecretAccessKey": creds['secretkey'],
         "SessionToken": creds['sessiontoken']}

    expiry = iso8601(creds['expiration'])
    if expiry:
        d["Expiration"] = expiry
    else:
        print >> sys.stderr, ("warning: could not interpret credential expiry "
                              "%r - boto3 will treat these credentials as "
                              "static and will not refresh them"
                              % (creds['expiration'],))

    return json.dumps(d)


def main():
    args = sys.argv[1:]

    opt_json = False
    if args and args[0] == '--json':
        opt_json = True
        args = args[1:]

    if args:
        usage()

    scheduled_token_hash = os.environ.get("TKLBAM_SCHEDULED_TOKEN_SHA256")
    if scheduled_token_hash:
        import connection
        token = connection.initialized_daily(registry)
        if not token or hashlib.sha256(token).hexdigest() != scheduled_token_hash:
            fatal("The Hub connection changed while preparing scheduled backup credentials.")
        hb = hub.Backups(token)
    else:
        try:
            hb = hub_backups()
        except hub.Backups.NotInitialized, e:
            fatal(e)

    creds = get_credentials(hb)
    if scheduled_token_hash:
        try:
            connection.verify_scheduled(registry, token)
        except hub.Error, e:
            fatal(e)
    if creds.type != 'iamrole':
        fatal("STS agent incompatible with '%s' type credentials" % creds.type)

    if opt_json:
        print format_json(creds)
    else:
        print format(creds)

if __name__ == "__main__":
    main()
