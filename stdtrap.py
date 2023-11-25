#
# Copyright (c) 2007-2013 Liraz Siri <liraz@turnkeylinux.org>
# Copyright (c) 2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# This file is part of turnkey-pylib.
#
# turnkey-pylib is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
"""
Module that contains classes for capturing stdout/stderr.

Warning: if you aren't careful, exceptions raised after trapping stdout/stderr
will cause your program to exit silently.

StdTrap usage:
    trap = StdTrap()
    try:
        expression
    finally:
        trap.close()

    trapped_stdout = trap.stdout.read()
    trapped_stderr = trap.stderr.read()

UnitedStdTrap usage:

    trap = UnitedStdTrap()
    try:
        expression
    finally:
        trap.close()

    trapped_output = trap.std.read()

UnitedStdTrap examples with tee to logfile:

    ## example 1: traps output and writes it to session.log ##

    import os
    from stdtrap import UnitedStdTrap

    # in another session, you can shadow this shell session in real-time::
    #
    #     tail -f session.log
    #
    fh = file("session.log", "w")
    trap = UnitedStdTrap(usepty=True, transparent=True, tee=fh)
    try:
        os.system("/bin/bash")
    finally:
        trap.close()
        fh.close()

    ## example 2: traps output and writes it to stdout and /tmp/log ##

    # also writes intercepted output to /tmp/log
    logfile = file("/tmp/log", "w")
    trap = UnitedStdTrap(transparent=True, tee=logfile)
    try:
        os.system("echo hello world")

        for i in range(10):
            print i
    finally:
        trap.close()

    trapped_output = trap.std.read()
    logfile.close()

    assert file("/tmp/log").read() == trapped_output

"""

import os
import sys
import select
from io import StringIO
import signal
from typing import IO, Callable, Optional

class Error(Exception):
    pass


