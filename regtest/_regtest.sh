#!/bin/bash

cd $(dirname $0)

usage() {
    1>&2 cat<<EOF
Syntax: $0 [ --options ]
Regression test.
Options:
    --createrefs  Internal command which re-creates reference files in REF.

Environment variables:

    BIN          Path to tklbam source (default: $BIN)
    REF          Path to test reference (default: $REF)
    DEBUG        Turn on debugging. Increases verbosity.
    
EOF
    exit 1
}

[ -z "$BIN" ] && BIN=".."
[ -z "$REF" ] && REF="ref"

. functions.sh

if [ "$1" = "-h" ]; then
    usage
fi

for arg; do
    case "$arg" in
        --createrefs)
            createrefs=yes
            rm -f $REF/results/*
            ;;

        *)
            usage
    esac
done

[ -n "$DEBUG" ] && set -x
rm -rf ./testdir && tar xf $REF/testdir.tar

# test index creation
cmd dirindex --create index testdir
cp ./index ./index.orig
testresult ./index "dirindex creation"

# test index creation with limitation
cmd dirindex --create index -- ./testdir/ -testdir/subdir/ testdir/subdir/subsubdir
testresult ./index "dirindex creation with limitation"

# test dirindex comparison
cd ./testdir/
    mv {file,file-renamed}
    ln -sf file-renamed link
    mv emptydir emptydir-renamed
    echo changed >> subdir/file2
    chgrp 666 subdir/file2
    echo foo > subdir/subsubdir/file4
    chown 666 subdir/subsubdir/file4
    rm subdir/subsubdir/file3
    mkdir new
    touch new/empty

    chown 666 chown
    chgrp 666 chgrp
    chmod 000 chmod

    chown 666:666 subdir

    chmod 750 subdir/subsubdir
cd ../

cmd dirindex ./index.orig testdir/ > delta
cp delta delta.orig
testresult ./delta "dirindex comparison"

cd ./testdir/
    chmod 700 subdir/
    chown 0 chown
    chmod 644 chmod
    chown 1:1 subdir/subsubdir
    rm subdir/subsubdir/file4
cd ../

cmd fixstat -s ./delta.orig > ./fixstat
testresult ./fixstat "fixstat simulation"

cmd fixstat -s ./delta.orig testdir/subdir > ./fixstat
testresult ./fixstat "fixstat simulation with limitation"

cmd fixstat -s ./delta.orig -- testdir -testdir/subdir > fixstat
testresult ./fixstat "fixstat simulation with exclusion"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta.orig > ./fixstat
testresult ./fixstat "fixstat with uid and gid mapping"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta.orig > ./fixstat
testresult ./fixstat "fixstat repeated - nothing to do"

cmd dirindex ./index.orig -- testdir/subdir/ -testdir/subdir/subsubdir > delta
testresult ./delta "dirindex comparison with limitation"

cmd dirindex ./index.orig -- testdir/ -testdir/subdir testdir/subdir/subsubdir > delta
testresult ./delta "dirindex comparison with inverted limitation"

cd ./testdir
    touch file
    touch subdir/subsubdir/file3
cd ../

cmd delete -s ./delta.orig > delete
testresult ./delete "delete simulation"

cmd delete -s ./delta.orig testdir/subdir > delete
testresult ./delete "delete simulation with limitation"

cmd delete -v ./delta.orig > delete
testresult ./delete "delete"

cmd delete -v ./delta.orig > delete
testresult ./delete "delete repeated - nothing to do"

rm -rf testdir
rm -f index index.orig delta delta.orig fixstat delete

cmd merge-userdb $REF/old-passwd $REF/old-group $REF/new-passwd $REF/new-group merged-passwd merged-group > merge-maps

testresult-exact merged-passwd "merge-userdb passwd"
testresult-exact merged-group "merge-userdb group"
testresult-exact merge-maps "merge-userdb output maps"

rm -f merged-passwd merged-group merge-maps

cmd newpkgs $REF/base-packages $REF/old-packages | sort > delta-packages
testresult-exact ./delta-packages "newpkgs"
rm -f delta-packages

cmd newpkgs-install -s -i $REF/newpkgs_install > newpkgs-install
testresult-exact ./newpkgs-install "newpkgs-install simulation"
rm -f newpkgs-install

cmd mysql2fs --fromfile $REF/testsql -D myfs -v > mysql2fs-output
testresult-exact mysql2fs-output "mysql2fs verbose output"
rm -f mysql2fs-output

tar cf myfs.tar myfs
md5sum myfs.tar > myfs-md5
testresult-exact myfs-md5 "mysql2fs myfs.tar md5sum"

cmd fs2mysql -v --tofile=sql ./myfs > fs2mysql-output
testresult-exact fs2mysql-output "fs2mysql verbose output"
testresult-exact sql "fs2mysql tofile=sql"

rm -rf myfs myfs.tar myfs-md5 fs2mysql-output sql
