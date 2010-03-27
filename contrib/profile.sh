#!/bin/bash -e

packages() {
    echo packages: $@
}

dirindex() {
    echo dirindex: $@
}

usage() {
    1>&2 cat<<EOF
Syntax: $0 command [args]
Commands:
    
    packages image.iso                  Prints list of packages in ISO
    dirindex image.iso dirindex.conf    Prints dirindex

Environment variables:

    BIN          Path to tklbam source (default: $BIN)
    DEBUG        Turn on debugging. Increases verbosity.
    
EOF
    exit 1
}

[ -z "$BIN" ] && BIN=".."
[ -n "$DEBUG" ] && set -x

if [ "$#" = "0" ] || [ "$1" = "-h" ]; then
    usage
fi

command=$1
shift 

case "$command" in
    packages)
        packages $@
        ;;
    dirindex)
        dirindex $@
        ;;
    *)
        usage
esac


