# Copyright (c) 2007-2011 Liraz Siri <liraz@turnkeylinux.org>
#               2019-2023 TurnKey GNU/Linux <admin@turnkeylinux.org>
#
# turnkey-command is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

"A high-level interface for command execution"

import os
import signal
from signal import Signals
import time
import select
import re
import sys
import errno
import termios

from typing import Optional, Callable, Self
from shlex import quote
from io import StringIO, TextIOWrapper

import popen4
from fifobuffer import FIFOBuffer
from fileevent import FileEventAdaptor, Observer


def fmt_argv(argv: list[str]) -> str:
    if not argv:
        return ""

    args = argv[1:]

    for i, arg in enumerate(args):
        if re.search(r"[\s'\"]", arg):
            args[i] = quote(arg)
        else:
            args[i] = " " + arg

    return argv[0] + " " + " ".join(args)


def get_blocking(fd: int|TextIOWrapper) -> bool:
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if flags & os.O_NONBLOCK:
        return False
    else:
        return True


def set_blocking(fd: int|TextIOWrapper, blocking: bool) -> None:
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    if flags == -1:
        flags = 0

    if not blocking:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


class FileEnhancedRead:
    def __init__(self, fh: TextIOWrapper):
        self.fh = fh

    def __getattr__(self, attr: str) -> str:
        return getattr(self.fh, attr)

    def read(self, size: int = -1, timeout: Optional[float] = None) -> Optional[str]:
        """A better read where you can (optionally) configure how long to wait
        for data.

        Arguments:

        'timeout': how many seconds to wait before for output.

                If no output return None.
                If EOF return ''

        """
        if timeout is None:
            return self.fh.read(size)

        if timeout < 0:
            timeout = 0

        fd = self.fh.fileno()

        p = select.poll()
        p.register(fd, select.POLLIN | select.POLLHUP)

        started = time.time()
        try:
            events = p.poll(timeout * 1000)
        except select.error:
            return self.read(size, timeout - (time.time() - started))

        if not events:
            return None

        mask = events[0][1]
        if mask & select.POLLIN:

            bytes_ = None

            orig_blocking = get_blocking(fd)
            set_blocking(fd, False)
            try:
                bytes_ = self.fh.read(size)
            except IOError as e:
                if e.errno != errno.EAGAIN:
                    raise
            finally:
                set_blocking(fd, orig_blocking)

            return bytes_

        if mask & select.POLLHUP:
            return ''

        return None


