#
# Copyright (c) 2010-2015 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
from os.path import *

import re
import sys
import tempfile

from subprocess import *
from squid import Squid

from utils import AttrDict, iamroot

import resource
RLIMIT_NOFILE_MAX = 8192

# hard code default path to debian package duplicity executable
DEFAULT_DUPLICITY = "/usr/bin/duplicity"
DUPLICITY = os.environ.get('DUPLICITY', DEFAULT_DUPLICITY)

# Removed with the move to Debian's duplicity:
#
# - TARGET_ADDRESS / TKLBAM_BUCKET, PATH_DEPS_BIN and PATH_DEPS_PYLIB were all
#   computed and never read. _find_duplicity_pylib() returned before its body,
#   so it only ever yielded the duplicity *binary* path, not a pylib dir.
#
# - a pair of shutil.move() calls swapped deps/lib/duplicity in and out of the
#   way depending on which duplicity binary was selected. That vendored library
#   is no longer shipped, so both branches were dead - but they ran at *import*
#   time in a root-owned directory, and conf imports this module, so had either
#   path ever reappeared every non-root tklbam command would have died on
#   import. Setting $DUPLICITY still selects a different binary; only the
#   library shuffling is gone.

# boto3 runs this to (re-)fetch short lived IAM role credentials; see
# cmd_internals/cmd_stsagent.py --json
STSAGENT_COMMAND = "/usr/bin/tklbam-internal stsagent --json"

def _write_aws_config(command=STSAGENT_COMMAND):
    """Write a throwaway AWS config wiring boto3 up to our credential_process.

    Returns the path. The caller owns the file and must remove it. It holds no
    secrets - only the command to run - but is written 0600 regardless.
    """
    fd, path = tempfile.mkstemp(prefix="tklbam-aws-config-")
    fob = os.fdopen(fd, "w")
    try:
        fob.write("[default]\ncredential_process = %s\n" % command)
    finally:
        fob.close()

    os.chmod(path, 0600)
    return path

class Error(Exception):
    pass

class Duplicity:
    """low-level interface to Duplicity"""

    def __init__(self, *args):
        """Duplicity command. The first member of args can be a an array of tuple arguments"""

        if isinstance(args[0], list):
            opts = args[0][:]
            args = args[1:]
        else:
            opts = []

        if not args:
            raise Error("no arguments!")

        if iamroot():
            opts += [ ('archive-dir', '/var/cache/duplicity') ]

        opts = [ "--%s=%s" % (key, val) for key, val in opts ]
        self.command = [DUPLICITY] + opts + list(args)

    def run(self, passphrase, creds=None, debug=False, log=None):
        sys.stdout.flush()
        if log is None:
            log = lambda s: None

        env = os.environ.copy()
        aws_config = None

        if creds:
            if creds.type in ('devpay', 'iamuser'):
                env['AWS_ACCESS_KEY_ID'] = creds.accesskey
                env['AWS_SECRET_ACCESS_KEY'] = creds.secretkey
                env['X_AMZ_SECURITY_TOKEN'] = (",".join([creds.producttoken,
                                                                creds.usertoken])
                                                    if creds.type == 'devpay'
                                                    else creds.sessiontoken)

            elif creds.type == 'iamrole':
                # /var/lib/tklbam/iam_role should not be needed; this part was
                # added early in the v19.x testing and should be removed...
                # this read "self.env[...]", but Duplicity only ever sets
                # self.command - so whenever the iam_role file existed this
                # raised AttributeError before any credential reached the
                # child. Same slip that 5d3bdef fixed in Target; missed here.
                if exists("/var/lib/tklbam/iam_role"):
                    with open("/var/lib/tklbam/iam_role") as fob:
                        env['AWS_ROLE_ARN'] = fob.read().strip()

                # IAM role credentials are short lived, so handing boto3 a
                # static copy meant a transfer outliving the token died part
                # way through. Point it at a credential_process instead and it
                # re-runs stsagent whenever the token is close to expiring.
                #
                # Static AWS_* variables beat credential_process in boto3's
                # resolution order, so they must not be set here - including
                # any inherited from the ambient environment.
                for var in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                            'AWS_SESSION_TOKEN'):
                    env.pop(var, None)

                aws_config = _write_aws_config()
                env['AWS_CONFIG_FILE'] = aws_config

        env['PASSPHRASE'] = passphrase

        if debug:
            print """
  The --debug option has dropped you into an interactive shell in which you can
  explore the state of the system just before the above duplicity command is
  run, and/or execute it manually.

  For Duplicity usage info, options and storage backends, run "duplicity --help".
  To exit from the shell and continue running duplicity "exit 0".
  To exit from the shell and abort this session "exit 1".
"""

            from pylib import executil
            shell = os.environ.get("SHELL", "/bin/bash")
            if shell == "/bin/bash":
                shell += " --norc"

            executil.system(shell)

        log("\n// duplicity started...")
        log("\n * self.command: " + str(self.command))
        try:
            child = Popen(self.command, env=env)
            exitcode = child.wait()
        finally:
            # must outlive the child, but not this call
            if aws_config and exists(aws_config):
                os.remove(aws_config)
        log("\n// duplicity stopped...")
        if exitcode != 0:
            raise Error("non-zero exitcode (%d) from backup command: %s" % (exitcode, str(self)))

    def __str__(self):
        return " ".join(self.command)


