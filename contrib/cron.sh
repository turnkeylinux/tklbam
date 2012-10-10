#!/bin/sh

set ${JITTER:=3600}

randomsleep() {
    MAXSLEEP=$1

    if [ -n "$MAXSLEEP" ] ; then
        if [ $MAXSLEEP -gt 0 ] ; then
            if [ -z "$RANDOM" ] ; then
                # A fix for shells that do not have this bash feature.
                RANDOM=$(dd if=/dev/urandom count=1 2> /dev/null | cksum | cut -c"1-5")
            fi
            TIME=$(($RANDOM % $MAXSLEEP))
            sleep $TIME
        fi
    fi
}

# prevent everyone from hitting the Hub API at exactly the same time...
randomsleep $JITTER
tklbam-backup --quiet