class Command:
    """Convenience module for executing a command

    attribute notes::

        'exitcode' - None if the process hasn't exited, exitcode otherwise

        'output' - None if the process hasn't exited and fromchild hasn't
                   been accessed, the full output of the process

        'running' - True if process is still running, False otherwise

        'terminated' - Returns signal number if terminated, None otherwise

    Usage example::

        c = Command("./test.py")
        if c.running:
            c.wait()

        assert c.running is False

        print(c.output)

        c = Command("./test.py")

        # Unless you read from command.fromchild or use
        # command.outputsearch() command.output will be None until the
        # command finishes.

        while c.output is None:
            time.sleep(1)

        print("output = '%s', exitcode = %d" % (c.output, c.exitcode))

        c = Command("cat", pty=True)
        print >> c.tochild, "test"
        print(c.fromchild.readline(),)

    """
    class Error(Exception):
        pass

    class _ChildObserver(Observer):
        def __init__(self, outputbuf: FIFOBuffer, debug: bool = False):
            self.debug = debug
            self.outputbuf = outputbuf

        def _dprint(self, event: str, msg: str) -> None:
            if self.debug:
                print("# EVENT '%s':\n%s" % (event, msg), file=sys.stderr)

        def notify(self, subject: Self, event: str, value: str) -> None:
            if event in ('read', 'readline'):
                self._dprint(event, value)
                self.outputbuf.write(value)
            elif event in ('readlines', 'xreadlines'):
                self._dprint(event, "".join(value))
                self.outputbuf.write("".join(value))

    def __init__(self, cmd: list[str], runas: Optional[str] = None,
                 pty: bool = False, setpgrp: bool = False, debug: bool = False
                 ):
        """Args:
        'cmd' what command to execute
            Can be a list ("/bin/ls", "-la")
            or a string "/bin/ls" (will be passed to sh -c)

        'pty' do we allocate a pty for command?
        'runas' user we run as (set user, set groups, etc.)
        'setpgrp' do we setpgrp in child? (create its own process group)
        """

        self.ppid = os.getpid()

        self._child = None
        self._child = popen4.Popen4(cmd, 0, pty, runas, setpgrp)
        self.tochild = self._child.tochild
        self._fromchild = None

        self.pid = self._child.pid

        self._setpgrp = setpgrp
        self._debug = debug
        self._cmd = cmd

        self._output = FIFOBuffer()
        self._dprint(f"# command started (pid={self._child.pid},"
                     f" pty={repr(pty)}): {cmd}")

    def __del__(self) -> None:
        if not self._child:
            return

        # don't terminate() a process we didn't start
        if os.getpid() == self.ppid:
            self.terminate()

    def _dprint(self, msg: str) -> None:
        if self._debug:
            print(msg, file=sys.stderr)

    def terminate(self, gracetime: int = 0, sig: Signals = signal.SIGTERM) -> None:
        """terminate command. kills command with 'sig', then sleeps for
        'gracetime', before sending SIGKILL
        """

        if self.running:
            assert self._child is not None
            if self._child.pty:
                # XXX shouldn't be a string? Should be popen4.CatchIOErrorWrapper!?
                cc_magic = termios.tcgetattr(self._child.tochild.fileno())[-1]  #type: ignore[operator]
                ctrl_c = cc_magic[termios.VINTR]
                # and again ...
                self._child.tochild.write(ctrl_c)  #type: ignore[operator]

            pid = self.pid
            if self._setpgrp and pid is not None:
                pid = -pid

            try:
                assert pid is not None
                os.kill(pid, sig)
            except OSError as e:
                if e.errno != errno.EPERM or \
                   not self._child.pty or \
                   not self.wait(timeout=6, poll_interval=0.1):
                    raise

                return

            for i in range(gracetime):
                if not self.running:
                    return
                time.sleep(1)

            if self.running and pid != None:
                os.kill(pid, signal.SIGKILL)

                if not self.wait(timeout=3, poll_interval=0.1):
                    raise self.Error("process just won't die!")

                self._dprint(f"# command (pid {self._child.pid}) terminated")

    def terminated_(self) -> Optional[str]:
        assert self._child is not None
        status = self._child.poll()

        if not os.WIFSIGNALED(status):
            return None

        return str(os.WTERMSIG(status))
    terminated = property(terminated_)

    def running_(self) -> bool:
        assert self._child is not None
        if self._child.poll() == -1:
            return True

        return False

    running = property(running_)

    def exitcode_(self) -> Optional[int]:
        if self.running:
            return None

        assert self._child is not None
        status = self._child.poll()

        if not os.WIFEXITED(status):
            return None

        return os.WEXITSTATUS(status)

    exitcode = property(exitcode_)

    def wait(self, timeout: Optional[int] = None, poll_interval: float = 0.2, callback: Optional[Callable] = None) -> bool:
        """wait for process to finish executing.
        'timeout': how long we wait in seconds (None is forever)
        'poll_interval': how long we sleep between checks to see if process has
                         finished
        'callback': you can use callback to check for other conditions (e.g.,
                    besides timeout) and stop wait early.

        return value: did the process finish? True/False

        """
        if not self.running:
            return True

        if timeout is None:
            assert self._child is not None
            self._child.wait()
            return True
        else:
            start = time.time()
            while time.time() - start < timeout:
                if callback and callback() is False:
                    return False

                if not self.running:
                    return True
                time.sleep(poll_interval)

            return False

    def output_(self) -> str|None:
        if len(self._output):
            return self._output.getvalue()

        if self.running:
            return None

        # this will read into self._output via _ChildObserver
        self.fromchild.read()

        return self._output.getvalue()

    output = property(output_)

    def fromchild_(self) -> Optional[FileEventAdaptor|FileEnhancedRead]:
        """return the command's filehandler.

        NOTE: this file handler magically updates self._output"""

        if self._fromchild:
            return self._fromchild
        assert self._child is not None
        fh = FileEventAdaptor(self._child.fromchild.fh)
        fh.addObserver(self._ChildObserver(self._output,
                                           self._debug))
        assert isinstance(fh, TextIOWrapper)
        self._fromchild = FileEnhancedRead(fh)
        return self._fromchild

    fromchild = property(fromchild_)

    def outputsearch(self,
                     p: re.Pattern|str|list[re.Pattern|str],
                     timeout: Optional[int] = None,
                     linemode: bool = False
                     ) -> Optional[tuple[re.Pattern|str, re.Match]]:
        """Search for 'p' in the command's output, while listening for more
        output from command, within 'timeout'

        'p' can be a list of re patterns or a single re pattern
           the value of a pattern can be an re string, or a compiled re object
        If 'timeout' is None, wait forever [*]

        'linemode' determines whether we search output line by line (as it
        comes), or all of the output in aggregate

        Return value:
        Did we match the output?
            Return a tuple (the pattern we matched, the string match)
        Otherwise (timeout/HUP) Return empty tuple ()

        Side effects:
        - If we HUP, we wait for the process to finish.
          You can check if the process is still running.

        - Output is collected and can be accessed by the output attribute [*]
        """

        patterns: list[str|re.Pattern] = []
        if isinstance(p, (tuple, list)):
            patterns.extend(p)
        elif isinstance(p, (re.Pattern, str)):
            patterns.append(p)
        else:
            raise self.Error(f"P is wrong type")

        # compile all patterns into re objects, but keep the original pattern
        # object so we can return it to user when matched (friendy interface)
        ret_patterns: list[tuple[str|re.Pattern, re.Pattern]] = []
        for i in range(len(patterns)):
            pattern_orig = patterns[i]
            pattern_re = re.compile(patterns[i])
            ret_patterns.append((pattern_orig, pattern_re))

        def check_match() -> Optional[tuple[re.Pattern|str, re.Match]]:
            if linemode:
                while 1:
                    line = self._output.readline(True)
                    if not line:
                        return None

                    for pattern_orig, pattern_re in ret_patterns:
                        match = pattern_re.search(line)
                        if match:
                            return pattern_orig, match

                    if not line.endswith('\n'):
                        return None

            else:
                # match against the entire buffered output
                for pattern_orig, pattern_re in ret_patterns:
                    match = pattern_re.search(self._output.getvalue())
                    if match:
                        return pattern_orig, match
                return None

        # maybe we already match? (in buffered output)
        m = check_match()
        if m:
            return m

        ref: list[tuple[re.Pattern|str, re.Match]] = []
        started = time.time()

        def callback(self, buf: str) -> bool:
            if buf:
                m = check_match()
                if m:
                    ref[0] = m
                    return False

            if buf == '':
                return False

            if timeout is not None:
                elapsed_time = time.time() - started
                if elapsed_time >= timeout:
                    return False

            return True

        fh = self.read(callback)
        return ref[0]

    def read(self, callback: Optional[Callable] = None, callback_interval: float = 0.1) -> str:
        """Read output from child.

        Args:
        'callback': callback(command, readbuf) every read loop or
                    callback_interval (whichever comes sooner).

                    readbuf may be:

                    1) a string
                    2) None (no input during callback_interval)
                    2) an empty string (EOF)

                    If callbacks returns False, stop reading

        Return read bytes.

        """

        if not callback:
            return self.fromchild.read()

        sio = StringIO()
        while True:

            output = self.fromchild.read(timeout=callback_interval)
            if output:
                sio.write(output)

            finished = callback(self, output) is False
            if finished:
                return sio.getvalue()

            if not self.running:
                break

            if output == '':
                self.wait()
                break

        if output != '':  # no leftovers if EOF
            leftovers = self.fromchild.read()
            sio.write(leftovers)
            callback(self, leftovers)

        return sio.getvalue()

    def __repr__(self) -> str:
        return "Command(%s)" % repr(self._cmd)

    def __str__(self) -> str:
        if isinstance(self._cmd, str):
            return self._cmd

        return fmt_argv(self._cmd)


