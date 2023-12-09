#
# Copyright (c) 2010-2012 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import sys
import re
import subprocess
from typing import Generator, Self, Optional

from fnmatch import fnmatch


class Error(Exception):
    pass


def installed() -> list[str]:
    """Return list of installed packages"""

    def parse_status(path: str) -> Generator[str, None, None]:
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

    packages = []
    for control in parse_status("/var/lib/dpkg/status"):
        d = dict([re.split(r':\s*', line, 1)
                  for line in control.split('\n')
                  if line and (':' in line) and (line[0] != ' ')])

        if "ok installed" in d['Status']:
            packages.append(d['Package'])

    return packages


class Packages(set):
    @classmethod
    def fromfile(cls, path: str) -> Self:
        with open(path) as fob:
            packages = fob.read().strip().split('\n')
        return cls(packages)

    def tofile(self, path: str) -> None:
        packages = list(self)
        packages.sort()
        with open(path, "w") as fob:
            fob.write('\n'.join(packages) + '\n')

    def __init__(self, packages: Optional[list[str]] = None) -> None:
        """If <packages> is None we get list of packages from the package
        manager.
        """
        if packages is None:
            packages_ = installed()
        else:
            packages_ = packages
        set.__init__(self, packages_)


class AptCache(set):
    Error = Error

    def __init__(self, packages: list[str]) -> None:
        command = ["apt-cache", "show", *packages]
        p = subprocess.run(command, capture_output=True, text=True)
        if p.returncode not in (0, 100):
            raise self.Error("execution failed (%d): %s\n%s" % (p.returncode,
                                                                ''.join(command),
                                                                p.stderr))
        cached = [line.split()[1]
                  for line in p.stdout.split("\n") if
                  line.startswith("Package: ")]
        set.__init__(self, cached)


class Blacklist:
    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns

    def __contains__(self, val: str) -> bool:
        if self.patterns:
            for pattern in self.patterns:
                if fnmatch(val, pattern):
                    return True
        return False

def installable(packages: list[str], blacklist: Optional[list[str]] = None) -> tuple[list[str], list[str]]:
    installed = Packages()
    aptcache = AptCache(packages)
    if blacklist is None:
        blacklist_ = Blacklist([])
    else:
        blacklist_ = Blacklist(blacklist)

    installable = []
    skipped = []
    for package in set(packages):
        if package in installed:
            continue

        if package not in aptcache:
            skipped.append(package)
            continue

        if package in blacklist_:
            skipped.append(package)
            continue

        installable.append(package)

    return installable, skipped

class Installer:
    """
    Interface::
        installer.command       Command executed
        installer.installable   List of packages to be installed
        installer.skipping      List of packages we're skipping
                                (e.g., because we couldn't find them in the apt-cache)

        installer()             Run installation command and return an error code
                                By default noninteractive...
    """
    Error = Error

    command: Optional[list[str]]
    installed: Optional[set[str]]

    def __init__(self, packages: list[str], blacklist: Optional[list[str]] = None) -> None:
        if blacklist is None:
            blacklist_ = []
        else:
            blacklist_ = blacklist
        self.installable, self.skipping = installable(packages, blacklist_)
        self.installed = None

        self.installable.sort()
        self.skipping.sort()

        if self.installable:
            self.command = ["apt-get", "install", "--assume-yes", *self.installable]
        else:
            self.command = None

    def __call__(self, interactive: bool = False) -> tuple[int, str]:
        """Install packages. Return (exitcode, output) from execution of installation command
        """
        if not self.installable:
            raise Error("no installable packages")
        env = {}
        if not interactive:
            env = {"DEBIAN_FRONTEND": "noninteractive"}
        sys.stdout.flush()
        sys.stderr.flush()

        if self.command is None:
            return 1, 'command not set'
        packages_before = Packages()
        p = subprocess.run(self.command, env=env, capture_output=True, text=True)
        packages_after = Packages()

        self.installed = packages_after - packages_before
        return p.returncode, p.stdout
