#!/usr/bin/python3
# 
# Copyright (c) 2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
# 
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
# 
# TKLBAM is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
# 
"""
Create custom backup profile 

What is a backup profile?

A backup profile is used to calculate the list of system changes that need to
be backed up (e.g., new files and packages). It typically describes the
installation state of the system and includes 3 files:

* dirindex.conf: list of filesystem paths to scan for changes
* dirindex: index of timestamps, ownership and permissions for dirindex.conf paths
* packages: list of currently installed packages.

What file paths should a backup profile keep track of?

It depends on what you're using TKLBAM for. If you want to use it like TurnKey
take a look at the dirindex.conf file in the "core" profile, which all
appliance backup profiles inherit from. 

In principle, we want to track changes to the user-servicable, customizable
parts of the filesystem (e.g., /etc /root /home /var /usr/local /var /opt /srv)
while ignoring changes in areas maintained by the package management system.
The "Filesystem Hierarchy Standard" describes the Linux filesystem structure.

Why not backup everything?

TKLBAM was originaly designed to make it easy for users to only backup the
delta (I.e., changes) from a fixed installation base (I.e., an appliance). In
this usage scenario, less is more.

By default we only backup your data and configurations, plus a list of new
packages you've installed. Later when you restore these will be overlaid on top
of the new appliance's filesystem and the package management system will be
asked to install the missing packages.

By contrast, If you backup the entire filesystem TKLBAM won't be able to help
you migrate your data and configurations to a newer version of an appliance.
The restore will just run everything over. At best you'll end up with the old
appliance in a new location. But more likely you'll end up mixing the old and
new filesystems and break the package management system.

Arguments:
    
    <conf>          Path to configuration file with list of includes/exclude paths 
                    ('-' for stdin input)

Options:

    -f --force      Overwrite non-empty directories

    --no-packages   Don't create a list of installed packages from /var/lib/dpkg/status

                    Without this we won't be able to detect which packages have
                    changed since the profile was generated so the backup will
                    include all currently installed packages.

    --no-dirindex   Don't create an index of file timestamps, ownerships and permissions.

                    Without this we won't be able to detect changes since the
                    profile was generated so the backup will include everything wholesale.
                    (e.g., all files in /etc vs only files in /etc that have changed)

    --root=PATH     Use this as the root path, instead of /
                    This is useful for generating backup profiles for chroot filesystems


Usage examples:

    # create my-custom-profile by profiling state of files in the paths in profile.conf
    echo /etc -/etc/.git > profile.conf
    tklbam-internal create-profile my-custom-profile/ profile.conf

    # same as above but read paths to profile from stdin instead of a file
    echo /etc -/etc/.git | tklbam-internal create-profile -- my-custom-profile/ -

"""
import os
from os.path import *

import sys
import getopt
import re

import dirindex
from backup import ProfilePaths
from temp import TempFile

class Error(Exception):
    pass

def usage(e=None):
    from paged import stdout

    if e:
        print >> stdout, "error: " + str(e)

    print >> stdout, "Syntax: %s [ -options ] output/profile/ <conf>" % sys.argv[0]
    print >> stdout, __doc__.strip()
    sys.exit(1)

def fatal(e):
    print >> sys.stderr, "error: " + str(e)
    sys.exit(1)

class ProfileGenerator:

    @staticmethod
    def _get_dirindex(path_dirindex_conf, path_rootfs):
        with open(path_dirindex_conf) as fob:
            paths = dirindex.read_paths(fob)
        paths = [ re.sub(r'^(-?)', '\\1' + path_rootfs, path) 
                  for path in paths ]

        tmp = TempFile()
        dirindex.create(tmp.path, paths)

        with open(tmp.path) as fob:
            filtered = [ re.sub(r'^' + path_rootfs, '', line)
                            for line in fob.readlines() ]
        return "".join(filtered)

    @staticmethod
    def _get_packages(path_rootfs):
        def parse_status(path):
            control = ""
            with open(path) as fob:
                for line in fob.readlines():
                    if not line.strip():
                        yield control
                        control = ""
                    else:
                        control += line

            if control.strip():
                yield control

        def parse_control(control):
            return dict([ line.split(': ', 1) 
                          for line in control.splitlines() 
                          if re.match(r'^Package|Status', line) ])

        packages = []
        for control in parse_status(join(path_rootfs, "var/lib/dpkg/status")):
            d = parse_control(control)
            if d['Status'] == 'install ok installed':
                packages.append(d['Package'])

        packages.sort()
        return packages

    def __init__(self, conf_paths, path_output, rootfs="/", packages=True, dirindex=True):

        paths = ProfilePaths(path_output)


        with open(paths.dirindex_conf, "w") as fob:
            fob.write(("\n".join(conf_paths) + "\n")
                      if conf_paths else "")

        if dirindex:
            di = self._get_dirindex(paths.dirindex_conf, rootfs)
            with open(paths.dirindex, "w") as fob:
                fob.write(di)

        if packages:
            packages = self._get_packages(rootfs)
            with open(paths.packages, "w") as fob:
                fob.writelines([ package + "\n"
                                 for package in packages ])

        self.paths = paths

def parse_conf(fh):
    paths = []
    for line in fh.readlines():
        line = re.sub(r'#.*', '', line)
        line = line.strip()
        if not line:
            continue

        _paths = re.split(r'\s+', line)
        for path in _paths:
            # only accept absolute paths
            if not re.match(r'^-?/', path):
                raise Error("%s is not an absolute path, try %s instead" % (`path`, os.path.abspath(path)))

        paths += _paths

    return paths

def main():

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'fh', ['force', 'help', 
                                                            'root=',
                                                            'no-dirindex', 
                                                            'no-packages'])
    except getopt.GetoptError, e:
        usage(e)

    opt_force = False
    opt_dirindex = True
    opt_packages = True
    opt_root = "/"

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()

        if opt in ('-f', '--force'):
            opt_force = True

        if opt == '--no-dirindex':
            opt_dirindex = False

        if opt == "--no-packages":
            opt_packages = False

        if opt == '--root':
            opt_root = val

    if not args:
        usage()

    if len(args) != 2:
        usage("incorrect number of arguments")

    path_output, path_conf = args

    if exists(path_output):
        if not isdir(path_output):
            fatal("'%s' is not a directory" % path_output)

        if not opt_force and os.listdir(path_output) != []:
            fatal("'%s' is not an empty directory (use --force to override)" % path_output)

    if not exists(path_output):
        os.mkdir(path_output)

    try:
        conf_paths = parse_conf(sys.stdin if path_conf == '-' else open(path_conf))
    except Error, e:
        fatal(e)

    profile = ProfileGenerator(conf_paths, path_output, opt_root, packages=opt_packages, dirindex=opt_dirindex)

    title = "Custom profile written to %s" % profile.paths.path
    print title
    print "=" * len(title)

    print
    print "# List of backup includes and exclude paths"
    print profile.paths.dirindex_conf

    if exists(profile.paths.dirindex):
        print
        print "# Index of file timestamps, ownerships and permissions for paths in dirindex.conf"
        print profile.paths.dirindex

    if exists(profile.paths.packages):
        print
        print "# List of currently installed packages"
        print profile.paths.packages

if __name__=="__main__":
    main()
