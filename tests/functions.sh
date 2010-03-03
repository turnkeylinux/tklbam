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

test_count=1
testresult-exact() {
    file=$1
    testdesc=$2

    result="$REF/results/${test_count}:$(basename $file):$(echo $testdesc | sed 's/[^0-9a-zA-Z \.]//g; s/ \+/_/g')"

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

testresult() {
    file=$1
    testdesc=$2

    # make relative
    tmp=$(tempfile)
    sed "s|$(/bin/pwd)/||" $file | sort > $tmp
    cat $tmp > $file
    rm $tmp

    testresult-exact $1 "$2"
}