class CommandTrue:
    """
    Simplified interface to Command class.

    A command istrue() if its exitcode == 0
    """
    def __init__(self, cmd: list[str]):
        self._c = Command(cmd)

    def wait(self, timeout: Optional[int] = None) -> int:
        if timeout:
            return self._c.wait(timeout)
        else:
            return 0

    def terminate(self) -> None:
        self._c.terminate()

    def istrue(self) -> Optional[bool]:
        exitcode = self._c.exitcode
        if exitcode is None:
            return None

        if exitcode != 0:
            return False
        else:
            return True


last_exitcode = None
last_output = None


def eval(cmd, setpgrp: bool = False) -> bool:
    """convenience function
    execute 'cmd' and return True/False is exitcode == 0

    Side effect: sets command.last_exitcode and command.last_output
    """
    global last_output
    global last_exitcode

    c = Command(cmd, setpgrp=setpgrp)
    c.wait()
    last_output = c.output
    last_exitcode = c.exitcode
    return last_exitcode == 0


def output(cmd: list[str]) -> Callable[[], str]:
    """convenience function
    execute 'cmd' and return it's output

    Side effect: sets command.last_exitcode and command.last_output

    """
    global last_output
    global last_exitcode

    c = Command(cmd)
    c.wait()
    last_output = c.output
    last_exitcode = c.exitcode

    return last_output
