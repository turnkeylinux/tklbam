import os

class IdMap(dict):
    """
    Implements mapping of ids with transparent fallback.
    If no mapping exists, the original id is returned.
    """
    @classmethod
    def fromline(cls, line):
        d = ([ map(int, val.split(',', 1)) for val in line.split(':') ])
        return cls(d)

    def __getitem__(self, key):
        if key in self:
            return dict.__getitem__(self, key)
        return key

def fixstat(changes, uidmap, gidmap):
    for change in changes:
        if not os.path.exists(change.path):
            continue

        if change.OP == 'd':
            continue
        
        # optimization: if not remapped we can skip 'o' changes
        if change.OP == 'o' and \
           change.uid not in uidmap and change.gid not in gidmap:
            continue

        st = os.lstat(change.path)
        if change.OP in ('s', 'o'):
            if st.st_uid != uidmap[change.uid] or \
               st.st_gid != gidmap[change.gid]:
                yield os.chown, (change.path, 
                                 uidmap[change.uid], gidmap[change.gid])

        if change.OP == 's':
            if st.st_mode != change.mode:
                yield os.chmod, (change.path, change.mode)