def _raise_rlimit(type, newlimit):
    soft, hard = resource.getrlimit(type)
    if soft > newlimit:
        return

    if hard > newlimit:
        return resource.setrlimit(type, (newlimit, hard))

    try:
        resource.setrlimit(type, (newlimit, newlimit))
    except ValueError:
        return

def _region_opts(target):
    """Duplicity options carrying the S3 region, if this target has one.

    Target.__init__ strips the region-bearing endpoint host out of the address,
    and it has to: duplicity parses the whole s3:// URL as a path, so
    "s3://s3-eu-west-1.amazonaws.com/bucket" would be read as bucket
    "s3-eu-west-1.amazonaws.com". That leaves --s3-region-name as the only way
    to tell duplicity which region the bucket is in.

    Previously the region was extracted, stashed on the Target and never read
    by anything, so boto3 was left to guess - which works for a bucket in
    whichever region it defaults to and fails for the rest.
    """
    region = getattr(target, "region", "")
    if not region:
        return []

    return [("s3-region-name", region)]

# An S3 endpoint host, in the spellings AWS has used over the years:
#
#   s3-ap-southeast-2.amazonaws.com             what the Hub emits today
#   s3.ap-southeast-2.amazonaws.com             AWS's current standard form
#   s3.dualstack.ap-southeast-2.amazonaws.com   IPv6 dual-stack
#
# The host has to come out of the address whichever spelling it is, because
# duplicity parses the whole s3:// URL as a path and would otherwise take the
# endpoint for the bucket name. Once it is gone, the region it carried is the
# only thing left that can tell duplicity where the bucket lives, hence
# _region_opts().
#
# This replaces a startswith("s3-") test and an addr_split[2][3:-14] slice,
# which silently depended on ".amazonaws.com" being exactly 14 characters.
S3_ENDPOINT_RE = re.compile(
    r'^s3[.-](?:dualstack\.)?([a-z0-9-]+)\.amazonaws\.com$')

class Target(AttrDict):
    def __init__(self, address, credentials, secret):
        AttrDict.__init__(self)
        addr_split = address.split("/")
        region = ""
        # only S3 targets carry a region. file://, rsync://, ssh://, ftp:// and
        # friends are all legitimate backup addresses (see tklbam-backup
        # --help), and they used to trip the warning below - and a short
        # "s3:..." address indexed addr_split[2] without checking the length.
        is_s3 = addr_split[0] == "s3:"

        endpoint = None
        if is_s3 and len(addr_split) > 2:
            endpoint_host = addr_split[2]
            if endpoint_host == "s3.amazonaws.com":
                region = "us-east-1"
            else:
                endpoint = S3_ENDPOINT_RE.match(endpoint_host)

        if endpoint:
            region = endpoint.group(1)

        if region:
            del addr_split[2]
            address = "/".join(addr_split)
        elif is_s3:
            print "ERROR: could not determine AWS region - this may cause failure"
        self.region = region
        self.address = address
        self.credentials = credentials
        self.secret = secret

