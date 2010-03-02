#!/bin/bash

set ${BIN:=..}
set ${REF:=ref}

echoerr()
{
    echo "$*" >& 2
}

fatal()
{
    echoerr "$@"
    exit 1
}

cmd() {
    name=$1
    shift;
    $BIN/cmd_$name.py $@
}

diff() {
    if ! $(which diff) $@; then
        fatal "ERROR: unexpected diff output"
    fi
}

mkrelative() {
    sed -i "s|$(/bin/pwd)/||" $1
}

set -ex
rm -rf ./testdir && rsync -a $REF/testdir ./

# test index creation
cmd dirindex --create index testdir
mkrelative ./index
diff -u $REF/index ./index

# test index creation with limitation
cmd dirindex --create index -- ./testdir/ -testdir/subdir/ testdir/subdir/subsubdir
mkrelative ./index
diff -u $REF/index-without-subdir ./index

# test dirindex comparison
cmd dirindex --create index testdir

cd testdir/

mv {file,file-renamed}
ln -sf file-renamed link
mv emptydir emptydir-renamed
echo changed >> subdir/file2
echo foo > subdir/subsubdir/file4
rm subdir/subsubdir/file3
mkdir new
touch new/empty

chown 666 chown
chmod 000 chmod

chown 666 subdir
chmod 750 subdir/subsubdir

cd ../

cmd dirindex ./index testdir/ > delta
mkrelative delta
diff -u $REF/delta1 ./delta

cmd dirindex ./index -- testdir/subdir/ -testdir/subdir/subsubdir > delta
mkrelative delta

diff -u $REF/delta2 ./delta

cmd dirindex ./index -- testdir/ -testdir/subdir testdir/subdir/subsubdir > delta
mkrelative delta

diff -u $REF/delta3 ./delta
