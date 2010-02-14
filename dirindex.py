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

def compare(path_index, paths):
    map_index = {}
    for line in file(path_index).readlines():
        path, mtime, size = line.split('\t')
        map_index[path] = (int(mtime), int(size))

    map_fs = {}
    for path in paths:
        for dpath, dnames, fnames in os.walk(path):
            for fname in fnames:
                path = abspath(join(dpath, fname))
                st = os.lstat(path)
                map_fs[path] = (st.st_mtime, st.st_size)

    # new paths
    delta = list(set(map_fs) - set(map_index))

    samepaths = set(map_fs) & set(map_index)
    for path in samepaths:
        if map_index[path] != map_fs[path]:
            delta.append(path)
    
    return delta
