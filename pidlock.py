import os
from os.path import exists
import fcntl
import errno
from typing import Optional

class Locked(Exception):
    pass


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False

    return True


class PidLock:
    Locked = Locked

    def __init__(self, filename: str, nonblock: bool = False) -> None:
        self.filename = filename
        self.nonblock = nonblock
        self.locked = False
        self.fh = None

    def lock(self, nonblock: Optional[bool] = None) -> Optional[bool]:
        if exists(self.filename):
            try:
                with open(self.filename, 'r') as fob:
                    pid = int(fob.read())
                if not pid_exists(pid):
                    os.remove(self.filename)
            except ValueError:
                pass

        flags = 0
        if nonblock is None:
            nonblock = self.nonblock
        if nonblock:
            flags = fcntl.LOCK_NB

        self.fh = open(self.filename, "a")

        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | flags)
            with open(self.filename, 'w') as fob:
                fob.write(repr(os.getpid()))
        except IOError as e:
            if e.errno == errno.EWOULDBLOCK:
                raise Locked()

        self.locked = True

    def unlock(self) -> None:
        if not self.locked or self.fh is None:
            return

        fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        self.fh = None

        self.locked = False

    def __del__(self) -> None:
        self.unlock()


# run this twice for best effect
def _test():
    import time

    def sleep(n):
        print(("sleeping for %d seconds" % n))
        time.sleep(n)

    l = PidLock("lock.lock", nonblock=False)
    l.lock()
    sleep(5)
    l.unlock()

    sleep(0.1)

    l.lock()
    sleep(5)
    l.unlock()


if __name__ == '__main__':
    _test()
