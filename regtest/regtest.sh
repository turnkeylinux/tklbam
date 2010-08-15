#!/bin/sh

# faketime messes with Python's object caching mechanism
cd ../
    make clean
cd -
faketime -f "1970-1-1 00:00:00" fakeroot $(dirname $0)/_regtest.sh $@
