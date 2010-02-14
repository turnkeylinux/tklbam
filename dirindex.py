import os
from os.path import *

class Error(Exception):
    pass

class DirIndex(dict):
    def __init__(self, fromfile=None):
        pass

    def walk(self, *paths):
        pass

    def save(self, tofile):
        pass

def create(path_index, paths):
    fh = file(path_index, "w" )
    for path in paths:
        for dpath, dnames, fnames in os.walk(path):
            for fname in fnames:
                path = abspath(join(dpath, fname))
                st = os.lstat(path)
                print >> fh, "%s\t%d\t%d" % (path, st.st_mtime, st.st_size)

def _create(path_index, paths):
    di = DirIndex()
    di.walk(*paths)
    di.save(path_index)

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

def _compare(path_index, paths):
    di_saved = DirIndex(path_index)
    di_fs = DirIndex()
    di_fs.walk(*paths)

    delta = list(set(di_fs) - set(di_saved))
    samepaths = set(di_fs) & set(di_index)
    for path in samepaths:
        if di_index[path] != di_fs[path]:
            delta.append(path)
    
    return delta
