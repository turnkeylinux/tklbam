import os
from os.path import *

def create(path_index, paths):
    fh = file(path_index, "w" )
    for path in paths:
        for dpath, dnames, fnames in os.walk(path):
            for fname in fnames:
                path = abspath(join(dpath, fname))
                st = os.lstat(path)
                print >> fh, "%s\t%d\t%d" % (path, st.st_mtime, st.st_size)