class Splicer:
    """Inside the _splice method, stdout is intercepted at
    the file descriptor level by redirecting it to a pipe. Now
    whenever someone writes to stdout, we can read it out the
    other end of the pipe.

    The problem is that if we don't suck data out of this pipe then
    eventually if enough data is written to it the process writing to
    stdout will be blocked by the kernel, which means we'll be limited to
    capturing up to 65K of output and after that anything else will hang.
    So to solve that we create a splicer subprocess to get around the OS's
    65K buffering limitation. The splicer subprocess's job is to suck the
    pipe into a local buffer and spit it back out to:

    1) the parent process through a second pipe created for this purpose.
    2) If `transparent` is True then the data from the local pipe is
       redirected back to the original filedescriptor.

    3) If `tee` is provided then data from the local pipe is tee'ed into
       those file handles.
    """
    @staticmethod
    def _splice(spliced_fd: int,
                usepty: bool, transparent: bool,
                tee: Optional[list[str]] = None
                ) -> tuple[int, IO[str], int]:
        """splice into spliced_fd -> (splicer_pid, splicer_reader, orig_fd_dup)"""

        if not tee:
            tee = []

        # duplicate the fd we want to trap for safe keeping
        orig_fd_dup = os.dup(spliced_fd)

        # create a bi-directional pipe/pty
        # data written to w can be read from r
        if usepty:
            r, w = os.openpty()
        else:
            r, w = os.pipe()

        # splice into spliced_fd by overwriting it
        # with the newly created `w` which we can read from with `r`
        os.dup2(w, spliced_fd)
        os.close(w)

        outpipe = Pipe()

        # the child process uses this to signal the parent to continue
        # the parent uses this to signal the child to close
        signal_event = SignalEvent()

        splicer_pid = os.fork()
        if splicer_pid:
            signal_continue = signal_event

            outpipe.w.close()
            os.close(r)

            while not signal_continue.isSet():
                pass

            return splicer_pid, outpipe.r, orig_fd_dup

        signal_closed = signal_event

        # child splicer
        outpipe.r.close()

        outpipe = outpipe.w

        # we don't need this copy of spliced_fd
        # keeping it open will prevent it from closing
        os.close(spliced_fd)
        set_blocking(r, False)
        set_blocking(outpipe.fileno(), False)

        poll = select.poll()
        poll.register(r, select.POLLIN | select.POLLHUP)

        closed = False
        SignalEvent.send(os.getppid())

        r_fh = os.fdopen(r, "rb")

        sinks = [Sink(outpipe.fileno())]
        if tee:
            sinks += [Sink(int(f)) for f in tee]
        if transparent:
            sinks.append(Sink(orig_fd_dup))

        while True:
            has_unwritten_data = True in [sink.data != '' for sink in sinks]

            if not closed:
                closed = signal_closed.isSet()

            if closed and not has_unwritten_data:
                break

            try:
                events = poll.poll(1)
            except select.error:
                events = list(())

            for fd, mask in events:
                if fd == r:
                    if mask & select.POLLIN:

                        data = r_fh.read()
                        for sink in sinks:
                            sink.buffer(data)
                            poll.register(sink.fd)

                        poll.register(outpipe.fileno(), select.POLLOUT)

                    if mask & select.POLLHUP:
                        closed = True
                        poll.unregister(fd)

                else:
                    for sink in sinks:
                        if sink.fd != fd:
                            continue

                        if mask & select.POLLOUT:
                            wrote_all = sink.write()
                            if wrote_all:
                                poll.unregister(sink.fd)

        os._exit(0)

    def __init__(self, spliced_fd: int, usepty: bool = False, transparent: bool = False, tee: Optional[IO[str]|list[str]] = None):
        if tee is None:
            tee = []

        if not isinstance(tee, list):
            tee = [str(tee)]

        vals = self._splice(spliced_fd, usepty, transparent, tee)
        self.splicer_pid, self.splicer_reader, self.orig_fd_dup = vals

        self.spliced_fd = spliced_fd

    def close(self) -> str:
        """closes the splice -> captured output"""
        # dupping orig_fd_dup -> spliced_fd does two things:
        # 1) it closes spliced_fd - signals our splicer process to stop reading
        # 2) it overwrites spliced_fd with a dup of the unspliced original fd
        os.dup2(self.orig_fd_dup, self.spliced_fd)
        SignalEvent.send(self.splicer_pid)

        os.close(self.orig_fd_dup)

        captured = self.splicer_reader.read()
        os.waitpid(self.splicer_pid, 0)

        return captured


class SignalEvent:
    SIG = signal.SIGUSR1

    @classmethod
    def send(cls, pid: int) -> None:
        """send signal event to pid"""
        os.kill(pid, cls.SIG)

    def _sighandler(self, sig: signal.Signals, frame: bytes) -> None:
        self.value = True


    def __init__(self):
        self.value = False
        signal.signal(self.SIG, self._sighandler)
        # E ▎Argument of type "(sig: Signals, frame: bytes) -> None" cannot be assigned to parameter "handler" of type "_HANDLER" in function "signal" 
        #    Type "(sig: Signals, frame: bytes) -> None" cannot be assigned to type "_HANDLER"
        #        Type "(sig: Signals, frame: bytes) -> None" cannot be assigned to type "(int, FrameType | None) -> Any"
        #    Parameter 1: type "int" cannot be assigned to type "Signals"
        #        "int" is incompatible with "Signals"
        #    Parameter 2: type "FrameType | None" cannot be assigned to type "bytes"
        #        Type "FrameType | None" cannot be assigned to type "bytes"
        #        "FrameType" is incompatible with "bytes"
        #    "function" is incompatible with "int"

    def isSet(self):
        return self.value

    def clear(self):
        self.value = False


class Pipe:
    fileno: Callable
    def __init__(self):
        r, w = os.pipe()
        self.r = os.fdopen(r, "r")
        self.w = os.fdopen(w, "w")


