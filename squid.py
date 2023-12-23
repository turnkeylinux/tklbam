import os
import socket
import signal
import errno
from typing import Optional

import command

PATH_DEPS = os.environ.get('TKLBAM_DEPS', '/usr/lib/tklbam3/deps')
SQUID_BIN = os.path.join(PATH_DEPS, "usr/sbin/tklbam3-squid")

def _is_listening(localport: int) -> bool:
    sock = socket.socket()
    try:
        sock.connect(('127.0.0.1', localport))
        return True
    except socket.error as e:
        if e.errno == errno.ECONNREFUSED:
            return False
    return False

def _find_free_port(port_from: int) -> int:
    while True:
        if _is_listening(port_from) is False:
            return port_from

        port_from += 1

class Error(Exception):
    pass

class Squid:
    def __init__(self, cache_size: str, cache_dir: str) -> None:

        self.cache_size = cache_size
        self.cache_dir = cache_dir
        self.address: Optional[str] = None
        self.command: Optional[command.Command] = None

    def start(self) -> None:
        os.environ['TKLBAM_SQUID_CACHE_DIR'] = self.cache_dir

        localport = _find_free_port(33128)
        self.address = f"127.0.0.1:{localport}"
        self.command = command.Command([SQUID_BIN, self.address, self.cache_size],
                                       setpgrp=True, pty=True)

        def cb() -> bool:
            if _is_listening(localport):
                continue_waiting = False
            else:
                continue_waiting = True

            return continue_waiting

        finished = self.command.wait(timeout=10, callback=cb)
        if not self.command.running or not _is_listening(localport):
            self.command.terminate()
            raise Error(f"{SQUID_BIN} failed to start:\n{self.command.output}")

    def stop(self) -> None:
        if self.command:
            self.command.terminate(gracetime=1, sig=signal.SIGINT)

    def __del__(self) -> None:
        self.stop()
