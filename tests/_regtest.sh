#!/bin/bash -e

[ -z "$BIN" ] && BIN=".."
[ -z "$REF" ] && REF="ref"

usage() {
    1>&2 cat<<EOF
Syntax: $0 [ --options ]
Regression test.
Options:
    --create    Internal command which re-creates reference files in REF.

Environment variables:

    BIN         Path to tklbam source (default: $BIN)
    REF         Path to test reference (default: $REF)
    DEBUG       Turn on debugging. Increases verbosity.
    
EOF
    exit 1
}

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
    if [ -z "$create" ]; then
        $(which diff) -u $@ || fatal "ERROR: unexpected diff output"
    else
        cp $2 $1;
    fi
}

mkrelative() {
    sed -i "s|$(/bin/pwd)/||" $1
}

clean() {
    rm -rf testdir
    rm -f index delta fixstat
}

test_count=1
passed() {
    if [ -z "$create" ]; then
        echo "OK: $test_count - $@"
        test_count=$((test_count + 1))
    fi
}

if [ "$1" = "-h" ]; then
    usage
fi

for arg; do
    case "$arg" in
        --create)
            create=yes
            ;;

        *)
            usage
    esac
done

[ -n "$DEBUG" ] && set -x
rm -rf ./testdir && rsync -a $REF/testdir ./

# test index creation
cmd dirindex --create index testdir
mkrelative ./index
diff $REF/index ./index
passed "index creation"

# test index creation with limitation
cmd dirindex --create index -- ./testdir/ -testdir/subdir/ testdir/subdir/subsubdir
mkrelative ./index
diff $REF/index-without-subdir ./index
passed "index creation with limitation"

# test dirindex comparison
cmd dirindex --create index testdir

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

cmd dirindex ./index testdir/ > delta
mkrelative delta
diff $REF/delta1 ./delta
passed "index comparison"

cmd dirindex ./index testdir/ > delta

cd testdir/
chmod 700 subdir/
chown 0 chown
chmod 644 chmod
chown 1:1 subdir/subsubdir
rm subdir/subsubdir/file4

cd ../

cmd fixstat -s ./delta > ./fixstat
mkrelative fixstat
diff $REF/fixstat1 ./fixstat
passed "fixstat simulation"

cmd fixstat -s ./delta testdir/subdir > ./fixstat
mkrelative fixstat
diff $REF/fixstat2 ./fixstat
passed "fixstat simulation with limitation"

cmd fixstat -s ./delta -- testdir -testdir/subdir > fixstat
mkrelative fixstat
diff $REF/fixstat3 ./fixstat
passed "fixstat simulation with exclusion"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta > ./fixstat
mkrelative fixstat
diff $REF/fixstat4 ./fixstat
passed "fixstat with uid and gid mapping"

cmd fixstat -u 666,777:111,222 -g 666,777:111,222 -v ./delta > ./fixstat
mkrelative fixstat
diff $REF/fixstat5 ./fixstat
passed "fixstat repeated - nothing to do"

cmd dirindex ./index -- testdir/subdir/ -testdir/subdir/subsubdir > delta
mkrelative delta

diff $REF/delta2 ./delta
passed "index comparison with limitation"

cmd dirindex ./index -- testdir/ -testdir/subdir testdir/subdir/subsubdir > delta
mkrelative delta

diff $REF/delta3 ./delta
passed "index comparison with inverted limitation"

clean
