import os
import re
import commands
from utils import system

class Error(Exception):
    pass

def installed():
    """Return list of installed packages"""

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
    for control in parse_status("/var/lib/dpkg/status"):
        d = dict([ re.split(':\s*', line, 1) 
                   for line in control.split('\n') 
                   if line and line[0] != ' ' ])

        if "ok installed" in d['Status']:
            packages.append(d['Package'])

    return packages

class Packages(set):
    @classmethod
    def fromfile(cls, path):
        packages = file(path).read().strip().split('\n')
        return cls(packages)

    def tofile(self, path):
        packages = list(self)
        packages.sort()

        fh = file(path, "w")
        for package in packages:
            print >> fh, package
        fh.close()

    def __init__(self, packages=None):
        """If <packages> is None we get list of packages from the package
        manager.
        """
        if packages is None:
            packages = installed()

        set.__init__(self, packages)

class AptCache(set):
    Error = Error

    def __init__(self, packages):
        command = "apt-cache show " + " ".join(packages)
        status, output = commands.getstatusoutput(command)
        status = os.WEXITSTATUS(status)
        if status not in (0, 100):
            raise self.Error("execution failed (%d): %s\n%s" % (status, command, output))
        
        cached = [ line.split()[1] 
                   for line in output.split("\n") if
                   line.startswith("Package: ") ]

        set.__init__(self, cached)

def installable(packages):
    installed = Packages()
    aptcache = AptCache(packages)

    installable = []
    skipped = []
    for package in set(packages):
        if package in installed:
            continue

        if package not in aptcache:
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

    def __init__(self, packages):
        self.installable, self.skipping = installable(packages)

        self.installable.sort()
        self.skipping.sort()

        if self.installable:
            self.command = "apt-get install " + " ".join(self.installable)
        else:
            self.command = None

    def __call__(self, interactive=False):
        """Install packages. Return (exitcode, output) from execution of installation command
        """
        if not self.installable:
            raise Error("no installable packages")

        command = self.command
        if not interactive:
            command = "DEBIAN_FRONTEND=noninteractive " + command

        status, output = system(command)
        return (status, output)