def set_blocking(fd: int, block: bool) -> None:
    import fcntl
    arg = os.O_NONBLOCK
    if block:
        arg = ~arg
    fcntl.fcntl(fd, fcntl.F_SETFL, arg)


class Sink:
    def __init__(self, fd: int|Pipe):
        if isinstance(fd, Pipe):
            if hasattr(fd, 'fileno'):
                fd = fd.fileno()
            else:
                raise Error('Pipe has no fileno()')

        self.fd = fd
        self.data: bytes = b''

    def buffer(self, data: bytes) -> None:
        self.data += data

    def write(self) -> bool:
        if not isinstance(self.fd, int) and isinstance(self.fd, Pipe):
            raise Error("fd is not int or Pipe")
        try:
            written = os.write(self.fd, self.data)
        except:
            return False

        self.data = self.data[written:]
        if not self.data:
            return True
        return False


class UnitedStdTrap:
    def __init__(self, usepty: bool = False, transparent: bool = False, tee: Optional[IO[str]|list[str]] = None):
        if not tee:
            tee = []
        self.usepty = usepty
        self.transparent = transparent

        sys.stdout.flush()
        self.stdout_splice = Splicer(sys.stdout.fileno(), usepty,
                                     transparent, tee)

        sys.stderr.flush()
        self.stderr_dupfd = os.dup(sys.stderr.fileno())
        os.dup2(sys.stdout.fileno(), sys.stderr.fileno())

        self.std: Optional[IO[str]] = None
        self.stderr: Optional[IO[str]] = None
        self.stdout: Optional[IO[str]] = None

    def close(self) -> None:
        sys.stdout.flush()
        self.stderr = self.stdout = StringIO(self.stdout_splice.close())

        sys.stderr.flush()
        os.dup2(self.stderr_dupfd, sys.stderr.fileno())
        os.close(self.stderr_dupfd)


def silence(callback: Callable, args: Optional[list[str]] = None) -> str:
    """convenience function - traps stdout and stderr for callback.
    Returns (ret, trapped_output)
    """
    if not args:
        args = []
    trap = UnitedStdTrap()
    try:
        ret = callback(*args)
    finally:
        trap.close()

    return ret


def getoutput(callback: Callable, args: Optional[list[str]] = None) -> str:
    if not args:
        args = []
    trap = UnitedStdTrap()
    try:
        callback(*args)
    finally:
        trap.close()

    if trap.std:
        return trap.std.read()
    return ''


def tests() -> None:
    def test(transparent: bool = False) -> None:
        def sysprint():
            os.system("echo echo stdout")
            os.system("echo echo stderr 1>&2")

        def _read(stdout) -> str:
            if stdout:
                return stdout.read()
            return ''

        print("--- 1:")

        s1 = UnitedStdTrap(transparent=transparent)
        print("printing to united stdout...")
        print("printing to united stderr...", file=sys.stderr)
        sysprint()
        s1.close()
        print('trapped united stdout and stderr: """%s"""' % _read(s1.stdout))
        print("printing to stderr", file=sys.stderr)

        print("--- 2: None")

        print("--- 3: None")

    def test3() -> None:
        trap = UnitedStdTrap(transparent=True)
        try:
            for i in range(10):
                print("A" * 70)
                sys.stdout.flush()
                print("B" * 70, file=sys.stderr)
                sys.stderr.flush()
        finally:
            trap.close()
        assert trap.stdout is not None
        print(len(trap.stdout.read()))

    def test_united_tee():
        with open('/tmp/log', 'w') as fob:

            trap = UnitedStdTrap(transparent=True, tee=fob)
            try:
                os.system("echo hello world")
                for i in range(10):
                    print(i)
            finally:
                trap.close()
            assert trap.std != None
            trapped_output = trap.std.read()

        with open('/tmp/log', 'r') as fob:
            assert fob.read() == trapped_output

    test(False)
    print()
    print("=== TRANSPARENT MODE ===")
    print()
    test(True)
    test3()
    test_united_tee()
