#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import re
import executil

from utils import AttrDict

class Error(Exception):
    pass

class Version(AttrDict):
    def __init__(self, codename, release=None, arch=None):
        AttrDict.__init__(self)
        self.codename = codename
        self.release = release
        self.arch = arch

    def __str__(self):
        return "turnkey-%s-%s-%s" % (self.codename, self.release, self.arch)

    def is_complete(self):
        if self.codename and self.release and self.arch:
            return True

        return False

    @classmethod
    def from_system(cls):
        try:
            system_version = file("/etc/turnkey_version").readline().strip()
        except:
            try:
                system_version = executil.getoutput("turnkey-version")
            except executil.ExecError:
                return None

        return cls.from_string(system_version)

    @classmethod
    def from_string(cls, version):
        if not version.startswith('turnkey-'):
            raise Error("not a turnkey version '%s'" % version)

        version = re.sub(r'^turnkey-', '', version)
        
        m = re.match(r'(.*?)-((?:[\d\.]+|beta).*)-(amd64|i386|x86)$', version)
        if m:
            name, release, arch = m.groups()
            return cls(name, release, arch)

        m = re.match(r'(.*?)-((?:[\d\.]+|beta).*?)-?$', version)
        if m:
            name, release = m.groups()
            return cls(name, release)

        m = re.match(r'(.*?)-?$', version)
        if m:
            name = m.group(1)
            return cls(name)
