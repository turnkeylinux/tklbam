#!/usr/bin/python
# 
# Copyright (c) 2010 Liraz Siri <liraz@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
Make profile

Options:
    
    --profiles-conf=PATH    Dir containing profile conf files
                            Environment: PROFILES_CONF

"""
import os
from os.path import *

import sys
import getopt

import re

from StringIO import StringIO
import executil

from temp import TempDir, TempFile
from backup import ProfilePaths
import dirindex
import debinfo

class Error(Exception):
    pass

def usage(e=None):
    if e:
        print >> sys.stderr, "error: " + str(e)

    print >> sys.stderr, "Syntax: %s path/to/appliance.iso path/to/output" % sys.argv[0]
    print >> sys.stderr, __doc__.strip()
    sys.exit(1)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

class MountISO:
    def __init__(self, iso):
        cdroot = TempDir()
        rootfs = TempDir()

        executil.system("mount -o loop", iso, cdroot)
        executil.system("mount -o loop", join(cdroot, "casper/10root.squashfs"), rootfs)

        self.cdroot = cdroot
        self.rootfs = rootfs

    def __del__(self):
        executil.system("umount", self.rootfs)
        executil.system("umount", self.cdroot)

def get_turnkey_version(rootfs):
    return executil.getoutput("turnkey-version", rootfs)

def get_codename(turnkey_version):
    m = re.match(r'turnkey-(.*?)-([\d\.]+|beta)', turnkey_version)
    if not m:
        raise Error("couldn't parse turnkey version '%s'" % turnkey_version)

    codename, release = m.groups()
    return codename

def get_dirindex_conf(path_profiles_conf, codename):

    def path_conf(codename):
        return join(path_profiles_conf, codename)

    sio = StringIO()
    sio.write(file(path_conf("core")).read())

    if not exists(path_conf(codename)):
        raise Error("no profile conf file for '%s'" % codename)

    print >> sio
    print >> sio, "# %s" % codename

    sio.write(file(path_conf(codename)).read())

    return sio.getvalue()

def get_dirindex(path_dirindex_conf, path_rootfs):
    paths = dirindex.read_paths(file(path_dirindex_conf))
    paths = [ re.sub(r'^(-?)', '\\1' + path_rootfs, path) 
              for path in paths ]

    tmp = TempFile()
    dirindex.create(tmp.path, paths)

    filtered = [ re.sub(r'^' + path_rootfs, '', line) 
                        for line in file(tmp.path).readlines() ]
    return "".join(filtered)

def get_packages(path_rootfs):
    def parse_status(path):
        control = ""
        for line in file(path).readlines():
            if not line.strip():
                yield control
                control = ""
            else:
                control += line

        if control.strip():
            yield control

    packages = []
    for control in parse_status(join(path_rootfs, "var/lib/dpkg/status")):
        d = debinfo.parse_control(control)
        if d['Status'] == 'install ok installed':
            packages.append(d['Package'])

    packages.sort()
    return packages

def make_profile(rootfs, path_profiles_conf):
    version = get_turnkey_version(rootfs)
    codename = get_codename(version)

    profile = ProfilePaths(TempDir())

    dc = get_dirindex_conf(path_profiles_conf, codename)
    file(profile.dirindex_conf, "w").write(dc)

    di = get_dirindex(profile.dirindex_conf, rootfs)
    file(profile.dirindex, "w").write(di)

    packages = get_packages(rootfs)
    file(profile.packages, "w").writelines([ package + "\n"
                                             for package in packages ])

    return profile

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', 
                                       ['profiles-conf=', 'help'])
    except getopt.GetoptError, e:
        usage(e)

    profiles_conf = os.environ.get("PROFILES_CONF")

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt == '--profiles-conf':
            profiles_conf = val

    if not args:
        usage()

    if len(args) != 2:
        usage("incorrect number of arguments")

    if not profiles_conf:
        fatal("need a profiles conf dir")

    iso_path, output_path = args

    mount = MountISO(iso_path)

    path = make_profile(mount.rootfs, profiles_conf)
    print mount.rootfs
    os.system("cd %s; /bin/bash" % path)

if __name__=="__main__":
    main()
