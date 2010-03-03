#!/bin/bash -e

[ -z "$BIN" ] && BIN=".."
[ -z "$REF" ] && REF="ref"

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

error()
{
    echo "$*" >& 2
    false
}

cmd() {
    name=$1
    shift;
    $BIN/cmd_$name.py $@
}

clean() {
    rm -rf testdir
    rm -f index delta fixstat
}

test_count=1
testresult() {
    file=$1
    testdesc=$2

    result="$REF/results/${test_count}:$(basename $file):$(echo $testdesc | sed 's/ /_/g')"

    # make relative
    sed -i "s|$(/bin/pwd)/||" $file
    if [ -z "$createrefs" ]; then
        $(which diff) -u $result $file || error "FAIL: $test_count - $testdesc"
    else
        cp $file $result;
    fi
    if [ -z "$createrefs" ]; then
        echo "OK: $test_count - $testdesc"
    fi
    test_count=$((test_count+1))
}

if [ "$1" = "-h" ]; then
    usage
fi

for arg; do
    case "$arg" in
        --createrefs)
            createrefs=yes
            ;;

        *)
            usage
    esac
done

[ -n "$DEBUG" ] && set -x
rm -rf ./testdir && rsync -a $REF/testdir ./

# test index creation
cmd dirindex --create index testdir
testresult ./index "index creation"

# test index creation with limitation
cmd dirindex --create index -- ./testdir/ -testdir/subdir/ testdir/subdir/subsubdir
testresult ./index "index creation with limitation"

# test dirindex comparison
cd testdir/

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

cmd dirindex --create index testdir
cmd dirindex ./index testdir/ > delta
testresult ./delta "index comparison"

cd testdir/
chmod 700 subdir/
chown 0 chown
chmod 644 chmod
chown 1:1 subdir/subsubdir
rm subdir/subsubdir/file4

cd ../

cmd dirindex ./index testdir/ > delta
cmd fixstat -s ./delta > ./fixstat
testresult ./fixstat "fixstat simulation"

cmd fixstat -s ./delta testdir/subdir > ./fixstat
testresult ./fixstat "fixstat simulation with limitation"

cmd fixstat -s ./delta -- testdir -testdir/subdir > fixstat
testresult ./fixstat "fixstat simulation with exclusion"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta > ./fixstat
testresult ./fixstat "fixstat with uid and gid mapping"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta > ./fixstat
testresult ./fixstat "fixstat repeated - nothing to do"

cmd dirindex ./index -- testdir/subdir/ -testdir/subdir/subsubdir > delta
testresult ./delta "index comparison with limitation"

cmd dirindex ./index -- testdir/ -testdir/subdir testdir/subdir/subsubdir > delta
testresult ./delta "index comparison with inverted limitation"

clean
