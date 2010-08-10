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
import os
import sys

class Redirect:
    def __init__(self, origin, sink):
        sink.flush()
        origin.flush()

        if sink.fileno() != origin.fileno():
            self.dupfd = os.dup(origin.fileno())
            os.dup2(sink.fileno(), origin.fileno())

        self.sink = sink
        self.origin = origin

    def close(self):
        if self.sink.fileno() != self.origin.fileno():
            self.sink.flush()
            self.origin.flush()
            os.dup2(self.dupfd, self.origin.fileno())
            os.close(self.dupfd)

class RedirectOutput:
    def __init__(self, sink):
        self.rstdout = Redirect(sys.stdout, sink)
        self.rstderr = Redirect(sys.stderr, sink)

    def close(self):
        self.rstdout.close()
        self.rstderr.close()

def test():
    print "redirecting to /tmp/output"
    fh = file("/tmp/output", "w")

    print "BEFORE"
    redirector = Redirect(sys.stdout, fh)
    try:
        os.system("ls -la")
    finally:
        redirector.close()

    print "AFTER"

if __name__ == "__main__":
    test()
