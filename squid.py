import os

import socket
import command

import signal

import errno

PATH_DEPS = os.environ.get('TKLBAM_DEPS', '/usr/lib/tklbam/deps')
SQUID_BIN = os.path.join(PATH_DEPS, "usr/sbin/tklbam-squid")

def _is_listening(localport):
    sock = socket.socket()
    try:
        sock.connect(('127.0.0.1', localport))
        return True
    except socket.error as e:
        if e.errno == errno.ECONNREFUSED:
            return False

def _find_free_port(port_from):
    while True:
        if _is_listening(port_from) is False:
            return port_from

        port_from += 1

class Error(Exception):
    pass

class Squid:
    def __init__(self, cache_size, cache_dir):

        self.cache_size = cache_size
        self.cache_dir = cache_dir
        self.address = None
        self.command = None

    def start(self):
        os.environ['TKLBAM_SQUID_CACHE_DIR'] = self.cache_dir

        localport = _find_free_port(33128)
        self.address = "127.0.0.1:%d" % localport
        self.command = command.Command((SQUID_BIN, self.address, self.cache_size),
                                       setpgrp=True, pty=True)

        def cb():
            if _is_listening(localport):
                continue_waiting = False
            else:
                continue_waiting = True

            return continue_waiting

        finished = self.command.wait(timeout=10, callback=cb)
        if not self.command.running or not _is_listening(localport):
            self.command.terminate()
            raise Error("%s failed to start\n" % SQUID_BIN + self.command.output)

    def stop(self):
        if self.command:
            self.command.terminate(gracetime=1, sig=signal.SIGINT)

    def __del__(self):
        self.stop()
