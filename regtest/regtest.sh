#!/bin/sh

fatal() { echo "FATAL: $@"; exit 1; }

DEPS="faketime fakeroot"
for dep in $DEPS; do
    [ "$(which $dep)" ] || fatal "missing dependency: $dep"
done

# faketime messes with Python's object caching mechanism
cd ../
    make clean > /dev/null
cd - > /dev/null
faketime -f '2020-1-1 00:00:00' fakeroot $(dirname $0)/_regtest.sh $@
