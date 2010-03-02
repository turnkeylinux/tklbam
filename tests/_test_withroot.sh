#!/bin/bash -ex

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

rm -rf ./testdir && rsync -a $REF/testdir ./
cmd dirindex --create index testdir
sed -i "s|^$(/bin/pwd)/||" ./index

diff -u $REF/index ./index
