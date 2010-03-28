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

def test():
    print "redirecting to /tmp/output"
    fh = file("/tmp/output", "w")

    print "BEFORE"
    redirector = Redirector(sys.stdout, fh)
    try:
        os.system("ls -la")
    finally:
        redirector.close()

    print "AFTER"

if __name__ == "__main__":
    test()
