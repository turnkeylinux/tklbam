#!/bin/bash -e

packages() {
    rootfs=$1
    cat $rootfs/var/lib/dpkg/status|awk '/^Package: / {pkg=$2} /^Status:.*ok installed/ {print pkg}'|sort
}

dirindex() {
    rootfs=$1
    dirindex_conf=$2

    tmpconf=$(mktemp)
    sed "s|^\(-\)\?/|\1$rootfs/|" $dirindex_conf > $tmpconf

    tmpdi=$(mktemp)
    $BIN/cmd_dirindex.py --create $tmpdi -i $tmpconf
    rm -f $tmpconf

    sed "s|^$rootfs||" $tmpdi
    rm -f $tmpdi
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

if [ $# -lt 2 ] || [ "$1" = "-h" ]; then
    usage
fi

command=$1
iso=$2
shift 2

case "$command" in
    packages) ;;
    dirindex) 
        if ! [ -f "$1" ]; then
            echo "error: bad dirindex.conf ($1)"
            usage
        fi
        ;;
    *)
        usage
esac

if ! [ -f $iso ]; then
    echo "error: no such file $iso"
    exit 1
fi

mnt_iso=$(mktemp -d)
mnt_rootfs=$(mktemp -d)

mount -o loop $iso $mnt_iso
mount -o loop $mnt_iso/casper/10root.squashfs $mnt_rootfs

trap "(umount $mnt_rootfs; umount $mnt_iso; rmdir $mnt_iso $mnt_rootfs) >& /dev/null;" INT TERM EXIT

$command $mnt_rootfs $@
