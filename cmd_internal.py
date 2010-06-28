#!/usr/bin/python
"""
Execute an internal command
"""
import os
from cliwrapper import CliWrapper

import cmd_internals

class CliWrapper(CliWrapper):
    DESCRIPTION = __doc__
    PATH = cmd_internals.__path__

if __name__ == "__main__":
    CliWrapper.main()