class Downloader(AttrDict):
    """High-level interface to Duplicity downloads"""

    CACHE_SIZE = "50%"
    CACHE_DIR = "/var/cache/tklbam/restore"

    def __init__(self, time=None, cache_size=CACHE_SIZE, cache_dir=CACHE_DIR):
        AttrDict.__init__(self)
        self.time = time
        self.cache_size = cache_size
        self.cache_dir = cache_dir

    def __call__(self, download_path, target, debug=False, log=None, force=False):
        if log is None:
            log = lambda s: None

        if self.time:
            opts = [("restore-time", self.time)]
        else:
            opts = []

        opts += _region_opts(target)

        # squid and the http_proxy override must be torn down even when the
        # download fails. Duplicity.run() raises on a non-zero exit (bad
        # passphrase, network failure, missing backup), and without a finally
        # the teardown below was skipped and cleanup fell to Squid.__del__ ->
        # Command.__del__. Those finalizers are only prompt under refcounting;
        # on pypy they are not, so a failed restore orphaned the squid process
        # (holding a port and the cache dir) and left http_proxy pointing at it.
        squid = None
        orig_env = None
        proxy_overridden = False

        try:
            if iamroot():
                log("// started squid: caching downloaded backup archives to " + self.cache_dir + "\n")

                squid = Squid(self.cache_size, self.cache_dir)
                squid.start()

                orig_env = os.environ.get('http_proxy')
                os.environ['http_proxy'] = squid.address
                proxy_overridden = True

            _raise_rlimit(resource.RLIMIT_NOFILE, RLIMIT_NOFILE_MAX)
            args = [ '--s3-unencrypted-connection', target.address, download_path ]
            if force:
                args = [ '--force' ] + args

            # duplicity 2.0+ wants an explicit action verb and otherwise infers
            # one, logging "No valid action found. Will imply 'restore' ...". It
            # infers correctly, but say it outright: the cleanup call in Uploader
            # already passes a verb, and a future duplicity may stop inferring.
            command = Duplicity(opts, "restore", *args)

            log("# " + str(command))

            command.run(target.secret, target.credentials, debug=debug)

        finally:
            if proxy_overridden:
                if orig_env:
                    os.environ['http_proxy'] = orig_env
                else:
                    os.environ.pop('http_proxy', None)

            # Squid.stop() is safe to call more than once and safe after a
            # failed start(): it no-ops when self.command is unset, and
            # Command.terminate() checks whether the process is still running.
            if squid is not None:
                log("\n// stopping squid\n")
                squid.stop()

        sys.stdout.flush()

class Uploader(AttrDict):
    """High-level interface to Duplicity uploads"""

    VOLSIZE = 25
    FULL_IF_OLDER_THAN = "1M"
    S3_PARALLEL_UPLOADS = 1

    def __init__(self,
                 verbose=True,
                 volsize=VOLSIZE,
                 full_if_older_than=FULL_IF_OLDER_THAN,
                 s3_parallel_uploads=S3_PARALLEL_UPLOADS,

                 includes=[],
                 include_filelist=None,
                 excludes=[],
                 ):

        AttrDict.__init__(self)

        self.verbose = verbose
        self.volsize = volsize
        if full_if_older_than == "now":
            full_if_older_than = "1s"
        self.full_if_older_than = full_if_older_than
        self.s3_parallel_uploads = s3_parallel_uploads

        self.includes = includes
        self.include_filelist = include_filelist
        self.excludes = excludes

    def __call__(self, source_dir, target, force_cleanup=True, dry_run=False, debug=False, log=None):
        if log is None:
            log = lambda s: None

        opts = []
        if self.verbose:
            opts += [('verbosity', 5)]

        opts += _region_opts(target)

        if force_cleanup:
            cleanup_command = Duplicity(opts, "cleanup", "--force", target.address)
            log(cleanup_command)

            if not dry_run:
                cleanup_command.run(target.secret, target.credentials, log=log)

            log("\n")

        opts += [('volsize', self.volsize),
                 ('full-if-older-than', self.full_if_older_than),
                 ('gpg-options', '--cipher-algo=aes')]

        for include in self.includes:
            opts += [ ('include', include) ]

        if self.include_filelist:
            opts += [ ('include-filelist', self.include_filelist) ]

        for exclude in self.excludes:
            opts += [ ('exclude', exclude) ]

        args = [ '--s3-unencrypted-connection', '--allow-source-mismatch' ]

        if dry_run:
            args += [ '--dry-run' ]

        if self.s3_parallel_uploads > 1:
            s3_multipart_chunk_size = self.volsize / self.s3_parallel_uploads
            if s3_multipart_chunk_size < 5:
                s3_multipart_chunk_size = 5
            # --s3-use-multiprocessing was removed in duplicity 2.0.0 ("Option
            # '--s3-use-multiprocessing' was removed in 2.0.0"), so passing it
            # made any backup with s3-parallel-uploads > 1 fail outright.
            # --s3-multipart-max-procs is the modern equivalent.
            args += [ '--s3-multipart-chunk-size=%d' % s3_multipart_chunk_size,
                      '--s3-multipart-max-procs=%d' % self.s3_parallel_uploads ]

        args += [ source_dir, target.address ]

        # explicit action verb - see the comment in Downloader.__call__. The
        # verb goes between the options and the args, so the order-sensitive
        # --include / --include-filelist / --exclude set is untouched.
        backup_command = Duplicity(opts, "backup", *args)

        log(str(backup_command))
        backup_command.run(target.secret, target.credentials, debug=debug)
        log("\n")
