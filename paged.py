# Copyright (c) 2008 Liraz Siri <liraz@turnkeylinux.org>
#               2019 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# turnkey-paged is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

"""This modules provides an stdout instances which
redirect output through a pager if:
  A) PAGER is configured in the environment
  B) stdout is a tty
"""

import os
import sys
import errno
import subprocess
import shlex
import atexit


class _PagedStdout:
    # lazy definition of pager attribute so that we
    # execute pager the first time we need it
    def pager(self):
        if hasattr(self, '_pager'):
            return self._pager

        pager = None
        if os.isatty(sys.stdout.fileno()):
            pager_env = os.environ.get('PAGER',
                                       subprocess.getoutput('which less'))
            if pager_env:
                pager_env = shlex.split(pager_env)
                pager = subprocess.Popen(pager_env, stdin=subprocess.PIPE)

        self._pager = pager
        atexit.register(self.close)
        return pager
    pager = property(pager)

    def flush(self):
        if self.pager:
            self.pager.stdin.flush()
        else:
            sys.stdout.flush()

    def write(self, text):
        if self.pager:
            try:
                self.pager.stdin.write(bytes(text, 'utf8'))

            except IOError as e:
                if e[0] != errno.EPIPE:
                    raise
        else:
            sys.stdout.write(text)

    def close(self):
        if self.pager:
            self.pager.stdin = sys.stdin
            self.pager.communicate()


stdout = _PagedStdout()


def test():
    global stdout

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        print(line, end=' ', file=stdout)


if __name__ == "__main__":
    test()
