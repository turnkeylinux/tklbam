import os

import socket
import command

import signal

import errno

def _find_free_port(port_from):
    def _is_listening(localport):
        sock = socket.socket()
        try:
            sock.connect(('127.0.0.1', localport))
            return True
        except socket.error, e:
            if e.errno == errno.ECONNREFUSED:
                return False

    while True:
        if _is_listening(port_from) is False:
            return port_from

        port_from += 1

class Squid:
    def __init__(self, cache_size, cache_dir):

        self.cache_size = cache_size
        self.cache_dir = cache_dir
        self.address = None
        self.command = None

    def start(self):
        os.environ['TKLBAM_SQUID_CACHE_DIR'] = self.cache_dir

        self.address = "127.0.0.1:%d" % _find_free_port(33128)
        self.command = command.Command(("/usr/local/sbin/tklbam-squid", self.address, self.cache_size),
                                       setpgrp=True, pty=True)


    def stop(self):
        if self.command:
            self.command.terminate(gracetime=1, sig=signal.SIGINT)

    def __del__(self):
        self.stop()
